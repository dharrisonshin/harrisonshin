# Library

Movies and tv come from [`library/movies.json`](library/movies.json). Both pages read that same file. Books and podcasts on `/library/` are still headings only.

## movies.json

The file is a JSON array. Each object uses these fields:

| field | type |
| --- | --- |
| `title` | string |
| `year` | number, or null |
| `director` | string, or null |
| `genres` | array of strings |
| `rating` | number from 0 to 5, or null |
| `last_watched` | `YYYY-MM-DD`, or null |
| `takeaway` | string, or null |

`/library/` shows a recently watched list: the 10 films with a `last_watched` date, newest first. Each row is the title, the year, stars when there is a rating, the date, and the takeaway when it is present. A blank takeaway is left off the row. Under the list, `see all films (N)` links to `/library/movies/`. `N` is every film in the file.

`/library/movies/` lists every film. It groups by the year of `last_watched`, newest year first. Entries with no date go under `earlier`, sorted by title. A rating renders as stars. A takeaway renders only when it is present. The count and the search box are computed in the browser from this file. Search matches the title, year, director, genres, and takeaway.

The committed sample is a few classics so the page renders before the first sync. The workflow below replaces that file from Notion.

## Notion sync

[`.github/workflows/notion-sync.yml`](.github/workflows/notion-sync.yml) runs every 15 minutes and when started by hand. The job runs only on `main`. It does not run from a pull request branch.

It queries Notion database `fb0aa94ce43d46bda4a4cfe87c98b02b` with the official API and the `NOTION_TOKEN` repository secret. That database id is the `NOTION_DATABASE_ID` variable at the top of the workflow. The script is [`scripts/sync_movies.py`](scripts/sync_movies.py). It follows Notion pagination until every page is read.

| Notion property | movies.json field |
| --- | --- |
| Title | `title` |
| Year | `year` |
| Director | `director` |
| Genre (multi-select) | `genres` |
| Rating (select, ★ through ★★★★★) | `rating`, the number of stars |
| Last Watched (date) | `last_watched` |
| Review (rich text, optional) | `takeaway` when Review has text |
| Takeaway, if Review is missing or blank | `takeaway`, or null when that is blank too |

The job commits `library/movies.json` to `main` only when the file contents changed. A push made with the workflow token does not start the Pages workflow by itself, so when there is a commit the same job starts **Deploy static content to Pages** on `main`.

If `NOTION_TOKEN` is missing, the job prints one line and exits successfully. The file is left as it is.

Setup:

1. Put the Notion integration token in the repository secret `NOTION_TOKEN`.
2. Share the movies database with that integration.
3. Keep the property names in the table. Rating options are ★, ★★, ★★★, ★★★★, and ★★★★★.
4. Let GitHub Actions push to `main`. If `main` only accepts pull requests, the sync will fail when the file changes.
