(function () {
  var root = document.getElementById("books");
  if (!root) return;

  var mode = root.getAttribute("data-mode") || "all";
  var src = root.getAttribute("data-src") || "books.json";
  var RECENT = 10;
  var scope = root.closest(".shelf") || document;
  var countEl = scope.querySelector("[data-count]");
  var input = scope.querySelector("[data-search]");
  var allLink = root.getAttribute("data-all")
    ? document.getElementById(root.getAttribute("data-all"))
    : null;
  var books = [];

  function haystack(book) {
    var bits = [book.title, book.author, book.takeaway];
    if (Array.isArray(book.tags)) bits = bits.concat(book.tags);
    return bits
      .filter(function (v) { return v !== null && v !== undefined && v !== ""; })
      .join(" ")
      .toLowerCase();
  }

  function entry(book) {
    var li = document.createElement("li");
    var what = document.createElement("p");
    what.className = "what";
    what.appendChild(document.createTextNode(book.title));
    if (book.author) {
      var who = document.createElement("span");
      who.className = "who";
      who.textContent = " " + book.author;
      what.appendChild(who);
    }
    li.appendChild(what);
    if (typeof book.takeaway === "string" && book.takeaway.trim()) {
      var take = document.createElement("p");
      take.className = "take";
      take.textContent = book.takeaway.trim();
      li.appendChild(take);
    }
    return li;
  }

  function noun(n) {
    return n === 1 ? "book" : "books";
  }

  function render(query) {
    var q = (query || "").trim().toLowerCase();
    var matched = books.filter(function (book) {
      return !q || haystack(book).indexOf(q) !== -1;
    });
    var shown = mode === "recent" ? matched.slice(0, RECENT) : matched;
    var total = books.length;
    if (countEl) {
      if (q) countEl.textContent = matched.length + " of " + total + " books";
      else countEl.textContent = total + " " + noun(total);
    }
    if (allLink) allLink.textContent = "see all books (" + total + ")";
    root.textContent = "";
    if (!shown.length) {
      var empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = books.length ? "nothing matches." : "no books yet.";
      root.appendChild(empty);
      return;
    }
    var ul = document.createElement("ul");
    ul.className = "log";
    shown.forEach(function (book) { ul.appendChild(entry(book)); });
    root.appendChild(ul);
  }

  function fail() {
    if (countEl) countEl.textContent = "";
    root.textContent = "";
    var p = document.createElement("p");
    p.className = "note";
    p.textContent = "books could not be loaded.";
    root.appendChild(p);
  }

  if (input) input.addEventListener("input", function () { render(input.value); });

  fetch(src)
    .then(function (res) {
      if (!res.ok) throw new Error("bad status");
      return res.json();
    })
    .then(function (data) {
      books = Array.isArray(data) ? data.filter(function (book) {
        return book && typeof book.title === "string" && book.title.trim();
      }) : [];
      render(input ? input.value : "");
    })
    .catch(fail);
})();
