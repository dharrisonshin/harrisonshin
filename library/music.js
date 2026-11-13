(function () {
  var root = document.getElementById("music");
  if (!root) return;

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

  function entry(item) {
    var li = document.createElement("li");
    var what = document.createElement("p");
    what.className = "what";
    var artist = item.artist.trim();
    var link = typeof item.link === "string" ? item.link.trim() : "";
    if (/^https?:\/\//i.test(link)) {
      var a = document.createElement("a");
      a.href = link;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = artist;
      what.appendChild(a);
    } else {
      what.appendChild(document.createTextNode(artist));
    }
    var bits = [];
    if (typeof item.album === "string" && item.album.trim()) bits.push(item.album.trim());
    if (typeof item.year === "number") bits.push(String(item.year));
    if (bits.length) {
      var who = document.createElement("span");
      who.className = "who";
      who.textContent = " " + bits.join(" · ");
      what.appendChild(who);
    }
    li.appendChild(what);
    if (typeof item.rating === "number" && item.rating >= 0 && item.rating <= 5) {
      li.appendChild(stars(Math.round(item.rating)));
    }
    if (typeof item.note === "string" && item.note.trim()) {
      var note = document.createElement("p");
      note.className = "take";
      note.textContent = item.note.trim();
      li.appendChild(note);
    }
    return li;
  }

  function fail() {
    root.textContent = "";
    var p = document.createElement("p");
    p.className = "note";
    p.textContent = "music could not be loaded.";
    root.appendChild(p);
  }

  fetch("music.json")
    .then(function (res) {
      if (!res.ok) throw new Error("bad status");
      return res.json();
    })
    .then(function (data) {
      var items = Array.isArray(data) ? data.filter(function (item) {
        return item && typeof item.artist === "string" && item.artist.trim();
      }) : [];
      root.textContent = "";
      if (!items.length) {
        var empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = "no music yet.";
        root.appendChild(empty);
        return;
      }
      var ul = document.createElement("ul");
      ul.className = "log";
      items.forEach(function (item) { ul.appendChild(entry(item)); });
      root.appendChild(ul);
    })
    .catch(fail);
})();
