#!/usr/bin/env python3
"""Fetch RSS/Atom feeds from reader/feeds.json into reader/items.json.

Keeps items from the last KEEP_DAYS days (Pacific). Safe to run locally or
from GitHub Actions. Network failures on a single feed are skipped.

YouTube Shorts are never kept. Any RSS or Atom item whose link, guid, or
url contains /shorts/ is dropped. YouTube feeds should be UULF playlists
(long-form uploads only), not channel feeds.

An Atom feed with zero entries is valid. A new email bridge often looks
like that until the first letter arrives, and that is a successful fetch.

Private feeds name an environment variable in "url_secret". The script
reads that variable when it fetches and skips the feed when it is unset.
The secret URL is never printed and never written to items.json. A private
item keeps its title, date, a short plain-text excerpt, and a public link.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FEEDS_PATH = ROOT / "reader" / "feeds.json"
ITEMS_PATH = ROOT / "reader" / "items.json"
OPML_PATH = ROOT / "reader" / "feeds.opml"
KEEP_DAYS = 14
MAX_PER_FEED = 40
USER_AGENT = "harrisonshin-reader/1.0 (+https://harrisonshin.com/reader/)"
PACIFIC = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
HTML_TAG = re.compile(r"<[^>]+>")
WHITESPACE = re.compile(r"\s+")
# watch?v=, embed/, youtu.be/, or bare 11-char id in yt:video:…
# Shorts URLs are rejected before an id is extracted.
YT_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:[^#]*&)?v=|embed/|v/)|youtu\.be/|yt:video:)([A-Za-z0-9_-]{11})"
)
SHORTS_MARK = "/shorts/"
YT_ID_ONLY = re.compile(r"^[A-Za-z0-9_-]{11}$")
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
STYLE_OR_SCRIPT = re.compile(
    r"<(script|style|head|noscript)\b[^>]*>.*?</\1>",
    re.I | re.S,
)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
CSS_RULE = re.compile(r"[^{}]{0,240}\{[^}]{0,500}\}")
URL_RE = re.compile(r"https?://[^\s<>\"']+")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
LONG_TOKEN = re.compile(r"\b[A-Za-z0-9]{24,}\b")
BOILERPLATE = (
    "unsubscribe",
    "email preferences",
    "view in browser",
    "view this email",
    "manage preferences",
    "manage your preferences",
    "opt out",
    "opt-out",
)
TIM_BULLET_POST = re.compile(
    r"https://tim\.blog/\d{4}/\d{2}/\d{2}/[A-Za-z0-9-]*bullet[A-Za-z0-9-]*/?",
    re.I,
)
FIVE_BULLET_ARCHIVE = "https://tim.blog/5-bullet-friday/"
FIVE_BULLET_ID = "five-bullet-friday"
CONTENT_MIN_TEXT = 80
CONTENT_FULL_TEXT = 700
CONTENT_CAP = 80000
READING_TAGS = {
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "pre", "code",
    "strong", "em", "b", "i", "a", "img",
    "figure", "figcaption", "sub", "sup",
    "table", "thead", "tbody", "tr", "th", "td",
    "div", "span",
}
DROP_TAGS = {
    "script", "style", "noscript", "iframe", "object", "embed",
    "svg", "math", "form", "button", "input", "textarea", "select",
    "template", "head", "link", "meta", "canvas",
}
CHROME_TAGS = {"nav", "footer", "header", "aside", "form"}
VOID_TAGS = {"br", "hr", "img"}
UNSUB_RE = re.compile(
    r"unsubscribe|manage[- ]subscription|email preferences|subscription preferences|"
    r"opt[- ]out|manage your preferences|update your preferences|view in browser|"
    r"view this email",
    re.I,
)
TRACK_RE = re.compile(
    r"pixel|beacon|spacer|1x1|doubleclick|google-analytics|facebook\.com/tr|"
    r"scorecardresearch|quantserve|list-manage\.com/track|open\.gif|"
    r"/track(?:ing)?/|utm_source=email.*open",
    re.I,
)


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def local_text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def strip_html(raw: str) -> str:
    text = HTML_TAG.sub(" ", raw or "")
    text = html.unescape(text)
    return WHITESPACE.sub(" ", text).strip()


def truncate(text: str, limit: int = 280) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",.;:")
    return (cut or text[: limit - 1]) + "…"


def parse_date(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    cleaned = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        return None


def item_id(feed_id: str, guid: str, link: str, title: str) -> str:
    seed = guid or link or f"{feed_id}:{title}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def contains_shorts(*values: str | None) -> bool:
    """True when any link, guid, or url points at a YouTube Short."""
    for value in values:
        if value and SHORTS_MARK in value:
            return True
    return False


def entry_short_values(entry: ET.Element) -> list[str]:
    """Link hrefs plus guid/id/url text. Descriptions are not scanned."""
    found: list[str] = []
    for el in entry.iter():
        if not isinstance(el.tag, str):
            continue
        local = el.tag.rsplit("}", 1)[-1].lower()
        if local not in ("link", "guid", "id", "url"):
            continue
        href = (el.get("href") or "").strip()
        if href:
            found.append(href)
        text = "".join(el.itertext()).strip()
        if text:
            found.append(text)
    return found


def is_short_entry(entry: ET.Element, link: str, guid: str) -> bool:
    return contains_shorts(link, guid, *entry_short_values(entry))


def log_skip_short(feed: dict, ref: str) -> None:
    if feed.get("url_secret"):
        print(f"skip short {feed['id']}", file=sys.stderr)
        return
    print(f"skip short {feed['id']}: {ref}", file=sys.stderr)


def unescape_repeated(text: str) -> str:
    for _ in range(4):
        nxt = html.unescape(text)
        if nxt == text:
            break
        text = nxt
    return text


def secret_markers(secret_url: str) -> list[str]:
    """Pieces of a private feed URL that must not land in items.json."""
    raw = (secret_url or "").strip()
    if not raw:
        return []
    found = [raw]
    parsed = urllib.parse.urlparse(raw)
    if parsed.path:
        found.append(parsed.path)
    for seg in parsed.path.split("/"):
        stem = seg.split(".")[0]
        if len(stem) >= 16:
            found.append(stem)
            found.append(seg)
            encoded = urllib.parse.quote(stem, safe="")
            if encoded != stem:
                found.append(encoded)
    uniq: list[str] = []
    for marker in sorted(set(found), key=len, reverse=True):
        if marker and marker not in uniq:
            uniq.append(marker)
    return uniq


def scrub_markers(text: str, markers: list[str]) -> str:
    for marker in markers:
        if marker and marker in text:
            text = text.replace(marker, " ")
    return text


def drop_boilerplate(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text)
    kept = []
    for part in parts:
        low = part.lower()
        if any(phrase in low for phrase in BOILERPLATE):
            continue
        kept.append(part)
    return " ".join(kept)


def plain_excerpt(raw: str, markers: list[str]) -> str:
    """Plain-text excerpt with markup, addresses, and secret tokens removed."""
    text = unescape_repeated(raw or "")
    text = HTML_COMMENT.sub(" ", text)
    text = STYLE_OR_SCRIPT.sub(" ", text)
    text = HTML_TAG.sub(" ", text)
    text = unescape_repeated(text)
    text = CSS_RULE.sub(" ", text)
    text = URL_RE.sub(" ", text)
    text = EMAIL_RE.sub(" ", text)
    text = LONG_TOKEN.sub(" ", text)
    text = scrub_markers(text, markers)
    text = text.replace("\u200b", "").replace("\ufeff", "").replace("\u00a0", " ")
    text = drop_boilerplate(WHITESPACE.sub(" ", text).strip())
    return truncate(text)


def bullet_post_urls(raw: str) -> list[str]:
    text = unescape_repeated(raw or "")
    found: list[str] = []
    for match in TIM_BULLET_POST.findall(text):
        url = match.split("?")[0].split("#")[0]
        if not url.endswith("/"):
            url += "/"
        if url not in found:
            found.append(url)
    return found


class _HtmlNode:
    def __init__(self, tag: str, attrs: list[tuple[str, str | None]]):
        self.tag = tag
        self.attrs = attrs
        self.children: list[_HtmlNode | str] = []


class _HtmlTree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _HtmlNode("root", [])
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _HtmlNode(tag.lower(), attrs)
        self.stack[-1].children.append(node)
        if tag.lower() not in VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack[-1].children.append(_HtmlNode(tag.lower(), attrs))

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1].children.append(data)


def _parse_html_tree(raw: str) -> _HtmlNode:
    builder = _HtmlTree()
    try:
        builder.feed(raw or "")
        builder.close()
    except Exception:
        return _HtmlNode("root", [])
    return builder.root


def _attr_map(node: _HtmlNode) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, value in node.attrs:
        if key and value is not None:
            found[key.lower()] = value
    return found


def _node_text(node: _HtmlNode | str) -> str:
    if isinstance(node, str):
        return node
    return "".join(_node_text(child) for child in node.children)


def _is_tracking_image(attrs: dict[str, str]) -> bool:
    src = attrs.get("src") or ""
    if not src or src.startswith("data:") or TRACK_RE.search(src):
        return True
    host = urllib.parse.urlparse(src).netloc.lower()
    path = urllib.parse.urlparse(src).path.lower()
    if host.startswith("open.") or host.startswith("click.") or "/open/" in path:
        return True
    if any(piece in host for piece in ("fourhourmail.com", "sparkloop.app", "list-manage.com", "convertkit.com")):
        return True
    dims = []
    for key in ("width", "height"):
        raw = attrs.get(key) or ""
        match = re.match(r"\d+", raw.strip())
        if match:
            dims.append(int(match.group(0)))
    return len(dims) == 2 and dims[0] <= 2 and dims[1] <= 2


def _b64_http_url(segment: str) -> str | None:
    if len(segment) < 16:
        return None
    padded = segment + "=" * ((4 - len(segment) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
    except Exception:
        return None
    match = re.match(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+", decoded)
    if not match:
        return None
    return match.group(0)


def _rewrite_href(href: str, markers: list[str]) -> str | None:
    """Return a public href, or None when the link should be dropped."""
    if any(marker and marker in href for marker in markers):
        return None
    host = urllib.parse.urlparse(href).netloc.lower()
    tracking = (
        host.startswith("click.")
        or host.startswith("open.")
        or any(piece in host for piece in ("fourhourmail.com", "sparkloop.app", "list-manage.com", "convertkit.com", "ck.page"))
    )
    if tracking:
        for segment in urllib.parse.urlparse(href).path.split("/"):
            dest = _b64_http_url(segment)
            if not dest or not dest.startswith("https://"):
                continue
            dest_host = urllib.parse.urlparse(dest).netloc.lower()
            if dest_host.startswith("click.") or "fourhourmail.com" in dest_host or "sparkloop.app" in dest_host:
                continue
            return dest
        return None
    if markers and re.search(r"[A-Za-z0-9]{28,}", urllib.parse.urlparse(href).path):
        return None
    return href


def _bad_link(href: str, text: str, markers: list[str]) -> bool:
    blob = f"{href} {text}"
    if UNSUB_RE.search(blob):
        return True
    for marker in markers:
        if marker and marker in href:
            return True
    return False


def _serialize_node(
    node: _HtmlNode | str,
    base_url: str,
    markers: list[str],
    drop_chrome: bool,
) -> str:
    if isinstance(node, str):
        text = scrub_markers(node, markers)
        text = text.replace("\u200b", "").replace("\ufeff", "")
        return html.escape(text, quote=False)
    tag = node.tag
    if tag in DROP_TAGS or (drop_chrome and tag in CHROME_TAGS):
        return ""
    inner = "".join(
        _serialize_node(child, base_url, markers, drop_chrome) for child in node.children
    )
    if tag == "root":
        return inner
    if tag not in READING_TAGS:
        return inner
    attrs = _attr_map(node)
    if tag == "a":
        href = (attrs.get("href") or "").strip()
        text = _node_text(node)
        if not href or href.lower().startswith(("javascript:", "mailto:", "data:")):
            return inner
        absolute = urllib.parse.urljoin(base_url, href) if base_url else href
        if _bad_link(absolute, text, markers) or _bad_link(href, text, markers):
            return "" if len(text.strip()) < 160 else inner
        rewritten = _rewrite_href(absolute, markers)
        if not rewritten:
            return "" if len(text.strip()) < 160 else inner
        if not rewritten.startswith(("http://", "https://")):
            return inner
        return (
            f'<a href="{html.escape(rewritten, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{inner}</a>'
        )
    if tag == "img":
        src = (attrs.get("src") or "").strip()
        if not src:
            return ""
        absolute = urllib.parse.urljoin(base_url, src) if base_url else src
        if not absolute.startswith("https://") or _is_tracking_image({"src": absolute, **attrs}):
            return ""
        for marker in markers:
            if marker and marker in absolute:
                return ""
        alt = html.escape(attrs.get("alt") or "", quote=True)
        return f'<img src="{html.escape(absolute, quote=True)}" alt="{alt}" loading="lazy">'
    if tag in VOID_TAGS:
        return f"<{tag}>"
    if not inner.strip():
        return ""
    return f"<{tag}>{inner}</{tag}>"


def sanitize_html(raw: str, base_url: str = "", markers: list[str] | None = None, drop_chrome: bool = False) -> str:
    """Allow a small set of readable tags. Drop scripts, pixels, and unsubscribe links."""
    markers = markers or []
    text = unescape_repeated(raw or "")
    text = HTML_COMMENT.sub(" ", text)
    tree = _parse_html_tree(text)
    cleaned = _serialize_node(tree, base_url, markers, drop_chrome)
    cleaned = scrub_markers(cleaned, markers).strip()
    if len(cleaned) > CONTENT_CAP:
        cleaned = cleaned[:CONTENT_CAP].rsplit("<", 1)[0].rstrip()
    return cleaned


def html_text_len(fragment: str) -> int:
    return len(WHITESPACE.sub(" ", HTML_TAG.sub(" ", fragment or "")).strip())


def _decode_response(raw: bytes, content_type: str) -> str:
    charset = "utf-8"
    match = re.search(r"charset=([^\s;]+)", content_type or "", re.I)
    if match:
        charset = match.group(1).strip("\"'")
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def fetch_html(url: str) -> tuple[str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        final = resp.geturl()
        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype.lower() and "xml" not in ctype.lower():
            return "", final
        payload = resp.read(1_500_000)
    return _decode_response(payload, ctype), final


def _best_article(node: _HtmlNode) -> _HtmlNode | None:
    best: _HtmlNode | None = None
    best_score = 0

    def walk(current: _HtmlNode) -> None:
        nonlocal best, best_score
        if current.tag in ("article", "main") or current.tag in ("div", "section", "td"):
            text = html_text_len(_node_text(current))
            links = html_text_len(
                " ".join(_node_text(child) for child in current.children if isinstance(child, _HtmlNode) and child.tag == "a")
            )
            score = text - links
            if current.tag in ("article", "main"):
                score += 400
            if score > best_score and text >= CONTENT_FULL_TEXT:
                best = current
                best_score = score
        for child in current.children:
            if isinstance(child, _HtmlNode):
                walk(child)

    walk(node)
    return best


def extract_readable(url: str) -> str:
    """Fetch a public article and keep its main text. Failures become an empty string."""
    try:
        page, final = fetch_html(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return ""
    if not page:
        return ""
    tree = _parse_html_tree(HTML_COMMENT.sub(" ", page))
    target = _best_article(tree) or tree
    cleaned = _serialize_node(target, final or url, [], True).strip()
    plain = WHITESPACE.sub(" ", HTML_TAG.sub(" ", cleaned)).strip().lower()
    if html_text_len(cleaned) < CONTENT_FULL_TEXT:
        return ""
    if any(phrase in plain[:500] for phrase in ("sign in to continue", "subscribe to read", "enable javascript")):
        return ""
    return cleaned[:CONTENT_CAP]


def reading_html(item: dict) -> str:
    raw = item.get("_html") or ""
    markers = item.get("_markers") or []
    private = bool(item.get("_private"))
    base = item.get("url") or ""
    cleaned = sanitize_html(raw, base, markers, drop_chrome=False)
    if item.get("videoId") or item.get("kind") == "youtube":
        return ""
    if any(marker and marker in (base or "") for marker in markers):
        private = True
    if private or html_text_len(cleaned) >= CONTENT_FULL_TEXT:
        return cleaned
    if not base.startswith("http"):
        return cleaned
    host = urllib.parse.urlparse(base).netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return cleaned
    print(f"extract {item.get('feedId')}", file=sys.stderr)
    extracted = extract_readable(base)
    if html_text_len(extracted) > html_text_len(cleaned):
        return extracted
    return cleaned


def apply_reading(items: list[dict]) -> None:
    """Attach sanitized full text. Private items never keep bridge links."""

    def work(item: dict) -> tuple[dict, str]:
        try:
            return item, reading_html(item)
        except Exception:
            return item, ""

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(work, items))
    for item, fragment in results:
        markers = item.pop("_markers", []) or []
        item.pop("_html", None)
        item.pop("_private", None)
        fragment = scrub_markers(fragment or "", markers).strip()
        if any(marker and marker in fragment for marker in markers):
            fragment = ""
        if html_text_len(fragment) >= CONTENT_MIN_TEXT:
            item["contentHtml"] = fragment
        else:
            item.pop("contentHtml", None)


def privatize_item(item: dict, feed: dict, desc: str) -> dict:
    """Drop bridge links and raw email HTML from a secret-backed feed."""
    if desc:
        item["_html"] = desc
    if not feed.get("url_secret"):
        return item
    markers = secret_markers(feed.get("_fetch_url") or "")
    item["_private"] = True
    item["_markers"] = markers
    item["summary"] = plain_excerpt(desc, markers) if desc else ""
    author = item.get("author") or ""
    if "@" in author or any(marker and marker in author for marker in markers):
        item.pop("author", None)
    if feed.get("id") == FIVE_BULLET_ID:
        item["_public_candidates"] = bullet_post_urls(desc)
        item["url"] = FIVE_BULLET_ARCHIVE
    else:
        item["url"] = (feed.get("url") or "").strip()
    for key, value in list(item.items()):
        if key.startswith("_") or not isinstance(value, str):
            continue
        item[key] = scrub_markers(value, markers).strip()
    if feed.get("id") == FIVE_BULLET_ID and not item.get("url"):
        item["url"] = FIVE_BULLET_ARCHIVE
    return item


def apply_public_links(items: list[dict]) -> None:
    """Point Five Bullet Friday at a public tim.blog post, or the archive."""
    blog = [item for item in items if item.get("feedId") == "tim-ferriss-blog"]
    for item in items:
        candidates = item.pop("_public_candidates", None)
        if item.get("feedId") != FIVE_BULLET_ID:
            continue
        chosen = FIVE_BULLET_ARCHIVE
        from_email: list[str] = []
        for url in candidates or []:
            if isinstance(url, str) and url.startswith("https://tim.blog/") and "bullet" in url.lower():
                clean = url.split("?")[0].split("#")[0]
                if clean not in from_email:
                    from_email.append(clean)
        published = parse_date(item.get("published"))
        best_url = None
        best_delta = None
        for post in blog:
            url = (post.get("url") or "").split("?")[0].split("#")[0]
            title = (post.get("title") or "").lower()
            if "bullet" not in url.lower() and "bullet" not in title:
                continue
            posted = parse_date(post.get("published"))
            if published is None or posted is None:
                continue
            delta = abs((posted - published).total_seconds())
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_url = url
        if best_url and best_delta is not None and best_delta <= 5 * 86400:
            chosen = best_url
        elif len(from_email) == 1:
            chosen = from_email[0]
        item["url"] = chosen


def youtube_id_from_text(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        text = value.strip()
        if not text:
            continue
        if YT_ID_ONLY.match(text):
            return text
        match = YT_ID_RE.search(text)
        if match:
            return match.group(1)
    return None


def media_description(entry: ET.Element) -> str:
    for el in entry.iter():
        if not isinstance(el.tag, str):
            continue
        # YouTube channel feeds put the blurb in MRSS media:description.
        if el.tag != "{http://search.yahoo.com/mrss/}description":
            continue
        text = "".join(el.itertext()).strip()
        if text:
            return text
    return ""


def yt_video_id_from_entry(entry: ET.Element) -> str | None:
    for el in entry.iter():
        if isinstance(el.tag, str) and el.tag.rsplit("}", 1)[-1] == "videoId":
            found = local_text(el)
            if found and YT_ID_ONLY.match(found):
                return found
    return None


def attach_youtube(item: dict, entry: ET.Element | None = None, guid: str = "") -> dict:
    """Add videoId when this item is a YouTube watch URL or yt entry."""
    video_id = yt_video_id_from_entry(entry) if entry is not None else None
    if entry is not None:
        media_desc = media_description(entry)
        if media_desc and (not item.get("summary") or item.get("kind") == "youtube"):
            item["summary"] = truncate(strip_html(media_desc))
    if not video_id:
        video_id = youtube_id_from_text(item.get("url"), guid)
    if video_id:
        item["videoId"] = video_id
        url = item.get("url") or ""
        if item.get("kind") in (None, "", "other") and (
            "youtube.com" in url or "youtu.be" in url or guid.startswith("yt:video:")
        ):
            item["kind"] = "youtube"
        if not url:
            item["url"] = f"https://www.youtube.com/watch?v={video_id}"
    return item


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read()


def child(el: ET.Element, *names: str) -> ET.Element | None:
    for name in names:
        found = el.find(name)
        if found is not None:
            return found
        if "}" not in name and name.startswith("{"):
            continue
    for child_el in list(el):
        tag = child_el.tag
        local = tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""
        if local in names or tag in names:
            return child_el
    return None


def atom_link(entry: ET.Element) -> str:
    for link in entry.findall("atom:link", ATOM_NS) + entry.findall(
        "{http://www.w3.org/2005/Atom}link"
    ) + entry.findall("link"):
        rel = link.get("rel") or "alternate"
        href = (link.get("href") or "").strip()
        if href and rel in ("alternate", "self") and (
            not link.get("type") or "html" in (link.get("type") or "") or rel == "alternate"
        ):
            if rel == "alternate":
                return href
    for link in entry.findall("atom:link", ATOM_NS) + entry.findall(
        "{http://www.w3.org/2005/Atom}link"
    ) + entry.findall("link"):
        href = (link.get("href") or "").strip()
        if href:
            return href
    return ""


def element_inner(el: ET.Element) -> str:
    parts = [el.text or ""]
    for child_el in list(el):
        parts.append(ET.tostring(child_el, encoding="unicode", short_empty_elements=True))
        parts.append(child_el.tail or "")
    return "".join(parts).strip()


def entry_html(entry: ET.Element) -> str:
    """Prefer full content over the short summary."""
    ranked: list[tuple[int, str]] = []
    for el in list(entry):
        if not isinstance(el.tag, str):
            continue
        local = el.tag.rsplit("}", 1)[-1].lower()
        if local not in ("encoded", "content", "description", "summary"):
            continue
        if el.tag.startswith("{http://search.yahoo.com/mrss/}"):
            continue
        inner = element_inner(el)
        if not inner:
            continue
        rank = {"encoded": 0, "content": 1, "description": 2, "summary": 3}[local]
        ranked.append((rank, inner))
    if not ranked:
        return ""
    rich = [item for item in ranked if item[0] <= 1]
    pool = rich or ranked
    pool.sort(key=lambda item: len(item[1]), reverse=True)
    return pool[0][1]


def parse_rss_items(root: ET.Element, feed: dict) -> list[dict]:
    items: list[dict] = []
    channel = root.find("channel")
    if channel is None:
        channel = root
    for entry in channel.findall("item"):
        title = local_text(child(entry, "title"))
        link = local_text(child(entry, "link"))
        guid_el = child(entry, "guid")
        guid = local_text(guid_el) or (guid_el.get("isPermaLink") if guid_el is not None else "") or ""
        if not link and guid.startswith("http"):
            link = guid
        desc = entry_html(entry)
        published = parse_date(local_text(child(entry, "pubDate", "date", "{http://purl.org/dc/elements/1.1/}date")))
        author = local_text(child(entry, "author", "{http://purl.org/dc/elements/1.1/}creator"))
        if not title and not link:
            continue
        if is_short_entry(entry, link, guid):
            log_skip_short(feed, link or guid)
            continue
        item = {
            "id": item_id(feed["id"], guid, link, title),
            "title": title or link,
            "url": link,
            "feedId": feed["id"],
            "feedTitle": feed.get("title") or feed["id"],
            "kind": feed.get("kind") or "other",
            "published": published.isoformat() if published else None,
            "summary": plain_excerpt(desc, []) if desc else "",
            "author": author or None,
        }
        if contains_shorts(item.get("url")):
            log_skip_short(feed, item.get("url") or "")
            continue
        items.append(privatize_item(attach_youtube(item, entry, guid), feed, desc))
        if len(items) >= MAX_PER_FEED:
            break
    return items


def atom_entries(root: ET.Element) -> list[ET.Element]:
    """Entry elements, once each.

    ElementTree matches a namespaced entry through both the prefix map and
    the Clark notation, so concatenating those two queries would list every
    entry twice and burn the per-feed cap.
    """
    found = root.findall("atom:entry", ATOM_NS) + root.findall(
        "{http://www.w3.org/2005/Atom}entry"
    )
    if not found:
        found = [
            el
            for el in root
            if isinstance(el.tag, str) and el.tag.rsplit("}", 1)[-1] == "entry"
        ]
    unique: list[ET.Element] = []
    seen: set[int] = set()
    for el in found:
        marker = id(el)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(el)
    return unique


def parse_atom_items(root: ET.Element, feed: dict) -> list[dict]:
    items: list[dict] = []
    entries = atom_entries(root)
    for entry in entries:
        title = local_text(child(entry, "atom:title", "{http://www.w3.org/2005/Atom}title", "title"))
        link = atom_link(entry)
        guid = local_text(child(entry, "atom:id", "{http://www.w3.org/2005/Atom}id", "id"))
        desc = entry_html(entry)
        published = parse_date(
            local_text(
                child(
                    entry,
                    "atom:published",
                    "{http://www.w3.org/2005/Atom}published",
                    "atom:updated",
                    "{http://www.w3.org/2005/Atom}updated",
                    "published",
                    "updated",
                )
            )
        )
        author_el = child(entry, "atom:author", "{http://www.w3.org/2005/Atom}author", "author")
        author = ""
        if author_el is not None:
            author = local_text(
                child(author_el, "atom:name", "{http://www.w3.org/2005/Atom}name", "name")
            )
        if not title and not link:
            continue
        if is_short_entry(entry, link, guid):
            log_skip_short(feed, link or guid)
            continue
        item = {
            "id": item_id(feed["id"], guid, link, title),
            "title": title or link,
            "url": link,
            "feedId": feed["id"],
            "feedTitle": feed.get("title") or feed["id"],
            "kind": feed.get("kind") or "other",
            "published": published.isoformat() if published else None,
            "summary": plain_excerpt(desc, []) if desc else "",
            "author": author or None,
        }
        if contains_shorts(item.get("url")):
            log_skip_short(feed, item.get("url") or "")
            continue
        items.append(privatize_item(attach_youtube(item, entry, guid), feed, desc))
        if len(items) >= MAX_PER_FEED:
            break
    return items


def parse_feed(raw: bytes, feed: dict) -> list[dict]:
    # Some feeds include a BOM or leading whitespace.
    text = raw.lstrip(b"\xef\xbb\xbf \t\r\n")
    root = ET.fromstring(text)
    tag = root.tag.rsplit("}", 1)[-1].lower()
    # A <feed> with no <entry> (or an <rss> channel with no <item>) is an
    # empty digest, not a failed fetch. Return that empty list directly.
    # Do not use `or` here: an empty list is falsy and would look like failure.
    if tag == "feed":
        return parse_atom_items(root, feed)
    if tag == "rss" or tag == "rdf" or root.find("channel") is not None:
        return parse_rss_items(root, feed)
    rss_items = parse_rss_items(root, feed)
    if rss_items:
        return rss_items
    return parse_atom_items(root, feed)


def normalize_feed(entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None
    feed_id = entry.get("id")
    if not isinstance(feed_id, str) or not feed_id.strip():
        return None
    feed_id = feed_id.strip()
    url = entry.get("url")
    secret = entry.get("url_secret")
    has_url = isinstance(url, str) and bool(url.strip())
    has_secret = isinstance(secret, str) and bool(secret.strip())
    if not has_url and not has_secret:
        return None
    secret_name = ""
    if has_secret:
        secret_name = secret.strip()
        if not ENV_NAME.fullmatch(secret_name):
            print(
                f"skip {feed_id}: url_secret must be an environment variable name",
                file=sys.stderr,
            )
            return None
    title = entry.get("title")
    kind = entry.get("kind")
    return {
        "id": feed_id,
        "url": url.strip() if has_url else "",
        "url_secret": secret_name,
        "title": title.strip() if isinstance(title, str) and title.strip() else feed_id,
        "kind": kind.strip() if isinstance(kind, str) and kind.strip() else "other",
    }


def resolve_fetch_url(feed: dict) -> str | None:
    """Download URL. None means the feed is skipped (unset secret, or no URL)."""
    if feed.get("url_secret"):
        return os.environ.get(feed["url_secret"], "").strip() or None
    return (feed.get("url") or "").strip() or None


def xml_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def public_opml_feeds(raw_feeds: list) -> list[dict]:
    """Public feeds only. Anything with url_secret stays out of the OPML."""
    public: list[dict] = []
    seen: set[str] = set()
    for raw in raw_feeds:
        if not isinstance(raw, dict):
            continue
        secret = raw.get("url_secret")
        if isinstance(secret, str) and secret.strip():
            continue
        feed = normalize_feed(raw)
        if not feed or not feed.get("url") or feed["id"] in seen:
            continue
        seen.add(feed["id"])
        public.append(feed)
    return public


def render_opml(feeds: list[dict]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        "  <head>",
        "    <title>harrison shin feed</title>",
        "  </head>",
        "  <body>",
    ]
    for feed in feeds:
        lines.append(
            "    "
            + '<outline type="rss" text="{title}" title="{title}" xmlUrl="{url}" category="{kind}"/>'.format(
                title=xml_attr(feed["title"]),
                url=xml_attr(feed["url"]),
                kind=xml_attr(feed["kind"]),
            )
        )
    lines.extend(["  </body>", "</opml>", ""])
    return "\n".join(lines)


def write_opml(raw_feeds: list) -> None:
    text = render_opml(public_opml_feeds(raw_feeds))
    previous = OPML_PATH.read_text(encoding="utf-8") if OPML_PATH.exists() else None
    if previous == text:
        print(f"opml unchanged ({text.count('<outline ')} feeds)")
        return
    OPML_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPML_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {OPML_PATH.relative_to(ROOT)} ({text.count('<outline ')} feeds)")


def main() -> int:
    config = load_json(FEEDS_PATH, {"feeds": []})
    raw_feeds = config.get("feeds") if isinstance(config, dict) else []
    if not isinstance(raw_feeds, list):
        print("reader/feeds.json must contain a feeds array", file=sys.stderr)
        return 1
    write_opml(raw_feeds)

    feeds = []
    seen_ids = set()
    for raw in raw_feeds:
        feed = normalize_feed(raw)
        if not feed:
            continue
        if feed["id"] in seen_ids:
            print(f"skip duplicate feed id: {feed['id']}", file=sys.stderr)
            continue
        seen_ids.add(feed["id"])
        feeds.append(feed)

    active: list[dict] = []
    markers: list[str] = []
    for feed in feeds:
        fetch_url = resolve_fetch_url(feed)
        if not fetch_url:
            # Unset url_secret is a quiet skip, not a failed feed.
            continue
        ready = dict(feed)
        ready["_fetch_url"] = fetch_url
        active.append(ready)
        if ready.get("url_secret"):
            markers.extend(secret_markers(fetch_url))
    markers = sorted(set(markers), key=len, reverse=True)

    cutoff = datetime.now(UTC) - timedelta(days=KEEP_DAYS)
    collected: list[dict] = []
    errors: list[dict] = []

    for feed in active:
        try:
            raw = fetch_bytes(feed["_fetch_url"])
            items = parse_feed(raw, feed)
            kept = 0
            for item in items:
                if contains_shorts(item.get("url"), item.get("link"), item.get("guid")):
                    log_skip_short(feed, item.get("url") or "")
                    continue
                published = parse_date(item.get("published"))
                if published is not None and published < cutoff:
                    continue
                if published is not None:
                    item["published"] = published.isoformat()
                if not item.get("author"):
                    item.pop("author", None)
                collected.append(item)
                kept += 1
            print(f"ok {feed['id']}: {kept} items")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ET.ParseError, OSError) as exc:
            if feed.get("url_secret"):
                msg = type(exc).__name__
            else:
                msg = f"{type(exc).__name__}: {exc}"
            print(f"fail {feed['id']}: {msg}", file=sys.stderr)
            errors.append({"feedId": feed["id"], "error": msg})

    # Prefer newest; stable by id for ties
    def sort_key(item: dict):
        published = parse_date(item.get("published")) or datetime.min.replace(tzinfo=UTC)
        return (published, item.get("id") or "")

    collected.sort(key=sort_key, reverse=True)
    apply_public_links(collected)
    apply_reading(collected)

    # Deduplicate by id (first = newest wins)
    deduped: list[dict] = []
    seen = set()
    for item in collected:
        for key in list(item):
            if key.startswith("_"):
                item.pop(key, None)
        for key, value in list(item.items()):
            if isinstance(value, str) and markers:
                item[key] = scrub_markers(value, markers).strip()
        iid = item["id"]
        if iid in seen:
            continue
        seen.add(iid)
        deduped.append(item)

    now = datetime.now(UTC)
    payload = {
        "updated": now.isoformat().replace("+00:00", "Z"),
        "updatedPacific": now.astimezone(PACIFIC).strftime("%Y-%m-%d %H:%M %Z"),
        "keepDays": KEEP_DAYS,
        "feedCount": len(active),
        "itemCount": len(deduped),
        "errors": errors,
        "items": deduped,
    }

    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    for marker in markers:
        if marker and marker in encoded:
            print(
                "refusing to write digest: a private feed value would have been stored",
                file=sys.stderr,
            )
            return 1

    ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ITEMS_PATH.write_text(encoded, encoding="utf-8")

    print(f"wrote {ITEMS_PATH.relative_to(ROOT)} ({len(deduped)} items, {len(errors)} errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
