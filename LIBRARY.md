# Library

Movies come from [`library/movies.json`](library/movies.json). Shows come from [`library/tv.json`](library/tv.json). The two files use the same fields. Finished books come from [`library/books.json`](library/books.json). Music is hand-edited in [`library/music.json`](library/music.json). Podcasts on `/library/` are still a heading only.

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

The committed samples are a few classics, two shows, and four finished books so the sections render before the first sync. The workflow below replaces the movie, tv, and book files from Notion. It does not touch `library/music.json`.

## Books

[`library/books.json`](library/books.json) is a JSON array. Each object uses these fields:

| field | type |
| --- | --- |
| `title` | string |
| `author` | string, or null |
| `tags` | array of strings |
| `takeaway` | string, or null |

`/library/` lists up to 10 books, in the order of the file. A row is the title, the author, and the takeaway when it is present. `see all books (N)` links to `/library/books/`, which lists every book and has a count and a search box. Search matches the title, author, tags, and takeaway.

The seed is Steve Jobs and Elon Musk by Walter Isaacson, Meditations by Marcus Aurelius, and Atomic Habits by James Clear. Those rows have no takeaway.

The sync writes only pages whose Status is Done. It orders them by the page `last_edited_time`, newest first, so the first 10 on `/library/` are the most recently edited finished books. To read and Reading stay out of the file.

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

It uses the official API and the `NOTION_TOKEN` repository secret. The script is [`scripts/sync_movies.py`](scripts/sync_movies.py). It follows Notion pagination until every page is read.

Movies and tv come from database `fb0aa94ce43d46bda4a4cfe87c98b02b` (`NOTION_DATABASE_ID` at the top of the workflow).

Finished books come from the Reading list database `4d5d72e04b7344f8906d5fbd1d18f5bd` (`NOTION_BOOKS_DATABASE_ID`). Both databases must be connected to the same Notion integration that owns `NOTION_TOKEN`. If the books database is not shared with that integration, the job logs that and leaves `library/books.json` unchanged. The movie and tv sync still runs.

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

Books use a separate set of properties. Only a page whose Status is Done is exported.

| Notion property | books.json field |
| --- | --- |
| Title | `title` |
| Author (text) | `author` |
| Status (select: To read, Reading, Done) | included only when the value is Done |
| Tags (multi-select) | `tags` |
| Takeaways (text) | `takeaway` when the text is not empty, otherwise null |

### Type

Add a select property named `Type`. Use `Movie` for films and `TV` for shows. A page with no Type, or a blank Type, is written to `library/movies.json`.

### How to write a review

Open the entry in Notion and add a heading at the bottom of the page. The heading text is `Review`. Any heading level works. A leading emoji or a trailing colon is fine (`Review:`, `📝 Review`).

Under that heading, write paragraphs or bullets. The sync keeps that text until the next heading, or until the page ends, and stores it as `takeaway`. A Review heading that is a toggle uses the text inside the toggle as well.

If the page has no Review heading, the sync uses the Review property when that property has text, then the Takeaway property.

The sync does not download every page body on every run. It stores the page id and `last_edited_time` in [`.github/notion-review-cache.json`](.github/notion-review-cache.json), which is committed with the library files and is not part of the public site. A later run fetches blocks only for pages edited since that timestamp. The first run, or a run with no cache, reads every page. Notion rate limits are retried.

The job commits `library/movies.json`, `library/tv.json`, `library/books.json`, and the review cache only when something changed. A push made with the workflow token does not start the Pages workflow by itself, so when there is a commit the same job starts **Deploy static content to Pages** on `main`.

If `NOTION_TOKEN` is missing, the job prints one line and exits successfully. The files are left as they are.

Setup:

1. Put the Notion integration token in the repository secret `NOTION_TOKEN`.
2. Share both databases with that same integration: the movies database and the Reading list database.
3. Keep the property names in the tables. Rating options are ★, ★★, ★★★, ★★★★, and ★★★★★. Type options are Movie and TV. Book Status options are To read, Reading, and Done.
4. Let GitHub Actions push to `main`. If `main` only accepts pull requests, the sync will fail when a file changes.
