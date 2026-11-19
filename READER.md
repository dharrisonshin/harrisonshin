# Reader

A curated RSS/Atom digest at [`/reader/`](reader/). It is meant to feel like a lighter Readwise Reader: one place for newsletters, blogs, and YouTube channels, with a daily digest view, unread filtering, and per-device read state. Anyone can open the page. There is no login.

## How it works

1. Edit [`reader/feeds.json`](reader/feeds.json) with the feeds you want.
2. [`scripts/fetch_reader_feeds.py`](scripts/fetch_reader_feeds.py) downloads those feeds and writes [`reader/items.json`](reader/items.json) (last 14 days).
3. A GitHub Action (`.github/workflows/reader-digest.yml`) runs that script every morning Pacific time, commits when the digest changes, and redeploys Pages.
4. [`reader/index.html`](reader/index.html) loads `items.json` in the browser. Mark-as-read is stored in `localStorage` on that phone, iPad, or laptop only.

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
| YouTube channel | `https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID` |
| This site | `https://harrisonshin.com/writing/feed.xml` |

For YouTube, set `"kind": "youtube"`. The digest shows a thumbnail; tap play to load an embedded `youtube-nocookie` player in place. Shorts and watch URLs both work. Find a channel id from the channel’s About page or from any video URL’s channel link (`/channel/UC…`).

Email-only newsletters need an RSS URL (Substack usually has one) or a bridge that turns mail into a feed. This reader does not ingest email directly.

After editing feeds, either wait for the morning Action or run it by hand:

```bash
python3 scripts/fetch_reader_feeds.py
```

On GitHub: **Actions → Refresh reader digest → Run workflow**.

## Phone and iPad

Open `https://harrisonshin.com/reader/` in Safari, then **Share → Add to Home Screen**. The page has a web app manifest and apple touch icon so it opens fullscreen. Read state stays on that device.

## Limits (vs Readwise Reader)

- Public RSS/Atom only — no email inbox, no paywalled full-text scraping.
- No highlights, annotations, or sync across devices.
- Digest refreshes on the Action schedule (and when you run the script), not continuously.
- Failed feeds are listed under `errors` in `items.json` and skipped until the next run.

Starter feeds in `feeds.json` are examples you can replace with your own list.
