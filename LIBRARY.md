# Library

Movies come from [`library/movies.json`](library/movies.json). Shows come from [`library/tv.json`](library/tv.json). The two files use the same fields. Music is hand-edited in [`library/music.json`](library/music.json). Books and podcasts on `/library/` are still headings only.

Books, movies, tv, music, and podcasts on `/library/` are collapsible. Each section is a `details` element and starts open.

## JSON files

Each file is a JSON array. Each object uses these fields:

| field | type |
| --- | --- |
| `title` | string |
| `year` | number, or null |
| `director` | string, or null. For a show, this is whoever is in the Director property, usually the creator. |
| `genres` | array of strings |
| `rating` | number from 0 to 5, or null |
| `last_watched` | `YYYY-MM-DD`, or null |
| `takeaway` | string, or null. This is the review. |

`/library/` shows a recently watched list for movies and another for tv. Each list is the 10 entries with a `last_watched` date, newest first. A row is the title, the year, stars when there is a rating, the date, and the review when it is present. A blank review is left off the row. Under the movies list, `see all films (N)` links to `/library/movies/`. Under the tv list, `see all shows (N)` links to `/library/tv/`.

`/library/movies/` lists every film. `/library/tv/` lists every show. Each page groups by the year of `last_watched`, newest year first. Entries with no date go under `earlier`, sorted by title. The count and the search box are computed in the browser. Search matches the title, year, director, genres, and review.

The committed samples are a few classics and two shows so the sections render before the first sync. The workflow below replaces both files from Notion. It does not touch `library/music.json`.

## Music

[`library/music.json`](library/music.json) is a JSON array. Edit the file by hand. There is no Notion sync for music yet. The page sorts by artist, ignoring a leading "The", and the file is kept in that same order.

| field | type |
| --- | --- |
| `artist` | string |
| `album` | string, or null |
| `year` | number, or null |
| `rating` | number from 0 to 5, or null |
| `note` | string, or null |
| `link` | `http` or `https` URL, or null |

A row shows the artist. An album or a year is added when it is set. A rating renders as stars. A note renders only when it is present. A link makes the artist name open that URL. On a wide line the names sit in two columns. An entry with an album, a rating, or a note spans the full width. The list starts with Alvvays, Beach House, Lord Huron, and Lo Moon, plus the artists added later. Optional fields on those rows are empty.

## Notion sync

[`.github/workflows/notion-sync.yml`](.github/workflows/notion-sync.yml) runs every 15 minutes and when started by hand. The job runs only on `main`. It does not run from a pull request branch.

It queries Notion database `fb0aa94ce43d46bda4a4cfe87c98b02b` with the official API and the `NOTION_TOKEN` repository secret. That database id is the `NOTION_DATABASE_ID` variable at the top of the workflow. The script is [`scripts/sync_movies.py`](scripts/sync_movies.py). It follows Notion pagination until every page is read.

| Notion property | JSON field |
| --- | --- |
| Title | `title` |
| Year | `year` |
| Director | `director` |
| Genre (multi-select) | `genres` |
| Rating (select, ★ through ★★★★★) | `rating`, the number of stars |
| Last Watched (date) | `last_watched` |
| Type (select) | chooses the file. `TV` or `Television` is a show. Missing, blank, or `Movie` is a film. |
| Review heading on the page | `takeaway` |
| Review property, if there is no Review heading | `takeaway` when that property has text |
| Takeaway, if both of the above are missing or blank | `takeaway`, or null when that is blank too |

### Type

Add a select property named `Type`. Use `Movie` for films and `TV` for shows. A page with no Type, or a blank Type, is written to `library/movies.json`.

### How to write a review

Open the entry in Notion and add a heading at the bottom of the page. The heading text is `Review`. Any heading level works. A leading emoji or a trailing colon is fine (`Review:`, `📝 Review`).

Under that heading, write paragraphs or bullets. The sync keeps that text until the next heading, or until the page ends, and stores it as `takeaway`. A Review heading that is a toggle uses the text inside the toggle as well.

If the page has no Review heading, the sync uses the Review property when that property has text, then the Takeaway property.

The sync does not download every page body on every run. It stores the page id and `last_edited_time` in [`.github/notion-review-cache.json`](.github/notion-review-cache.json), which is committed with the library files and is not part of the public site. A later run fetches blocks only for pages edited since that timestamp. The first run, or a run with no cache, reads every page. Notion rate limits are retried.

The job commits `library/movies.json`, `library/tv.json`, and the review cache only when something changed. A push made with the workflow token does not start the Pages workflow by itself, so when there is a commit the same job starts **Deploy static content to Pages** on `main`.

If `NOTION_TOKEN` is missing, the job prints one line and exits successfully. The files are left as they are.

Setup:

1. Put the Notion integration token in the repository secret `NOTION_TOKEN`.
2. Share the movies database with that integration.
3. Keep the property names in the table. Rating options are ★, ★★, ★★★, ★★★★, and ★★★★★. Type options are Movie and TV.
4. Let GitHub Actions push to `main`. If `main` only accepts pull requests, the sync will fail when a file changes.
