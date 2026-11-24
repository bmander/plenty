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
