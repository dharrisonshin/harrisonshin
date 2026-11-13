#!/usr/bin/env python3
"""Pull Notion into library/movies.json, library/tv.json, and library/books.json.

Reads NOTION_TOKEN and NOTION_DATABASE_ID from the environment.
If NOTION_TOKEN is missing, exits 0 without changing the files.

A review is the text under a heading named Review on the Notion page.
Page bodies are cached by last_edited_time in .github/notion-review-cache.json
so unchanged pages are not fetched again.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

NOTION_VERSION = "2022-06-28"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOVIES_OUT = os.path.join(ROOT, "library", "movies.json")
TV_OUT = os.path.join(ROOT, "library", "tv.json")
BOOKS_OUT = os.path.join(ROOT, "library", "books.json")
CACHE_OUT = os.path.join(ROOT, ".github", "notion-review-cache.json")
PAGE_SIZE = 100
MAX_PAGES = 50
BLOCK_PAUSE = 0.35
TV_NAMES = {"tv", "television"}


def plain(rich):
    if not rich:
        return ""
    return "".join(part.get("plain_text", "") for part in rich).strip()


def as_text(prop):
    if not prop:
        return None
    kind = prop.get("type")
    if kind == "rich_text":
        return plain(prop.get("rich_text")) or None
    if kind == "title":
        return plain(prop.get("title")) or None
    if kind == "select":
        selected = prop.get("select") or {}
        return (selected.get("name") or "").strip() or None
    if kind == "number" and prop.get("number") is not None:
        return str(prop.get("number"))
    return None


def as_year(prop):
    if not prop:
        return None
    if prop.get("type") == "number" and prop.get("number") is not None:
        number = prop["number"]
        if isinstance(number, bool):
            return None
        if isinstance(number, (int, float)):
            whole = int(number)
            if whole == number:
                return whole
        return None
    text = as_text(prop)
    if text and text.isdigit():
        return int(text)
    return None


def as_stars(prop):
    if not prop or prop.get("type") != "select" or not prop.get("select"):
        return None
    name = prop["select"].get("name") or ""
    count = name.count("★")
    if count <= 0:
        return None
    return min(5, count)


def as_date(prop):
    if not prop or prop.get("type") != "date" or not prop.get("date"):
        return None
    start = prop["date"].get("start") or ""
    if len(start) >= 10 and start[4] == "-" and start[7] == "-":
        return start[:10]
    return None


def as_genres(prop):
    if not prop or prop.get("type") != "multi_select":
        return []
    names = []
    for option in prop.get("multi_select") or []:
        name = (option.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def as_takeaway(props):
    if "Review" in props:
        review = as_text(props.get("Review"))
        if review:
            return review
    return as_text(props.get("Takeaway"))


def as_kind(props):
    if "Type" not in props:
        return "movie"
    name = (as_text(props.get("Type")) or "").casefold()
    if name in TV_NAMES:
        return "tv"
    return "movie"


def normalize_heading(text):
    text = (text or "").strip().rstrip(":").strip()
    text = re.sub(r"^[^\w]+|[^\w]+$", "", text, flags=re.UNICODE).strip()
    return text.rstrip(":").strip().casefold()


def is_heading(block):
    return block.get("type") in ("heading_1", "heading_2", "heading_3")


def heading_text(block):
    kind = block.get("type")
    return plain((block.get(kind) or {}).get("rich_text"))


def block_text(block):
    kind = block.get("type")
    if kind == "paragraph":
        return plain((block.get("paragraph") or {}).get("rich_text")), "p"
    if kind == "bulleted_list_item":
        text = plain((block.get("bulleted_list_item") or {}).get("rich_text"))
        return (("• " + text) if text else ""), "li"
    if kind == "numbered_list_item":
        return plain((block.get("numbered_list_item") or {}).get("rich_text")), "li"
    return None, None


def section_text(blocks):
    parts = []
    prev = None
    for block in blocks:
        text, kind = block_text(block)
        if not text:
            continue
        if not parts:
            parts.append(text)
        elif kind == "li" or prev == "li":
            parts.append("\n" + text)
        else:
            parts.append("\n\n" + text)
        prev = kind
    return "".join(parts)


def extract_review(blocks, children_of=None):
    """Return (found, text). text is empty when the heading has no body."""
    for index, block in enumerate(blocks):
        if not is_heading(block):
            continue
        if normalize_heading(heading_text(block)) != "review":
            continue
        body = []
        if block.get("has_children") and children_of and block.get("id"):
            body.extend(children_of(block["id"]) or [])
        for later in blocks[index + 1:]:
            if is_heading(later):
                break
            body.append(later)
        return True, section_text(body)
    return False, ""


def resolve_takeaway(props, found, text):
    if found:
        return text or None
    return as_takeaway(props)


def entry_from_props(props, takeaway):
    title = as_text(props.get("Title"))
    if not title:
        return None
    return {
        "title": title,
        "year": as_year(props.get("Year")),
        "director": as_text(props.get("Director")),
        "genres": as_genres(props.get("Genre")),
        "rating": as_stars(props.get("Rating")),
        "last_watched": as_date(props.get("Last Watched")),
        "takeaway": takeaway,
    }


def sort_entries(entries):
    dated = [entry for entry in entries if entry["last_watched"]]
    undated = [entry for entry in entries if not entry["last_watched"]]
    dated.sort(key=lambda entry: entry["title"].casefold())
    dated.sort(key=lambda entry: entry["last_watched"], reverse=True)
    undated.sort(key=lambda entry: entry["title"].casefold())
    return dated + undated


def dumps(entries):
    return json.dumps(entries, indent=2, ensure_ascii=False) + "\n"


def dumps_cache(pages):
    return json.dumps({"pages": pages}, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def load_cache(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        print("review cache could not be read. fetching page bodies again.")
        return {}
    pages = data.get("pages") if isinstance(data, dict) else None
    return pages if isinstance(pages, dict) else {}


def lookup_cache(cache, page):
    entry = cache.get(page.get("id") or "")
    if not isinstance(entry, dict):
        return None
    if entry.get("last_edited_time") != page.get("last_edited_time"):
        return None
    return bool(entry.get("has_review")), entry.get("review") or ""


def remember(cache, page, found, text):
    page_id = page.get("id")
    if not page_id:
        return
    cache[page_id] = {
        "last_edited_time": page.get("last_edited_time"),
        "has_review": bool(found),
        "review": text or "",
    }


class NotionAccessError(Exception):
    def __init__(self, code):
        self.code = code


def notion(token, url, body=None, soft_access=False):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": "Bearer " + token,
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        method="GET" if body is None else "POST",
    )
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:500]
            if soft_access and error.code in (403, 404):
                raise NotionAccessError(error.code)
            if error.code == 429 and attempt < 5:
                retry = error.headers.get("Retry-After") if error.headers else None
                try:
                    wait = float(retry) if retry else 1.0
                except ValueError:
                    wait = 1.0
                time.sleep(min(max(wait, 0.5), 30))
                continue
            print("Notion request failed: HTTP %s %s" % (error.code, detail), file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as error:
            print("Notion request failed: %s" % error.reason, file=sys.stderr)
            sys.exit(1)
    print("Notion request failed after retries.", file=sys.stderr)
    sys.exit(1)


def query_database(token, database_id, soft_access=False):
    pages = []
    cursor = None
    calls = 0
    while calls < MAX_PAGES:
        body = {"page_size": PAGE_SIZE}
        if cursor:
            body["start_cursor"] = cursor
        payload = notion(
            token,
            "https://api.notion.com/v1/databases/%s/query" % database_id,
            body,
            soft_access=soft_access,
        )
        pages.extend(payload.get("results") or [])
        calls += 1
        if not payload.get("has_more"):
            return pages
        cursor = payload.get("next_cursor")
        if not cursor:
            return pages
    print("Notion query stopped after %s pages." % MAX_PAGES, file=sys.stderr)
    sys.exit(1)


def fetch_block_children(token, block_id):
    blocks = []
    cursor = None
    calls = 0
    while calls < MAX_PAGES:
        url = "https://api.notion.com/v1/blocks/%s/children?page_size=%s" % (block_id, PAGE_SIZE)
        if cursor:
            url += "&start_cursor=" + urllib.parse.quote(cursor)
        payload = notion(token, url)
        blocks.extend(payload.get("results") or [])
        calls += 1
        if not payload.get("has_more"):
            return blocks
        cursor = payload.get("next_cursor")
        if not cursor:
            return blocks
        time.sleep(BLOCK_PAUSE)
    print("Notion block list stopped after %s pages." % MAX_PAGES, file=sys.stderr)
    sys.exit(1)


def review_for_page(token, page, cache):
    cached = lookup_cache(cache, page)
    if cached is not None:
        return cached

    def children_of(block_id):
        blocks = fetch_block_children(token, block_id)
        time.sleep(BLOCK_PAUSE)
        return blocks

    blocks = fetch_block_children(token, page["id"])
    time.sleep(BLOCK_PAUSE)
    found, text = extract_review(blocks, children_of)
    remember(cache, page, found, text)
    return found, text


def collect(token, database_id, cache):
    try:
        raw_pages = query_database(token, database_id, soft_access=True)
    except NotionAccessError as error:
        print(
            "Movies database %s is not shared with the Notion integration (HTTP %s). library/movies.json and library/tv.json were left unchanged."
            % (database_id, error.code)
        )
        return None
    movies = []
    shows = []
    titled = 0
    fetched = 0
    kept = {}
    for page in raw_pages:
        props = page.get("properties") or {}
        if not as_text(props.get("Title")):
            continue
        titled += 1
        before = lookup_cache(cache, page) is not None
        found, text = review_for_page(token, page, cache)
        if not before:
            fetched += 1
        entry = entry_from_props(props, resolve_takeaway(props, found, text))
        if not entry:
            continue
        page_id = page.get("id")
        if page_id and page_id in cache:
            kept[page_id] = cache[page_id]
        if as_kind(props) == "tv":
            shows.append(entry)
        else:
            movies.append(entry)
    if raw_pages and not titled:
        print("Notion returned pages, but none had a Title. files were left unchanged.", file=sys.stderr)
        sys.exit(1)
    cache.clear()
    cache.update(kept)
    print("fetched review text for %s of %s pages." % (fetched, titled))
    return sort_entries(movies), sort_entries(shows)


def book_from_page(page):
    props = page.get("properties") or {}
    status = (as_text(props.get("Status")) or "").casefold()
    if status != "done":
        return None
    title = as_text(props.get("Title"))
    if not title:
        return None
    return {
        "title": title,
        "author": as_text(props.get("Author")),
        "tags": as_genres(props.get("Tags")),
        "takeaway": as_text(props.get("Takeaways")),
        "_edited": page.get("last_edited_time") or "",
    }


def sort_books(books):
    books.sort(key=lambda book: book["title"].casefold())
    books.sort(key=lambda book: book.get("_edited") or "", reverse=True)
    for book in books:
        book.pop("_edited", None)
    return books


def collect_books(token, database_id):
    try:
        raw_pages = query_database(token, database_id, soft_access=True)
    except NotionAccessError as error:
        print(
            "Books database %s is not shared with the Notion integration (HTTP %s). library/books.json was left unchanged."
            % (database_id, error.code)
        )
        return None
    books = []
    for page in raw_pages:
        book = book_from_page(page)
        if book:
            books.append(book)
    return sort_books(books)


def write_if_changed(path, text):
    previous = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            previous = handle.read()
    if text == previous:
        return False
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return True


def main():
    token = (os.environ.get("NOTION_TOKEN") or "").strip()
    if not token:
        print("NOTION_TOKEN is not set. skipping.")
        return 0
    database_id = (os.environ.get("NOTION_DATABASE_ID") or "").strip()
    if not database_id:
        print("NOTION_DATABASE_ID is not set.", file=sys.stderr)
        return 1
    cache = load_cache(CACHE_OUT)
    changed = False
    listed = collect(token, database_id, cache)
    if listed is not None:
        movies, shows = listed
        changed |= write_if_changed(MOVIES_OUT, dumps(movies))
        changed |= write_if_changed(TV_OUT, dumps(shows))
        changed |= write_if_changed(CACHE_OUT, dumps_cache(cache))
        print("movies: %s. shows: %s." % (len(movies), len(shows)))
    books_id = (os.environ.get("NOTION_BOOKS_DATABASE_ID") or "").strip()
    if not books_id:
        print("NOTION_BOOKS_DATABASE_ID is not set. library/books.json was left unchanged.")
    else:
        books = collect_books(token, books_id)
        if books is not None:
            changed |= write_if_changed(BOOKS_OUT, dumps(books))
            print("books: %s." % len(books))
    if changed:
        print("updated library files.")
    else:
        print("library files already match Notion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
