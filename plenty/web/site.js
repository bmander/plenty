// Sorting, filtering and hover tips. No dependencies.
(function () {
  "use strict";

  // --- hover tips for any element carrying data-tip
  var tip = document.createElement("div");
  tip.id = "tip";
  document.body.appendChild(tip);
  function place(e) {
    var pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
    var x = e.clientX + pad, y = e.clientY + pad;
    if (x + w > window.innerWidth - 8) x = e.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = e.clientY - h - pad;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  }
  // for a page's own script: a tip that follows the pointer over something drawn, such as a canvas
  window.plentyTip = {
    show: function (text, e) { tip.textContent = text; tip.style.display = "block"; place(e); },
    hide: function () { tip.style.display = "none"; }
  };
  document.addEventListener("mouseover", function (e) {
    var t = e.target.closest && e.target.closest("[data-tip]");
    if (!t) { tip.style.display = "none"; return; }
    tip.textContent = t.getAttribute("data-tip");
    tip.style.display = "block";
    place(e);
  });
  document.addEventListener("mousemove", function (e) {
    if (tip.style.display === "block") place(e);
  });
  // keyboard: show the tip under whatever focused element carries one
  document.addEventListener("focusin", function (e) {
    var t = e.target.closest && e.target.closest("[data-tip]");
    if (!t) { tip.style.display = "none"; return; }
    tip.textContent = t.getAttribute("data-tip");
    tip.style.display = "block";
    var r = t.getBoundingClientRect();
    place({ clientX: r.left, clientY: r.bottom });
  });
  document.addEventListener("focusout", function () { tip.style.display = "none"; });

  // --- sortable tables: th[data-sort="num"|"text"]
  document.querySelectorAll("table.ledger").forEach(function (table) {
    var heads = table.querySelectorAll("thead th[data-sort]");
    heads.forEach(function (th) {
      th.tabIndex = 0;
      function sort() {
        var idx = Array.prototype.indexOf.call(th.parentNode.children, th);
        var numeric = th.getAttribute("data-sort") === "num";
        var dir = th.getAttribute("aria-sort") === "descending" ? "ascending" : "descending";
        if (!th.hasAttribute("aria-sort") && !numeric) dir = "ascending";
        heads.forEach(function (h) { h.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", dir);
        var body = table.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) {
          var x = a.cells[idx].getAttribute("data-v") || a.cells[idx].textContent.trim();
          var y = b.cells[idx].getAttribute("data-v") || b.cells[idx].textContent.trim();
          var c = numeric ? parseFloat(x) - parseFloat(y) : x.localeCompare(y);
          return dir === "ascending" ? c : -c;
        });
        rows.forEach(function (r) { body.appendChild(r); });
        table.dispatchEvent(new Event("sorted"));
      }
      th.addEventListener("click", sort);
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); }
      });
    });
  });

  // --- expandable groups: a kind of sector opens its sectors beneath it
  document.querySelectorAll("button.expander").forEach(function (b) {
    var rows = document.querySelectorAll('tr[data-group="' + b.getAttribute("data-group") + '"]');
    b.addEventListener("click", function () {
      var open = b.getAttribute("aria-expanded") !== "true";
      b.setAttribute("aria-expanded", open ? "true" : "false");
      rows.forEach(function (r) { r.hidden = !open; });
    });
  });

  // --- capability filter: show the capabilities and tasks that match, and open them
  var tq = document.getElementById("tq");
  if (tq) {
    var tcount = document.getElementById("tcount");
    var sections = document.querySelectorAll("section[data-domain]");
    var caps = Array.prototype.map.call(document.querySelectorAll("tr[data-cap]"), function (row) {
      return { row: row, b: row.querySelector("button.expander"), text: null, ktext: null,
               kids: Array.prototype.slice.call(document.querySelectorAll('tr[data-group="' + row.id + '"]')) };
    });
    tq.addEventListener("input", function () {
      var needle = tq.value.trim().toLowerCase(), nc = 0, nt = 0;
      caps.forEach(function (c) {
        if (c.text === null) {   // read the rows' text once, on first use
          c.text = c.row.textContent.toLowerCase();
          c.ktext = c.kids.map(function (k) { return k.textContent.toLowerCase(); });
        }
        var own = !needle || c.text.indexOf(needle) !== -1, any = false;
        c.kids.forEach(function (k, i) {
          var m = !!needle && c.ktext[i].indexOf(needle) !== -1;
          k.hidden = !m;
          if (m) { any = true; nt++; }
        });
        c.row.hidden = !(own || any);
        if (needle && (own || any)) nc++;
        c.b.setAttribute("aria-expanded", any ? "true" : "false");
      });
      Array.prototype.forEach.call(sections, function (s) {
        s.hidden = !!needle && !s.querySelector("tr[data-cap]:not([hidden])");
      });
      tcount.textContent = !needle ? "" :
        nc + (nc === 1 ? " capability" : " capabilities") + " and " + nt + (nt === 1 ? " task" : " tasks") + " match";
    });
  }

  // --- sector filter
  var q = document.getElementById("q"), phys = document.getElementById("phys"), count = document.getElementById("count");
  var table = document.getElementById("sectors");
  if (q && table) {
    var rows = Array.prototype.slice.call(table.tBodies[0].rows);
    var apply = function () {
      var needle = q.value.trim().toLowerCase(), only = phys.checked, n = 0;
      rows.forEach(function (r) {
        var show = (!only || r.getAttribute("data-phys") === "1") &&
                   (!needle || r.getAttribute("data-text").indexOf(needle) !== -1);
        r.hidden = !show;
        if (show) n++;
      });
      count.textContent = n + " of " + rows.length + " sectors";
      stripe();
    };
    // nth-child banding breaks when rows are hidden or reordered, so band the visible rows here
    var stripe = function () {
      var i = 0;
      Array.prototype.forEach.call(table.tBodies[0].rows, function (r) {
        if (!r.hidden) r.classList.toggle("band", i++ % 2 === 0);
      });
    };
    table.addEventListener("sorted", stripe);
    q.addEventListener("input", apply);
    phys.addEventListener("change", apply);
    apply();
  }
})();
