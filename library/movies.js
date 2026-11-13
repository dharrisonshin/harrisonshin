(function () {
  var root = document.getElementById("movies");
  var countEl = document.getElementById("movie-count");
  var input = document.getElementById("movie-q");
  if (!root) return;

  var films = [];

  function yearOf(date) {
    if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return "earlier";
    return date.slice(0, 4);
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

  function entry(film) {
    var li = document.createElement("li");
    var what = document.createElement("p");
    what.className = "what";
    what.appendChild(document.createTextNode(film.title));
    var bits = [];
    if (typeof film.year === "number") bits.push(String(film.year));
    if (film.director) bits.push(film.director);
    if (bits.length) {
      var who = document.createElement("span");
      who.className = "who";
      who.textContent = " " + bits.join(" · ");
      what.appendChild(who);
    }
    li.appendChild(what);
    if (typeof film.rating === "number" && film.rating >= 0 && film.rating <= 5) {
      li.appendChild(stars(Math.round(film.rating)));
    }
    if (typeof film.takeaway === "string" && film.takeaway.trim()) {
      var take = document.createElement("p");
      take.className = "take";
      take.textContent = film.takeaway.trim();
      li.appendChild(take);
    }
    return li;
  }

  function render(query) {
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
      var empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = films.length ? "nothing matches." : "no films yet.";
      root.appendChild(empty);
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
      var items = groups[key].slice();
      if (key === "earlier") {
        items.sort(function (a, b) { return String(a.title).localeCompare(String(b.title)); });
      } else {
        items.sort(function (a, b) { return String(a.title).localeCompare(String(b.title)); });
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

  function fail() {
    if (countEl) countEl.textContent = "";
    root.textContent = "";
    var p = document.createElement("p");
    p.className = "note";
    p.textContent = "movies could not be loaded.";
    root.appendChild(p);
  }

  if (input) {
    input.addEventListener("input", function () { render(input.value); });
  }

  fetch("movies.json")
    .then(function (res) {
      if (!res.ok) throw new Error("bad status");
      return res.json();
    })
    .then(function (data) {
      films = Array.isArray(data) ? data.filter(function (film) {
        return film && typeof film.title === "string" && film.title.trim();
      }) : [];
      render(input ? input.value : "");
    })
    .catch(fail);
})();
