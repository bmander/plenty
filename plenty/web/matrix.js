// A matrix page: paints every entry of one of the model's matrices on a canvas, to be zoomed,
// marked and sorted. On the page for A it also takes a marked cell apart and lists one sector's
// column and row. The data file sets window.PLENTY_MATRIX (written by plenty/site.py). No dependencies.
(function () {
  "use strict";
  var M = window.PLENTY_MATRIX, canvas = document.getElementById("mx-canvas");
  if (!M || !canvas) return;
  // nr rows by nc columns; the rows and the columns may be different things, and of different number
  var nr = M.rows.names.length, nc = M.cols.names.length, unit = M.unit, LIST = 12, STEP = M.second ? 3 : 2;
  var LO = Math.log10(M.scale[0]), HI = Math.log10(M.scale[1]);   // the two ends of the colour scale

  // dense copies for the pointer, and each row's entries for "who uses it"
  var value = new Float32Array(nr * nc), capital = new Float32Array(nr * nc), byRow = [];
  for (var r = 0; r < nr; r++) byRow.push([]);
  M.cells.forEach(function (col, j) {
    for (var k = 0; k < col.length; k += STEP) {
      value[col[k] * nc + j] = col[k + 1] * unit;
      if (M.second) capital[col[k] * nc + j] = col[k + 2] * unit;   // the part that is equipment and buildings
      byRow[col[k]].push(j, col[k + 1]);
    }
  });

  function cents(dollars, digits) { return (dollars * 100).toFixed(digits === undefined ? 2 : digits) + "\u00a2"; }
  // For each kind of matrix: a value said in full, and a size (never negative) printed short on a cell.
  function hundredths(x) { x *= 100; return x.toFixed(x >= 99.95 ? 0 : x >= 9.995 ? 1 : 2); }
  function thousands(x) { return x >= 99500 ? Math.round(x / 1000) + "k" : x >= 999.5 ? (x / 1000).toFixed(1) + "k" : String(Math.round(x)); }
  var KINDS = {
    per_dollar: {
      say: function (v) { return cents(v) + " per dollar"; }, cell: hundredths,
      // a total of a dollar or more is said in dollars
      sum: function (v) { return (v >= 0.995 ? "$" + v.toFixed(2) : cents(v, 1)) + " per dollar"; },
      brief: function (v) { return v >= 0.995 ? "$" + v.toFixed(2) : cents(v, 0); }
    },
    share: { say: function (v) { return hundredths(v) + "%"; }, cell: hundredths },
    dollars: {
      say: function (v) { return (v < 0 ? "\u2212$" : "$") + Math.round(Math.abs(v)).toLocaleString("en-US") + " million"; },
      cell: thousands,
      sum: function (v) {
        var a = Math.abs(v), sign = v < 0 ? "\u2212$" : "$";
        return sign + (a >= 1e6 ? (a / 1e6).toFixed(1) + " trillion" : a >= 1e3 ? (a / 1e3).toFixed(1) + " billion" : Math.round(a) + " million");
      },
      brief: function (v) {
        var a = Math.abs(v), sign = v < 0 ? "\u2212$" : "$";
        return sign + (a >= 1e6 ? (a / 1e6).toFixed(1) + "T" : a >= 1e3 ? (a / 1e3).toFixed(a >= 1e4 ? 0 : 1) + "B" : Math.round(a) + "M");
      }
    },
    people: {
      say: function (v) { return Math.round(v).toLocaleString("en-US") + " jobs"; }, cell: thousands,
      sum: function (v) { return Math.round(v).toLocaleString("en-US") + " jobs"; },
      brief: function (v) { return v >= 999500 ? (v / 1e6).toFixed(1) + "M" : v >= 999.5 ? Math.round(v / 1000) + "k" : String(Math.round(v)); }
    },
    wage: {
      say: function (v) { return "$" + Math.round(v).toLocaleString("en-US") + " a year"; },
      cell: function (x) { return Math.round(x / 1000) + "k"; }
    },
    mark: {
      say: function () { return M.marked; }, cell: function () { return "1"; },
      sum: function (v) { return Math.round(v) + " in all"; }, brief: function (v) { return String(Math.round(v)); }
    }
  }, kind = KINDS[M.kind];

  // --- the picture: the whole matrix, or a window on it
  // The matrix is painted once, a pixel a cell, on a sheet off screen. The canvas shows the part
  // of the sheet in view, and the strips beside it name what is in view: groups from far off,
  // each sector once its cells are wide enough to label. Closer still, each cell carries its number.
  // Either axis can be put in the order of one line of the other, and a cell, a row or a column marked.
  var MIN_SPAN = 8;          // the closest view: this many sectors across
  var NAME_PX = 10;          // sectors are named once a cell is this wide
  var VALUE_PX = 32;         // and each cell shows its value, in cents, once it is this wide
  var GROUP_PX = 13;         // a group is named in the far view if it is this wide
  var NAME_FONT = 11, LINE = 1.15;
  var SORT_PX = 12;          // room in a sector's label for its sort button
  var GLYPH = { "0": "\u21c5", "-1": "\u2193", "1": "\u2191" };
  var plot = canvas.parentNode, topStrip = document.getElementById("mx-top"), leftStrip = document.getElementById("mx-left");
  var zoomIn = document.getElementById("mx-zoom-in"), zoomOut = document.getElementById("mx-zoom-out"), zoomAll = document.getElementById("mx-zoom-all");
  var unsort = document.getElementById("mx-unsort"), note = document.getElementById("mx-note");
  var hLine = document.getElementById("mx-h"), vLine = document.getElementById("mx-v");
  // The view: its left and top edge and its width, in cells. Cells are square and the picture has
  // the matrix's shape, so its height in cells follows from its width.
  var view = { x: 0, y: 0, span: nc };
  function down() { return view.span * nr / nc; }
  function home() { return view.span >= nc && !view.x && !view.y; }   // the whole matrix, square in the picture
  plot.style.aspectRatio = nc + " / " + nr;
  var sheet = document.createElement("canvas"), pending = 0, pointer = null, lit = [];
  var stops = [], paper = "#fff", off = "#eee", rule = "#888", faint = "#888", series = "#36c", onLight = "#000", onDark = "#fff", face = "sans-serif";
  sheet.width = nc;
  sheet.height = nr;

  // The picture's two axes. at[p] is the sector drawn at place p, and pos the other way round.
  // by is the line of the other axis this one is sorted by, as {k, dir} with dir 1 for smallest
  // first; sel is the sector marked on it.
  // names, codes and groups are its sectors', in the Bureau's order, and runs the groups as stretches of them.
  function axis(box, side) {
    var a = { box: box, n: side.names.length, names: side.names, codes: side.codes, groups: side.groups, runs: [], at: [], pos: [], by: null, sel: null };
    for (var k = 0; k < a.n; k++) { a.at.push(k); a.pos.push(k); }
    side.groups.forEach(function (g, j) {
      var last = a.runs[a.runs.length - 1];
      if (last && last.name === g) last.to = j + 1;
      else a.runs.push({ name: g, label: M.short[g] || g, from: j, to: j + 1 });
    });
    box.style.setProperty("--sort", SORT_PX + "px");
    return a;
  }
  var rows = axis(leftStrip, M.rows), cols = axis(topStrip, M.cols);
  // Totals, where the page has them: each row's in a strip down the right and each column's in one
  // along the bottom, as bars, with the whole matrix's in the corner between them.
  rows.sums = M.rowSums || null;
  cols.sums = M.colSums || null;
  rows.sumBox = document.getElementById("mx-row-sums");
  cols.sumBox = document.getElementById("mx-col-sums");
  var corner = document.getElementById("mx-total");
  if (corner && M.grand !== undefined) {
    corner.textContent = kind.brief(M.grand);
    corner.setAttribute("data-tip", "The whole matrix: " + kind.sum(M.grand));
  }
  // every surface that zooms, moves and marks: the picture and whatever is in its margins
  var surfaces = [canvas, topStrip, leftStrip, rows.sumBox, cols.sumBox].filter(Boolean);
  rows.other = cols;
  cols.other = rows;
  var selRow = plot.appendChild(el("i", "mx-sel mx-sel-row")), selCol = plot.appendChild(el("i", "mx-sel mx-sel-col"));
  var selCell = plot.appendChild(el("i", "mx-sel mx-sel-cell"));

  function rgb(hex) {
    var h = hex.trim().replace("#", "");
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  function luminance(c) {                             // relative luminance, 0 black to 1 white
    var l = c.map(function (x) { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); });
    return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2];
  }
  function shade(v) {                                 // the colour of a positive value, on the log scale
    var t = Math.min(1, Math.max(0, (Math.log10(v) - LO) / (HI - LO))) * (stops.length - 1);
    var a = stops[Math.floor(t)], b = stops[Math.min(stops.length - 1, Math.floor(t) + 1)], f = t - Math.floor(t);
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
  }
  function paint() {
    var css = getComputedStyle(document.documentElement), get = function (k) { return css.getPropertyValue(k).trim(); };
    stops = [0, 1, 2, 3, 4].map(function (i) { return rgb(get("--heat-" + i)); });
    paper = get("--paper") || paper;
    off = get("--bar") || off;
    rule = get("--rule") || rule;
    faint = get("--ink-2") || faint;
    series = get("--series") || series;
    var ink = get("--ink") || onLight, inkIsDark = luminance(rgb(ink)) < luminance(rgb(paper));
    onLight = inkIsDark ? ink : paper;                // the darker of ink and paper, for numbers on light cells
    onDark = inkIsDark ? paper : ink;
    face = getComputedStyle(document.body).fontFamily;
    var ctx = sheet.getContext("2d"), img = ctx.createImageData(nc, nr);
    for (var i = 0; i < nr; i++) {
      for (var j = 0; j < nc; j++) {
        var v = value[rows.at[i] * nc + cols.at[j]], p = 4 * (i * nc + j);
        if (v <= 0) continue;                         // zero, under the cut, or negative: left blank
        var c = shade(v);
        img.data[p] = c[0];
        img.data[p + 1] = c[1];
        img.data[p + 2] = c[2];
        img.data[p + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  // a cell's value as short as it can be said
  function figure(v) { return (v < 0 ? "\u2212" : "") + kind.cell(Math.abs(v)); }

  function cellPx() { return canvas.clientWidth / view.span; }
  // a number of cells as a share of the picture's width, and of its height
  function wide(cells) { return (cells / view.span * 100).toFixed(3) + "%"; }
  function tall(cells) { return (cells / down() * 100).toFixed(3) + "%"; }
  function named() { return cellPx() >= NAME_PX; }
  // The view can run past the matrix's edges. This is the part of the matrix in it, in cells.
  function seen() {
    return { x0: Math.max(0, view.x), x1: Math.min(nc, view.x + view.span), y0: Math.max(0, view.y), y1: Math.min(nr, view.y + down()) };
  }
  // a line across the picture, and one down it, reach only as far as the matrix does
  function fit(acrossIt, downIt) {
    var s = seen();
    acrossIt.style.left = wide(s.x0 - view.x);
    acrossIt.style.right = wide(view.x + view.span - s.x1);
    downIt.style.top = tall(s.y0 - view.y);
    downIt.style.bottom = tall(view.y + down() - s.y1);
  }

  function render() {
    pending = 0;
    var ratio = window.devicePixelRatio || 1, px = Math.max(1, Math.round(canvas.clientWidth * ratio));
    var py = Math.max(1, Math.round(canvas.clientWidth * ratio * nr / nc));
    if (canvas.width !== px || canvas.height !== py) { canvas.width = px; canvas.height = py; }
    var ctx = canvas.getContext("2d"), cell = px / view.span, line = Math.max(1, Math.round(ratio)), c;
    var s = seen(), X = function (c) { return Math.round((c - view.x) * cell); }, Y = function (c) { return Math.round((c - view.y) * cell); };
    var x0 = X(s.x0), y0 = Y(s.y0), w = X(s.x1) - x0, h = Y(s.y1) - y0;   // the matrix in the picture
    ctx.fillStyle = off;                              // whatever of the picture is off the matrix is tinted
    ctx.fillRect(0, 0, px, py);
    ctx.clearRect(x0, y0, w, h);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(sheet, s.x0, s.y0, s.x1 - s.x0, s.y1 - s.y0, (s.x0 - view.x) * cell, (s.y0 - view.y) * cell, (s.x1 - s.x0) * cell, (s.y1 - s.y0) * cell);
    if (named()) {                                    // close in, a gap of paper between cells
      ctx.fillStyle = paper;
      for (c = Math.ceil(s.x0); c < s.x1; c++) ctx.fillRect(X(c), y0, line, h);
      for (c = Math.ceil(s.y0); c < s.y1; c++) ctx.fillRect(x0, Y(c), w, line);
    }
    ctx.fillStyle = rule;                             // and a rule between groups, on an axis still in groups
    ctx.globalAlpha = named() ? 1 : 0.55;
    if (!cols.by) cols.runs.forEach(function (g) { if (g.from) ctx.fillRect(X(g.from), y0, line, h); });
    if (!rows.by) rows.runs.forEach(function (g) { if (g.from) ctx.fillRect(x0, Y(g.from), w, line); });
    ctx.globalAlpha = 1;
    ctx.fillRect(x0 - line, y0 - line, line, h + 2 * line);           // an edge of the matrix that is in the picture is ruled;
    ctx.fillRect(x0 + w, y0 - line, line, h + 2 * line);              // one at the picture's own edge falls outside it
    ctx.fillRect(x0, y0 - line, w, line);
    ctx.fillRect(x0, y0 + h, w, line);
    if (cellPx() >= VALUE_PX) {                       // closest in, the number on each cell
      ctx.font = "500 " + Math.round(Math.min(14, cellPx() / 3) * ratio) + "px " + face;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (var i = Math.floor(s.y0); i < s.y1; i++) {
        for (var j = Math.floor(s.x0); j < s.x1; j++) {
          var v = value[rows.at[i] * nc + cols.at[j]];
          if (!v) continue;
          ctx.fillStyle = v < 0 ? faint : luminance(shade(v)) > 0.2 ? onLight : onDark;
          ctx.fillText(figure(v), (j + 0.5 - view.x) * cell, (i + 0.5 - view.y) * cell);
        }
      }
    }
    strip(cols, view.x);
    strip(rows, view.y);
    totals(rows, view.y);
    totals(cols, view.x);
    selRow.style.display = rows.sel === null ? "none" : "block";
    selCol.style.display = cols.sel === null ? "none" : "block";
    selCell.style.display = rows.sel === null || cols.sel === null ? "none" : "block";
    fit(selRow, selCol);
    if (rows.sel !== null) { selRow.style.top = selCell.style.top = tall(rows.pos[rows.sel] - view.y); selRow.style.height = selCell.style.height = tall(1); }
    if (cols.sel !== null) { selCol.style.left = selCell.style.left = wide(cols.pos[cols.sel] - view.x); selCol.style.width = selCell.style.width = wide(1); }
    plot.classList.toggle("mx-zoomed", !home());
    zoomIn.disabled = view.span <= MIN_SPAN;
    zoomOut.disabled = view.span >= nc;
    zoomAll.disabled = home();
    unsort.disabled = !rows.by && !cols.by;
    if (pointer) hover(pointer);
  }
  function schedule() { if (!pending) pending = requestAnimationFrame(render); }

  // one strip of totals: a bar for each row or column in view, as long as its total is to the largest
  // total in view, and close in the figure itself
  function totals(a, from) {
    var box = a.sumBox;
    if (!box || !a.sums || !box.clientWidth) return;
    var across = a === cols, ratio = window.devicePixelRatio || 1, span = across ? view.span : down();
    var w = Math.round(box.clientWidth * ratio), h = Math.round(box.clientHeight * ratio);
    if (box.width !== w || box.height !== h) { box.width = w; box.height = h; }
    var ctx = box.getContext("2d"), cell = (across ? w : h) / span, room = (across ? h : w) - 2 * ratio, close = named();
    var gap = close ? Math.max(1, Math.round(ratio)) : 0, most = 0, p, v, at0, length;
    var first = Math.max(0, Math.floor(from)), end = Math.min(a.n, from + span);
    for (p = first; p < end; p++) most = Math.max(most, a.sums[a.at[p]]);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = series;
    ctx.globalAlpha = close ? 0.4 : 0.75;
    for (p = first; p < end; p++) {
      v = a.sums[a.at[p]];
      at0 = Math.round((p - from) * cell) + gap;
      length = most > 0 ? Math.max(0, v) / most * room : 0;
      if (across) ctx.fillRect(at0, 0, Math.max(1, cell - gap), length); else ctx.fillRect(0, at0, length, Math.max(1, cell - gap));
    }
    ctx.globalAlpha = 1;
    if (!close) return;
    ctx.fillStyle = faint;
    ctx.font = Math.round(Math.min(11, cellPx() - 1) * ratio) + "px " + face;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    for (p = first; p < end; p++) {
      var mid = (p + 0.5 - from) * cell, text = kind.brief(a.sums[a.at[p]]);
      if (!across) { ctx.fillText(text, 4 * ratio, mid); continue; }
      ctx.save();                                     // a column's figure is written down the strip
      ctx.translate(mid, 4 * ratio);
      ctx.rotate(Math.PI / 2);
      ctx.fillText(text, 0, 0);
      ctx.restore();
    }
  }
  // which row or column of an axis a pointer is over, in the axis's own strip or its strip of totals
  function placeOn(a, target, e) {
    var box = target.getBoundingClientRect();
    var p = Math.floor(a === rows ? view.y + (e.clientY - box.top) / box.height * down()
                                  : view.x + (e.clientX - box.left) / box.width * view.span);
    return p < 0 || p >= a.n ? null : a.at[p];
  }
  [rows, cols].forEach(function (a) {
    if (!a.sumBox || !a.sums) return;
    a.sumBox.addEventListener("pointermove", function (e) {
      var k = placeOn(a, a.sumBox, e);
      pointer = null;                                 // the pointer is no longer over a cell
      if (k === null) return window.plentyTip.hide();
      window.plentyTip.show((a === rows ? "Total of the row: " : "Total of the column: ") + a.names[k] + "\n" + kind.sum(a.sums[k]), e);
    });
    a.sumBox.addEventListener("pointerleave", function () { window.plentyTip.hide(); });
  });

  // one strip: the groups in view and, close in, a narrow band of groups with each sector's name
  // beside it. An axis that is sorted has no groups to show, and says what it is sorted by instead.
  function strip(a, from) {
    var box = a.box, across = a === cols, share = across ? wide : tall, to = from + (across ? view.span : down());
    var size = cellPx(), names = named();
    function put(cls, lo, hi, tip) {
      var s = el("span", cls);
      s.style[across ? "left" : "top"] = share(lo - from);
      s.style[across ? "width" : "height"] = share(hi - lo);
      s.setAttribute("data-tip", tip);
      box.appendChild(s);
      return s;
    }
    box.textContent = "";
    box.classList.toggle("mx-named", names);
    var band = null;
    if (a.by) {
      band = put("mx-group mx-sorted", Math.max(0, from), Math.min(a.n, to), sortedBy(a));
      band.textContent = sortedBy(a);
    } else a.runs.forEach(function (g, i) {
      var lo = Math.max(g.from, from), hi = Math.min(g.to, to);
      if (hi <= lo) return;
      band = put("mx-group" + (i % 2 ? "" : " alt"), lo, hi, g.name + ": " + (g.to - g.from) + " sectors");
      if (names || (hi - lo) * size >= GROUP_PX) band.textContent = g.label;
    });
    if (!names || !band) return;
    var font = Math.min(NAME_FONT, size / LINE), lines = Math.max(1, Math.floor(size / (font * LINE) + 0.01));
    var length = box.clientHeight - band.offsetHeight - SORT_PX;   // room for a name written up the top strip
    for (var p = Math.max(0, Math.floor(from)); p < Math.min(a.n, Math.ceil(to)); p++) {
      var c = a.at[p], first = !a.by && c && a.groups[c] !== a.groups[c - 1];
      var s = put("mx-name" + (first ? " first" : "") + (a.sel === c ? " sel" : ""), p, p + 1, a.names[c]);
      var text = el("span", lines > 1 ? "mx-text" : "mx-text one", a.names[c]), holder = s;
      text.style.fontSize = font.toFixed(2) + "px";
      text.style.webkitLineClamp = lines;
      if (across) {                                   // written sideways: a row of text turned a quarter turn
        holder = el("span", "mx-turn");
        holder.style.width = length + "px";
        holder.style.height = size + "px";
        holder.style.transform = "translateX(" + size + "px) rotate(-90deg)";
        s.appendChild(holder);
      }
      holder.appendChild(text);
      s.setAttribute("data-i", c);
      s.appendChild(sortButton(a.other, c, true));    // a row's button orders the columns, and a column's the rows
    }
  }

  // --- sorting: one row puts the columns in order, one column the rows
  function direction(a, k) { return a.by && a.by.k === k ? a.by.dir : 0; }
  function sortedBy(a) {
    var name = a.other.names[a.by.k], how = a.by.dir < 0 ? ", largest first" : ", smallest first";
    return (a === cols ? "Columns sorted by the row " : "Rows sorted by the column ") + name + how;
  }
  // what pressing the button for line k would say about axis a, the one it reorders
  function sortText(a, k) {
    var what = a === cols ? ["Columns", "row"] : ["Rows", "column"], d = direction(a, k);
    if (!d) return "Sort the " + what[0].toLowerCase() + " by this " + what[1];
    return what[0] + " sorted by this " + what[1] + (d < 0 ? ", largest first" : ", smallest first");
  }
  function sortButton(a, k, small) {
    var d = direction(a, k), b = el("button", "mx-sort" + (d ? " active" : ""), GLYPH[d] + (small ? "" : " " + sortText(a, k)));
    b.type = "button";
    b.setAttribute("data-axis", a === cols ? "cols" : "rows");
    b.setAttribute("data-k", k);
    if (small) { b.tabIndex = -1; b.setAttribute("data-tip", sortText(a, k)); }
    return b;
  }
  function order(a, by) {
    a.by = by;
    var key = function (x) { return a === rows ? value[x * nc + by.k] : value[by.k * nc + x]; };
    a.at.sort(function (x, y) { return (by ? by.dir * (key(x) - key(y)) : 0) || x - y; });   // ties keep the Bureau's order
    a.at.forEach(function (x, p) { a.pos[x] = p; });
    if (by) view[a === rows ? "y" : "x"] = 0;         // a new order is read from its start
    paint();
    remark();
    settle();
  }
  // largest first, then smallest first, then back to the Bureau's order
  function toggle(a, k) {
    var d = direction(a, k), by = d === 0 ? { k: k, dir: -1 } : d < 0 ? { k: k, dir: 1 } : null;
    if (by) a.other.sel = k;                          // the line sorted by is marked, so unmarking it is what lets go of the sort
    order(a, by);
  }
  plot.closest("figure").addEventListener("click", function (e) {
    var b = e.target.closest("button.mx-sort");
    if (b) toggle(b.getAttribute("data-axis") === "cols" ? cols : rows, +b.getAttribute("data-k"));
  });
  unsort.addEventListener("click", function () { order(rows, null); order(cols, null); });

  // --- marking: a cell with its row and column, or a row or a column alone (null for neither)
  function mark(i, j) {
    var same = rows.sel === i && cols.sel === j;      // marking the same thing again clears it
    var wasRow = rows.sel, wasCol = cols.sel;
    rows.sel = same ? null : i;
    cols.sel = same ? null : j;
    // a row or column that is no longer marked lets go of the order it gave the other axis
    if (wasRow !== null && wasRow !== rows.sel && direction(cols, wasRow)) order(cols, null);
    if (wasCol !== null && wasCol !== cols.sel && direction(rows, wasCol)) order(rows, null);
    remark();
    schedule();
  }
  // the lines under the picture that say what is marked, each with its sort button, and on a page
  // with a sector lookup a way to it
  function remark() {
    var i = rows.sel, j = cols.sel, lookup = document.getElementById("mx-pick");
    function line(label, a, k) {                      // sector k of axis a, whose button sorts the other axis
      var p = el("p"), name = el(lookup ? "a" : "b", "", a.names[k]);
      if (lookup) { name.href = "#sector"; name.setAttribute("data-sector", a.codes[k]); }
      p.appendChild(el("span", "dim", label + " "));
      p.appendChild(name);
      p.appendChild(sortButton(a.other, k, false));
      note.appendChild(p);
    }
    note.textContent = "";
    if (i === null && j === null) note.appendChild(el("p", "dim", "Nothing is marked."));
    if (i !== null) line(M.rowIs, rows, i);
    if (j !== null) line(M.colIs, cols, j);
    if (i !== null && j !== null) {
      note.appendChild(el("p", "", "Cell: " + amount(i, j)));
      if (M.parts) note.appendChild(derivation(i, j));
    }
  }

  // --- how a marked cell of A is made up. A = B D, so the cell is row i of B against column j of D:
  // a term for each industry that makes commodity j. B and D come in a file of their own,
  // fetched when a cell is first marked.
  var WHY = 8;                                        // terms listed before "show all"
  var parts = null, asked = false;                    // parts is false if the file could not be had
  function fetchParts() {
    if (asked) return;
    asked = true;
    var s = document.createElement("script");
    s.src = M.parts;
    s.onload = function () {
      var P = window.PLENTY_MATRIX_PARTS, m = P.industries.length;
      parts = { names: P.industries, m: m, makers: P.D, unit: P.unit, cut: P.cut, use: new Float32Array(nr * m), capital: new Float32Array(nr * m) };
      P.B.forEach(function (col, k) {
        for (var x = 0; x < col.length; x += 3) {
          parts.use[col[x] * m + k] = col[x + 1] * P.unit;
          parts.capital[col[x] * m + k] = col[x + 2] * P.unit;
        }
      });
      remark();
    };
    s.onerror = function () { parts = false; remark(); };
    document.head.appendChild(s);
  }
  function derivation(i, j) {
    var box = el("div", "mx-why"), fine = function (x) { return (x * 100).toFixed(3); };
    box.appendChild(document.getElementById("mx-why").content.cloneNode(true));
    if (!parts) {
      if (parts === null) fetchParts();
      box.appendChild(el("p", "dim", parts === null ? "Fetching the two tables..." : "The two tables could not be fetched."));
      return box;
    }
    var makers = parts.makers[j], terms = [], sum = 0, v = value[i * nc + j];
    for (var x = 0; x < makers.length; x += 2) {
      var k = makers[x], share = makers[x + 1] * parts.unit, use = parts.use[i * parts.m + k];
      terms.push({ name: parts.names[k], share: share, use: use, capital: parts.capital[i * parts.m + k], term: share * use });
      sum += share * use;
    }
    terms.sort(function (a, b) { return Math.abs(b.term) - Math.abs(a.term) || b.share - a.share; });
    box.appendChild(el("p", "", "Row i is " + rows.names[i] + " and column j is " + cols.names[j] + ", which " +
      (terms.length === 1 ? "one industry makes." : terms.length + " industries make.")));
    var wrap = el("div", "scroll"), table = el("table", "ledger"), body = el("tbody");
    table.appendChild(headRow(["Industry k that makes it", "Its share of the commodity", "\u00a2 of the input per dollar of its output",
                               "Of it, equipment and buildings", "Share \u00d7 use, \u00a2"]));
    terms.forEach(function (t) {
      var row = el("tr"), name = el("th", "", t.name);
      name.scope = "row";
      row.appendChild(name);
      [(t.share * 100).toFixed(t.share < 0.0995 ? 2 : 1) + "%", t.use ? fine(t.use) : "under " + fine(parts.cut),
       t.use ? fine(t.capital) : "", fine(t.term)].forEach(function (c) { row.appendChild(el("td", "num", c)); });
      body.appendChild(row);
    });
    table.appendChild(body);
    var foot = [];
    if (v !== 0 && Math.abs(v - sum) >= 0.5 * unit) foot.push(["Smaller terms and rounding", "", "", "", fine(v - sum)]);
    foot.push([v !== 0 ? "The cell" : "The cell, which is under " + cents(M.cut), "", "", "", fine(v !== 0 ? v : sum)]);
    table.appendChild(footRows(foot));
    wrap.appendChild(table);
    box.appendChild(wrap);
    fold(box, body, WHY);
    return box;
  }
  [rows, cols].forEach(function (a) {
    [a.box, a.sumBox].filter(Boolean).forEach(function (target) {
      target.addEventListener("click", function (e) {
        if (slid(e) || e.target.closest("button")) return;
        var k = placeOn(a, target, e);
        if (k === null) return;
        if (a === rows) mark(k, null); else mark(null, k);
      });
    });
  });

  // The view may run past an edge of the matrix by half its own width, at any zoom, so that a cell
  // at the edge can be brought to the middle of the picture.
  function settle() {
    view.span = Math.min(nc, Math.max(MIN_SPAN, view.span));
    var past = view.span / 2, pastDown = past * nr / nc;
    view.x = Math.min(nc - view.span + past, Math.max(-past, view.x));
    view.y = Math.min(nr - down() + pastDown, Math.max(-pastDown, view.y));
    schedule();
  }
  // zoom by a factor, keeping the point (fx, fy) of the picture, each 0 to 1, where it is
  function zoom(factor, fx, fy) {
    var span = Math.min(nc, Math.max(MIN_SPAN, view.span / factor));
    view.x += fx * (view.span - span);
    view.y += fy * (view.span - span) * nr / nc;
    view.span = span;
    settle();
  }
  function whole() { view.x = view.y = 0; view.span = nc; settle(); }

  function cellAt(e) {
    var box = canvas.getBoundingClientRect();
    var x = Math.floor(view.x + (e.clientX - box.left) / box.width * view.span);
    var y = Math.floor(view.y + (e.clientY - box.top) / box.height * down());
    return (x < 0 || y < 0 || x >= nc || y >= nr) ? null : { i: rows.at[y], j: cols.at[x], x: x, y: y };   // the sectors, and their places
  }
  function amount(i, j) {
    var v = value[i * nc + j], k = capital[i * nc + j];
    if (v === 0) return M.blank;
    return kind.say(v) + (M.second && Math.abs(k) >= M.cut ? ", " + cents(k) + " of it equipment and buildings" : "");
  }
  function describe(i, j) { return M.rowTip + ": " + rows.names[i] + "\n" + M.colTip + ": " + cols.names[j] + "\n" + amount(i, j); }
  // far off, a hair line through the cell's row and column; close in, a band around each
  function hover(e) {
    var c = cellAt(e), band = named();
    lit.forEach(function (x) { x.classList.remove("on"); });
    lit = [];
    if (!c) return unhover();
    window.plentyTip.show(describe(c.i, c.j), e);
    hLine.style.display = vLine.style.display = "block";
    hLine.className = vLine.className = band ? "band" : "";
    fit(hLine, vLine);
    hLine.style.top = tall(c.y - view.y + (band ? 0 : 0.5));
    vLine.style.left = wide(c.x - view.x + (band ? 0 : 0.5));
    hLine.style.height = band ? tall(1) : "";
    vLine.style.width = band ? wide(1) : "";
    [[topStrip, c.j], [leftStrip, c.i]].forEach(function (p) {
      var name = p[0].querySelector('[data-i="' + p[1] + '"]');
      if (name) { name.classList.add("on"); lit.push(name); }
    });
  }
  function unhover() {
    pointer = null;
    window.plentyTip.hide();
    hLine.style.display = vLine.style.display = "none";
  }

  // a scroll or a pinch over the picture or its margins zooms it, and is kept from the page.
  // The zoom holds still the point under the pointer, or the nearest point of the picture to it.
  function spot(e) {
    var box = canvas.getBoundingClientRect(), unit = function (x) { return Math.min(1, Math.max(0, x)); };
    return { fx: unit((e.clientX - box.left) / box.width), fy: unit((e.clientY - box.top) / box.height) };
  }
  var pinch = null;
  surfaces.forEach(function (target) {
    target.addEventListener("wheel", function (e) {
      e.preventDefault();
      var at = spot(e), step = -e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.002) * (e.ctrlKey ? 10 : 1);
      zoom(Math.pow(2, step), at.fx, at.fy);
    }, { passive: false });
    // Safari reports a trackpad pinch as a gesture, not a wheel
    target.addEventListener("gesturestart", function (e) {
      e.preventDefault();
      pinch = spot(e);
      pinch.scale = 1;
    });
    target.addEventListener("gesturechange", function (e) {
      e.preventDefault();
      if (!pinch) return;
      zoom(e.scale / pinch.scale, pinch.fx, pinch.fy);
      pinch.scale = e.scale;
    });
    target.addEventListener("gestureend", function () { pinch = null; });
  });

  // Dragging moves the view. With a mouse it takes the wheel button, or Control and the main
  // button, so that a plain press stays a click; a finger or a pen drags as it is, except over
  // the whole matrix in its place, where a finger is left to scroll the page.
  var drag = null, dragged = false, press = null;
  // whether the click that ends a press was really a drag, of the view or of nothing
  function slid(e) {
    var far = press && Math.pow(e.clientX - press.x, 2) + Math.pow(e.clientY - press.y, 2) >= 16, was = dragged || far;
    dragged = false;
    return was;
  }
  function pans(e) {
    if (e.pointerType !== "mouse") return e.button === 0 && !home();
    return e.button === 1 || e.ctrlKey;               // on a Mac, Control can make the main button report as the second
  }
  surfaces.forEach(function (target) {
    target.addEventListener("pointerdown", function (e) {
      dragged = false;
      press = { x: e.clientX, y: e.clientY };
      if (pans(e)) drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, id: e.pointerId };
    });
    target.addEventListener("pointermove", function (e) {
      if (!drag || drag.id !== e.pointerId) return;
      var dx = e.clientX - drag.x, dy = e.clientY - drag.y, box = canvas.getBoundingClientRect();
      if (!dragged && dx * dx + dy * dy < 16) return;                 // not yet a drag
      if (!dragged) {
        dragged = true;
        try { target.setPointerCapture(e.pointerId); } catch (err) { /* the pointer has gone; the drag still follows it over the picture */ }
        plot.classList.add("mx-dragging");
        unhover();
      }
      view.x = drag.vx - dx / box.width * view.span;
      view.y = drag.vy - dy / box.height * down();
      settle();
    });
    target.addEventListener("pointerup", drop);
    target.addEventListener("pointercancel", drop);
    // the wheel button must not start the browser's own scrolling, nor Control and a click open the menu on a Mac
    target.addEventListener("mousedown", function (e) { if (e.button === 1) e.preventDefault(); });
    target.addEventListener("contextmenu", function (e) { if (e.ctrlKey) e.preventDefault(); });
  });
  function drop() { drag = null; plot.classList.remove("mx-dragging"); }
  canvas.addEventListener("pointermove", function (e) {
    if (dragged && drag) return;
    pointer = { clientX: e.clientX, clientY: e.clientY };
    hover(pointer);
  });
  canvas.addEventListener("pointerleave", function () {
    lit.forEach(function (x) { x.classList.remove("on"); });
    unhover();
  });
  canvas.addEventListener("click", function (e) {
    if (slid(e)) return;
    var c = cellAt(e);
    if (c) mark(c.i, c.j);
  });

  zoomIn.addEventListener("click", function () { zoom(2, 0.5, 0.5); });
  zoomOut.addEventListener("click", function () { zoom(0.5, 0.5, 0.5); });
  zoomAll.addEventListener("click", whole);
  canvas.addEventListener("keydown", function (e) {
    var step = view.span / 8, move = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (move) { view.x += move[0] * step; view.y += move[1] * step; settle(); }
    else if (e.key === "+" || e.key === "=") zoom(2, 0.5, 0.5);
    else if (e.key === "-") zoom(0.5, 0.5, 0.5);
    else if (e.key === "0" || e.key === "Escape") whole();
    else return;
    e.preventDefault();
  });

  paint();
  remark();
  render();
  if (window.ResizeObserver) new ResizeObserver(schedule).observe(canvas);
  else window.addEventListener("resize", schedule);
  if (window.matchMedia) {
    var dark = window.matchMedia("(prefers-color-scheme: dark)");
    if (dark.addEventListener) dark.addEventListener("change", function () { paint(); schedule(); });
  }

  // --- one sector's column and row, on the page for A, where rows and columns are the same sectors.
  // The helpers below are used by the picture too; what follows this line runs only with a lookup.
  var pick = document.getElementById("mx-pick"), inBox = document.getElementById("mx-in"), outBox = document.getElementById("mx-out");
  if (!pick) return;
  var names = rows.names, groups = rows.groups, codes = rows.codes;
  var group = null, og = null;
  names.forEach(function (name, j) {
    if (groups[j] !== group) {
      group = groups[j];
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
    var b = el("button", "pick", names[j]);
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
  function headRow(heads) {
    var thead = el("thead"), tr = el("tr");
    heads.forEach(function (h, i) { var th = el("th", i ? "num" : "", h); th.scope = "col"; tr.appendChild(th); });
    thead.appendChild(tr);
    return thead;
  }
  function footRows(rows) {
    var tfoot = el("tfoot");
    rows.forEach(function (cells) {
      var tr = el("tr");
      cells.forEach(function (c, i) { tr.appendChild(el("td", i ? "num" : "", c)); });
      tfoot.appendChild(tr);
    });
    return tfoot;
  }
  // hide a table body's rows after the first few, behind a button that shows them all
  function fold(box, body, shown) {
    if (body.rows.length <= shown) return;
    Array.prototype.forEach.call(body.rows, function (r, i) { r.hidden = i >= shown; });
    var more = el("button", "more", "Show all " + body.rows.length);
    more.type = "button";
    more.addEventListener("click", function () {
      Array.prototype.forEach.call(body.rows, function (r) { r.hidden = false; });
      more.remove();
    });
    box.appendChild(more);
  }
  // rows: [{j, v, k?}], largest first; the list is cut to LIST until "show all" is pressed
  function listTable(box, heads, rows, foot) {
    box.textContent = "";
    var wrap = el("div", "scroll"), table = el("table", "ledger"), body = el("tbody");
    table.appendChild(headRow(heads));
    var vmax = rows.length ? Math.max(rows[0].v, 0) || 1 : 1;
    rows.forEach(function (r) {
      var row = el("tr"), name = el("th");
      name.scope = "row";
      name.appendChild(sectorButton(r.j));
      row.appendChild(name);
      row.appendChild(barCell(r.v, vmax));
      if (r.k !== undefined) row.appendChild(el("td", "num", (r.k * 100).toFixed(2)));
      body.appendChild(row);
    });
    table.appendChild(body);
    if (foot) table.appendChild(footRows(foot));
    wrap.appendChild(table);
    box.appendChild(wrap);
    fold(box, body, LIST);
  }

  function select(j) {
    pick.value = j;
    var name = names[j], col = M.cells[j], inputs = [], users = [], listed = 0, k;
    for (k = 0; k < col.length; k += 3) {
      inputs.push({ j: col[k], v: col[k + 1] * unit, k: col[k + 2] * unit });
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
    if (history.replaceState) history.replaceState(null, "", "#sector=" + codes[j]);
  }
  pick.addEventListener("change", function () { select(+pick.value); });

  // links elsewhere on the page that name a sector, and a sector in the address
  function fromHash() {
    var m = /^#sector=(.+)$/.exec(location.hash), j = m ? codes.indexOf(decodeURIComponent(m[1])) : -1;
    if (j >= 0) select(j);
    return j >= 0;
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-sector]");
    if (!a) return;
    e.preventDefault();
    select(codes.indexOf(a.getAttribute("data-sector")));
    document.getElementById("sector").scrollIntoView({ behavior: "smooth" });
  });
  window.addEventListener("hashchange", fromHash);
  if (!fromHash()) {
    var keep = location.hash;                          // opening on the default sector should not move the page
    select(Math.max(0, codes.indexOf(M.shown)));
    if (history.replaceState) history.replaceState(null, "", keep || location.pathname + location.search);
  }
})();
