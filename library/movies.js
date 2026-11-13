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

  function stars(n) {
    var p = document.createElement("p");
    p.className = "stars";
    var label = document.createElement("span");
    label.className = "sr";
    label.textContent = n + " of 5 stars";
    var visual = document.createElement("span");
    visual.setAttribute("aria-hidden", "true");
    var on = document.createElement("span");
    on.className = "on";
    on.textContent = "★★★★★".slice(0, n);
    visual.appendChild(on);
    if (n < 5) visual.appendChild(document.createTextNode("☆☆☆☆☆".slice(0, 5 - n)));
    p.appendChild(label);
    p.appendChild(visual);
    return p;
  }

  function addStars(li, item) {
    if (typeof item.rating === "number" && item.rating >= 0 && item.rating <= 5) {
      li.appendChild(stars(Math.round(item.rating)));
    }
  }

  function addTake(li, item) {
    if (typeof item.takeaway === "string" && item.takeaway.trim()) {
      var take = document.createElement("p");
      take.className = "take";
      take.textContent = item.takeaway.trim();
      li.appendChild(take);
    }
  }

  function whatLine(item, withDirector) {
    var what = document.createElement("p");
    what.className = "what";
    what.appendChild(document.createTextNode(item.title));
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

  function recentEntry(item) {
    var li = document.createElement("li");
    li.appendChild(whatLine(item, false));
    addStars(li, item);
    if (isDate(item.last_watched)) {
      var when = document.createElement("p");
      when.className = "when";
      when.textContent = formatDate(item.last_watched);
      li.appendChild(when);
    }
    addTake(li, item);
    return li;
  }

  function entry(item) {
    var li = document.createElement("li");
    li.appendChild(whatLine(item, true));
    addStars(li, item);
    addTake(li, item);
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

  function mount(root) {
    var mode = root.getAttribute("data-mode") || "all";
    var src = root.getAttribute("data-src");
    var kind = root.getAttribute("data-kind") === "show" ? "show" : "film";
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
      dated.sort(function (a, b) { return String(b.last_watched).localeCompare(String(a.last_watched)); });
      var shown = dated.slice(0, RECENT);
      root.textContent = "";
      if (!shown.length) {
        root.appendChild(emptyNote(items.length ? "nothing watched yet." : "no " + word + " yet."));
        return;
      }
      var ul = document.createElement("ul");
      ul.className = "log";
      shown.forEach(function (item) { ul.appendChild(recentEntry(item)); });
      root.appendChild(ul);
    }

    function renderAll(query) {
      var q = (query || "").trim().toLowerCase();
      var shown = items.filter(function (item) {
        return !q || haystack(item).indexOf(q) !== -1;
      });
      var n = shown.length;
      var total = items.length;
      if (countEl) {
        if (q) countEl.textContent = n + " of " + total + " " + word;
        else countEl.textContent = total + " " + plural(kind, total);
      }
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
        if (key !== "earlier") {
          list.sort(function (a, b) { return String(b.last_watched).localeCompare(String(a.last_watched)); });
        }
        var h = document.createElement("h3");
        h.textContent = key;
        var ul = document.createElement("ul");
        ul.className = "log";
        list.forEach(function (item) { ul.appendChild(entry(item)); });
        root.appendChild(h);
        root.appendChild(ul);
      });
    }

    function render() {
      if (allLink) allLink.textContent = "see all " + word + " (" + items.length + ")";
      if (mode === "recent") renderRecent();
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
    if (input) input.addEventListener("input", render);

    fetch(src)
      .then(function (res) {
        if (!res.ok) throw new Error("bad status");
        return res.json();
      })
      .then(function (data) {
        items = Array.isArray(data) ? data.filter(function (item) {
          return item && typeof item.title === "string" && item.title.trim();
        }) : [];
        render();
      })
      .catch(fail);
  }

  var roots = document.querySelectorAll("[data-catalog]");
  for (var i = 0; i < roots.length; i++) mount(roots[i]);
})();
