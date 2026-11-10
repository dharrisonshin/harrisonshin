# Writing

Posts are plain HTML. There is no build step and no framework.

## Add a post

1. Copy [`writing/template.html`](writing/template.html) to `writing/your-slug/index.html`.
2. Set the title, the lowercase visible date, the `<time datetime="YYYY-MM-DD">`, the meta description, and the canonical / `og:url` (`https://harrisonshin.com/writing/your-slug/`). Remove `noindex` from the template.
3. Put the essay in `.prose`. Each paragraph is its own `<p>`. A line that is only a quotation can be a `<blockquote><p>…</p></blockquote>`. Keep the wording as written, including curly quotes and dashes.
4. Add the post to the top of the list in [`writing/index.html`](writing/index.html) so the newest date is first.
5. Add an `<item>` at the top of [`writing/feed.xml`](writing/feed.xml) with the same title, absolute `https://harrisonshin.com` link, and `pubDate`.

Paths inside a post stay relative (`../style.css`, `../sky.js`, `../../favicon.ico`) so the page works on the project site and on `harrisonshin.com`.

The Pages workflow uploads the repository root, which includes the `writing/` directory.
