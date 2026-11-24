(function () {
  var RECENT = 10;
  var MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

  function plural(kind, n) {
    var word = kind === "show" ? "show" : "film";
    return n === 1 ? word : word + "s";
  }

  function pluralWord(kind) {
    return kind === "show" ? "shows" : "films";
  }

  function isDate(date) {
    return typeof date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(date);
  }

  function yearOf(date) {
    return isDate(date) ? date.slice(0, 4) : "earlier";
  }

  function formatDate(date) {
    var month = Number(date.slice(5, 7));
    var day = Number(date.slice(8, 10));
    if (month < 1 || month > 12 || day < 1 || day > 31) return date;
    return MONTHS[month - 1] + " " + day + ", " + date.slice(0, 4);
  }

  function haystack(item) {
    var bits = [item.title, item.year, item.director, item.takeaway];
    if (Array.isArray(item.genres)) bits = bits.concat(item.genres);
    return bits
      .filter(function (v) { return v !== null && v !== undefined && v !== ""; })
      .join(" ")
      .toLowerCase();
  }

  function starValue(n) {
    if (typeof n !== "number" || !isFinite(n) || n < 0 || n > 5) return null;
    return Math.round(n * 2) / 2;
  }

  function stars(n) {
    var halves = Math.round(n * 2);
    var full = Math.floor(halves / 2);
    var half = halves % 2 === 1;
    var empty = 5 - full - (half ? 1 : 0);
    var p = document.createElement("p");
    p.className = "stars";
    var label = document.createElement("span");
    label.className = "sr";
    label.textContent = (halves % 2 ? String(halves / 2) : String(full)) + " of 5 stars";
    var visual = document.createElement("span");
    visual.setAttribute("aria-hidden", "true");
    var on = document.createElement("span");
    on.className = "on";
    on.textContent = "★★★★★".slice(0, full) + (half ? "½" : "");
    visual.appendChild(on);
    if (empty > 0) visual.appendChild(document.createTextNode("☆☆☆☆☆".slice(0, empty)));
    p.appendChild(label);
    p.appendChild(visual);
    return p;
  }

  function addStars(parent, item) {
    var n = starValue(item.rating);
    if (n !== null) parent.appendChild(stars(n));
  }

  function addTake(parent, item) {
    if (typeof item.takeaway === "string" && item.takeaway.trim()) {
      var take = document.createElement("p");
      take.className = "take";
      take.textContent = item.takeaway.trim();
      parent.appendChild(take);
    }
  }

  function addMeta(parent, item, withDate) {
    var bits = [];
    if (withDate && isDate(item.last_watched)) bits.push(formatDate(item.last_watched));
    if (item.liked === true) bits.push("liked");
    if (item.rewatch === true) bits.push("rewatch");
    if (!bits.length) return;
    var when = document.createElement("p");
    when.className = "when";
    when.textContent = bits.join(" · ");
    parent.appendChild(when);
  }

  function isHttp(value) {
    return typeof value === "string" && /^https?:\/\//i.test(value.trim());
  }

  function titleNode(item) {
    if (!isHttp(item.link)) return document.createTextNode(item.title);
    var a = document.createElement("a");
    a.href = item.link.trim();
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = item.title;
    return a;
  }

  function whatLine(item, withDirector) {
    var what = document.createElement("p");
    what.className = "what";
    what.appendChild(titleNode(item));
    var bits = [];
    if (typeof item.year === "number") bits.push(String(item.year));
    if (withDirector && item.director) bits.push(item.director);
    if (bits.length) {
      var who = document.createElement("span");
      who.className = "who";
      who.textContent = " " + bits.join(" · ");
      what.appendChild(who);
    }
    return what;
  }

  function posterUrl(root, item) {
    var poster = typeof item.poster === "string" ? item.poster.trim() : "";
    if (!poster || poster.indexOf("..") !== -1) return "";
    if (isHttp(poster)) return poster;
    var src = root.getAttribute("data-src") || "";
    var slash = src.lastIndexOf("/");
    var prefix = slash >= 0 ? src.slice(0, slash + 1) : "";
    return prefix + poster.replace(/^\//, "");
  }

  function fill(li, item, withDirector, withDate, root) {
    var parent = li;
    var src = posterUrl(root, item);
    if (src) {
      parent = document.createElement("div");
      parent.className = "film-copy";
      var img = document.createElement("img");
      img.className = "poster";
      img.src = src;
      img.alt = "";
      img.width = 56;
      img.height = 84;
      img.loading = "lazy";
      img.decoding = "async";
      img.addEventListener("error", function () {
        img.remove();
        li.classList.remove("with-poster");
      });
      li.classList.add("with-poster");
      li.appendChild(img);
      li.appendChild(parent);
    }
    parent.appendChild(whatLine(item, withDirector));
    addStars(parent, item);
    addMeta(parent, item, withDate);
    addTake(parent, item);
  }

  function recentEntry(item, root) {
    var li = document.createElement("li");
    fill(li, item, false, true, root);
    return li;
  }

  function entry(item, root, withDate) {
    var li = document.createElement("li");
    fill(li, item, true, withDate, root);
    return li;
  }

  function emptyNote(text) {
    var p = document.createElement("p");
    p.className = "empty";
    p.textContent = text;
    return p;
  }

  function byTitle(a, b) {
    return String(a.title).localeCompare(String(b.title));
  }

  function byWatched(a, b) {
    var ad = isDate(a.last_watched) ? a.last_watched : "";
    var bd = isDate(b.last_watched) ? b.last_watched : "";
    if (ad === bd) return 0;
    return bd.localeCompare(ad);
  }

  function recentLimit(root) {
    var raw = parseInt(root.getAttribute("data-limit"), 10);
    if (!raw || raw < 1) return RECENT;
    return raw;
  }

  function mount(root) {
    var mode = root.getAttribute("data-mode") || "all";
    var src = root.getAttribute("data-src");
    var kind = root.getAttribute("data-kind") === "show" ? "show" : "film";
    var newest = root.getAttribute("data-order") === "newest";
    var scope = root.closest(".shelf") || document;
    var countEl = scope.querySelector("[data-count]");
    var input = scope.querySelector("[data-search]");
    var allLink = root.getAttribute("data-all")
      ? document.getElementById(root.getAttribute("data-all"))
      : null;
    var items = [];
    var word = pluralWord(kind);

    function renderRecent() {
      var dated = items.filter(function (item) { return isDate(item.last_watched); });
      dated.sort(byTitle);
      dated.sort(byWatched);
      var shown = dated.slice(0, recentLimit(root));
      root.textContent = "";
      if (!shown.length) {
        root.appendChild(emptyNote(items.length ? "nothing watched yet." : "no " + word + " yet."));
        return;
      }
      var ul = document.createElement("ul");
      ul.className = "log";
      shown.forEach(function (item) { ul.appendChild(recentEntry(item, root)); });
      root.appendChild(ul);
    }

    var pageSize = parseInt(root.getAttribute("data-page-size"), 10);
    if (!pageSize || pageSize < 1) pageSize = 10;
    var year = "all";
    var page = 1;
    var yearsNav = newest ? scope.querySelector("[data-years]") : null;

    function readUrl() {
      var params = new URLSearchParams(location.search);
      var nextYear = params.get("year") || "all";
      var nextPage = parseInt(params.get("page"), 10);
      if (!nextPage || nextPage < 1) nextPage = 1;
      return { year: nextYear, page: nextPage };
    }

    function hrefFor(nextYear, nextPage) {
      var params = new URLSearchParams();
      if (nextYear && nextYear !== "all") params.set("year", nextYear);
      if (nextPage > 1) params.set("page", String(nextPage));
      var qs = params.toString();
      return location.pathname + (qs ? "?" + qs : "");
    }

    function writeUrl(mode) {
      var url = hrefFor(year, page);
      if (url === location.pathname + location.search) return;
      if (mode === "push") history.pushState({ year: year, page: page }, "", url);
      else history.replaceState({ year: year, page: page }, "", url);
    }

    function watchedYear(item) {
      return isDate(item.last_watched) ? item.last_watched.slice(0, 4) : "";
    }

    function yearOk(value) {
      if (value === "all" || value === "undated") return true;
      return /^\d{4}$/.test(value);
    }

    function matchesYear(item) {
      if (year === "all") return true;
      if (year === "undated") return !isDate(item.last_watched);
      return watchedYear(item) === year;
    }

    function knownYears() {
      var found = {};
      var undated = false;
      items.forEach(function (item) {
        if (isDate(item.last_watched)) found[item.last_watched.slice(0, 4)] = true;
        else undated = true;
      });
      return {
        years: Object.keys(found).sort(function (a, b) { return Number(b) - Number(a); }),
        undated: undated
      };
    }

    function buildYears() {
      if (!yearsNav) return;
      var known = knownYears();
      yearsNav.textContent = "";
      function add(id, label) {
        var a = document.createElement("a");
        a.href = hrefFor(id, 1);
        a.setAttribute("data-year", id);
        a.textContent = label;
        yearsNav.appendChild(a);
      }
      add("all", "all");
      known.years.forEach(function (value) { add(value, value); });
      if (known.undated) add("undated", "undated");
      yearsNav.hidden = false;
    }

    function markYears() {
      if (!yearsNav) return;
      var links = yearsNav.querySelectorAll("a");
      for (var i = 0; i < links.length; i++) {
        if (links[i].getAttribute("data-year") === year) links[i].setAttribute("aria-current", "true");
        else links[i].removeAttribute("aria-current");
      }
    }

    function pageTokens(current, pages) {
      if (pages <= 7) {
        var all = [];
        for (var i = 1; i <= pages; i++) all.push(i);
        return all;
      }
      var keep = {};
      keep[1] = true;
      keep[pages] = true;
      for (var n = current - 2; n <= current + 2; n++) {
        if (n >= 1 && n <= pages) keep[n] = true;
      }
      var nums = Object.keys(keep).map(Number).sort(function (a, b) { return a - b; });
      var out = [];
      for (var j = 0; j < nums.length; j++) {
        if (j && nums[j] - nums[j - 1] > 1) out.push("gap");
        out.push(nums[j]);
      }
      return out;
    }

    function pager(current, pages) {
      var nav = document.createElement("nav");
      nav.className = "film-pages";
      nav.setAttribute("aria-label", "pages");
      function edge(label, target, enabled) {
        if (!enabled) {
          var span = document.createElement("span");
          span.className = "is-disabled";
          span.textContent = label;
          nav.appendChild(span);
          return;
        }
        var a = document.createElement("a");
        a.href = hrefFor(year, target);
        a.setAttribute("data-page", label);
        a.textContent = label;
        nav.appendChild(a);
      }
      edge("prev", current - 1, current > 1);
      pageTokens(current, pages).forEach(function (token) {
        if (token === "gap") {
          var gap = document.createElement("span");
          gap.className = "gap";
          gap.textContent = "…";
          nav.appendChild(gap);
          return;
        }
        var a = document.createElement("a");
        a.href = hrefFor(year, token);
        a.setAttribute("data-page", String(token));
        a.textContent = String(token);
        if (token === current) a.setAttribute("aria-current", "page");
        nav.appendChild(a);
      });
      edge("next", current + 1, current < pages);
      return nav;
    }

    function renderFlat(query) {
      var q = (query || "").trim().toLowerCase();
      var matched = items.filter(function (item) {
        if (q && haystack(item).indexOf(q) === -1) return false;
        return matchesYear(item);
      });
      var total = items.length;
      if (countEl) {
        if (q || year !== "all") countEl.textContent = matched.length + " of " + total + " " + word;
        else countEl.textContent = total + " " + plural(kind, total);
      }
      matched.sort(byTitle);
      matched.sort(byWatched);
      var pages = Math.max(1, Math.ceil(matched.length / pageSize));
      if (page > pages) page = pages;
      if (page < 1) page = 1;
      var shown = matched.slice((page - 1) * pageSize, page * pageSize);
      root.textContent = "";
      if (!shown.length) {
        root.appendChild(emptyNote(items.length ? "nothing matches." : "no " + word + " yet."));
      } else {
        var ul = document.createElement("ul");
        ul.className = "log";
        shown.forEach(function (item) { ul.appendChild(entry(item, root, true)); });
        root.appendChild(ul);
      }
      if (pages > 1) root.appendChild(pager(page, pages));
      markYears();
      writeUrl("replace");
    }

    function filtered(query) {
      var q = (query || "").trim().toLowerCase();
      var shown = items.filter(function (item) {
        return !q || haystack(item).indexOf(q) !== -1;
      });
      var total = items.length;
      if (countEl) {
        if (q) countEl.textContent = shown.length + " of " + total + " " + word;
        else countEl.textContent = total + " " + plural(kind, total);
      }
      return shown;
    }

    function renderAll(query) {
      var shown = filtered(query);
      root.textContent = "";
      if (!shown.length) {
        root.appendChild(emptyNote(items.length ? "nothing matches." : "no " + word + " yet."));
        return;
      }
      var groups = {};
      shown.forEach(function (item) {
        var key = yearOf(item.last_watched);
        if (!groups[key]) groups[key] = [];
        groups[key].push(item);
      });
      Object.keys(groups).sort(function (a, b) {
        if (a === "earlier") return 1;
        if (b === "earlier") return -1;
        return Number(b) - Number(a);
      }).forEach(function (key) {
        var list = groups[key].slice().sort(byTitle);
        if (key !== "earlier") list.sort(byWatched);
        var h = document.createElement("h3");
        h.textContent = key;
        var ul = document.createElement("ul");
        ul.className = "log";
        list.forEach(function (item) { ul.appendChild(entry(item, root, false)); });
        root.appendChild(h);
        root.appendChild(ul);
      });
    }

    function render() {
      if (allLink) allLink.textContent = "see all " + word + " (" + items.length + ")";
      if (mode === "recent") renderRecent();
      else if (newest) renderFlat(input ? input.value : "");
      else renderAll(input ? input.value : "");
    }

    function fail() {
      if (countEl) countEl.textContent = "";
      root.textContent = "";
      var p = document.createElement("p");
      p.className = "note";
      p.textContent = word + " could not be loaded.";
      root.appendChild(p);
    }

    if (!src) return;
    if (newest) {
      var initial = readUrl();
      year = yearOk(initial.year) ? initial.year : "all";
      page = initial.page;
      if (yearsNav) {
        yearsNav.addEventListener("click", function (event) {
          var link = event.target.closest("a[data-year]");
          if (!link) return;
          event.preventDefault();
          year = link.getAttribute("data-year") || "all";
          page = 1;
          writeUrl("push");
          render();
          if (scope.scrollIntoView) scope.scrollIntoView({ block: "start" });
        });
      }
      root.addEventListener("click", function (event) {
        var link = event.target.closest("a[data-page]");
        if (!link) return;
        event.preventDefault();
        var spec = link.getAttribute("data-page");
        if (spec === "prev") page -= 1;
        else if (spec === "next") page += 1;
        else page = parseInt(spec, 10) || 1;
        writeUrl("push");
        render();
        if (scope.scrollIntoView) scope.scrollIntoView({ block: "start" });
      });
      window.addEventListener("popstate", function () {
        var next = readUrl();
        year = yearOk(next.year) ? next.year : "all";
        page = next.page;
        render();
      });
    }
    if (input) input.addEventListener("input", function () {
      if (newest) {
        page = 1;
        writeUrl("replace");
      }
      render();
    });

    fetch(src)
      .then(function (res) {
        if (!res.ok) throw new Error("bad status");
        return res.json();
      })
      .then(function (data) {
        items = Array.isArray(data) ? data.filter(function (item) {
          return item && typeof item.title === "string" && item.title.trim();
        }) : [];
        if (newest) {
          var known = knownYears();
          var allowed = year === "all" || (year === "undated" && known.undated) || known.years.indexOf(year) !== -1;
          if (!allowed) {
            year = "all";
            page = 1;
            writeUrl("replace");
          }
          buildYears();
        }
        render();
      })
      .catch(fail);
  }

  var roots = document.querySelectorAll("[data-catalog]");
  for (var i = 0; i < roots.length; i++) mount(roots[i]);
})();
