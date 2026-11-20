(function () {
  var STORAGE_KEY = "harrisonshin.reader.readIds.v1";
  var root = document.getElementById("reader-root");
  var metaEl = document.getElementById("reader-meta");
  var kindsEl = document.getElementById("reader-kinds");
  var loadingEl = document.getElementById("reader-loading");
  if (!root) return;

  var PAGE_SIZE = 10;

  var state = {
    view: "digest",
    kind: "all",
    page: 1,
    items: [],
    readIds: loadReadIds(),
    updated: null,
    updatedPacific: null,
  };

  function loadReadIds() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (err) {
      return {};
    }
  }

  function saveReadIds() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.readIds));
    } catch (err) {
      /* private mode / full storage — ignore */
    }
  }

  function isRead(id) {
    return !!state.readIds[id];
  }

  function markRead(id, value) {
    if (value) state.readIds[id] = true;
    else delete state.readIds[id];
    saveReadIds();
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function parseDate(value) {
    if (!value) return null;
    var d = new Date(value);
    return isNaN(d.getTime()) ? null : d;
  }

  function pacificParts(date) {
    var parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Los_Angeles",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      weekday: "short",
      hour: "numeric",
      minute: "2-digit",
    }).formatToParts(date);
    var map = {};
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].type !== "literal") map[parts[i].type] = parts[i].value;
    }
    return map;
  }

  function dayKey(date) {
    var p = pacificParts(date);
    return p.year + "-" + p.month + "-" + p.day;
  }

  function todayKey() {
    return dayKey(new Date());
  }

  function formatDayHeading(key) {
    if (key === todayKey()) return "today";
    var yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    if (key === dayKey(yesterday)) return "yesterday";
    var bits = key.split("-");
    var d = new Date(Date.UTC(Number(bits[0]), Number(bits[1]) - 1, Number(bits[2]), 12));
    return new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Los_Angeles",
      weekday: "short",
      month: "short",
      day: "numeric",
    }).format(d).toLowerCase();
  }

  function formatTime(date) {
    var p = pacificParts(date);
    return (p.hour + ":" + p.minute + " " + (p.dayPeriod || "")).trim().toLowerCase();
  }

  function kindLabel(kind) {
    return kind || "other";
  }

  // Full-length videos only. A Short stays hidden even if it is still in items.json.
  function isYoutubeShort(item) {
    if (!item) return false;
    var fields = [item.url, item.link, item.guid];
    for (var i = 0; i < fields.length; i++) {
      if (fields[i] && String(fields[i]).indexOf("/shorts/") !== -1) return true;
    }
    return false;
  }

  function youtubeVideoId(item) {
    if (isYoutubeShort(item)) return null;
    if (item.videoId && /^[A-Za-z0-9_-]{11}$/.test(item.videoId)) {
      return item.videoId;
    }
    var url = item.url || "";
    var match = url.match(
      /(?:youtube\.com\/(?:watch\?(?:[^#]*&)?v=|embed\/|v\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/
    );
    return match ? match[1] : null;
  }

  function itemHash(id) {
    return "#item-" + encodeURIComponent(id);
  }

  function itemIdFromHash() {
    var hash = location.hash || "";
    if (hash.indexOf("#item-") !== 0) return null;
    try {
      return decodeURIComponent(hash.slice(6));
    } catch (err) {
      return null;
    }
  }

  function findItem(id) {
    for (var i = 0; i < state.items.length; i++) {
      if (state.items[i].id === id) return state.items[i];
    }
    return null;
  }

  function youtubeThumbHtml(item) {
    var id = youtubeVideoId(item);
    if (!id) return "";
    var title = item.title || "YouTube video";
    return (
      '<a class="reader-open reader-yt-play" href="' +
      itemHash(item.id) +
      '" aria-label="Watch ' +
      escapeHtml(title) +
      '">' +
      '<img class="reader-yt-thumb" src="https://i.ytimg.com/vi/' +
      escapeHtml(id) +
      '/hqdefault.jpg" alt="" loading="lazy" width="480" height="360">' +
      '<span class="reader-yt-icon" aria-hidden="true"></span>' +
      "</a>"
    );
  }

  function readingHtml(item) {
    var html = item.contentHtml || "";
    if (!html) return "";
    if (/<\s*script|javascript:|on\w+\s*=/i.test(html)) return "";
    return html;
  }

  function matchedItems() {
    var list = state.items.filter(function (item) {
      return !isYoutubeShort(item);
    });
    if (state.kind !== "all") {
      list = list.filter(function (item) {
        return item.kind === state.kind;
      });
    }
    if (state.view === "unread") {
      list = list.filter(function (item) {
        return !isRead(item.id);
      });
    } else if (state.view === "digest") {
      var today = todayKey();
      var todays = list.filter(function (item) {
        var d = parseDate(item.published);
        return d && dayKey(d) === today;
      });
      if (todays.length) {
        list = todays;
      } else {
        // Quiet day: show the newest calendar day that has items.
        var newestKey = null;
        for (var i = 0; i < list.length; i++) {
          var pd = parseDate(list[i].published);
          if (!pd) continue;
          newestKey = dayKey(pd);
          break;
        }
        if (newestKey) {
          list = list.filter(function (item) {
            var d = parseDate(item.published);
            return d && dayKey(d) === newestKey;
          });
        } else {
          list = [];
        }
      }
    }
    return list;
  }

  function pageWindow(list) {
    if (state.view !== "all") {
      return { items: list, page: 1, pages: 1 };
    }
    var pages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
    if (state.page > pages) state.page = pages;
    if (state.page < 1) state.page = 1;
    var start = (state.page - 1) * PAGE_SIZE;
    return {
      items: list.slice(start, start + PAGE_SIZE),
      page: state.page,
      pages: pages,
    };
  }

  function visibleItems() {
    return pageWindow(matchedItems()).items;
  }

  function groupByDay(items) {
    var groups = [];
    var map = {};
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var d = parseDate(item.published);
      var key = d ? dayKey(d) : "unknown";
      if (!map[key]) {
        map[key] = { key: key, items: [] };
        groups.push(map[key]);
      }
      map[key].items.push(item);
    }
    return groups;
  }

  function uniqueKinds(items) {
    var seen = {};
    var out = [];
    for (var i = 0; i < items.length; i++) {
      var kind = items[i].kind || "other";
      if (!seen[kind]) {
        seen[kind] = true;
        out.push(kind);
      }
    }
    out.sort();
    return out;
  }

  function renderKinds() {
    if (!kindsEl) return;
    var kinds = uniqueKinds(state.items);
    var html = '<button type="button" class="reader-chip' +
      (state.kind === "all" ? " is-active" : "") +
      '" data-kind="all" aria-pressed="' +
      (state.kind === "all" ? "true" : "false") +
      '">all kinds</button>';
    for (var i = 0; i < kinds.length; i++) {
      var kind = kinds[i];
      var active = state.kind === kind;
      html +=
        '<button type="button" class="reader-chip' +
        (active ? " is-active" : "") +
        '" data-kind="' +
        escapeHtml(kind) +
        '" aria-pressed="' +
        (active ? "true" : "false") +
        '">' +
        escapeHtml(kindLabel(kind)) +
        "</button>";
    }
    kindsEl.innerHTML = html;
  }

  function renderMeta() {
    if (!metaEl) return;
    var unread = 0;
    for (var i = 0; i < state.items.length; i++) {
      if (!isRead(state.items[i].id)) unread += 1;
    }
    var parts = [];
    if (state.updatedPacific) {
      parts.push("updated " + state.updatedPacific.toLowerCase());
    } else if (state.updated) {
      var d = parseDate(state.updated);
      if (d) {
        var p = pacificParts(d);
        parts.push(
          "updated " +
            p.month +
            "/" +
            p.day +
            " " +
            formatTime(d) +
            " pt"
        );
      }
    }
    parts.push(state.items.length + " items · " + unread + " unread");
    metaEl.hidden = false;
    metaEl.textContent = parts.join(" · ");
  }

  function itemHtml(item) {
    var d = parseDate(item.published);
    var read = isRead(item.id);
    var time = d ? formatTime(d) : "";
    var hasPlayer = !!youtubeVideoId(item);
    var summary = item.summary
      ? '<p class="reader-summary">' + escapeHtml(item.summary) + "</p>"
      : "";
    return (
      '<li class="reader-item' +
      (read ? " is-read" : "") +
      (hasPlayer ? " has-video" : "") +
      '" data-id="' +
      escapeHtml(item.id) +
      '">' +
      '<div class="reader-item-main">' +
      '<p class="reader-source"><span class="reader-kind">' +
      escapeHtml(kindLabel(item.kind)) +
      "</span> · " +
      escapeHtml(item.feedTitle || item.feedId || "") +
      (time ? " · <time datetime=\"" + escapeHtml(item.published || "") + "\">" + escapeHtml(time) + "</time>" : "") +
      "</p>" +
      '<a class="reader-title reader-open" href="' +
      itemHash(item.id) +
      '">' +
      escapeHtml(item.title || "untitled") +
      "</a>" +
      (hasPlayer ? '<div class="reader-yt">' + youtubeThumbHtml(item) + "</div>" : "") +
      summary +
      "</div>" +
      '<button type="button" class="reader-mark" data-mark="' +
      escapeHtml(item.id) +
      '" aria-pressed="' +
      (read ? "true" : "false") +
      '" aria-label="' +
      (read ? "mark as unread" : "mark as read") +
      '">' +
      (read ? "mark as unread" : "mark as read") +
      "</button>" +
      "</li>"
    );
  }

  function setReadingChrome(reading) {
    var nodes = document.querySelectorAll(".reader-head, .reader-toolbar, .reader-actions");
    for (var i = 0; i < nodes.length; i++) nodes[i].hidden = reading;
  }

  function watchHtml(item) {
    var id = youtubeVideoId(item);
    if (!id) return "";
    return (
      '<div class="reader-watch"><iframe src="https://www.youtube-nocookie.com/embed/' +
      encodeURIComponent(id) +
      '?rel=0" title="' +
      escapeHtml(item.title || "YouTube video") +
      '" allowfullscreen allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin"></iframe></div>'
    );
  }

  function renderItem(item) {
    setReadingChrome(true);
    if (!item) {
      root.innerHTML =
        '<article class="reader-piece"><button type="button" class="reader-back">back</button><p class="note">That item is not in this digest.</p></article>';
      return;
    }
    var d = parseDate(item.published);
    var time = d ? formatTime(d) : "";
    var author = item.author
      ? '<p class="reader-byline">' + escapeHtml(item.author) + "</p>"
      : "";
    var body = readingHtml(item);
    var prose = body
      ? '<div class="reader-prose">' + body + "</div>"
      : item.summary
        ? '<p class="reader-kicker">excerpt</p><div class="reader-prose"><p>' +
          escapeHtml(item.summary) +
          "</p></div>"
        : "";
    var original = item.url
      ? '<p class="reader-original"><a href="' +
        escapeHtml(item.url) +
        '" target="_blank" rel="noopener noreferrer">open original</a></p>'
      : "";
    root.innerHTML =
      '<article class="reader-piece">' +
      '<button type="button" class="reader-back">back</button>' +
      '<p class="reader-source"><span class="reader-kind">' +
      escapeHtml(kindLabel(item.kind)) +
      "</span> · " +
      escapeHtml(item.feedTitle || item.feedId || "") +
      (time ? " · <time datetime=\"" + escapeHtml(item.published || "") + "\">" + escapeHtml(time) + "</time>" : "") +
      "</p>" +
      "<h1>" +
      escapeHtml(item.title || "untitled") +
      "</h1>" +
      author +
      watchHtml(item) +
      prose +
      original +
      "</article>";
    window.scrollTo(0, 0);
  }

  function showFromHash() {
    var id = itemIdFromHash();
    state.itemId = id;
    if (id) {
      markRead(id, true);
      renderItem(findItem(id));
      return;
    }
    render();
    var y = state.listScroll || 0;
    requestAnimationFrame(function () {
      window.scrollTo(0, y);
    });
  }

  function paginationHtml(page, pages) {
    if (state.view !== "all" || pages < 2) return "";
    var html = '<nav class="reader-pages" aria-label="Pages">';
    html +=
      '<button type="button" class="reader-chip" data-page="prev"' +
      (page <= 1 ? " disabled" : "") +
      ">prev</button>";
    for (var n = 1; n <= pages; n++) {
      var active = n === page;
      html +=
        '<button type="button" class="reader-chip' +
        (active ? " is-active" : "") +
        '" data-page="' +
        n +
        '"' +
        (active ? ' aria-current="page"' : "") +
        ">" +
        n +
        "</button>";
    }
    html +=
      '<button type="button" class="reader-chip" data-page="next"' +
      (page >= pages ? " disabled" : "") +
      ">next</button>";
    html += "</nav>";
    return html;
  }

  function render() {
    if (itemIdFromHash()) {
      renderItem(findItem(itemIdFromHash()));
      return;
    }
    setReadingChrome(false);
    renderKinds();
    renderMeta();

    var matched = matchedItems();
    if (!matched.length) {
      var empty =
        state.view === "digest"
          ? "Nothing in today’s digest yet. Feeds refresh every hour. Try unread or all."
          : state.view === "unread"
            ? "You’re caught up."
            : "No items yet. Add feeds in reader/feeds.json and run the fetch workflow.";
      root.innerHTML = '<p class="note">' + escapeHtml(empty) + "</p>";
      return;
    }

    var paging = pageWindow(matched);
    var items = paging.items;
    var pager = paginationHtml(paging.page, paging.pages);
    var groups = groupByDay(items);
    var html = pager;
    for (var g = 0; g < groups.length; g++) {
      var group = groups[g];
      html +=
        '<section class="reader-day">' +
        "<h2>" +
        escapeHtml(group.key === "unknown" ? "undated" : formatDayHeading(group.key)) +
        ' <span class="reader-count">' +
        group.items.length +
        "</span></h2>" +
        '<ul class="reader-list">';
      for (var i = 0; i < group.items.length; i++) {
        html += itemHtml(group.items[i]);
      }
      html += "</ul></section>";
    }
    html += pager;
    root.innerHTML = html;
  }

  function setView(view) {
    state.view = view;
    state.page = 1;
    if (itemIdFromHash()) location.hash = "";
    var buttons = document.querySelectorAll(".reader-views [data-view]");
    for (var i = 0; i < buttons.length; i++) {
      var active = buttons[i].getAttribute("data-view") === view;
      buttons[i].classList.toggle("is-active", active);
      buttons[i].setAttribute("aria-pressed", active ? "true" : "false");
    }
    render();
  }

  function setKind(kind) {
    state.kind = kind;
    state.page = 1;
    render();
  }

  function setPage(next) {
    var pages = Math.max(1, Math.ceil(matchedItems().length / PAGE_SIZE));
    var page = next;
    if (page < 1) page = 1;
    if (page > pages) page = pages;
    if (page === state.page) return;
    state.page = page;
    render();
    var toolbar = document.querySelector(".reader-toolbar");
    if (toolbar && toolbar.scrollIntoView) {
      toolbar.scrollIntoView({ block: "start" });
    }
  }

  document.querySelector(".reader-views").addEventListener("click", function (event) {
    var btn = event.target.closest("[data-view]");
    if (!btn) return;
    setView(btn.getAttribute("data-view"));
  });

  if (kindsEl) {
    kindsEl.addEventListener("click", function (event) {
      var btn = event.target.closest("[data-kind]");
      if (!btn) return;
      setKind(btn.getAttribute("data-kind"));
    });
  }

  root.addEventListener("click", function (event) {
    var pageBtn = event.target.closest("[data-page]");
    if (pageBtn) {
      if (pageBtn.disabled) return;
      var spec = pageBtn.getAttribute("data-page");
      if (spec === "prev") setPage(state.page - 1);
      else if (spec === "next") setPage(state.page + 1);
      else setPage(parseInt(spec, 10) || 1);
      return;
    }
    var mark = event.target.closest("[data-mark]");
    if (mark) {
      var id = mark.getAttribute("data-mark");
      markRead(id, !isRead(id));
      render();
      return;
    }
    var back = event.target.closest(".reader-back");
    if (back) {
      if (history.length > 1) history.back();
      else location.hash = "";
      return;
    }
    var opener = event.target.closest("a.reader-open");
    if (opener) {
      state.listScroll = window.scrollY;
      var row = opener.closest(".reader-item");
      if (row) markRead(row.getAttribute("data-id"), true);
    }
  });

  window.addEventListener("hashchange", showFromHash);

  var markVisible = document.getElementById("mark-visible-read");
  if (markVisible) {
    markVisible.addEventListener("click", function () {
      var items = visibleItems();
      for (var i = 0; i < items.length; i++) markRead(items[i].id, true);
      render();
    });
  }

  var reset = document.getElementById("mark-all-unread");
  if (reset) {
    reset.addEventListener("click", function () {
      state.readIds = {};
      saveReadIds();
      render();
    });
  }

  fetch("items.json", { cache: "no-store" })
    .then(function (res) {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();
    })
    .then(function (data) {
      var loaded = Array.isArray(data.items) ? data.items : [];
      state.items = loaded.filter(function (item) {
        return !isYoutubeShort(item);
      });
      state.updated = data.updated || null;
      state.updatedPacific = data.updatedPacific || null;
      if (loadingEl) loadingEl.remove();
      if (itemIdFromHash()) showFromHash();
      else render();
    })
    .catch(function () {
      root.innerHTML =
        '<p class="note">Could not load the digest. Run <code>python3 scripts/fetch_reader_feeds.py</code> or wait for the hourly GitHub Action.</p>';
    });
})();
