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

  // --- the picture: the whole matrix, or a window on it
  // The matrix is painted once, a pixel a cell, on a sheet off screen. The canvas shows the part
  // of the sheet in view, and the strips beside it name what is in view: groups from far off,
  // each sector once its cells are wide enough to label. Closer still, each cell carries its number.
  var MIN_SPAN = 8;          // the closest view: this many sectors across
  var NAME_PX = 10;          // sectors are named once a cell is this wide
  var VALUE_PX = 32;         // and each cell shows its value, in cents, once it is this wide
  var GROUP_PX = 13;         // a group is named in the far view if it is this wide
  var NAME_FONT = 11, LINE = 1.15;
  var plot = canvas.parentNode, topStrip = document.getElementById("mx-top"), leftStrip = document.getElementById("mx-left");
  var zoomIn = document.getElementById("mx-zoom-in"), zoomOut = document.getElementById("mx-zoom-out"), zoomAll = document.getElementById("mx-zoom-all");
  var hLine = document.getElementById("mx-h"), vLine = document.getElementById("mx-v");
  var view = { x: 0, y: 0, span: n };                 // the left and top edge of the view and its width, in cells
  var sheet = document.createElement("canvas"), pending = 0, pointer = null, lit = [];
  var stops = [], paper = "#fff", rule = "#888", faint = "#888", onLight = "#000", onDark = "#fff", face = "sans-serif";
  sheet.width = sheet.height = n;

  var runs = [];                                      // the groups, as runs of sectors
  M.groups.forEach(function (g, j) {
    var last = runs[runs.length - 1];
    if (last && last.name === g) last.to = j + 1;
    else runs.push({ name: g, label: M.short[g] || g, from: j, to: j + 1 });
  });

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
    rule = get("--rule") || rule;
    faint = get("--ink-2") || faint;
    var ink = get("--ink") || onLight, inkIsDark = luminance(rgb(ink)) < luminance(rgb(paper));
    onLight = inkIsDark ? ink : paper;                // the darker of ink and paper, for numbers on light cells
    onDark = inkIsDark ? paper : ink;
    face = getComputedStyle(document.body).fontFamily;
    var ctx = sheet.getContext("2d"), img = ctx.createImageData(n, n);
    for (var p = 0; p < n * n; p++) {
      if (value[p] <= 0) continue;                    // zero, under the cut, or negative: left blank
      var c = shade(value[p]);
      img.data[4 * p] = c[0];
      img.data[4 * p + 1] = c[1];
      img.data[4 * p + 2] = c[2];
      img.data[4 * p + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
  }

  // a cell's value in cents, as short as it can be said
  function figure(v) {
    var c = Math.abs(v) * 100;
    return (v < 0 ? "\u2212" : "") + c.toFixed(c >= 9.995 ? 1 : 2);
  }

  function cellPx() { return canvas.clientWidth / view.span; }
  function named() { return cellPx() >= NAME_PX; }

  function render() {
    pending = 0;
    var ratio = window.devicePixelRatio || 1, px = Math.max(1, Math.round(canvas.clientWidth * ratio));
    if (canvas.width !== px) canvas.width = canvas.height = px;
    var ctx = canvas.getContext("2d"), cell = px / view.span, line = Math.max(1, Math.round(ratio)), c;
    ctx.clearRect(0, 0, px, px);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(sheet, view.x, view.y, view.span, view.span, 0, 0, px, px);
    if (named()) {                                    // close in, a gap of paper between cells
      ctx.fillStyle = paper;
      for (c = Math.ceil(view.x); c < view.x + view.span; c++) ctx.fillRect(Math.round((c - view.x) * cell), 0, line, px);
      for (c = Math.ceil(view.y); c < view.y + view.span; c++) ctx.fillRect(0, Math.round((c - view.y) * cell), px, line);
    }
    ctx.fillStyle = rule;                             // and a rule between groups
    ctx.globalAlpha = named() ? 1 : 0.55;
    runs.forEach(function (g) {
      if (!g.from) return;
      ctx.fillRect(Math.round((g.from - view.x) * cell), 0, line, px);
      ctx.fillRect(0, Math.round((g.from - view.y) * cell), px, line);
    });
    ctx.globalAlpha = 1;
    if (cellPx() >= VALUE_PX) {                       // closest in, the number on each cell
      ctx.font = "500 " + Math.round(Math.min(14, cellPx() / 3) * ratio) + "px " + face;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (var i = Math.floor(view.y); i < Math.min(n, view.y + view.span); i++) {
        for (var j = Math.floor(view.x); j < Math.min(n, view.x + view.span); j++) {
          var v = value[i * n + j];
          if (!v) continue;
          ctx.fillStyle = v < 0 ? faint : luminance(shade(v)) > 0.2 ? onLight : onDark;
          ctx.fillText(figure(v), (j + 0.5 - view.x) * cell, (i + 0.5 - view.y) * cell);
        }
      }
    }
    strip(topStrip, view.x);
    strip(leftStrip, view.y);
    plot.classList.toggle("mx-zoomed", view.span < n);
    zoomIn.disabled = view.span <= MIN_SPAN;
    zoomOut.disabled = zoomAll.disabled = view.span >= n;
    if (pointer) hover(pointer);
  }
  function schedule() { if (!pending) pending = requestAnimationFrame(render); }

  // one strip: the groups in view and, close in, a narrow band of groups with each sector's name beside it
  function strip(box, from) {
    var across = box === topStrip, to = from + view.span, size = cellPx(), names = named();
    function put(cls, a, b, tip) {
      var s = el("span", cls);
      s.style[across ? "left" : "top"] = ((a - from) / view.span * 100).toFixed(3) + "%";
      s.style[across ? "width" : "height"] = ((b - a) / view.span * 100).toFixed(3) + "%";
      s.setAttribute("data-tip", tip);
      box.appendChild(s);
      return s;
    }
    box.textContent = "";
    box.classList.toggle("mx-named", names);
    var band = null;
    runs.forEach(function (g, i) {
      var a = Math.max(g.from, from), b = Math.min(g.to, to);
      if (b <= a) return;
      band = put("mx-group" + (i % 2 ? "" : " alt"), a, b, g.name + ": " + (g.to - g.from) + " sectors");
      if (names || (b - a) * size >= GROUP_PX) band.textContent = g.label;
    });
    if (!names || !band) return;
    var font = Math.min(NAME_FONT, size / LINE), lines = Math.max(1, Math.floor(size / (font * LINE) + 0.01));
    var length = box.clientHeight - band.offsetHeight;          // room for a name written up the top strip
    for (var c = Math.floor(from); c < Math.min(n, Math.ceil(to)); c++) {
      var s = put("mx-name" + (c && M.groups[c] !== M.groups[c - 1] ? " first" : ""), c, c + 1, M.names[c]);
      var text = el("span", lines > 1 ? "mx-text" : "mx-text one", M.names[c]), holder = s;
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
    }
  }

  function settle() {
    view.span = Math.min(n, Math.max(MIN_SPAN, view.span));
    view.x = Math.min(n - view.span, Math.max(0, view.x));
    view.y = Math.min(n - view.span, Math.max(0, view.y));
    schedule();
  }
  // zoom by a factor, keeping the point (fx, fy) of the picture, each 0 to 1, where it is
  function zoom(factor, fx, fy) {
    var span = Math.min(n, Math.max(MIN_SPAN, view.span / factor));
    view.x += fx * (view.span - span);
    view.y += fy * (view.span - span);
    view.span = span;
    settle();
  }
  function whole() { view.x = view.y = 0; view.span = n; settle(); }

  function cellAt(e) {
    var box = canvas.getBoundingClientRect();
    var j = Math.floor(view.x + (e.clientX - box.left) / box.width * view.span);
    var i = Math.floor(view.y + (e.clientY - box.top) / box.height * view.span);
    return (i < 0 || j < 0 || i >= n || j >= n) ? null : { i: i, j: j };
  }
  function describe(i, j) {
    var v = value[i * n + j], k = capital[i * n + j];
    var amount = v === 0 ? "under " + cents(M.cut) + " per dollar" : cents(v) + " per dollar";
    if (v !== 0 && Math.abs(k) >= M.cut) amount += ", " + cents(k) + " of it equipment and buildings";
    return "Input: " + M.names[i] + "\nTo make: " + M.names[j] + "\n" + amount;
  }
  // far off, a hair line through the cell's row and column; close in, a band around each
  function hover(e) {
    var c = cellAt(e), band = named(), pct = function (x) { return (x / view.span * 100).toFixed(3) + "%"; };
    lit.forEach(function (x) { x.classList.remove("on"); });
    lit = [];
    if (!c) return unhover();
    window.plentyTip.show(describe(c.i, c.j), e);
    hLine.style.display = vLine.style.display = "block";
    hLine.className = vLine.className = band ? "band" : "";
    hLine.style.top = pct(c.i - view.y + (band ? 0 : 0.5));
    vLine.style.left = pct(c.j - view.x + (band ? 0 : 0.5));
    hLine.style.height = band ? pct(1) : "";
    vLine.style.width = band ? pct(1) : "";
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

  // pinch, or scroll with Control or Command held; a plain scroll is left to the page
  canvas.addEventListener("wheel", function (e) {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    var box = canvas.getBoundingClientRect();
    var step = -e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.002) * (e.ctrlKey ? 10 : 1);
    zoom(Math.pow(2, step), (e.clientX - box.left) / box.width, (e.clientY - box.top) / box.height);
  }, { passive: false });
  // Safari reports a trackpad pinch as a gesture, not a wheel
  var pinch = null;
  canvas.addEventListener("gesturestart", function (e) {
    e.preventDefault();
    var box = canvas.getBoundingClientRect();
    pinch = { scale: 1, fx: (e.clientX - box.left) / box.width, fy: (e.clientY - box.top) / box.height };
  });
  canvas.addEventListener("gesturechange", function (e) {
    e.preventDefault();
    if (!pinch) return;
    zoom(e.scale / pinch.scale, pinch.fx, pinch.fy);
    pinch.scale = e.scale;
  });
  canvas.addEventListener("gestureend", function () { pinch = null; });

  // drag to move the view; a press that does not move is a click
  var drag = null, dragged = false;
  canvas.addEventListener("pointerdown", function (e) {
    dragged = false;
    if (e.button === 0 && view.span < n) drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, id: e.pointerId };
  });
  canvas.addEventListener("pointermove", function (e) {
    if (drag && drag.id === e.pointerId) {
      var dx = e.clientX - drag.x, dy = e.clientY - drag.y, box = canvas.getBoundingClientRect();
      if (dragged || dx * dx + dy * dy >= 16) {
        if (!dragged) { dragged = true; canvas.setPointerCapture(e.pointerId); plot.classList.add("mx-dragging"); unhover(); }
        view.x = drag.vx - dx / box.width * view.span;
        view.y = drag.vy - dy / box.height * view.span;
        settle();
        return;
      }
    }
    pointer = { clientX: e.clientX, clientY: e.clientY };
    hover(pointer);
  });
  function drop() { drag = null; plot.classList.remove("mx-dragging"); }
  canvas.addEventListener("pointerup", drop);
  canvas.addEventListener("pointercancel", drop);
  canvas.addEventListener("pointerleave", function () {
    lit.forEach(function (x) { x.classList.remove("on"); });
    unhover();
  });
  canvas.addEventListener("click", function (e) {
    if (dragged) { dragged = false; return; }
    var c = cellAt(e);
    if (c) { select(c.j, c.i); document.getElementById("sector").scrollIntoView({ behavior: "smooth" }); }
  });

  zoomIn.addEventListener("click", function () { zoom(2, 0.5, 0.5); });
  zoomOut.addEventListener("click", function () { zoom(0.5, 0.5, 0.5); });
  zoomAll.addEventListener("click", whole);
  canvas.addEventListener("keydown", function (e) {
    var step = view.span / 8, move = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (move && view.span < n) { view.x += move[0] * step; view.y += move[1] * step; settle(); }
    else if (e.key === "+" || e.key === "=") zoom(2, 0.5, 0.5);
    else if (e.key === "-") zoom(0.5, 0.5, 0.5);
    else if (e.key === "0" || e.key === "Escape") whole();
    else return;
    e.preventDefault();
  });

  paint();
  render();
  if (window.ResizeObserver) new ResizeObserver(schedule).observe(canvas);
  else window.addEventListener("resize", schedule);
  if (window.matchMedia) {
    var dark = window.matchMedia("(prefers-color-scheme: dark)");
    if (dark.addEventListener) dark.addEventListener("change", function () { paint(); schedule(); });
  }

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
