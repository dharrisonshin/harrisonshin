# Writing

Posts are plain HTML. There is no build step and no framework.

## Add a post

1. Copy [`writing/template.html`](writing/template.html) to `writing/your-slug/index.html`.
2. Set the title, the lowercase visible date, the `<time datetime="YYYY-MM-DD">`, the meta description, and the canonical / `og:url` (`https://harrisonshin.com/writing/your-slug/`). Remove `noindex` from the template.
3. Put the essay in `.prose`. Each paragraph is its own `<p>`. A line that is only a quotation can be a `<blockquote><p>…</p></blockquote>`. Keep the wording as written, including curly quotes and dashes.
4. Add the post to the top of the list in [`writing/index.html`](writing/index.html) so the newest date is first.
5. Add the same post to the top of `POSTS` in [`writing/posts.js`](writing/posts.js) (`slug`, `title`, `date`). Newest first. Each post page reads that list for the newer/older links at the bottom. With only one neighbor missing, that side stays blank. With no neighbors, the nav stays hidden.
6. Add an `<item>` at the top of [`writing/feed.xml`](writing/feed.xml) with the same title, absolute `https://harrisonshin.com` link, and `pubDate`.

The template already includes the “all writing” link at the top and “back to writing” in the footer.

Paths inside a post stay relative (`../../read.css`, `../../read-sky.js`, `../../favicon.ico`) so the page works on the project site and on `harrisonshin.com`.

The Pages workflow uploads the repository root, which includes `writing/`, `about/`, `projects/`, `library/`, and `links/`.

## About (draft)

[`about/index.html`](about/index.html) is a **draft**. Harrison will edit this copy. Do not treat the wording as final.

## Projects

Add a project by copying an `<li>` in [`projects/index.html`](projects/index.html). Each entry is a name, one or two sentences, and an outbound link (`target="_blank"` and `rel="noopener noreferrer"`). The name voidrunnerz stays lowercase.

## Library

[`library/index.html`](library/index.html) is a shelf for books, movies & tv, and podcasts. It is under construction: headings only, no entries yet.

Add a real entry under the right heading, inside a year group. Newest year first.

```html
<h3>2026</h3>
<ul class="log">
  <li>
    <p class="what">Title <span class="who">Creator</span></p>
    <p class="take">One takeaway.</p>
  </li>
</ul>
```

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
