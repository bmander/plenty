// A matrix page: paints every entry on a canvas and lists one sector's column and row.
// The data file sets window.PLENTY_MATRIX (written by plenty/site.py). No dependencies.
(function () {
  "use strict";
  var M = window.PLENTY_MATRIX, canvas = document.getElementById("mx-canvas");
  if (!M || !canvas) return;
  var n = M.names.length, unit = M.unit, LIST = 12;
  var LO = Math.log10(M.cut), HI = 0;                 // the colour scale runs from the cut to one dollar

  // dense copies for the pointer, and each row's entries for "who uses it"
  var value = new Float32Array(n * n), capital = new Float32Array(n * n), byRow = [];
  for (var r = 0; r < n; r++) byRow.push([]);
  M.cols.forEach(function (col, j) {
    for (var k = 0; k < col.length; k += 3) {
      value[col[k] * n + j] = col[k + 1] * unit;
      capital[col[k] * n + j] = col[k + 2] * unit;
      byRow[col[k]].push(j, col[k + 1]);
    }
  });

  function cents(dollars, digits) { return (dollars * 100).toFixed(digits === undefined ? 2 : digits) + "\u00a2"; }

  // --- the picture
  function ramp() {
    var css = getComputedStyle(document.documentElement);
    return [0, 1, 2, 3, 4].map(function (i) {
      var h = css.getPropertyValue("--heat-" + i).trim().replace("#", "");
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
    });
  }
  function draw() {
    var ctx = canvas.getContext("2d"), img = ctx.createImageData(n, n), stops = ramp();
    for (var p = 0; p < n * n; p++) {
      var v = value[p];
      if (v <= 0) continue;                           // zero, under the cut, or negative: left blank
      var t = Math.min(1, Math.max(0, (Math.log10(v) - LO) / (HI - LO))) * (stops.length - 1);
      var a = stops[Math.floor(t)], b = stops[Math.min(stops.length - 1, Math.floor(t) + 1)], f = t - Math.floor(t);
      img.data[4 * p] = a[0] + (b[0] - a[0]) * f;
      img.data[4 * p + 1] = a[1] + (b[1] - a[1]) * f;
      img.data[4 * p + 2] = a[2] + (b[2] - a[2]) * f;
      img.data[4 * p + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
  }
  draw();
  if (window.matchMedia) {
    var dark = window.matchMedia("(prefers-color-scheme: dark)");
    if (dark.addEventListener) dark.addEventListener("change", draw);
  }

  var hLine = document.getElementById("mx-h"), vLine = document.getElementById("mx-v");
  function cellAt(e) {
    var box = canvas.getBoundingClientRect();
    var j = Math.floor((e.clientX - box.left) / box.width * n), i = Math.floor((e.clientY - box.top) / box.height * n);
    return (i < 0 || j < 0 || i >= n || j >= n) ? null : { i: i, j: j };
  }
  function describe(i, j) {
    var v = value[i * n + j], k = capital[i * n + j];
    var amount = v === 0 ? "under " + cents(M.cut) + " per dollar" : cents(v) + " per dollar";
    if (v !== 0 && Math.abs(k) >= M.cut) amount += ", " + cents(k) + " of it equipment and buildings";
    return "Input: " + M.names[i] + "\nTo make: " + M.names[j] + "\n" + amount;
  }
  canvas.addEventListener("pointermove", function (e) {
    var c = cellAt(e);
    if (!c) return;
    window.plentyTip.show(describe(c.i, c.j), e);
    hLine.style.display = vLine.style.display = "block";
    hLine.style.top = ((c.i + 0.5) / n * 100) + "%";
    vLine.style.left = ((c.j + 0.5) / n * 100) + "%";
  });
  canvas.addEventListener("pointerleave", function () {
    window.plentyTip.hide();
    hLine.style.display = vLine.style.display = "none";
  });
  canvas.addEventListener("click", function (e) {
    var c = cellAt(e);
    if (c) { select(c.j, c.i); document.getElementById("sector").scrollIntoView({ behavior: "smooth" }); }
  });

  // --- one sector's column and row
  var pick = document.getElementById("mx-pick"), inBox = document.getElementById("mx-in"), outBox = document.getElementById("mx-out");
  var group = null, og = null;
  M.names.forEach(function (name, j) {
    if (M.groups[j] !== group) {
      group = M.groups[j];
      og = document.createElement("optgroup");
      og.label = group;
      pick.appendChild(og);
    }
    var o = document.createElement("option");
    o.value = j;
    o.textContent = name;
    og.appendChild(o);
  });

  function el(tag, cls, text) {
    var x = document.createElement(tag);
    if (cls) x.className = cls;
    if (text !== undefined) x.textContent = text;
    return x;
  }
  function sectorButton(j) {
    var b = el("button", "pick", M.names[j]);
    b.type = "button";
    b.addEventListener("click", function () { select(j); });
    return b;
  }
  function barCell(v, vmax) {
    var td = el("td"), cell = el("div", "barcell"), bar = el("div", "bar"), fill = el("i");
    fill.style.width = Math.max(0, Math.min(100, 100 * v / vmax)).toFixed(1) + "%";
    bar.appendChild(fill);
    cell.appendChild(bar);
    cell.appendChild(el("span", "v", (v * 100).toFixed(2)));
    td.appendChild(cell);
    return td;
  }
  // rows: [{j, v, k?, marked}], largest first; the list is cut to LIST until "show all" is pressed
  function listTable(box, heads, rows, foot) {
    box.textContent = "";
    var wrap = el("div", "scroll"), table = el("table", "ledger"), thead = el("thead"), tr = el("tr"), body = el("tbody");
    heads.forEach(function (h, i) { var th = el("th", i ? "num" : "", h); th.scope = "col"; tr.appendChild(th); });
    thead.appendChild(tr);
    table.appendChild(thead);
    var vmax = rows.length ? Math.max(rows[0].v, 0) || 1 : 1;
    rows.forEach(function (r, i) {
      var row = el("tr"), name = el("th");
      name.scope = "row";
      name.appendChild(sectorButton(r.j));
      if (r.marked) name.appendChild(el("span", "dim", "  \u2190 the cell you clicked"));
      row.appendChild(name);
      row.appendChild(barCell(r.v, vmax));
      if (r.k !== undefined) row.appendChild(el("td", "num", (r.k * 100).toFixed(2)));
      row.hidden = i >= LIST && !r.marked;
      body.appendChild(row);
    });
    table.appendChild(body);
    if (foot) {
      var tfoot = el("tfoot");
      foot.forEach(function (cells) {
        var fr = el("tr");
        cells.forEach(function (c, i) { fr.appendChild(el("td", i ? "num" : "", c)); });
        tfoot.appendChild(fr);
      });
      table.appendChild(tfoot);
    }
    wrap.appendChild(table);
    box.appendChild(wrap);
    if (rows.length > LIST) {
      var more = el("button", "more", "Show all " + rows.length);
      more.type = "button";
      more.addEventListener("click", function () {
        Array.prototype.forEach.call(body.rows, function (r) { r.hidden = false; });
        more.remove();
      });
      box.appendChild(more);
    }
  }

  function select(j, markRow) {
    pick.value = j;
    var name = M.names[j], col = M.cols[j], inputs = [], users = [], listed = 0, k;
    for (k = 0; k < col.length; k += 3) {
      inputs.push({ j: col[k], v: col[k + 1] * unit, k: col[k + 2] * unit, marked: col[k] === markRow });
      listed += col[k + 1];
    }
    inputs.sort(function (a, b) { return b.v - a.v; });
    for (k = 0; k < byRow[j].length; k += 2) users.push({ j: byRow[j][k], v: byRow[j][k + 1] * unit });
    users.sort(function (a, b) { return b.v - a.v; });
    document.getElementById("mx-in-title").textContent = "What a dollar of " + name + " uses";
    document.getElementById("mx-out-title").textContent = "Who uses " + name;
    listTable(inBox, ["Input", "\u00a2 per dollar", "Of it, equipment and buildings"], inputs, [
      ["Inputs under " + cents(M.cut) + " each", ((M.total[j] - listed) * unit * 100).toFixed(2), ""],
      ["All inputs", (M.total[j] * unit * 100).toFixed(2), (M.capital[j] * unit * 100).toFixed(2)]
    ]);
    listTable(outBox, ["Sector that uses it", "\u00a2 per dollar of that sector's output"], users, null);
    if (!users.length) outBox.appendChild(el("p", "note", "No sector uses as much as " + cents(M.cut) + " of it per dollar of output."));
    if (history.replaceState) history.replaceState(null, "", "#sector=" + M.codes[j]);
  }
  pick.addEventListener("change", function () { select(+pick.value); });

  // links elsewhere on the page that name a sector, and a sector in the address
  function fromHash() {
    var m = /^#sector=(.+)$/.exec(location.hash), j = m ? M.codes.indexOf(decodeURIComponent(m[1])) : -1;
    if (j >= 0) select(j);
    return j >= 0;
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-sector]");
    if (!a) return;
    e.preventDefault();
    select(M.codes.indexOf(a.getAttribute("data-sector")));
    document.getElementById("sector").scrollIntoView({ behavior: "smooth" });
  });
  window.addEventListener("hashchange", fromHash);
  if (!fromHash()) {
    var keep = location.hash;                          // opening on the default sector should not move the page
    select(Math.max(0, M.codes.indexOf(M.shown)));
    if (history.replaceState) history.replaceState(null, "", keep || location.pathname + location.search);
  }
})();
