# Writing

Posts are plain HTML. There is no build step and no framework.

## Add a post

1. Copy [`writing/template.html`](writing/template.html) to `writing/your-slug/index.html`.
2. Set the title, the lowercase visible date, the `<time datetime="YYYY-MM-DD">`, the meta description, and the canonical / `og:url` (`https://harrisonshin.com/writing/your-slug/`). Remove `noindex` from the template.
3. Put the essay in `.prose`. Each paragraph is its own `<p>`. A line that is only a quotation can be a `<blockquote><p>…</p></blockquote>`. Keep the wording as written, including curly quotes and dashes.
4. Add the post to the top of the list in [`writing/index.html`](writing/index.html) so the newest date is first. Under the title, add a `.post-tags` row. Each tag is a link to `tags/<slug>/`.
5. Add the same post to the top of `POSTS` in [`writing/posts.js`](writing/posts.js) (`slug`, `title`, `date`, a one-sentence `teaser`, and `tags`). Newest first. `tags` is 1–3 labels from the fixed set below. Each post page reads that list for the newer/older links at the bottom. With only one neighbor missing, that side stays blank. With no neighbors, the nav stays hidden. The homepage shows the first entry under the status line: title, date, teaser, and a read link. A long teaser is one line and ends in an ellipsis. If `teaser` is missing, that line stays hidden. `excerpt` is accepted as another name for the same field. Optional `substack` is the URL of that essay on [harrisonshin.substack.com](https://harrisonshin.substack.com). When it is set, put an `also on substack` link to that URL in `.post-foot`, before “back to writing”. When it is absent, leave that link off. The template’s `.signup` form stays on every post.
6. On the post page, under the date, add the same `.post-tags` row. Each tag links to `../tags/<slug>/`.
7. If this is the first post to use a tag, add that tag’s page and filter link. See [Tags](#tags).
8. Add an `<item>` at the top of [`writing/feed.xml`](writing/feed.xml) with the same title, absolute `https://harrisonshin.com` link, and `pubDate`.

## Tags

The tag set is fixed. Use the label in prose and in `tags`. The slug is the label with spaces replaced by hyphens.

| label | slug |
| --- | --- |
| grad school | `grad-school` |
| building | `building` |
| games | `games` |
| stoicism | `stoicism` |
| higher ed | `higher-ed` |
| tech | `tech` |
| life | `life` |

Each post has 1–3 tags. A tag with no posts does not appear in the filter row and does not get a page.

`/writing/` has a filter row: `all`, then every tag that has at least one post, in the order of the table above. `all` links to `/writing/` and is marked `aria-current="page"` there. Each tag links to `/writing/tags/<slug>/`. The row is plain HTML, so it works without JavaScript.

A tag page lives at `writing/tags/<slug>/index.html`. It lists that tag’s posts, newest first, with the same pills, the same filter row (the current tag marked `aria-current="page"`), and an “all writing” link back to `/writing/`.

When a tag is used for the first time:

1. Copy an existing page in `writing/tags/` to `writing/tags/<slug>/index.html`.
2. Set the title, the heading, the description, and the canonical / `og:url` (`https://harrisonshin.com/writing/tags/<slug>/`).
3. Move `aria-current="page"` to that tag in the filter row. List only posts with that tag, newest first. Pill links on that page are `../<slug>/`. Post links are `../../<post-slug>/`. The “all writing” link is `../../`.
4. Add the new tag to the filter row on [`writing/index.html`](writing/index.html) and on every tag page, in the table order above.

The template already includes the “all writing” link at the top and “back to writing” in the footer.

Paths inside a post stay relative (`../../read.css`, `../../read-sky.js`, `../../favicon.ico`) so the page works on the project site and on `harrisonshin.com`.

The Pages workflow uploads the repository root, which includes `writing/`, `about/`, `projects/`, `library/`, and `links/`.

## About (draft)

[`about/index.html`](about/index.html) is a **draft**. Harrison will edit this copy. Do not treat the wording as final.

## Projects

Add a project by copying an `<li>` in [`projects/index.html`](projects/index.html). Each entry is a name, a status (`building` or `live`), one or two sentences, an outbound link (`target="_blank"` and `rel="noopener noreferrer"`), and a screenshot. The name voidrunnerz stays lowercase. If there is no image yet, use an empty `.shot-empty` slot.

## Library

Books and podcasts on [`library/index.html`](library/index.html) are still headings only. The shelf sections collapse, and they start open. Movies come from [`library/movies.json`](library/movies.json) and shows from [`library/tv.json`](library/tv.json): a short recently watched list on `/library/`, and the full lists at [`library/movies/`](library/movies/index.html) and [`library/tv/`](library/tv/index.html). See [LIBRARY.md](LIBRARY.md) for the schema and the Notion sync. Do not hand-edit those rows.

## Links

[`links/index.html`](links/index.html) is under construction: tools, everyday, and inspiration, with no entries yet.

Add a real entry under the right heading.

```html
<ul class="log">
  <li>
    <a href="https://example.com/" target="_blank" rel="noopener noreferrer">Name</a>
    <p class="take">Why it earns a place here.</p>
  </li>
</ul>
```
