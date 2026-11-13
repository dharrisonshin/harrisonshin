(function () {
  var root = document.getElementById("movies");
  if (!root) return;

  var mode = root.getAttribute("data-mode") || "all";
  var src = root.getAttribute("data-src") || "movies.json";
  var countEl = document.getElementById("movie-count");
  var input = document.getElementById("movie-q");
  var allLink = document.getElementById("all-films");
  var RECENT = 10;
  var MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
  var films = [];

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

  function haystack(film) {
    var bits = [film.title, film.year, film.director, film.takeaway];
    if (Array.isArray(film.genres)) bits = bits.concat(film.genres);
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

  function addStars(li, film) {
    if (typeof film.rating === "number" && film.rating >= 0 && film.rating <= 5) {
      li.appendChild(stars(Math.round(film.rating)));
    }
  }

  function addTake(li, film) {
    if (typeof film.takeaway === "string" && film.takeaway.trim()) {
      var take = document.createElement("p");
      take.className = "take";
      take.textContent = film.takeaway.trim();
      li.appendChild(take);
    }
  }

  function whatLine(film, withDirector) {
    var what = document.createElement("p");
    what.className = "what";
    what.appendChild(document.createTextNode(film.title));
    var bits = [];
    if (typeof film.year === "number") bits.push(String(film.year));
    if (withDirector && film.director) bits.push(film.director);
    if (bits.length) {
      var who = document.createElement("span");
      who.className = "who";
      who.textContent = " " + bits.join(" · ");
      what.appendChild(who);
    }
    return what;
  }

  function recentEntry(film) {
    var li = document.createElement("li");
    li.appendChild(whatLine(film, false));
    addStars(li, film);
    if (isDate(film.last_watched)) {
      var when = document.createElement("p");
      when.className = "when";
      when.textContent = formatDate(film.last_watched);
      li.appendChild(when);
    }
    addTake(li, film);
    return li;
  }

  function entry(film) {
    var li = document.createElement("li");
    li.appendChild(whatLine(film, true));
    addStars(li, film);
    addTake(li, film);
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

  function renderRecent() {
    var dated = films.filter(function (film) { return isDate(film.last_watched); });
    dated.sort(byTitle);
    dated.sort(function (a, b) { return String(b.last_watched).localeCompare(String(a.last_watched)); });
    var shown = dated.slice(0, RECENT);
    root.textContent = "";
    if (!shown.length) {
      root.appendChild(emptyNote(films.length ? "nothing watched yet." : "no films yet."));
      return;
    }
    var ul = document.createElement("ul");
    ul.className = "log";
    shown.forEach(function (film) { ul.appendChild(recentEntry(film)); });
    root.appendChild(ul);
  }

  function renderAll(query) {
    var q = (query || "").trim().toLowerCase();
    var shown = films.filter(function (film) {
      return !q || haystack(film).indexOf(q) !== -1;
    });
    var n = shown.length;
    var total = films.length;
    if (countEl) {
      if (q) countEl.textContent = n + " of " + total + " films";
      else countEl.textContent = total + (total === 1 ? " film" : " films");
    }

    root.textContent = "";
    if (!shown.length) {
      root.appendChild(emptyNote(films.length ? "nothing matches." : "no films yet."));
      return;
    }

    var groups = {};
    shown.forEach(function (film) {
      var key = yearOf(film.last_watched);
      if (!groups[key]) groups[key] = [];
      groups[key].push(film);
    });
    var keys = Object.keys(groups).sort(function (a, b) {
      if (a === "earlier") return 1;
      if (b === "earlier") return -1;
      return Number(b) - Number(a);
    });
    keys.forEach(function (key) {
      var items = groups[key].slice().sort(byTitle);
      if (key !== "earlier") {
        items.sort(function (a, b) { return String(b.last_watched).localeCompare(String(a.last_watched)); });
      }
      var h = document.createElement("h3");
      h.textContent = key;
      var ul = document.createElement("ul");
      ul.className = "log";
      items.forEach(function (film) { ul.appendChild(entry(film)); });
      root.appendChild(h);
      root.appendChild(ul);
    });
  }

  function render() {
    if (allLink) allLink.textContent = "see all films (" + films.length + ")";
    if (mode === "recent") renderRecent();
    else renderAll(input ? input.value : "");
  }

  function fail() {
    if (countEl) countEl.textContent = "";
    root.textContent = "";
    var p = document.createElement("p");
    p.className = "note";
    p.textContent = "movies could not be loaded.";
    root.appendChild(p);
  }

  if (input) input.addEventListener("input", render);

  fetch(src)
    .then(function (res) {
      if (!res.ok) throw new Error("bad status");
      return res.json();
    })
    .then(function (data) {
      films = Array.isArray(data) ? data.filter(function (film) {
        return film && typeof film.title === "string" && film.title.trim();
      }) : [];
      render();
    })
    .catch(fail);
})();
