(function () {
  var nav = document.querySelector("[data-post-nav]");
  if (!nav || typeof POSTS === "undefined") return;
  var parts = location.pathname.split("/").filter(Boolean);
  var slug = parts[parts.length - 1];
  if (slug === "index.html" && parts.length > 1) slug = parts[parts.length - 2];
  var i = -1;
  for (var n = 0; n < POSTS.length; n++) {
    if (POSTS[n].slug === slug) { i = n; break; }
  }
  if (i < 0) return;
  var newer = i > 0 ? POSTS[i - 1] : null;
  var older = i < POSTS.length - 1 ? POSTS[i + 1] : null;
  if (!newer && !older) return;

  function link(post, label, cls) {
    var a = document.createElement("a");
    a.className = cls;
    a.href = "../" + post.slug + "/";
    var dir = document.createElement("span");
    dir.className = "dir";
    dir.textContent = label;
    var title = document.createElement("span");
    title.className = "ttl";
    title.textContent = post.title;
    a.appendChild(dir);
    a.appendChild(title);
    return a;
  }

  if (newer) nav.appendChild(link(newer, "newer", "newer"));
  if (older) nav.appendChild(link(older, "older", "older"));
  nav.hidden = false;
})();
