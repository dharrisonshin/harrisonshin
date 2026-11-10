# harrison shin

Personal site for Harrison Shin — seeker, builder, stoic, documenting his journey in Irvine, CA. A starfield homepage (bio, link pills, a current-status caption, a Spotify playlist, and ko-fi / base support chips) plus a plain-HTML writing section. Inter is loaded from Google Fonts.

## Status

The caption under the pills is loaded from [`status.json`](status.json) on each visit. `text` is the status. Optional `attribution` is shown in italics after the status text, with a space before it (for example `- runaway by beach house`). If `attribution` is missing or blank, nothing extra is shown. `updated` is an ISO 8601 timestamp with a timezone offset, shown in Pacific Time (`updated nov 9, 10:42 pm pt`). If the file is missing or `text` is empty, the caption stays hidden. A missing or invalid `updated` hides only the second line.

The playlist at the lower left is the compact Spotify embed. On wide screens it sits in the corner; below 1260px it lifts above the support links so they stay clear; below 700px it collapses to a round button that loads the player on first open.

## Deploy

The site is the repository root (`index.html`, `status.json`, `about/`, `projects/`, `writing/`, `library/`, `links/`, favicons, and `og-image.png`). There is no build step. `.nojekyll` is included so GitHub Pages skips Jekyll and publishes the files as they are. The Pages workflow uploads that root (excluding `.git` and `.github`), so those folders ship with the site. See [WRITING.md](WRITING.md) to add a post, a library entry, or a link. The about page there is marked as a draft.

Image and icon URLs in the page are relative, so the same files work on the project site:

https://dharrisonshin.github.io/harrisonshin/

Open Graph tags stay on absolute `https://harrisonshin.com` URLs. This repo has no `CNAME`; add one only after `harrisonshin.com` is pointed at GitHub Pages.
