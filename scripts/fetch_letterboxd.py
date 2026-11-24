#!/usr/bin/env python3
"""Merge Harrison's public Letterboxd diary into library/letterboxd.json.

The hourly run reads the RSS feed. Diary entries update the file. Lists and
reviews with no watched date are skipped. Films already in the file stay,
because the feed only holds recent items.

`--full` walks the public diary and watched-film pages, with a pause between
requests, and backfills every logged film. `--pages-dir` reads saved copies
of those pages. A failed fetch, or a short page set, leaves the last good
file in place.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEED_URL = "https://letterboxd.com/smackushin/rss/"
FILMS_URL = "https://letterboxd.com/smackushin/films/"
DIARY_URL = "https://letterboxd.com/smackushin/films/diary/"
PROFILE_URL = "https://letterboxd.com/smackushin/"
USER_AGENT = "harrisonshin-letterboxd/1.0 (+https://harrisonshin.com/library/)"
PAUSE_SECONDS = 1.5
LB_NS = "https://letterboxd.com"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FILM_HREF_RE = re.compile(r"/for/(\d{4})/(\d{2})/(\d{2})/")
RATED_RE = re.compile(r"\brated-(\d+)\b")
NAME_RE = re.compile(r"^(.*)\s\((\d{4})\)$")
SLUG_RE = re.compile(r"^[a-z0-9-]+$")
IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
NEXT_RE = re.compile(r'<a class="next" href="([^"]+)"')
COUNT_RE = re.compile(r'title="(\d+)(?:&nbsp;|\s)*films"')
ROW_RE = re.compile(r'<tr class="diary-entry-row\b.*?</tr>', re.S)
ITEM_RE = re.compile(r'<li class="griditem">.*?</li>', re.S)
ATTR_RE_CACHE: dict[str, re.Pattern[str]] = {}


def attr(blob: str, name: str) -> str:
    pattern = ATTR_RE_CACHE.get(name)
    if pattern is None:
        pattern = re.compile(r'\b%s="([^"]*)"' % re.escape(name))
        ATTR_RE_CACHE[name] = pattern
    match = pattern.search(blob)
    if not match:
        return ""
    return html.unescape(match.group(1)).strip()


def norm_title(title: str) -> str:
    text = unicodedata.normalize("NFKC", title or "")
    text = text.replace("–", "-").replace("—", "-").replace("’", "'").replace("‘", "'")
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def title_key(title: str, year) -> str:
    year_bit = str(year) if isinstance(year, int) and not isinstance(year, bool) else ""
    return norm_title(title) + "|" + year_bit


def strip_paren(title: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", title or "").strip()


def match_tokens(title: str) -> list[str]:
    words = norm_title(strip_paren(title)).split()
    if "episode" in words:
        words = [word for word in words if word != "episode" and not re.fullmatch(r"[ivxlcdm]+", word)]
    return [word for word in words if word != "and"]


def contiguous(short: list[str], long: list[str]) -> bool:
    if len(short) < 2 or len(short) > len(long):
        return False
    width = len(short)
    for start in range(len(long) - width + 1):
        if long[start:start + width] == short:
            return True
    return False


def same_film(left: dict, right: dict) -> bool:
    if left.get("year") != right.get("year") or not isinstance(left.get("year"), int):
        return False
    if norm_title(left.get("title") or "") == norm_title(right.get("title") or ""):
        return True
    if norm_title(strip_paren(left.get("title") or "")) == norm_title(right.get("title") or ""):
        return True
    if norm_title(strip_paren(right.get("title") or "")) == norm_title(left.get("title") or ""):
        return True
    left_tokens = match_tokens(left.get("title") or "")
    right_tokens = match_tokens(right.get("title") or "")
    if len(left_tokens) >= 2 and left_tokens == right_tokens:
        return True
    return contiguous(left_tokens, right_tokens) or contiguous(right_tokens, left_tokens)


def clean_rating(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0 or value > 5:
        return None
    halves = round(float(value) * 2) / 2
    if halves == int(halves):
        return int(halves)
    return halves


def rating_from_class(blob: str):
    match = RATED_RE.search(blob)
    if not match:
        return None
    stars = int(match.group(1))
    if stars <= 0 or stars > 10:
        return None
    return clean_rating(stars / 2)


def split_name(name: str):
    match = NAME_RE.match((name or "").strip())
    if not match:
        text = (name or "").strip()
        return text, None
    return match.group(1).strip(), int(match.group(2))


def film_link(slug: str, item_link: str) -> str:
    link = (item_link or "").strip()
    if link.startswith("/film/"):
        path = link.split("?", 1)[0]
        if not path.endswith("/"):
            path += "/"
        return "https://letterboxd.com" + path
    if slug:
        return "https://letterboxd.com/film/%s/" % slug
    return ""


def poster_url(film_id: str, slug: str) -> str:
    if not film_id.isdigit() or not SLUG_RE.fullmatch(slug or ""):
        return ""
    folders = "/".join(film_id)
    return "https://a.ltrbxd.com/resized/film-poster/%s/%s-%s-0-230-0-345-crop.jpg" % (
        folders,
        film_id,
        slug,
    )


def blank_entry():
    return {
        "title": "",
        "year": None,
        "director": None,
        "genres": [],
        "rating": None,
        "last_watched": None,
        "takeaway": None,
        "link": None,
        "poster": None,
        "poster_url": "",
        "liked": None,
        "rewatch": None,
        "slug": "",
        "film_id": "",
        "from_letterboxd": False,
    }


def parse_diary_html(page: str) -> list[dict]:
    watches = []
    for row in ROW_RE.findall(page):
        name = attr(row, "data-item-full-display-name") or attr(row, "data-item-name")
        title, year = split_name(name)
        slug = attr(row, "data-item-slug").lower()
        if not title or not slug:
            continue
        date_match = FILM_HREF_RE.search(row)
        watched = None
        if date_match:
            watched = "%s-%s-%s" % date_match.groups()
        rewatch_td = re.search(r'<td class="([^"]*\bcol-rewatch[^"]*)"', row)
        rewatch = bool(rewatch_td) and "icon-status-off" not in rewatch_td.group(1)
        film_id_match = re.search(r"film:(\d+)", row)
        watches.append({
            "title": title,
            "year": year,
            "slug": slug,
            "film_id": film_id_match.group(1) if film_id_match else "",
            "rating": rating_from_class(row),
            "last_watched": watched,
            "liked": "icon-liked" in row,
            "rewatch": rewatch,
            "link": film_link(slug, attr(row, "data-item-link")),
        })
    return watches


def parse_films_html(page: str) -> list[dict]:
    films = []
    for item in ITEM_RE.findall(page):
        name = attr(item, "data-item-full-display-name") or attr(item, "data-item-name")
        title, year = split_name(name)
        slug = attr(item, "data-item-slug").lower()
        if not title or not slug:
            continue
        film_id_match = re.search(r"film:(\d+)", item)
        films.append({
            "title": title,
            "year": year,
            "slug": slug,
            "film_id": film_id_match.group(1) if film_id_match else "",
            "rating": rating_from_class(item),
            "last_watched": None,
            "liked": "icon-liked" in item,
            "rewatch": False,
            "link": film_link(slug, attr(item, "data-item-link")),
        })
    return films


def page_count(page: str, label: str):
    for match in COUNT_RE.finditer(page):
        window = page[match.end():match.end() + 40]
        if label in window:
            return int(match.group(1))
    return None


def combine_letterboxd(diary_pages: list[str], film_pages: list[str], rss_films: list[dict] | None):
    """Return films keyed by slug, newest diary watch first, or None if short."""
    diary_rows = []
    expected_diary = None
    for page in diary_pages:
        if expected_diary is None:
            expected_diary = page_count(page, "Diary")
        diary_rows.extend(parse_diary_html(page))
    film_rows = []
    expected_films = None
    for page in film_pages:
        if expected_films is None:
            expected_films = page_count(page, "Watched")
        film_rows.extend(parse_films_html(page))
    if expected_diary is not None and len(diary_rows) < expected_diary:
        print(
            "diary pages had %s of %s entries. library/letterboxd.json was left unchanged."
            % (len(diary_rows), expected_diary)
        )
        return None
    if expected_films is not None and len({row["slug"] for row in film_rows}) < expected_films:
        print(
            "film pages had %s of %s films. library/letterboxd.json was left unchanged."
            % (len({row["slug"] for row in film_rows}), expected_films)
        )
        return None
    if not film_rows and not diary_rows:
        print("letterboxd pages had no films. library/letterboxd.json was left unchanged.")
        return None

    by_slug: dict[str, dict] = {}
    for row in diary_rows:
        current = by_slug.get(row["slug"])
        if current is None:
            by_slug[row["slug"]] = {
                "title": row["title"],
                "year": row["year"],
                "slug": row["slug"],
                "film_id": row["film_id"],
                "rating": row["rating"],
                "last_watched": row["last_watched"],
                "liked": row["liked"],
                "rewatch": row["rewatch"],
                "link": row["link"],
                "watches": 1,
            }
            continue
        current["watches"] += 1
        current["rewatch"] = True
        current["liked"] = current["liked"] or row["liked"]
        if row["rewatch"]:
            current["rewatch"] = True
        if row["film_id"] and not current["film_id"]:
            current["film_id"] = row["film_id"]
        if row["last_watched"] and (
            not current["last_watched"] or row["last_watched"] > current["last_watched"]
        ):
            current["last_watched"] = row["last_watched"]
            current["title"] = row["title"] or current["title"]
            if row["year"] is not None:
                current["year"] = row["year"]
            if row["rating"] is not None:
                current["rating"] = row["rating"]
        elif current["rating"] is None and row["rating"] is not None:
            current["rating"] = row["rating"]

    for row in film_rows:
        current = by_slug.get(row["slug"])
        if current is None:
            by_slug[row["slug"]] = {
                "title": row["title"],
                "year": row["year"],
                "slug": row["slug"],
                "film_id": row["film_id"],
                "rating": row["rating"],
                "last_watched": None,
                "liked": row["liked"],
                "rewatch": False,
                "link": row["link"],
                "watches": 0,
            }
            continue
        if current["rating"] is None and row["rating"] is not None:
            current["rating"] = row["rating"]
        current["liked"] = current["liked"] or row["liked"]
        if row["film_id"] and not current["film_id"]:
            current["film_id"] = row["film_id"]
        if row["title"] and not current["title"]:
            current["title"] = row["title"]
        if current["year"] is None and row["year"] is not None:
            current["year"] = row["year"]
        if not current["link"]:
            current["link"] = row["link"]

    if rss_films:
        for row in rss_films:
            slug = row.get("slug") or ""
            current = by_slug.get(slug) if slug else None
            if current is None:
                continue
            if row.get("poster_url") and not current.get("poster_url"):
                current["poster_url"] = row["poster_url"]
            if row.get("last_watched") and (
                not current["last_watched"] or row["last_watched"] > current["last_watched"]
            ):
                current["last_watched"] = row["last_watched"]
                if row.get("rating") is not None:
                    current["rating"] = row["rating"]
                current["rewatch"] = current["rewatch"] or bool(row.get("rewatch"))
                current["liked"] = current["liked"] or bool(row.get("liked"))

    for film in by_slug.values():
        if film.get("watches", 0) > 1:
            film["rewatch"] = True
        if not film.get("poster_url"):
            film["poster_url"] = poster_url(film.get("film_id") or "", film.get("slug") or "")
    return list(by_slug.values())


def local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def child_text(item: ET.Element, name: str) -> str:
    for child in list(item):
        if local_tag(child.tag) == name and child.text:
            return child.text.strip()
    return ""


def parse_rss(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    channel = None
    for element in root.iter():
        if local_tag(element.tag) == "channel":
            channel = element
            break
    if channel is None:
        raise ValueError("rss has no channel")
    films = []
    for item in list(channel):
        if local_tag(item.tag) != "item":
            continue
        link = ""
        for child in list(item):
            if local_tag(child.tag) == "link" and child.text:
                link = child.text.strip()
                break
        if "/list/" in link:
            continue
        watched = child_text(item, "watchedDate")
        title = child_text(item, "filmTitle")
        if not DATE_RE.fullmatch(watched) or not title:
            continue
        year_text = child_text(item, "filmYear")
        year = int(year_text) if year_text.isdigit() else None
        slug_match = re.search(r"letterboxd\.com/(?:[^/]+/)?film/([^/?#]+)", link, re.I)
        slug = slug_match.group(1).lower() if slug_match else ""
        description = ""
        for child in list(item):
            if local_tag(child.tag) == "description" and child.text:
                description = child.text
                break
        image = ""
        image_match = IMG_RE.search(description or "")
        if image_match:
            candidate = html.unescape(image_match.group(1))
            if candidate.startswith("https://") and (
                "ltrbxd.com" in candidate or "letterboxd.com" in candidate
            ):
                image = candidate
        films.append({
            "title": title,
            "year": year,
            "slug": slug,
            "film_id": "",
            "rating": clean_rating(_float_or_none(child_text(item, "memberRating"))),
            "last_watched": watched,
            "liked": child_text(item, "memberLike").casefold() == "yes",
            "rewatch": child_text(item, "rewatch").casefold() == "yes",
            "link": film_link(slug, ""),
            "poster_url": image,
            "watches": 1,
        })
    return films


def _float_or_none(text: str):
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fetch_bytes(url: str, timeout: int = 30, limit: int = 5_000_000) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise urllib.error.HTTPError(url, status, "bad status", response.headers, None)
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("response too large")
    if b"Just a moment" in data[:4000] or b"cf-challenge" in data[:8000]:
        raise ValueError("letterboxd presented a challenge page")
    return data


def crawl_pages(start: str, fetch, pause) -> list[str] | None:
    pages = []
    url = start
    seen = set()
    for _ in range(40):
        if not url or url in seen:
            break
        seen.add(url)
        try:
            raw = fetch(url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            print("letterboxd fetch failed: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
            print("library/letterboxd.json was left unchanged.")
            return None
        page = raw.decode("utf-8", "replace")
        pages.append(page)
        match = NEXT_RE.search(page)
        if not match:
            break
        url = urllib.parse.urljoin("https://letterboxd.com/", html.unescape(match.group(1)))
        pause(PAUSE_SECONDS)
    return pages


def load_rss(fetch) -> list[dict] | None:
    try:
        raw = fetch(FEED_URL)
        return parse_rss(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ET.ParseError, OSError, ValueError) as exc:
        print("letterboxd rss failed: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return None


def load_json(path: Path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print("could not read %s: %s" % (path.name, exc), file=sys.stderr)
        return None
    if not isinstance(data, list):
        print("%s is not a list. library/letterboxd.json was left unchanged." % path.name)
        return None
    return data


def catalog_entry(item: dict):
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    year = item.get("year")
    if isinstance(year, bool) or not isinstance(year, int):
        year = None
    genres = item.get("genres") if isinstance(item.get("genres"), list) else []
    genres = [genre.strip() for genre in genres if isinstance(genre, str) and genre.strip()]
    director = item.get("director")
    if not isinstance(director, str) or not director.strip():
        director = None
    takeaway = item.get("takeaway")
    if not isinstance(takeaway, str) or not takeaway.strip():
        takeaway = None
    watched = item.get("last_watched")
    if not isinstance(watched, str) or not DATE_RE.fullmatch(watched):
        watched = None
    entry = blank_entry()
    entry.update({
        "title": title.strip(),
        "year": year,
        "director": director,
        "genres": genres,
        "rating": clean_rating(item.get("rating")),
        "last_watched": watched,
        "takeaway": takeaway,
    })
    link = item.get("link")
    if isinstance(link, str) and link.startswith("https://letterboxd.com/film/"):
        entry["link"] = link
        slug_match = re.search(r"/film/([^/?#]+)", link)
        entry["slug"] = slug_match.group(1).lower() if slug_match else ""
        entry["from_letterboxd"] = True
    poster = item.get("poster")
    if isinstance(poster, str) and poster.startswith("posters/") and ".." not in poster:
        entry["poster"] = poster
    if item.get("liked") is True or item.get("liked") is False:
        entry["liked"] = bool(item.get("liked"))
    if item.get("rewatch") is True or item.get("rewatch") is False:
        entry["rewatch"] = bool(item.get("rewatch"))
    if entry["from_letterboxd"]:
        entry["liked"] = bool(entry["liked"])
        entry["rewatch"] = bool(entry["rewatch"])
    return entry


def catalog_index(entries: list[dict]):
    by_key = {}
    by_title = {}
    for entry in entries:
        key = title_key(entry["title"], entry["year"])
        by_key.setdefault(key, entry)
        by_title.setdefault(norm_title(entry["title"]), []).append(entry)
    return by_key, by_title


def match_key(film: dict, by_key: dict, by_title: dict):
    key = title_key(film.get("title") or "", film.get("year"))
    if key in by_key:
        return key
    if isinstance(film.get("year"), int):
        missing_year = [
            entry for entry in by_title.get(norm_title(film.get("title") or ""), [])
            if entry.get("year") is None
        ]
        if len(missing_year) == 1:
            return title_key(missing_year[0]["title"], None)
    loose = [
        entry for entry in by_key.values()
        if same_film(film, entry) and title_key(entry["title"], entry["year"]) != key
    ]
    if len(loose) == 1:
        return title_key(loose[0]["title"], loose[0]["year"])
    return None


def overlay_letterboxd(entry: dict, film: dict):
    if film.get("title"):
        entry["title"] = film["title"]
    if isinstance(film.get("year"), int):
        entry["year"] = film["year"]
    entry["rating"] = film.get("rating")
    if film.get("last_watched"):
        entry["last_watched"] = film["last_watched"]
    if film.get("link"):
        entry["link"] = film["link"]
    entry["slug"] = film.get("slug") or entry.get("slug") or ""
    entry["film_id"] = film.get("film_id") or entry.get("film_id") or ""
    if film.get("poster_url"):
        entry["poster_url"] = film["poster_url"]
    entry["liked"] = bool(film.get("liked"))
    entry["rewatch"] = bool(film.get("rewatch"))
    entry["from_letterboxd"] = True
    return entry


def merge_library(previous: list[dict], catalog: list[dict], letterboxd_films: list[dict]):
    prev_entries = [entry for entry in (catalog_entry(item) for item in previous) if entry]
    cat_entries = [entry for entry in (catalog_entry(item) for item in catalog) if entry]
    prev_by_slug = {entry["slug"]: entry for entry in prev_entries if entry.get("slug")}
    prev_by_key, _ = catalog_index(prev_entries)
    cat_by_key, cat_by_title = catalog_index(cat_entries)
    used_catalog = set()
    merged = []
    seen_slugs = set()

    for film in letterboxd_films:
        slug = film.get("slug") or ""
        if slug and slug in seen_slugs:
            continue
        if slug:
            seen_slugs.add(slug)
        base = None
        if slug and slug in prev_by_slug:
            base = json.loads(json.dumps(prev_by_slug[slug]))
        key = match_key(film, cat_by_key, cat_by_title)
        catalog_hit = cat_by_key.get(key) if key else None
        if catalog_hit is not None:
            used_catalog.add(id(catalog_hit))
            if base is None:
                base = json.loads(json.dumps(catalog_hit))
            else:
                if catalog_hit.get("director"):
                    base["director"] = catalog_hit["director"]
                if catalog_hit.get("genres"):
                    base["genres"] = list(catalog_hit["genres"])
                if catalog_hit.get("takeaway"):
                    base["takeaway"] = catalog_hit["takeaway"]
        if base is None:
            key = match_key(film, prev_by_key, catalog_index(prev_entries)[1])
            prev_hit = prev_by_key.get(key) if key else None
            base = json.loads(json.dumps(prev_hit)) if prev_hit else blank_entry()
        merged.append(overlay_letterboxd(base, film))

    for entry in cat_entries:
        if id(entry) in used_catalog:
            continue
        key = title_key(entry["title"], entry["year"])
        if any(title_key(item["title"], item["year"]) == key for item in merged):
            continue
        copied = json.loads(json.dumps(entry))
        copied["from_letterboxd"] = False
        merged.append(copied)
    return merged


def sort_entries(entries: list[dict]):
    entries.sort(key=lambda entry: (entry.get("title") or "").casefold())
    entries.sort(key=lambda entry: entry.get("last_watched") or "", reverse=True)
    return entries


def public_entry(entry: dict) -> dict:
    out = {
        "title": entry.get("title") or "",
        "year": entry.get("year"),
        "director": entry.get("director"),
        "genres": entry.get("genres") or [],
        "rating": entry.get("rating"),
        "last_watched": entry.get("last_watched"),
        "takeaway": entry.get("takeaway"),
    }
    if entry.get("link"):
        out["link"] = entry["link"]
    if entry.get("poster"):
        out["poster"] = entry["poster"]
    if entry.get("from_letterboxd"):
        out["liked"] = bool(entry.get("liked"))
        out["rewatch"] = bool(entry.get("rewatch"))
    return out


def dumps(entries: list[dict]) -> str:
    return json.dumps([public_entry(entry) for entry in entries], indent=2, ensure_ascii=False) + "\n"


def write_if_changed(path: Path, text: str) -> bool:
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    if previous == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
    return True


def load_poster_cache(path: Path) -> dict:
    data = load_json_object(path)
    posters = data.get("posters") if isinstance(data, dict) else None
    return posters if isinstance(posters, dict) else {}


def load_json_object(path: Path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def fetch_image(url: str, timeout: int = 30) -> bytes:
    # The poster CDN rejects the library bot after a burst, and accepts a browser UA.
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "https://letterboxd.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise urllib.error.HTTPError(url, status, "bad status", response.headers, None)
        return response.read(1_500_001)


def image_bytes(data: bytes | None) -> bytes | None:
    if not data or len(data) > 1_500_000:
        return None
    if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or (data[:4] == b"RIFF" and b"WEBP" in data[:16]):
        return data
    return None


def poster_candidates(url: str) -> list[str]:
    urls = [url]
    # Some posters are filed under the slug with a trailing year removed
    # (x-2022 is stored as x). A wrong name comes back as a challenge page.
    match = re.search(r"/(\d+)-([a-z0-9-]+)-0-\d+-0-\d+-crop", url)
    if match:
        film_id, slug = match.group(1), match.group(2)
        short = re.sub(r"-\d{4}$", "", slug)
        if short and short != slug and SLUG_RE.fullmatch(short):
            urls.append(url.replace("%s-%s-" % (film_id, slug), "%s-%s-" % (film_id, short), 1))
    return urls


def download_poster(url: str, fetch) -> bytes | None:
    for candidate in poster_candidates(url):
        try:
            data = image_bytes(fetch(candidate))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
            data = None
        if data:
            return data
        time.sleep(0.2)
    return None


def cache_posters(entries: list[dict], poster_dir: Path, cache_path: Path, fetch) -> bool:
    cache = load_poster_cache(cache_path)
    changed = False
    jobs = []
    for entry in entries:
        slug = entry.get("slug") or ""
        url = entry.get("poster_url") or ""
        if not SLUG_RE.fullmatch(slug):
            continue
        filename = slug + ".jpg"
        destination = poster_dir / filename
        if destination.exists() and cache.get(filename) == url and url:
            entry["poster"] = "posters/" + filename
            continue
        if destination.exists() and not url:
            entry["poster"] = "posters/" + filename
            continue
        if url:
            jobs.append((entry, filename, destination, url))
    if not jobs:
        return False

    def pull(job):
        entry, filename, destination, url = job
        data = download_poster(url, fetch)
        return entry, filename, destination, url, data

    with ThreadPoolExecutor(max_workers=2) as pool:
        for entry, filename, destination, url, data in pool.map(pull, jobs):
            if not data:
                if destination.exists():
                    entry["poster"] = "posters/" + filename
                print("poster skipped: %s" % filename, file=sys.stderr)
                continue
            poster_dir.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(".jpg.tmp")
            temporary.write_bytes(data)
            os.replace(temporary, destination)
            cache[filename] = url
            entry["poster"] = "posters/" + filename
            changed = True
    if changed:
        text = json.dumps({"posters": cache}, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        write_if_changed(cache_path, text)
    return changed


def rss_as_films(rows: list[dict]) -> list[dict]:
    by_key = {}
    for row in rows:
        key = row.get("slug") or title_key(row.get("title") or "", row.get("year"))
        current = by_key.get(key)
        if current is None:
            by_key[key] = dict(row)
            continue
        newer = row if (row.get("last_watched") or "") >= (current.get("last_watched") or "") else current
        older = current if newer is row else row
        chosen = dict(newer)
        chosen["rewatch"] = True
        chosen["liked"] = bool(newer.get("liked") or older.get("liked"))
        if not chosen.get("poster_url"):
            chosen["poster_url"] = older.get("poster_url") or ""
        by_key[key] = chosen
    return list(by_key.values())


def reconcile(catalog: list[dict], films: list[dict]) -> dict:
    cat_entries = [entry for entry in (catalog_entry(item) for item in catalog) if entry]
    cat_by_key, cat_by_title = catalog_index(cat_entries)
    used = set()
    missing = []
    mismatches = []
    for film in films:
        key = match_key(film, cat_by_key, cat_by_title)
        site = cat_by_key.get(key) if key else None
        if site is None:
            missing.append({
                "title": film.get("title"),
                "year": film.get("year"),
                "rating": film.get("rating"),
                "watched_date": film.get("last_watched"),
                "letterboxd_url": film.get("link"),
            })
            continue
        used.add(id(site))
        rating_differs = (
            site.get("rating") is not None
            and film.get("rating") is not None
            and site.get("rating") != film.get("rating")
        )
        date_differs = (
            site.get("last_watched")
            and film.get("last_watched")
            and site.get("last_watched") != film.get("last_watched")
        )
        if rating_differs or date_differs:
            mismatches.append({
                "title": film.get("title") or site.get("title"),
                "year": film.get("year") if film.get("year") is not None else site.get("year"),
                "site_rating": site.get("rating"),
                "letterboxd_rating": film.get("rating"),
                "site_watched": site.get("last_watched"),
                "letterboxd_watched": film.get("last_watched"),
                "letterboxd_url": film.get("link"),
            })
    site_only = []
    for entry in cat_entries:
        if id(entry) in used:
            continue
        site_only.append({
            "title": entry.get("title"),
            "year": entry.get("year"),
            "rating": entry.get("rating"),
            "watched_date": entry.get("last_watched"),
        })
    missing.sort(key=lambda item: ((item.get("title") or "").casefold(), item.get("year") or 0))
    site_only.sort(key=lambda item: ((item.get("title") or "").casefold(), item.get("year") or 0))
    mismatches.sort(key=lambda item: ((item.get("title") or "").casefold(), item.get("year") or 0))
    return {
        "letterboxd_not_on_site": missing,
        "site_not_on_letterboxd": site_only,
        "mismatches": mismatches,
    }


def export_artifacts(films: list[dict], report: dict, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for film in sort_entries([dict(film) for film in films]):
        rows.append({
            "title": film.get("title") or "",
            "year": film.get("year"),
            "rating": film.get("rating"),
            "watched_date": film.get("last_watched"),
            "liked": bool(film.get("liked")),
            "rewatch": bool(film.get("rewatch")),
            "letterboxd_url": film.get("link") or "",
        })
    (directory / "letterboxd-full.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with (directory / "letterboxd-full.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["title", "year", "rating", "watched date", "liked", "rewatch", "letterboxd url"])
        for row in rows:
            writer.writerow([
                row["title"],
                "" if row["year"] is None else row["year"],
                "" if row["rating"] is None else row["rating"],
                row["watched_date"] or "",
                "true" if row["liked"] else "false",
                "true" if row["rewatch"] else "false",
                row["letterboxd_url"],
            ])
    (directory / "letterboxd-reconciliation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_pages(directory: Path):
    diary = []
    films = []
    paths = sorted(directory.glob("*.html"))

    def page_number(path: Path) -> int:
        match = re.search(r"page_(\d+)", path.name)
        return int(match.group(1)) if match else 1

    diary_paths = []
    film_paths = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "Just a moment" in text[:500]:
            continue
        if "diary-entry-row" in text:
            diary_paths.append((page_number(path), text))
        elif 'class="griditem"' in text:
            film_paths.append((page_number(path), text))
    diary_paths.sort(key=lambda item: item[0])
    film_paths.sort(key=lambda item: item[0])
    return [text for _, text in diary_paths], [text for _, text in film_paths]


def apply_posters_and_sort(entries, poster_dir, cache_path, fetch, download: bool):
    if download:
        cache_posters(entries, poster_dir, cache_path, fetch_image)
    else:
        for entry in entries:
            slug = entry.get("slug") or ""
            filename = slug + ".jpg"
            if SLUG_RE.fullmatch(slug) and (poster_dir / filename).exists():
                entry["poster"] = "posters/" + filename
    return sort_entries(entries)


def update(root: Path, *, full: bool = False, pages_dir: str = "", artifacts: str = "", fetch=fetch_bytes, pause=time.sleep, download_posters: bool = True) -> int:
    library = root / "library"
    out_path = library / "letterboxd.json"
    catalog_path = library / "movies.json"
    poster_dir = library / "posters"
    cache_path = root / ".github" / "letterboxd-poster-cache.json"
    previous = load_json(out_path)
    catalog = load_json(catalog_path)
    if previous is None or catalog is None:
        print("library/letterboxd.json was left unchanged.")
        return 0

    letterboxd_films = None
    report_films = None
    if pages_dir or full:
        if pages_dir:
            diary_pages, film_pages = read_pages(Path(pages_dir))
        else:
            print("fetching letterboxd diary.")
            diary_pages = crawl_pages(DIARY_URL, fetch, pause)
            if diary_pages is None:
                return 0
            pause(PAUSE_SECONDS)
            print("fetching letterboxd films.")
            film_pages = crawl_pages(FILMS_URL, fetch, pause)
            if film_pages is None:
                return 0
        rss = load_rss(fetch)
        if rss is None:
            print("rss was skipped. pages still merge.")
            rss = []
        letterboxd_films = combine_letterboxd(diary_pages, film_pages, rss)
        if letterboxd_films is None:
            return 0
        report_films = letterboxd_films
    else:
        rss = load_rss(fetch)
        if rss is None:
            print("library/letterboxd.json was left unchanged.")
            return 0
        if not rss:
            print("letterboxd rss had no diary entries. library/letterboxd.json was left unchanged.")
            return 0
        fresh = rss_as_films(rss)
        # RSS rows come first so they win over the copy already in the file.
        # Films already saved, and not in this feed, are appended and kept.
        existing_internal = [entry for entry in (catalog_entry(item) for item in previous) if entry]
        prior_films = []
        for entry in existing_internal:
            if not entry.get("from_letterboxd"):
                continue
            prior_films.append({
                "title": entry["title"],
                "year": entry["year"],
                "slug": entry.get("slug") or "",
                "film_id": "",
                "rating": entry.get("rating"),
                "last_watched": entry.get("last_watched"),
                "liked": bool(entry.get("liked")),
                "rewatch": bool(entry.get("rewatch")),
                "link": entry.get("link") or "",
                "poster_url": "",
            })
        seen = {row.get("slug") for row in fresh if row.get("slug")}
        letterboxd_films = fresh + [film for film in prior_films if film["slug"] not in seen]
        report_films = None

    merged = merge_library(previous, catalog, letterboxd_films)
    apply_posters_and_sort(merged, poster_dir, cache_path, fetch, download_posters and bool(letterboxd_films))
    text = dumps(merged)
    wrote = write_if_changed(out_path, text)
    print("films: %s. wrote: %s." % (len(merged), "yes" if wrote else "no"))
    if report_films is not None and artifacts:
        report = reconcile(catalog, report_films)
        export_artifacts(report_films, report, Path(artifacts))
        print(
            "reconciliation: %s on letterboxd only, %s on the site only, %s mismatches."
            % (
                len(report["letterboxd_not_on_site"]),
                len(report["site_not_on_letterboxd"]),
                len(report["mismatches"]),
            )
        )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sync the library movies list from Letterboxd.")
    parser.add_argument("--full", action="store_true", help="Fetch the diary and films pages.")
    parser.add_argument("--pages-dir", default="", help="Read saved diary and films HTML instead of fetching pages.")
    parser.add_argument("--artifacts", default="", help="Write the full list and reconciliation into this directory.")
    parser.add_argument("--skip-posters", action="store_true", help="Do not download posters.")
    args = parser.parse_args(argv)
    try:
        return update(
            ROOT,
            full=args.full,
            pages_dir=args.pages_dir,
            artifacts=args.artifacts,
            download_posters=not args.skip_posters,
        )
    except Exception as exc:  # last resort: never take the site build down
        print("letterboxd sync failed: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        print("library/letterboxd.json was left unchanged.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
