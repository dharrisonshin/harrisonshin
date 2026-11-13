#!/usr/bin/env python3
"""Pull the Notion movies database into library/movies.json.

Reads NOTION_TOKEN and NOTION_DATABASE_ID from the environment.
If NOTION_TOKEN is missing, exits 0 without changing the file.
"""

import json
import os
import sys
import urllib.error
import urllib.request

NOTION_VERSION = "2022-06-28"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "library", "movies.json")
PAGE_SIZE = 100
MAX_PAGES = 50


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


def movie_from_page(page):
    props = page.get("properties") or {}
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
        "takeaway": as_text(props.get("Takeaway")),
    }


def sort_movies(movies):
    dated = [movie for movie in movies if movie["last_watched"]]
    undated = [movie for movie in movies if not movie["last_watched"]]
    dated.sort(key=lambda movie: movie["title"].casefold())
    dated.sort(key=lambda movie: movie["last_watched"], reverse=True)
    undated.sort(key=lambda movie: movie["title"].casefold())
    return dated + undated


def dumps(movies):
    return json.dumps(movies, indent=2, ensure_ascii=False) + "\n"


def notion_query(token, database_id, cursor):
    body = {"page_size": PAGE_SIZE}
    if cursor:
        body["start_cursor"] = cursor
    request = urllib.request.Request(
        "https://api.notion.com/v1/databases/%s/query" % database_id,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + token,
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:500]
        print("Notion query failed: HTTP %s %s" % (error.code, detail), file=sys.stderr)
        sys.exit(1)


def fetch_movies(token, database_id):
    movies = []
    pages = 0
    cursor = None
    raw_pages = 0
    while pages < MAX_PAGES:
        payload = notion_query(token, database_id, cursor)
        results = payload.get("results") or []
        raw_pages += len(results)
        for page in results:
            movie = movie_from_page(page)
            if movie:
                movies.append(movie)
        pages += 1
        if not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")
        if not cursor:
            break
    else:
        print("Notion query stopped after %s pages." % MAX_PAGES, file=sys.stderr)
        sys.exit(1)
    if raw_pages and not movies:
        print("Notion returned pages, but none had a Title. movies.json was left unchanged.", file=sys.stderr)
        sys.exit(1)
    return sort_movies(movies)


def main():
    token = (os.environ.get("NOTION_TOKEN") or "").strip()
    if not token:
        print("NOTION_TOKEN is not set. skipping.")
        return 0
    database_id = (os.environ.get("NOTION_DATABASE_ID") or "").strip()
    if not database_id:
        print("NOTION_DATABASE_ID is not set.", file=sys.stderr)
        return 1
    movies = fetch_movies(token, database_id)
    text = dumps(movies)
    previous = ""
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as handle:
            previous = handle.read()
    if text == previous:
        print("library/movies.json already matches Notion (%s films)." % len(movies))
        return 0
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write(text)
    print("wrote library/movies.json (%s films)." % len(movies))
    return 0


if __name__ == "__main__":
    sys.exit(main())
