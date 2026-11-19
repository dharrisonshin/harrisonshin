#!/usr/bin/env python3
"""Fetch RSS/Atom feeds from reader/feeds.json into reader/items.json.

Keeps items from the last KEEP_DAYS days (Pacific). Safe to run locally or
from GitHub Actions. Network failures on a single feed are skipped.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FEEDS_PATH = ROOT / "reader" / "feeds.json"
ITEMS_PATH = ROOT / "reader" / "items.json"
KEEP_DAYS = 14
MAX_PER_FEED = 40
USER_AGENT = "harrisonshin-reader/1.0 (+https://harrisonshin.com/reader/)"
PACIFIC = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
HTML_TAG = re.compile(r"<[^>]+>")
WHITESPACE = re.compile(r"\s+")


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
        desc = local_text(child(entry, "description", "content:encoded", "{http://purl.org/rss/1.0/modules/content/}encoded"))
        if not desc:
            content = child(entry, "content:encoded", "{http://purl.org/rss/1.0/modules/content/}encoded")
            desc = local_text(content)
        published = parse_date(local_text(child(entry, "pubDate", "date", "{http://purl.org/dc/elements/1.1/}date")))
        author = local_text(child(entry, "author", "{http://purl.org/dc/elements/1.1/}creator"))
        if not title and not link:
            continue
        items.append(
            {
                "id": item_id(feed["id"], guid, link, title),
                "title": title or link,
                "url": link,
                "feedId": feed["id"],
                "feedTitle": feed.get("title") or feed["id"],
                "kind": feed.get("kind") or "other",
                "published": published.isoformat() if published else None,
                "summary": truncate(strip_html(desc)) if desc else "",
                "author": author or None,
            }
        )
        if len(items) >= MAX_PER_FEED:
            break
    return items


def parse_atom_items(root: ET.Element, feed: dict) -> list[dict]:
    items: list[dict] = []
    entries = root.findall("atom:entry", ATOM_NS) + root.findall(
        "{http://www.w3.org/2005/Atom}entry"
    )
    if not entries:
        entries = [el for el in root if el.tag.rsplit("}", 1)[-1] == "entry"]
    for entry in entries:
        title = local_text(child(entry, "atom:title", "{http://www.w3.org/2005/Atom}title", "title"))
        link = atom_link(entry)
        guid = local_text(child(entry, "atom:id", "{http://www.w3.org/2005/Atom}id", "id"))
        summary_el = child(
            entry,
            "atom:summary",
            "{http://www.w3.org/2005/Atom}summary",
            "atom:content",
            "{http://www.w3.org/2005/Atom}content",
            "summary",
            "content",
        )
        desc = ""
        if summary_el is not None:
            desc = "".join(summary_el.itertext()).strip() or local_text(summary_el)
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
        items.append(
            {
                "id": item_id(feed["id"], guid, link, title),
                "title": title or link,
                "url": link,
                "feedId": feed["id"],
                "feedTitle": feed.get("title") or feed["id"],
                "kind": feed.get("kind") or "other",
                "published": published.isoformat() if published else None,
                "summary": truncate(strip_html(desc)) if desc else "",
                "author": author or None,
            }
        )
        if len(items) >= MAX_PER_FEED:
            break
    return items


def parse_feed(raw: bytes, feed: dict) -> list[dict]:
    # Some feeds include a BOM or leading whitespace.
    text = raw.lstrip(b"\xef\xbb\xbf \t\r\n")
    root = ET.fromstring(text)
    tag = root.tag.rsplit("}", 1)[-1].lower()
    if tag == "rss" or root.find("channel") is not None:
        return parse_rss_items(root, feed)
    if tag == "feed":
        return parse_atom_items(root, feed)
    # RDF RSS 1.0
    if tag == "rdf":
        return parse_rss_items(root, feed)
    return parse_rss_items(root, feed) or parse_atom_items(root, feed)


def normalize_feed(entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None
    feed_id = entry.get("id")
    url = entry.get("url")
    if not isinstance(feed_id, str) or not feed_id.strip():
        return None
    if not isinstance(url, str) or not url.strip():
        return None
    title = entry.get("title")
    kind = entry.get("kind")
    return {
        "id": feed_id.strip(),
        "url": url.strip(),
        "title": title.strip() if isinstance(title, str) and title.strip() else feed_id.strip(),
        "kind": kind.strip() if isinstance(kind, str) and kind.strip() else "other",
    }


def main() -> int:
    config = load_json(FEEDS_PATH, {"feeds": []})
    raw_feeds = config.get("feeds") if isinstance(config, dict) else []
    if not isinstance(raw_feeds, list):
        print("reader/feeds.json must contain a feeds array", file=sys.stderr)
        return 1

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

    cutoff = datetime.now(UTC) - timedelta(days=KEEP_DAYS)
    collected: list[dict] = []
    errors: list[dict] = []

    for feed in feeds:
        try:
            raw = fetch_bytes(feed["url"])
            items = parse_feed(raw, feed)
            kept = 0
            for item in items:
                published = parse_date(item.get("published"))
                if published is not None and published < cutoff:
                    continue
                if published is not None:
                    item["published"] = published.isoformat()
                # Drop author if empty
                if not item.get("author"):
                    item.pop("author", None)
                collected.append(item)
                kept += 1
            print(f"ok {feed['id']}: {kept} items")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ET.ParseError, OSError) as exc:
            msg = f"{type(exc).__name__}: {exc}"
            print(f"fail {feed['id']}: {msg}", file=sys.stderr)
            errors.append({"feedId": feed["id"], "error": msg})

    # Prefer newest; stable by id for ties
    def sort_key(item: dict):
        published = parse_date(item.get("published")) or datetime.min.replace(tzinfo=UTC)
        return (published, item.get("id") or "")

    collected.sort(key=sort_key, reverse=True)

    # Deduplicate by id (first = newest wins)
    deduped: list[dict] = []
    seen = set()
    for item in collected:
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
        "feedCount": len(feeds),
        "itemCount": len(deduped),
        "errors": errors,
        "items": deduped,
    }

    ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ITEMS_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"wrote {ITEMS_PATH.relative_to(ROOT)} ({len(deduped)} items, {len(errors)} errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
