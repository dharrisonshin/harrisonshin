# Reader

A curated RSS/Atom digest at [`/reader/`](reader/). The page heading is feed. It is meant to feel like a lighter Readwise Reader: one place for newsletters, blogs, and YouTube channels, with a daily digest view, an all view of 10 items per page, unread filtering, and per-device read state. Anyone can open the page. There is no login.

## How it works

1. Edit [`reader/feeds.json`](reader/feeds.json) with the feeds you want.
2. [`scripts/fetch_reader_feeds.py`](scripts/fetch_reader_feeds.py) downloads those feeds and writes [`reader/items.json`](reader/items.json) (last 14 days).
3. A GitHub Action (`.github/workflows/reader-digest.yml`) runs that script every hour, commits when the digest or the OPML changes, and redeploys Pages.
4. [`reader/index.html`](reader/index.html) loads `items.json` in the browser. Opening an item stays on the page: videos play in an embedded player, and articles show sanitized full text from the feed or, when the feed only has a short blurb, text extracted from the public page during the refresh. Each item has an open-original link. Mark-as-read is stored in `localStorage` on that phone, iPad, or laptop only. Back returns to the same list page and scroll position.

## Add a feed

Append an object to the `feeds` array in `reader/feeds.json`:

```json
{
  "id": "unique-slug",
  "title": "Display name",
  "url": "https://example.com/feed.xml",
  "kind": "blog"
}
```

`kind` is one of: `blog`, `newsletter`, `youtube`, `podcast`, `other`. The reader uses it for filter chips.

Useful feed URL patterns:

| Source | URL pattern |
| --- | --- |
| Most blogs | Look for `/feed`, `/rss`, or `/atom.xml` |
| Substack | `https://name.substack.com/feed` |
| YouTube (full videos only) | `https://www.youtube.com/feeds/videos.xml?playlist_id=UULF…` |
| This site | `https://harrisonshin.com/writing/feed.xml` |

For YouTube, set `"kind": "youtube"`. The digest shows a thumbnail; tap play to load an embedded `youtube-nocookie` player in place. Only full-length videos are shown. Shorts are never shown.

YouTube feeds must use the long-form uploads playlist (`UULF`), never the channel feed. The channel feed (`?channel_id=UC…`) mixes in Shorts. To add a channel:

1. Copy the channel id (`UC` plus 22 characters) from the channel’s About page or from `/channel/UC…` on any video.
2. Replace the leading `UC` with `UULF`.
3. Set the feed URL to `https://www.youtube.com/feeds/videos.xml?playlist_id=UULF…`.

Example: channel `UC3V0rBqEbyeBCFB7NDkV1XQ` (Base) uses playlist `UULF3V0rBqEbyeBCFB7NDkV1XQ`.

The fetch script drops any RSS or Atom item whose link, guid, or url contains `/shorts/`. The page hides those items as well, so a Short cannot appear in the digest.

Email-only newsletters need a public RSS URL (Substack usually has one) or a private bridge. This reader does not ingest email directly. Private bridge addresses stay out of the repo. See below.

After editing feeds, either wait for the next hourly Action or run it by hand:

```bash
python3 scripts/fetch_reader_feeds.py
```

On GitHub: **Actions → Refresh reader digest → Run workflow**.

## Private newsletter bridges

A feed whose address should not be public uses `url_secret` instead of `url`. The value is the name of an environment variable, not the address itself.

```json
{
  "id": "five-bullet-friday",
  "title": "Tim Ferriss' Five Bullet Friday",
  "url_secret": "FIVE_BULLET_FRIDAY_FEED_URL",
  "kind": "newsletter"
}
```

Five Bullet Friday reads the secret named `FIVE_BULLET_FRIDAY_FEED_URL`.

1. Open the repository on GitHub, then **Settings → Secrets and variables → Actions → New repository secret**.
2. Set the name to `FIVE_BULLET_FRIDAY_FEED_URL`.
3. Paste the private feed address as the value. It is not stored in git.
4. The workflow `.github/workflows/reader-digest.yml` already passes that secret into the fetch script. A local run can use the same variable name in the environment. Do not commit the address.

If the variable is unset, the script skips that feed and continues. An empty Atom feed (no entries yet) is a successful fetch, not an error.

Items from a private feed do not keep the bridge address, per-message links, or raw email HTML. Each item stores the title, the date, and a short plain-text excerpt. Five Bullet Friday links to [the public archive](https://tim.blog/5-bullet-friday/), or to the matching public post on tim.blog when the script can find one.

To add another private bridge:

1. Append a feed with its own `url_secret`, for example `SOME_LETTER_FEED_URL`.
2. Pass that secret in `.github/workflows/reader-digest.yml` the same way, as an `env` entry on the fetch step.
3. Create the Actions secret under that exact name.
4. Optional `url` on the same object is the public page readers should open. When it is set alongside `url_secret`, the script fetches the secret address and stores `url` on each item.

## OPML export

[`reader/feeds.opml`](reader/feeds.opml) is a public OPML 2.0 file at `/reader/feeds.opml`. Import it into another RSS app. The fetch script rewrites it from `feeds.json` on every run, and the hourly Action commits it when the list changes.

Feeds that use `url_secret` are left out. Private addresses never appear in the file.

The all view lists 10 items per page, with previous, next, and page numbers. Digest and unread stay a single list: digest is one day, and unread is whatever is still open.

## Phone and iPad

Open `https://harrisonshin.com/reader/` in Safari, then **Share → Add to Home Screen**. The page has a web app manifest and apple touch icon so it opens fullscreen. Read state stays on that device.

## Limits (vs Readwise Reader)

- Public RSS/Atom, plus private feeds whose address lives in an Actions secret. No paywalled full-text scraping.
- No highlights, annotations, or sync across devices.
- The digest refreshes hourly (and when you run the script), not continuously.
- Failed feeds are listed under `errors` in `items.json` and skipped until the next run.

The list in `feeds.json` is the set of feeds this reader follows.
