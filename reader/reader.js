(function () {
  var STORAGE_KEY = "harrisonshin.reader.readIds.v1";
  var root = document.getElementById("reader-root");
  var metaEl = document.getElementById("reader-meta");
  var kindsEl = document.getElementById("reader-kinds");
  var loadingEl = document.getElementById("reader-loading");
  if (!root) return;

  var state = {
    view: "digest",
    kind: "all",
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

  function youtubePlayerHtml(item) {
    var id = youtubeVideoId(item);
    if (!id) return "";
    var title = item.title || "YouTube video";
    return (
      '<div class="reader-yt" data-youtube-id="' +
      escapeHtml(id) +
      '">' +
      '<button type="button" class="reader-yt-play" aria-label="Play ' +
      escapeHtml(title) +
      '">' +
      '<img class="reader-yt-thumb" src="https://i.ytimg.com/vi/' +
      escapeHtml(id) +
      '/hqdefault.jpg" alt="" loading="lazy" width="480" height="360">' +
      '<span class="reader-yt-icon" aria-hidden="true"></span>' +
      "</button>" +
      "</div>"
    );
  }

  function visibleItems() {
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
    var href = item.url || "#";
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
      '<a class="reader-title" href="' +
      escapeHtml(href) +
      '" target="_blank" rel="noopener noreferrer">' +
      escapeHtml(item.title || "untitled") +
      "</a>" +
      youtubePlayerHtml(item) +
      summary +
      "</div>" +
      '<button type="button" class="reader-mark" data-mark="' +
      escapeHtml(item.id) +
      '" aria-pressed="' +
      (read ? "true" : "false") +
      '" aria-label="' +
      (read ? "Mark unread" : "Mark read") +
      '">' +
      (read ? "unread" : "read") +
      "</button>" +
      "</li>"
    );
  }

  function mountYoutubePlayer(shell) {
    var id = shell.getAttribute("data-youtube-id");
    if (!id || !/^[A-Za-z0-9_-]{11}$/.test(id)) return;
    var iframe = document.createElement("iframe");
    iframe.className = "reader-yt-frame";
    iframe.src =
      "https://www.youtube-nocookie.com/embed/" +
      encodeURIComponent(id) +
      "?autoplay=1&rel=0";
    iframe.title = "YouTube video";
    iframe.setAttribute("allowfullscreen", "");
    iframe.setAttribute(
      "allow",
      "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
    );
    iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    iframe.loading = "lazy";
    shell.innerHTML = "";
    shell.appendChild(iframe);
    shell.classList.add("is-playing");
  }

  function render() {
    renderKinds();
    renderMeta();

    var items = visibleItems();
    if (!items.length) {
      var empty =
        state.view === "digest"
          ? "Nothing in today’s digest yet. Feeds refresh once a day. Try unread or all."
          : state.view === "unread"
            ? "You’re caught up."
            : "No items yet. Add feeds in reader/feeds.json and run the fetch workflow.";
      root.innerHTML = '<p class="note">' + escapeHtml(empty) + "</p>";
      return;
    }

    var groups = groupByDay(items);
    var html = "";
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
    root.innerHTML = html;
  }

  function setView(view) {
    state.view = view;
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
    render();
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
    var mark = event.target.closest("[data-mark]");
    if (mark) {
      var id = mark.getAttribute("data-mark");
      markRead(id, !isRead(id));
      render();
      return;
    }
    var play = event.target.closest(".reader-yt-play");
    if (play) {
      event.preventDefault();
      var shell = play.closest(".reader-yt");
      var row = play.closest(".reader-item");
      if (shell) mountYoutubePlayer(shell);
      if (row) {
        markRead(row.getAttribute("data-id"), true);
        row.classList.add("is-read");
        var markBtn = row.querySelector("[data-mark]");
        if (markBtn) {
          markBtn.setAttribute("aria-pressed", "true");
          markBtn.setAttribute("aria-label", "Mark unread");
          markBtn.textContent = "unread";
        }
        renderMeta();
      }
      return;
    }
    var title = event.target.closest(".reader-title");
    if (title) {
      var item = title.closest(".reader-item");
      if (item) {
        markRead(item.getAttribute("data-id"), true);
        // Let the link open; refresh styles after a tick so navigation still happens.
        setTimeout(render, 0);
      }
    }
  });

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
      render();
    })
    .catch(function () {
      root.innerHTML =
        '<p class="note">Could not load the digest. Run <code>python3 scripts/fetch_reader_feeds.py</code> or wait for the daily GitHub Action.</p>';
    });
})();
