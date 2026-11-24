# harrison shin

Personal site for Harrison Shin: seeker, builder, stoic, documenting his journey in Irvine, CA. A starfield homepage (bio, link pills, a current-status caption, a Spotify playlist, and ko-fi / base support chips) plus a plain-HTML writing section. Inter is loaded from Google Fonts.

## Status

The caption under the pills is loaded from [`status.json`](status.json) on each visit. `text` is the status. Optional `attribution` is shown in italics after the status text, with a space before it (for example `- runaway by beach house`). If `attribution` is missing or blank, nothing extra is shown. Optional `image` is a site-root relative path to a `gif`, `png`, `jpg`, `jpeg`, or `webp` under the repo (for example `status/media/weird-shit.gif`). Put the file in the repo first, then set `image`. Invalid or missing paths hide only the media. `updated` is an ISO 8601 timestamp with a timezone offset, shown in Pacific Time (`updated nov 9, 10:42 pm pt`). If the file is missing or `text` is empty, the caption stays hidden. A missing or invalid `updated` hides only the timestamp line. A `previous updates` link under that line goes to [`/status/`](status/).

To change the caption, edit `status.json` (and add any new media file) and push to `main`. You do not edit the history by hand. A GitHub Action archives the previous caption into [`status-history.json`](status-history.json) after each change, including `image` when it was set. [`/status/`](status/) shows the current caption first, then the archived ones newest first, 10 per page. The page has prev, the page number, and next.

The playlist at the lower left is the compact Spotify embed. On wide screens it sits in the corner; below 1260px it lifts above the support links so they stay clear; below 700px it collapses to a round button that loads the player on first open.

## Deploy

The site is the repository root (`index.html`, `CNAME`, `404.html`, `status.json`, `status-history.json`, `about/`, `projects/`, `writing/`, `library/`, `reader/`, `links/`, `status/` including `status/media/`, favicons, and `og-image.png`). There is no build step. `.nojekyll` is included so GitHub Pages skips Jekyll and publishes the files as they are. The Pages workflow uploads that root (excluding `.git` and `.github`), so those folders ship with the site. See [WRITING.md](WRITING.md) to add a post, a project, or a link, [LIBRARY.md](LIBRARY.md) for movies, and [READER.md](READER.md) for the curated RSS digest. The about page there is marked as a draft.

`CNAME` contains `harrisonshin.com`. GitHub Pages serves the custom domain from that file. Unknown paths use `404.html`. The project URL redirects to the custom domain:

https://dharrisonshin.github.io/harrisonshin/

Image and icon URLs in the page are relative, so the same files work before that redirect. Open Graph tags stay on absolute `https://harrisonshin.com` URLs.
