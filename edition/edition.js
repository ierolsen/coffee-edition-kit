/* Coffee Edition: renders one issue into A4 page frames and paginates it.
 *
 * The issue is plain data (see README.md). Blocks are grouped into units (a label travels with
 * the block under it, a caption with the block above it) and placed one by one into the current
 * page's three-column flow. When a unit pushes text into a fourth column, it moves whole to a
 * new continuation page. A wide unit (a slide, a wide diagram or wide code) spans all three
 * columns; the text before it is balanced above it and the text after it continues below. The closing band sits on the last page, page numbers are written once
 * the page count is known, and the leading tightens (never the type) only to pull back a
 * nearly empty last page. CoffeeEdition.run() returns a report; nothing here talks to the network.
 *
 * The words the page prints around the article (nameplate, date, "Continued on page 2", the
 * caption leads) come from edition/labels.json; build.mjs passes them in with configure().
 */
(function () {
  "use strict";

  const LEADINGS = [14.5, 14.25, 14]; // px at a fixed 12 px type size
  const SHORT_PAGE = 0.25;            // a last continuation page filled less than this is worth pulling back
  const MAX_PAGES = 4;

  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const pad3 = (n) => String(n).padStart(3, "0");

  // edition/labels.json, set by configure() before anything is laid out
  let L = null;
  function configure(labels) {
    L = labels;
    if (typeof document !== "undefined") document.documentElement.lang = labels.lang;
  }
  // a label with its {placeholders} filled in; the label's own text is escaped, the values are HTML already
  const say = (key, values = {}) => esc(L[key]).replace(/\{(\w+)\}/g, (m, k) => (k in values ? String(values[k]) : m));

  // Inline markup: **bold**, *italic*, `mono`, !!accent!!, _{sub}, ^{sup}; a backslash escapes the next character.
  function inline(text) {
    const kept = [];
    const keep = (html) => "\u0000" + (kept.push(html) - 1) + "\u0000";
    let s = String(text).replace(/\\([\\*`!_^{}])/g, (m, ch) => keep(esc(ch)));
    s = s.replace(/`([^`]+)`/g, (m, code) => keep('<span class="mono">' + esc(code) + "</span>"));
    s = esc(s);
    s = s.replace(/!!(.+?)!!/g, '<strong class="accent">$1</strong>');
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/\*(.+?)\*/g, "<em>$1</em>");
    s = s.replace(/_\{([^}]*)\}/g, "<sub>$1</sub>");
    s = s.replace(/\^\{([^}]*)\}/g, "<sup>$1</sup>");
    // The concatenation bar: no vendored font draws it well, so it is two ruled lines, upright even in italic formulas.
    s = s.replace(/‖/g, '<span class="concat" title="‖"></span>');
    return s.replace(/\u0000(\d+)\u0000/g, (m, i) => kept[Number(i)]);
  }

  function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  function dateLine(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return say("date", { weekday: esc(L.weekdays[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]), day: d, month: esc(L.months[m - 1]), year: y });
  }

  function num(v, decimals) {
    return typeof v === "number" ? v.toFixed(decimals) : esc(v);
  }

  // ---- tables ------------------------------------------------------------------------------

  function cellHTML(v, col, decimals) {
    if (Array.isArray(v)) {
      const [a, b] = v;
      const after = num(b, decimals);
      return num(a, decimals) + " → " + (a === b ? after : "<strong>" + after + "</strong>");
    }
    return typeof v === "number" ? num(v, decimals) : inline(v);
  }

  function dumbbell(pair, chart) {
    const pos = (v) => (((v - chart.min) / (chart.max - chart.min)) * 100).toFixed(2) + "%";
    const [a, b] = pair;
    const lo = Math.min(a, b);
    return '<div class="dumbbell"><i class="track"></i>' +
      (a !== b ? '<i class="span" style="left:' + pos(lo) + ";width:" + (((Math.abs(b - a)) / (chart.max - chart.min)) * 100).toFixed(2) + '%"></i>' : "") +
      '<i class="before" style="left:' + pos(a) + '"></i><i class="after" style="left:' + pos(b) + '"></i></div>';
  }

  function table(t, wide) {
    const decimals = t.decimals == null ? 1 : t.decimals;
    const wrap = el("div", wide ? "table-wrap wide" : "table-wrap");
    const tb = el("table");
    const head = el("tr");
    t.columns.forEach((c, i) => head.appendChild(el("th", c.align === "right" ? "r" : (wide && i > 0 ? "gap-left" : ""), inline(c.label))));
    if (t.chart) head.appendChild(el("th", "chart-h", inline(t.chart.label)));
    if (t.delta) head.appendChild(el("th", "r", inline(t.delta.label)));
    const thead = el("thead");
    thead.appendChild(head);
    tb.appendChild(thead);
    const body = el("tbody");
    t.rows.forEach((row, ri) => {
      const tr = el("tr", ri === t.rows.length - 1 ? "last" : "");
      row.forEach((v, ci) => {
        const c = t.columns[ci] || {};
        const cls = [c.align === "right" ? "r" : (wide && ci > 0 ? "gap-left" : ""), c.tone === "muted" ? "muted" : ""].filter(Boolean).join(" ");
        tr.appendChild(el("td", cls, cellHTML(v, c, decimals)));
      });
      if (t.chart) tr.appendChild(el("td", "chart", dumbbell(row[t.chart.column], t.chart)));
      if (t.delta) {
        const [a, b] = row[t.delta.column];
        tr.appendChild(el("td", "r delta", (b - a >= 0 ? "+" : "") + (b - a).toFixed(decimals)));
      }
      body.appendChild(tr);
    });
    if (t.chart && t.chart.ticks) {
      const axis = el("tr", "axis");
      axis.appendChild(Object.assign(el("td"), { colSpan: t.columns.length }));
      axis.appendChild(el("td", "chart", '<div class="dumbbell">' + t.chart.ticks.map((v) =>
        '<i class="tick" style="left:' + (((v - t.chart.min) / (t.chart.max - t.chart.min)) * 100).toFixed(2) + '%">' + v + "</i>").join("") + "</div>"));
      if (t.delta) axis.appendChild(el("td"));
      body.appendChild(axis);
    }
    tb.appendChild(body);
    wrap.appendChild(tb);
    return wrap;
  }

  // ---- blocks ------------------------------------------------------------------------------

  // Under a picture, table or flow it says what it shows; under code, what the code does.
  const caption = (text, lead = "shows") => el("p", "p caption", "<strong>" + say(lead) + "</strong> " + inline(text));

  const BLOCKS = {
    label: (b) => el("div", "label", inline(b.text)),
    p: (b) => el("p", "p", (b.lead ? '<span class="lead' + (b.lead_accent ? " accent" : "") + '">' + inline(b.lead) + "</span> " : "") + inline(b.text)),
    caption: (b) => caption(b.text),
    steps: (b) => {
      const box = el("div", "steps");
      b.items.forEach((it, i) => box.appendChild(el("div", "step" + (it.accent ? " accent" : ""),
        "<span><strong>" + (i + 1) + "</strong> · " + inline(it.text) + '</span><span class="' + (it.symbol_plain ? "" : "step-symbol") + '">' + inline(it.symbol || "") + "</span>")));
      return box;
    },
    formulas: (b) => {
      const box = el("div", "formulas");
      b.items.forEach((it, i) => box.appendChild(el("div", "formula",
        (i === 0 && b.label ? '<div class="label">' + inline(b.label) + "</div>" : "") +
        '<div class="formula-name">' + inline(it.name) + '</div><div class="formula-line">' + inline(it.formula) + "</div>" +
        '<p class="p"><strong>' + say("says") + "</strong> " + inline(it.says) + "</p>")));
      if (b.symbols) box.appendChild(el("p", "p symbols", "<strong>" + say("symbols") + "</strong> " + inline(b.symbols)));
      return box;
    },
    code: (b) => {
      const box = el("div", b.wide ? "code code-wide" : "code");
      b.lines.forEach((line) => {
        const indent = line.match(/^ */)[0].length;
        const d = el("div");
        d.textContent = line.slice(indent) || " ";
        if (indent) d.style.paddingLeft = indent + "ch";
        box.appendChild(d);
      });
      return box;
    },
    table: (b) => table(b, false),
    image: (b) => figure(b, "slide"),
    diagram: (b) => figure(b, "diagram"),
    bars: (b) => {
      const box = el("div", "bars");
      const max = b.max != null ? b.max : Math.max(...b.rows.map((r) => r[1]));
      const decimals = b.decimals == null ? 1 : b.decimals;
      const accent = new Set(b.accent || []);
      b.rows.forEach(([label, value], i) => {
        const cls = accent.has(i) ? " accent" : "";
        box.appendChild(el("span", "bar-label" + cls, inline(label)));
        const track = el("span", "bar-track" + cls, '<i class="bar-fill"></i>');
        track.firstChild.style.width = Math.max(0, Math.min(100, (value / max) * 100)).toFixed(2) + "%";
        box.appendChild(track);
        box.appendChild(el("span", "bar-value" + cls, esc(b.prefix || "") + num(value, decimals) + esc(b.suffix || "")));
      });
      return box;
    },
  };

  // A picture the build has prepared: a slide from the issue's assets, or a diagram it drew and
  // photographed at print resolution. Its size is known before layout, so nothing shifts later.
  function figure(b, kind) {
    const fig = el("div", "figure " + kind);
    if (!b._img) { fig.style.height = "40px"; fig.style.border = "1px dashed var(--rule)"; return fig; }
    const img = el("img");
    img.alt = "";
    img.src = b._img.src;
    img.style.aspectRatio = b._img.width + " / " + b._img.height;
    if (kind === "diagram") img.style.width = "min(100%, " + b._img.width.toFixed(2) + "px)";
    fig.appendChild(img);
    return fig;
  }

  // ---- Fresh Ink: the night's new AI methods, a newspaper of one to four pages ----------------
  //
  // The radar part of an issue prints as Fresh Ink: a front page (the full masthead on a morning
  // that prints only Fresh Ink, a running head after an article), then inner pages. Cards are
  // stories, two to a row, in the order the writer put them: the first is the lead, its headline
  // the page's H1. Up to four cards marked "brief" go to IN BRIEF on the front page instead. A
  // story may carry a chart redrawn from its source's own table, drawn here at the width it
  // prints at, so its labels never collide or run out of the box (a chart that would is refused,
  // not squeezed). Every story and brief ends in a QR code to its source. The list of the others
  // and how the paper is made close the last page. A row never breaks: one that does not fit moves
  // to the next page, and more than four pages is refused with what to do about it.

  const FI_PAGES = 4;
  const FI_BRIEFS = 4;
  const SVGNS = "http://www.w3.org/2000/svg";

  function svgEl(tag, attrs, text) {
    const e = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, String(v));
    if (text != null) e.textContent = text;
    return e;
  }

  // The QR code's address: the card's link, else its code, else the page its id names.
  function cardLink(c) {
    if (c.link) return c.link;
    if (c.code) return "https://" + String(c.code).replace(/^https?:\/\//, "");
    const m = String(c.id || "").match(/^(arxiv|github|model):(.+)$/);
    if (!m) return null;
    return { arxiv: "https://arxiv.org/abs/", github: "https://github.com/", model: "https://huggingface.co/" }[m[1]] + m[2];
  }

  // A QR code as an SVG path, two modules of quiet zone. M (15% recovery) when the address fits
  // in a small symbol, L for a long one so its modules stay large enough to print and scan.
  function qrSvg(url, px) {
    let q = window.qrcode(0, "M");
    q.addData(url);
    q.make();
    if (q.getModuleCount() > 33) { q = window.qrcode(0, "L"); q.addData(url); q.make(); }
    const n = q.getModuleCount(), quiet = 2, span = n + 2 * quiet;
    let d = "";
    for (let r = 0; r < n; r++) {
      for (let c = 0; c < n; ) {
        if (!q.isDark(r, c)) { c++; continue; }
        const s = c;
        while (c < n && q.isDark(r, c)) c++;
        d += "M" + s + " " + r + "h" + (c - s) + "v1h-" + (c - s) + "z";
      }
    }
    const svg = svgEl("svg", { class: "fi-qr", viewBox: [-quiet, -quiet, span, span].join(" "), width: px, height: px, "shape-rendering": "crispEdges", role: "img", "aria-label": "QR: " + url });
    svg.appendChild(svgEl("path", { d, fill: "#000000" }));
    svg.dataset.url = url;
    return svg;
  }

  // ---- charts: measured with the printing font, laid out to fit, refused when they cannot ----

  let measurer = null;
  function textWidth(s, weight) {
    if (!measurer) {
      measurer = svgEl("svg", { class: "fi-chart-svg", width: 10, height: 10, style: "position:absolute;left:-10000px;top:0" });
      measurer.appendChild(svgEl("text", { x: 0, y: 10 }));
      document.body.appendChild(measurer);
    }
    const t = measurer.firstChild;
    t.setAttribute("font-weight", weight || 400);
    t.textContent = String(s);
    return t.getComputedTextLength();
  }

  const fmt = (v, c) => (c.decimals != null ? Number(v).toFixed(c.decimals) : String(v)) + (c.unit || "");

  // A drawing that keeps the box of every label and mark, so overlaps can be found before print.
  function Plot(W, H, label) {
    const svg = svgEl("svg", { class: "fi-chart-svg", viewBox: "0 0 " + W + " " + H, width: W, height: H, role: "img", "aria-label": label });
    const marks = [], texts = [], segs = [];
    return {
      svg, texts, marks, segs,
      text(x, y, s, o = {}) {
        const w = textWidth(s, o.bold ? 600 : 400);
        const x0 = o.anchor === "end" ? x - w : o.anchor === "middle" ? x - w / 2 : x;
        const box = [x0, y - 9.5, x0 + w, y + 3];
        const t = svgEl("text", { x, y, "text-anchor": o.anchor || "start", "font-weight": o.bold ? 600 : 400 }, s);
        svg.appendChild(t);
        texts.push({ box, s, el: t });
        return box;
      },
      rect(x, y, w, h, style) {
        w = Math.max(w, 1);
        if (style === "solid") svg.appendChild(svgEl("rect", { x, y, width: w, height: h, class: "solid" }));
        else svg.appendChild(svgEl("rect", { x: x + 0.6, y: y + 0.6, width: Math.max(w - 1.2, 0.8), height: h - 1.2, class: style === "hatch" ? "hatch" : "outline" }));
        marks.push([x, y, x + w, y + h]);
      },
      line(x1, y1, x2, y2, cls, track) {
        svg.appendChild(svgEl("line", { x1, y1, x2, y2, class: cls }));
        if (track) segs.push([x1, y1, x2, y2]);
      },
      poly(pts, cls) {
        svg.appendChild(svgEl("polyline", { points: pts.map((p) => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" "), class: cls }));
        for (let i = 1; i < pts.length; i++) segs.push([pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]]);
      },
      dot(x, y, filled) {
        svg.appendChild(svgEl("circle", { cx: x, cy: y, r: 3.4, class: filled ? "dot" : "dot open" }));
        marks.push([x - 3.4, y - 3.4, x + 3.4, y + 3.4]);
      },
      // a label that must not touch other labels, marks or lines, nor leave the drawing
      free(box, skipText) {
        const [a0, a1, a2, a3] = box;
        if (a0 < -0.5 || a2 > W + 0.5 || a1 < -0.5 || a3 > H + 0.5) return false;
        const hit = (b) => a0 < b[2] && b[0] < a2 && a1 < b[3] && b[1] < a3;
        if (texts.some((t) => t !== skipText && hit(t.box)) || marks.some(hit)) return false;
        return !segs.some(([x1, y1, x2, y2]) => {
          for (let k = 0; k <= 20; k++) {
            const px = x1 + ((x2 - x1) * k) / 20, py = y1 + ((y2 - y1) * k) / 20;
            if (px > a0 && px < a2 && py > a1 && py < a3) return true;
          }
          return false;
        });
      },
      // labels drawn with text() overlapping each other or out of the drawing
      clashes() {
        const out = [];
        texts.forEach((t, i) => {
          const [a0, a1, a2, a3] = t.box;
          if (a0 < -0.5 || a2 > W + 0.5) out.push('"' + t.s + '" runs out of the chart');
          texts.slice(i + 1).forEach((u) => {
            const b = u.box;
            if (a0 < b[2] && b[0] < a2 && a1 < b[3] && b[1] < a3) out.push('"' + t.s + '" and "' + u.s + '" overlap');
          });
        });
        return out;
      },
    };
  }

  // Bars, one row each: the accent rows solid, the others outlined; optional second line under
  // a label (`sub`, the hardware), printed value labels (`labels`), a column on the right (`side`).
  function barsChart(c, W, problems) {
    const rows = c.rows, accent = new Set(c.accent || []), sub = c.sub, side = c.side;
    const vlabels = c.labels || rows.map((r) => fmt(r[1], c));
    const bold = (i) => accent.has(i) && !c.all_solid;
    const labelW = Math.max(...rows.map((r, i) => textWidth(r[0], bold(i) ? 600 : 400)), ...(sub || []).map((s) => textWidth(s))) + 8;
    const valueW = Math.max(...vlabels.map((v, i) => textWidth(v, bold(i) ? 600 : 400))) + 7;
    const sideW = side ? Math.max(textWidth(side.label, 600), ...side.values.map((v) => textWidth(String(v), 600))) + 14 : 0;
    const x0 = Math.ceil(labelW), barMax = W - x0 - valueW - sideW - 2;
    if (barMax < 70) problems.push("the labels leave the bars less than 70 px: shorten them");
    const max = c.max != null ? c.max : Math.max(...rows.map((r) => r[1]));
    const rowH = sub ? 31 : 19, top = side ? 17 : 1, H = top + rows.length * rowH + 1;
    const p = Plot(W, H, c.title);
    if (side) p.text(W - 2, 11, side.label, { anchor: "end", bold: true });
    rows.forEach((r, i) => {
      const y = top + i * rowH, w = (Math.max(barMax, 10) * r[1]) / max;
      p.text(x0 - 8, y + 12, r[0], { anchor: "end", bold: bold(i) });
      if (sub) p.text(x0 - 8, y + 25, sub[i], { anchor: "end" });
      p.rect(x0, y + 3, w, 12, c.all_solid || accent.has(i) ? "solid" : "outline");
      p.text(x0 + w + 5, y + 13, vlabels[i], { bold: bold(i) });
      if (side) p.text(W - 2, y + 13, String(side.values[i]), { anchor: "end", bold: bold(i) });
    });
    p.line(x0, top - 1, x0, H, "axis");
    if (side) p.line(W - sideW + 4, top, W - sideW + 4, H, "grid");
    problems.push(...p.clashes());
    return p.svg;
  }

  // The hatching a middle series is filled with: one pattern for every chart, outside the pages.
  function ensureHatch() {
    if (document.getElementById("fi-hatch")) return;
    const defs = svgEl("svg", { width: 0, height: 0, style: "position:absolute;left:0;top:0", "aria-hidden": "true" });
    const pat = svgEl("pattern", { id: "fi-hatch", width: 4, height: 4, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
    pat.appendChild(svgEl("rect", { width: 4, height: 4, fill: "#ffffff" }));
    pat.appendChild(svgEl("line", { x1: 0, y1: 0, x2: 0, y2: 4, stroke: "#000000", "stroke-width": 1.6 }));
    const d = svgEl("defs");
    d.appendChild(pat);
    defs.appendChild(d);
    document.body.appendChild(defs);
  }

  // Groups of two or three bars per row; the last series is the one the story is about (solid),
  // a middle one hatched, the first outlined. With short series names the values stand in
  // columns on the right, each headed by its series' name and swatch, so they never sit on the
  // bars; with long names a legend row heads the chart and each value follows its bar.
  function groupsChart(c, W, problems) {
    const k = c.series.length, styles = k === 3 ? ["outline", "hatch", "solid"] : ["outline", "solid"];
    if (k === 3) ensureHatch();
    const last = (j) => j === k - 1;
    const vals = c.rows.map((r) => r.slice(1).map((v) => fmt(v, c)));
    const labelW = Math.max(...c.rows.map((r) => textWidth(r[0]))) + 8;
    const x0 = Math.ceil(labelW);
    const colW = c.series.map((s, j) => Math.max(textWidth(s, last(j) ? 600 : 400) + 16, ...vals.map((r) => textWidth(r[j], last(j) ? 600 : 400))) + 10);
    const valuesW = colW.reduce((a, b) => a + b, 0);
    const columns = W - x0 - valuesW - 6 >= 60;
    const max = c.max != null ? c.max : Math.max(...c.rows.flatMap((r) => r.slice(1)));
    // with the values at the bar ends, the bars of a row stand 14 px apart so their labels clear each other
    const bh = k === 3 ? (columns ? 8 : 9) : 10, gap = columns ? 2 : 14 - (k === 3 ? 9 : 10);
    const rowH = k * bh + (k - 1) * gap + 9, top = 18, H = top + c.rows.length * rowH;
    const p = Plot(W, H, c.title);
    if (columns) {
      const barMax = W - x0 - valuesW - 6;
      let x = W;
      const colRight = [];
      for (let j = k - 1; j >= 0; j--) { colRight[j] = x - 2; x -= colW[j]; }
      c.series.forEach((s, j) => {
        p.rect(colRight[j] - textWidth(s, last(j) ? 600 : 400) - 16, 3, 11, 9, styles[j]);
        p.text(colRight[j], 11, s, { anchor: "end", bold: last(j) });
      });
      c.rows.forEach((r, i) => {
        const y = top + i * rowH;
        p.text(x0 - 8, y + rowH / 2 + 1, r[0], { anchor: "end" });
        r.slice(1).forEach((v, j) => {
          p.rect(x0, y + j * (bh + gap), (barMax * v) / max, bh, styles[j]);
          p.text(colRight[j], y + rowH / 2 + 1, vals[i][j], { anchor: "end", bold: last(j) });
        });
      });
      p.line(W - valuesW + 2, top - 2, W - valuesW + 2, H - 4, "grid");
    } else {
      const valueW = Math.max(...vals.flat().map((v) => textWidth(v, 600))) + 7;
      const barMax = W - x0 - valueW - 2;
      if (barMax < 70) problems.push("the labels leave the bars less than 70 px: shorten them");
      let lx = x0;
      c.series.forEach((s, j) => {
        p.rect(lx, 3, 11, 9, styles[j]);
        p.text(lx + 15, 11, s, { bold: last(j) });
        lx += 15 + textWidth(s, last(j) ? 600 : 400) + 14;
      });
      if (lx - 14 > W + 1) problems.push("the legend is wider than the chart: shorten the series names");
      c.rows.forEach((r, i) => {
        const y = top + i * rowH;
        p.text(x0 - 8, y + rowH / 2 + 1, r[0], { anchor: "end" });
        r.slice(1).forEach((v, j) => {
          const w = (Math.max(barMax, 10) * v) / max;
          p.rect(x0, y + j * (bh + gap), w, bh, styles[j]);
          p.text(x0 + w + 5, y + j * (bh + gap) + bh - 0.5, vals[i][j], { bold: last(j) });
        });
      });
    }
    p.line(x0, top - 2, x0, H - 4, "axis");
    problems.push(...p.clashes());
    return p.svg;
  }

  // Lines over categories (x.labels) or numbers (x.values, optionally on a log scale): the first
  // series thick with filled dots, the others thin with open dots, dashed reference lines (refs).
  // A point may carry its own label as a third element; each is placed right, left, above or
  // below its point, wherever it touches nothing, and the chart is refused when none is free.
  function lineChart(c, W, problems) {
    const xs = c.x.labels || c.x.values, byLabel = !!c.x.labels;
    const ticks = c.y.ticks || [c.y.min, c.y.max];
    const tickW = Math.max(...ticks.map((t) => textWidth(fmt(t, { decimals: c.y.decimals })))) + 6;
    const ends = c.series.map((s) => { const last = s.points[s.points.length - 1]; return last.length > 2 ? String(last[2]) : fmt(last[1], c); });
    const endW = Math.max(...ends.map((e, i) => textWidth(e, i === 0 ? 600 : 400))) + 9;
    const x0 = Math.ceil(tickW) + 2, x1 = W - endW - 4, top = 22, y1 = top + 96, H = y1 + (c.x.title ? 36 : 22);
    if (x1 - x0 < 120) problems.push("the end labels leave the plot less than 120 px: shorten them");
    const log = !!c.x.log, lo = Math.min(...(byLabel ? [0] : xs)), hi = Math.max(...(byLabel ? [xs.length - 1] : xs));
    const pad = byLabel ? 14 : 0;
    const X = (v) => {
      const t = byLabel ? xs.indexOf(v) : v;
      const f = byLabel ? t / Math.max(1, xs.length - 1) : log ? Math.log(t / lo) / Math.log(hi / lo) : (t - lo) / (hi - lo || 1);
      return x0 + pad + f * (x1 - x0 - 2 * pad);
    };
    const Y = (v) => y1 - ((v - c.y.min) / (c.y.max - c.y.min)) * (y1 - top);
    const p = Plot(W, H, c.title);
    // the legend: a short stroke and dot per series, then its name
    let lx = x0;
    c.series.forEach((s, i) => {
      p.line(lx, 8, lx + 16, 8, i === 0 ? "series" : "series thin", false);
      p.dot(lx + 8, 8, i === 0);
      p.text(lx + 22, 12, s.name, { bold: i === 0 });
      lx += 22 + textWidth(s.name, i === 0 ? 600 : 400) + 16;
    });
    if (lx - 16 > W + 1) problems.push("the legend is wider than the chart: shorten the series names");
    ticks.forEach((t) => {
      p.line(x0, Y(t), x1, Y(t), "grid", false);
      p.text(x0 - 6, Y(t) + 4, fmt(t, { decimals: c.y.decimals }), { anchor: "end" });
    });
    xs.forEach((v) => {
      p.line(X(v), y1, X(v), y1 + 4, "axis", false);
      p.text(X(v), y1 + 18, String(v), { anchor: "middle" });
    });
    if (c.x.title) p.text((x0 + x1) / 2, y1 + 32, c.x.title, { anchor: "middle" });
    (c.refs || []).forEach((r) => p.line(x0, Y(r.y), x1, Y(r.y), "ref", true));
    c.series.forEach((s, i) => p.poly(s.points.map((pt) => [X(pt[0]), Y(pt[1])]), i === 0 ? "series" : "series thin"));
    c.series.forEach((s, i) => s.points.forEach((pt) => p.dot(X(pt[0]), Y(pt[1]), i === 0)));
    // each reference line's label sits on it, at its left end or, when that is taken, its right
    (c.refs || []).forEach((r) => {
      const w = textWidth(r.label), y = Y(r.y);
      const spot = [[x0 + 4, y - 4], [x1 - 4 - w, y - 4], [x0 + 4, y + 13], [x1 - 4 - w, y + 13]].find(([sx, sy]) => p.free([sx, sy - 9.5, sx + w, sy + 3]));
      if (!spot) problems.push('no free place for the label "' + r.label + '"');
      else p.text(spot[0], spot[1], r.label);
    });
    // point labels: the last point of every series, and any point that names its own
    const wanted = [];
    c.series.forEach((s, i) => s.points.forEach((pt, j) => {
      if (j === s.points.length - 1) wanted.push([pt, ends[i], i === 0, true]);
      else if (pt.length > 2) wanted.push([pt, String(pt[2]), i === 0, false]);
    }));
    for (const [pt, s, bold, isEnd] of wanted) {
      const x = X(pt[0]), y = Y(pt[1]), w = textWidth(s, bold ? 600 : 400);
      const spots = (isEnd ? [[x + 7, y + 4], [x + 7, y - 7], [x + 7, y + 15]] : [])
        .concat([[x + 7, y + 4], [x - 7 - w, y + 4], [x - w / 2, y - 8], [x - w / 2, y + 17], [x + 6, y - 7], [x + 6, y + 15], [x - 6 - w, y - 7], [x - 6 - w, y + 15]]);
      const spot = spots.find(([sx, sy]) => p.free([sx, sy - 9.5, sx + w, sy + 3]));
      if (!spot) { problems.push('no free place for the label "' + s + '"'); continue; }
      p.text(spot[0], spot[1], s, { bold });
    }
    p.line(x0, top - 4, x0, y1, "axis", false);
    problems.push(...p.clashes());
    return p.svg;
  }

  const CHARTS = { bars: barsChart, groups: groupsChart, line: lineChart };

  // A chart with its title above and, below, what it shows and where its data comes from.
  function chartBlock(c, W, problems) {
    const box = el("div", "fi-chart");
    box.appendChild(el("div", "fi-chart-title", inline(c.title)));
    const holder = el("div", "fi-chart-holder");
    holder.appendChild(CHARTS[c.kind](c, W, problems));
    box.appendChild(holder);
    box.appendChild(el("p", "fi-shows", "<strong>" + say("shows") + "</strong> " + inline(c.what) + ' <span class="fi-data"><strong>' + say("fi_data") + "</strong> " + inline(c.table) + "</span>"));
    return box;
  }

  // the card's source line: its code without the scheme (breaking after a slash) and its source
  const sourceLine = (c) => el("div", "fi-src",
    (c.code ? esc(c.code).replace(/\//g, "/<wbr>") + "<br>" : "") + inline(c.source).replace(/arXiv /g, "arXiv\u00a0"));

  // A story: kicker, headline, what and how in one paragraph, the chart or the number callout,
  // when to use it, and the QR code with the source. The lead's headline and what are the page's
  // H1 and deck, so its story leaves them out.
  function fiStory(c, i, W, problems, lead) {
    const s = el("article", "fi-story fi-box");
    s.dataset.card = String(i);
    s.appendChild(el("div", "fi-kicker", inline(c.area) + (c.signal ? " \u00b7 " + inline(c.signal) : "")));
    if (!lead) s.appendChild(el("h2", "fi-head", inline(c.headline || c.name)));
    s.appendChild(el("p", "fi-body", "<strong>" + inline(c.name) + ".</strong> " + (lead ? "" : inline(c.what) + " ") + inline(c.how)));
    if (c.chart) s.appendChild(chartBlock(c.chart, W, problems));
    else s.appendChild(el("div", "fi-number", '<div class="value">' + inline(c.number.value) + '</div><div class="says">' + inline(c.number.says) + "</div>"));
    const foot = el("div", "fi-foot");
    const words = el("div", "fi-foot-words");
    words.appendChild(el("p", "fi-when", "<strong>" + say("radar_when") + "</strong> " + inline(c.when)));
    words.appendChild(el("div", "fi-src", inline(c.source).replace(/arXiv /g, "arXiv\u00a0")));
    foot.appendChild(words);
    const link = cardLink(c);
    if (link) foot.appendChild(qrSvg(link, 56));
    s.appendChild(foot);
    return s;
  }

  // IN BRIEF: up to four cards in a row of columns, each its name, what it is, its number and QR.
  function fiBriefs(cards) {
    const box = el("section", "fi-briefs fi-box");
    box.appendChild(el("div", "fi-section-head", '<span class="fi-rule"></span><span>' + say("fi_brief") + '</span><span class="fi-rule"></span>'));
    const grid = el("div", "fi-briefs-grid");
    grid.style.gridTemplateColumns = "repeat(" + Math.max(cards.length, 2) + ", minmax(0, 1fr))";
    cards.forEach(({ c, i }) => {
      const b = el("div", "fi-brief fi-box");
      b.dataset.card = String(i);
      b.appendChild(el("p", "fi-brief-text", "<strong>" + inline(c.name) + ".</strong> " + inline(c.what) + " <strong>" + inline(c.number.value) + "</strong> " + inline(c.number.says)));
      const foot = el("div", "fi-foot");
      foot.appendChild(el("div", "fi-src", inline(c.source)));
      const link = cardLink(c);
      if (link) foot.appendChild(qrSvg(link, 52));
      b.appendChild(foot);
      grid.appendChild(b);
    });
    box.appendChild(grid);
    return box;
  }

  // The others worth a look: one line each, the work's short name and why.
  function fiAlso(also) {
    const box = el("section", "fi-also fi-box");
    box.appendChild(el("div", "fi-section-head left", "<span>" + say("radar_also") + '</span><span class="fi-rule"></span>'));
    also.forEach((a) => {
      const name = String(a.title).split(": ")[0].replace(/[\u2013\u2014]/g, "-");  // the paper's own name; no dashes print
      const stop = /[.?!:]$/.test(name) ? "" : ".";   // "Has X Achieved Y?" keeps its own mark
      box.appendChild(el("p", "fi-also-item", "<strong>" + inline(name) + stop + "</strong> " + inline(a.text)));
    });
    return box;
  }

  // How the paper is made, with what was scanned for this issue, by source, to scale.
  const SOURCES = [["arxiv", "fi_src_arxiv"], ["hf", "fi_src_hf"], ["hn", "fi_src_hn"], ["trending", "fi_src_trending"],
    ["letters", "fi_src_letters"], ["blogs", "fi_src_blogs"], ["github", "fi_src_github"], ["models", "fi_src_models"]];
  function fiMade(issue, W, problems) {
    const r = issue.radar, n = r.scanned;
    const box = el("section", "fi-made fi-box");
    box.appendChild(el("div", "fi-made-title", say("fi_made_title")));
    box.appendChild(el("p", "fi-made-text", say("fi_made", { time: esc(issue.print_time || "") })));
    const rows = SOURCES.filter(([k]) => n[k]).map(([k, label]) => [L[label], n[k]]).sort((a, b) => b[1] - a[1]);
    if (rows.length >= 2) {
      box.appendChild(el("div", "fi-chart-title", say("fi_scanned_title")));
      const holder = el("div", "fi-chart-holder");
      holder.appendChild(barsChart({ title: L.fi_scanned_title, rows, all_solid: true }, W - 22, problems));
      box.appendChild(holder);
    }
    const total = Object.values(n).reduce((a, b) => a + b, 0);
    box.appendChild(el("p", "fi-made-text", say("fi_scanned_total", { total, count: r.items.length })));
    return box;
  }

  // INSIDE: what each later page holds, by name, filled in once the pages are known.
  function fiInside() {
    return el("p", "fi-inside fi-box", '<span class="fi-inside-label">' + say("fi_inside") + "</span>");
  }

  // A column of an inner Fresh Ink page: its free height, and whether what it holds overflows.
  function colFree(col) {
    const box = col.getBoundingClientRect();
    const last = col.lastElementChild;
    return last ? box.bottom - 2 - last.getBoundingClientRect().bottom : box.height - 2;
  }
  const colOverflows = (col) => col.scrollHeight > col.clientHeight || colFree(col) < 0;

  // The free height at the foot of a Fresh Ink page's flow, in px; on an inner page, its fuller column's.
  function freshFree(pg) {
    if (pg.cols) return Math.min(...pg.cols.map(colFree));
    const box = pg.flow.getBoundingClientRect();
    const kids = [...pg.flow.children];
    const gap = parseFloat(getComputedStyle(pg.flow).rowGap) || 0;
    const used = kids.reduce((n, u) => n + u.getBoundingClientRect().height, 0) + gap * Math.max(0, kids.length - 1);
    return box.height - 2 - used;   // less the flow's 2 px of padding; INSIDE sits at the foot of the front page, so its gap above is free room too
  }

  const fiRow = (...cells) => {
    const row = el("div", "fi-row");
    cells.forEach((x) => row.appendChild(x));
    return row;
  };

  // A Fresh Ink page overflows when its flow box no longer holds what it was given.
  // Two pixels are kept free at the foot, so a rule or a descender never touches the footer.
  function freshOverflows(pg) {
    if (pg.cols && pg.cols.some(colOverflows)) return true;
    const box = pg.flow.getBoundingClientRect();
    if (pg.flow.scrollHeight > pg.flow.clientHeight) return true;
    for (const u of pg.flow.children) {
      const r = u.getBoundingClientRect();
      if (r.bottom > box.bottom - 1.5 || r.right > box.right + 1) return true;   // .fi-flow keeps 2 px of padding there
    }
    return [...pg.flow.querySelectorAll(".fi-box")].some((b) => b.scrollWidth > b.clientWidth + 1);
  }

  // The width a story's chart prints at: half the flow, less the gap between the columns.
  function freshWidths(issue) {
    const pg = frame("fresh", issue, { cont: true, no: 2 });
    document.getElementById("edition").appendChild(pg.el);
    const box = pg.flow.getBoundingClientRect();
    const probe = el("div", "fi-cols", '<div class="fi-col"><div class="fi-story fi-box"></div></div><div class="fi-col"></div>');
    pg.flow.appendChild(probe);
    const front = fiRow(el("div", "fi-story fi-box"), el("div", "fi-story fi-box"));
    pg.flow.appendChild(front);
    const w = Math.min(probe.querySelector(".fi-story").getBoundingClientRect().width, front.firstChild.getBoundingClientRect().width);
    pg.el.remove();
    return { flow: box.width, story: Math.floor(w) };
  }

  // Lays the radar part out as Fresh Ink pages through add(); returns the error, or null.
  function freshLayout(issue, add) {
    const r = issue.radar, items = r.items || [];
    const W = freshWidths(issue), problems = [];
    const briefs = [], stories = [];
    items.forEach((c, i) => (c.brief ? briefs : stories).push({ c, i }));
    if (briefs.length > FI_BRIEFS) return "Fresh Ink: " + briefs.length + " briefs; IN BRIEF holds " + FI_BRIEFS;
    if (stories.length < 2) return "Fresh Ink: the front page needs two stories (cards without \"brief\")";
    const story = ({ c, i }, lead) => {
      const own = [];
      const s = fiStory(c, i, W.story, own, lead);
      problems.push(...own.map((m) => "radar.items[" + i + "].chart: " + m));
      return s;
    };
    const lead = stories[0];
    const front = add("fresh", "radar", { lead: lead.c });
    const pages = [front];
    front.flow.appendChild(fiRow(story(lead, true), story(stories[1])));
    if (briefs.length) front.flow.appendChild(fiBriefs(briefs));
    const inside = fiInside();
    front.flow.appendChild(inside);
    if (problems.length) return [...new Set(problems)].join("; ");
    if (freshOverflows(front)) return "Fresh Ink: the front page does not fit: shorten the two lead stories (" +
      [lead, stories[1]].map((s) => "radar.items[" + s.i + "]").join(", ") + "), drop a chart there, or move a brief to the stories";

    // The rest flows like a newspaper's inner page: two columns, each story into the column with
    // the more room. When the next story does not fit there, one of the three after it that does
    // fits takes its place, so no column is left half empty; the story waits for the next page.
    // The list of the others and how the paper is made close the last page. A story never breaks.
    const also = r.also && r.also.length ? r.also : null;
    const queue = stories.slice(2).map((s) => ({ cards: [s], make: () => story(s), what: "radar.items[" + s.i + "]" }));
    const closing = [];
    if (also) closing.push({ cards: [], make: () => fiAlso(also), what: "the list of the others (radar.also)" });
    closing.push({ cards: [], make: () => fiMade(issue, W.story, problems), what: "how the paper is made" });
    let pg = null;
    const newPage = () => {
      pg = add("fresh", "radar", { cont: true });
      pages.push(pg);
      pg.cards = [];
      const cols = el("div", "fi-cols");
      pg.cols = [el("div", "fi-col"), el("div", "fi-col")];
      pg.cols.forEach((col) => cols.appendChild(col));
      pg.flow.appendChild(cols);
    };
    const roomiest = () => pg.cols.reduce((a, c) => (colFree(c) > colFree(a) ? c : a));
    const tryIn = (col, b) => {
      const node = b.make();
      col.appendChild(node);
      if (!colOverflows(col)) return true;
      node.remove();
      return false;
    };
    newPage();
    while (queue.length) {
      const col = roomiest();
      const k = queue.slice(0, 4).findIndex((b) => tryIn(col, b));
      if (k >= 0) { pg.cards.push(...queue.splice(k, 1)[0].cards); continue; }
      if (!pg.cols.some((c) => c.children.length)) return "Fresh Ink: " + queue[0].what + " does not fit in an empty column: shorten it";
      newPage();
    }
    for (const b of closing) {
      if (tryIn(roomiest(), b)) continue;
      newPage();
      if (!tryIn(pg.cols[0], b)) return "Fresh Ink: " + b.what + " does not fit in an empty column: shorten it";
    }
    // INSIDE: the names on each later page, by the page's number in the paper; the front page must still fit with them
    pages.slice(1).forEach((p) => {
      const names = p.cards.map((s) => inline(s.c.name));
      if (p === pages[pages.length - 1] && also) names.push(say("fi_inside_more", { count: also.length }));
      inside.appendChild(el("span", "fi-inside-page", "<strong>" + say("fi_inside_page", { page: p.no }) + "</strong> " + names.join(", ")));
    });
    if (freshOverflows(front)) return "Fresh Ink: the front page does not fit once INSIDE lists the later pages: shorten the two lead stories";
    if (pages.length > FI_PAGES) return "Fresh Ink runs to " + pages.length + " pages; at most " + FI_PAGES +
      ": mark more cards \"brief\" (up to " + FI_BRIEFS + "), drop a chart or two, shorten the stories, or cut a card";
    return problems.length ? [...new Set(problems)].join("; ") : null;
  }

  const isWide = (b) => b.type === "image" ? b.wide !== false : !!b.wide;

  function units(blocks) {
    const out = [];
    let glue = false;
    let prev = null;
    for (const b of blocks) {
      const parts = b.type === "bullets"
        ? b.items.map((t) => { const d = el("div", "bullet"); d.appendChild(el("p", null, inline(t))); return d; })
        : b.type === "caption" ? [caption(b.text, prev && prev.type === "code" ? "does" : "shows")]
        : [BLOCKS[b.type](b)];
      parts.forEach((node) => {
        if (glue || (b.type === "caption" && out.length)) out[out.length - 1].appendChild(node);
        else { const u = el("div", "unit"); u.appendChild(node); out.push(u); }
        if (isWide(b)) out[out.length - 1].classList.add("wide");
        if (["image", "diagram", "bars", "code"].includes(b.type)) out[out.length - 1].classList.add("keep");
        glue = false;
      });
      if (b.type === "label") glue = true;
      prev = b;
    }
    return out;
  }

  // ---- page frames -------------------------------------------------------------------------

  // A Fresh Ink page: on a morning that prints only Fresh Ink its front page carries the full
  // masthead (ears, nameplate, edition bar); after an article, and on every later page, the
  // running head. Then the flag, and on the front page the lead's headline and what it is.
  function freshFrame(issue, extra) {
    const page = el("section", "page page-fresh");
    const r = issue.radar, n = r.scanned || {};
    const total = Object.values(n).reduce((a, b) => a + b, 0);
    const radarOnly = !(issue.front && issue.front.length);
    if (!extra.cont && radarOnly) {
      page.appendChild(el("header", "fi-mast",
        '<div class="fi-ear">' + say("fi_ear_scanned", { total }) + '</div><span class="nameplate">' + say("nameplate") +
        '</span><div class="fi-ear">' + say("fi_ear_checked") + "</div>"));
      page.appendChild(el("div", "fi-bar",
        "<span>" + say("issue", { issue: pad3(issue.issue) }) + (issue.print_time ? " · " + say("print_time", { time: esc(issue.print_time) }) : "") +
        "</span><span>" + dateLine(issue.date) + "</span><span>" + say("fi_count", { count: r.items.length }) + "</span>"));
    } else if (extra.cont) {
      // a later page: the flag rides in the running head, with where the paper goes on from
      page.appendChild(el("header", "running fi-running",
        '<div><span class="nameplate">' + say("nameplate") + '</span><span class="fi-flag">' + say("fi_flag") + '</span><span class="running-title">' +
        say("fi_continued", { page: extra.no - 1 }) + '</span></div><span class="running-meta">' + dateLine(issue.date) + " · " + say("issue", { issue: pad3(issue.issue) }) + "</span>"));
    } else {
      page.appendChild(el("header", "running",
        '<div><span class="nameplate">' + say("nameplate") + '</span><span class="running-title">' + say("radar_running") + "</span></div>" +
        '<span class="running-meta">' + dateLine(issue.date) + " · " + say("issue", { issue: pad3(issue.issue) }) + "</span>"));
    }
    if (!extra.cont) page.appendChild(el("div", "fi-flag-row",
      '<span class="fi-flag">' + say("fi_flag") + '</span><span class="fi-flag-rule"></span><span class="fi-flag-tag">' + say("fi_tagline") + "</span>"));
    if (!extra.cont) {
      const lead = extra.lead || {};
      page.appendChild(el("h1", "fi-h1", inline(lead.headline || r.headline)));
      page.appendChild(el("p", "fi-deck", inline(lead.what || "")));
    }
    const flow = el("div", "fi-flow");
    page.appendChild(flow);
    const foot = el("footer", "foot", '<span class="foot-left">' + say("radar_sources") + '</span><span class="foot-right"></span>');
    page.appendChild(foot);
    return { el: page, kind: "fresh", flow, end: null, foot };
  }

  function frame(kind, issue, extra = {}) {
    if (kind === "fresh") return freshFrame(issue, extra);
    const page = el("section", "page page-" + kind);
    if (kind === "front") {
      page.appendChild(el("header", "masthead",
        '<div class="mast-row"><span class="nameplate">' + say("nameplate") + '</span><div class="mast-meta"><span>' + dateLine(issue.date) +
        "</span><span>" + say("issue", { issue: pad3(issue.issue) }) + " · " + (issue.print_time ? say("print_time", { time: esc(issue.print_time) }) : esc(issue.edition)) +
        '</span></div></div><div class="mast-rule"></div>'));
      page.appendChild(el("section", "article-head",
        '<div class="kicker-row"><span class="kicker">' + inline(issue.kicker) + '</span><span class="byline">' + inline(issue.byline) +
        "</span></div><h1>" + inline(issue.headline) + '</h1><p class="standfirst">' + inline(issue.standfirst) + "</p>"));
    } else {
      page.appendChild(el("header", "running",
        '<div><span class="nameplate">' + say("nameplate") + '</span><span class="running-title">' + say("continued", { title: inline(issue.short_title) }) + "</span></div>" +
        '<span class="running-meta">' + dateLine(issue.date) + " · " + say("issue", { issue: pad3(issue.issue) }) + "</span>"));
    }
    if (kind === "results") {
      const r = issue.results;
      const s = el("section", "results");
      s.appendChild(el("div", "results-head", "<h2>" + inline(r.headline) + '</h2><span class="label">' + inline(r.label) + "</span>"));
      s.appendChild(table(r.table, true));
      if (r.caption) s.appendChild(caption(r.caption));
      page.appendChild(s);
    }
    const flow = el("div", "flow");
    const end = el("div", "flow-end");
    flow.appendChild(end);
    page.appendChild(flow);
    const sources = kind === "front" && issue.sources && issue.sources.length
      ? say("sources") + " " + issue.sources.map((s) => '<a href="' + esc(s.url) + '">' + inline(s.text) + "</a>").join(" · ")
      : "";
    const foot = el("footer", "foot", '<span class="foot-left">' + sources + '</span><span class="foot-right"></span>');
    page.appendChild(foot);
    return { el: page, kind, flow, end, foot };
  }

  // Text that does not fit lands in a column past the flow box's right edge; the end marker follows it there.
  // A wide unit does not move into columns: it overflows when it reaches past the bottom.
  function overflows(pg) {
    if (pg.kind === "fresh") return freshOverflows(pg);
    const box = pg.flow.getBoundingClientRect();
    const end = pg.end.getBoundingClientRect();
    if (end.left > box.right - 2 || end.top > box.bottom + 1) return true;
    for (const u of pg.flow.querySelectorAll(":scope > .unit.wide")) {
      const r = u.getBoundingClientRect();
      if (r.bottom > box.bottom + 1 || r.right > box.right + 1) return true;
    }
    return false;
  }

  function fill(pg) {
    const box = pg.flow.getBoundingClientRect();
    if (pg.kind === "fresh") return 1 - freshFree(pg) / box.height;
    let used = 0;
    pg.flow.querySelectorAll(":scope > .unit").forEach((u) => {
      const across = u.classList.contains("wide") ? 3 : 1;
      for (const r of u.getClientRects()) used += r.height * across;
    });
    return used / (3 * box.height);
  }

  function layout(issue, lh, spare) {
    const root = document.getElementById("edition");
    root.innerHTML = "";
    root.style.setProperty("--lh", lh + "px");
    const pages = [];
    const add = (kind, part, extra = {}) => {
      const pg = frame(kind, issue, { ...extra, no: pages.length + 1 });
      pg.part = part;
      pg.no = pages.length + 1;   // its number in the paper, for INSIDE and "continued from"
      root.appendChild(pg.el);
      pages.push(pg);
      return pg;
    };
    const tooBig = (u) => ({ error: "a block does not fit on an empty page: " + u.textContent.trim().slice(0, 60) });
    const parts = [];
    if (issue.front && issue.front.length) parts.push({ kind: "front", blocks: issue.front });  // a RADAR-only file has no front
    if (issue.results) parts.push({ kind: "results", blocks: issue.results.blocks || [] });

    for (const part of parts) {
      let pg = add(part.kind, part.kind);
      for (const u of units(part.blocks)) {
        pg.flow.insertBefore(u, pg.end);
        if (!overflows(pg)) continue;
        u.remove();
        if (pg.kind === "cont" && !pg.flow.querySelector(".unit")) return tooBig(u);
        pg = add("cont", part.kind);
        pg.flow.insertBefore(u, pg.end);
        if (overflows(pg)) return tooBig(u);
      }
    }

    // The closing band shortens the last page's flow; if text no longer fits, the band moves on
    // with the last unit so it never stands alone on a page.
    if (pages.length) {
      let last = pages[pages.length - 1];
      const band = el("section", "closing", '<div class="label">' + say("takeaway") + "</div><p>" + inline(issue.takeaway) + "</p>");
      last.el.insertBefore(band, last.foot);
      if (overflows(last)) {
        const us = last.flow.querySelectorAll(":scope > .unit");
        const moved = us[us.length - 1];
        const pg = add("cont", last.part);
        if (moved) pg.flow.insertBefore(moved, pg.end);
        pg.el.insertBefore(band, pg.foot);
        if (overflows(last) || overflows(pg)) return tooBig(moved || band);
        last = pg;
      }
    }

    // Fresh Ink comes after the issue (and its closing band), on pages of its own. `spare` is the
    // room, in px, the pages must keep free before the push, where the writer's machine may break
    // a line differently from the Linux build that prints: the front page always, and every page
    // once Fresh Ink is at its four, since one line more there would push a row onto a fifth page.
    let radarError = null;
    if (issue.radar) {
      radarError = freshLayout(issue, add);
      const fresh = pages.filter((p) => p.kind === "fresh");
      if (!radarError && spare) {
        const tight = fresh.map((p, i) => [i, freshFree(p)]).filter(([i, free]) => free < spare && (i === 0 || fresh.length >= FI_PAGES));
        if (tight.length) radarError = "Fresh Ink: " + tight.map(([i, free]) => "page " + (i + 1) + " has " + Math.max(0, Math.round(free)) + " px left").join(", ") +
          "; before the push it keeps one line (" + Math.round(spare) + " px) free: shorten a story there";
      }
    }

    const n = pages.length;
    pages.forEach((p, i) => {
      p.foot.querySelector(".foot-right").innerHTML = i < n - 1
        ? say("continues", { next: i + 2, page: i + 1, pages: n })
        : say("last_page", { nameplate: esc(L.nameplate), issue: pad3(issue.issue), page: n, pages: n });
    });
    return { pages, lh, radarError };
  }

  // ---- checks ------------------------------------------------------------------------------

  function lineRects(node) {
    const range = document.createRange();
    range.selectNodeContents(node);
    return [...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0);
  }

  // Everything stays inside its page; inside a flow, every line and box stays inside its own column.
  function checkBounds(pages) {
    const problems = [];
    pages.forEach((pg, pi) => {
      const pr = pg.el.getBoundingClientRect();
      const cs = getComputedStyle(pg.el);
      const left = pr.left + parseFloat(cs.paddingLeft) - 0.5, right = pr.right - parseFloat(cs.paddingRight) + 0.5;
      const box = pg.flow.getBoundingClientRect();
      const gap = parseFloat(getComputedStyle(pg.flow).columnGap);
      const colW = (box.width - 2 * gap) / 3;
      const walker = document.createTreeWalker(pg.el, NodeFilter.SHOW_TEXT);
      const rects = [];
      for (let t = walker.nextNode(); t; t = walker.nextNode()) {
        if (t.textContent.trim()) lineRects(t).forEach((r) => rects.push([r, t.parentElement]));
      }
      pg.el.querySelectorAll(".step, .formulas, .code > div, table, .bullet, .figure img, .bars > *, .fi-chart-svg, .fi-qr").forEach((e) => { for (const r of e.getClientRects()) rects.push([r, e]); });
      for (const [r, e] of rects) {
        const what = (e.textContent || "").trim().slice(0, 50) || e.tagName.toLowerCase();
        if (r.left < left || r.right > right) { problems.push("page " + (pi + 1) + ": outside the page: " + what); continue; }
        if (!pg.flow.contains(e)) continue;
        if (pg.kind === "fresh") {
          // on a Fresh Ink page every line and drawing stays inside its own story, brief or box
          const owner = e.closest(".fi-box");
          const b = owner ? owner.getBoundingClientRect() : pg.flow.getBoundingClientRect();
          if (r.left < b.left - 1 || r.right > b.right + 1 || r.bottom > b.bottom + 1) problems.push("page " + (pi + 1) + ": outside its box: " + what);
          continue;
        }
        if (e.closest(".unit.wide")) {
          if (r.left < box.left - 1 || r.right > box.right + 1 || r.bottom > box.bottom + 1) problems.push("page " + (pi + 1) + ": outside the text area: " + what);
          continue;
        }
        const col = Math.max(0, Math.min(2, Math.floor((r.left - box.left + 1) / (colW + gap))));
        const colRight = box.left + col * (colW + gap) + colW;
        if (r.right > colRight + 1) problems.push("page " + (pi + 1) + ": wider than its column: " + what);
      }
    });
    return [...new Set(problems)];
  }

  // Every character must exist in one of the vendored fonts of its stack; otherwise the browser
  // would borrow a system font whose widths differ from machine to machine.
  function checkGlyphs(roots, cmaps) {
    const sets = {};
    for (const [key, cps] of Object.entries(cmaps)) sets[key] = new Set(cps);
    const missing = new Map();
    roots.forEach((root) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let t = walker.nextNode(); t; t = walker.nextNode()) {
        if (t.parentElement.closest("style, script, title, desc")) continue;  // a diagram's own CSS is not text
        const cs = getComputedStyle(t.parentElement);
        const families = cs.fontFamily.split(",").map((f) => f.trim().replace(/^["']|["']$/g, ""));
        const style = cs.fontStyle === "italic" ? "italic" : "normal";
        for (const ch of t.textContent) {
          if (/\s/.test(ch)) continue;
          const cp = ch.codePointAt(0);
          const ok = families.some((f) => (sets[f + "|" + style] || sets[f + "|normal"] || { has: () => false }).has(cp));
          if (!ok) missing.set(ch, (t.textContent.trim().slice(0, 40)));
        }
      }
    });
    return [...missing].map(([ch, where]) => "no vendored glyph for " + JSON.stringify(ch) + " (U+" + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, "0") + ") in: " + where);
  }

  // ---- entry point -------------------------------------------------------------------------

  // Characters compared with the PDF's text. Whitespace and hyphens are left out: pdftotext
  // drops the hyphen of a word broken across lines, and that is not missing text.
  const countChars = (s) => s.normalize("NFKC").replace(/[\s\-\u00ad\u2010\u2011]+/g, "").length;

  // opts.radarSpare: keep a line free on the Fresh Ink pages (build.mjs sets it for --preflight)
  function run(issue, cmaps, opts = {}) {
    if (!L) throw new Error("CoffeeEdition.configure(labels) has not been called");
    const tries = [];
    for (const lh of LEADINGS) {
      const res = layout(issue, lh);
      if (res.error) return { ok: false, errors: [res.error], warnings: [], pages: [] };
      const lastOfPart = (pg, i) => i === res.pages.length - 1 || res.pages[i + 1].part !== pg.part;
      const short = res.pages.some((pg, i) => pg.kind === "cont" && lastOfPart(pg, i) && fill(pg) < SHORT_PAGE);
      tries.push({ lh, count: res.pages.length, short });
      if (!short) break;
    }
    const best = tries.reduce((a, b) => (b.count < a.count ? b : a));
    const { pages, lh, radarError } = layout(issue, best.lh, opts.radarSpare ? 17 : 0);
    const errors = [], warnings = [];
    if (radarError) errors.push(radarError);
    if (best.short) warnings.push("the last page of a section is less than a quarter full; shortening the text a little would save a page");
    const main = pages.filter((pg) => pg.kind !== "fresh").length;  // the Fresh Ink pages come on top of the limit
    if (main > MAX_PAGES) errors.push(main + " pages; more than " + MAX_PAGES + " means the issue is far too long");
    errors.push(...checkBounds(pages));
    if (cmaps) errors.push(...checkGlyphs(pages.map((pg) => pg.el), cmaps));
    const fresh = pages.filter((pg) => pg.kind === "fresh");
    return {
      ok: errors.length === 0,
      leading: lh,
      fresh_free_px: fresh.length ? fresh.map((pg) => Math.round(freshFree(pg))) : undefined,
      // each Fresh Ink page's rows and boxes, in px, so a writer sees what takes the room
      fresh_rows: fresh.length ? fresh.map((pg) => pg.cols ? pg.cols.map((c) => [...c.children].map((u) => Math.round(u.getBoundingClientRect().height)))
        : [...pg.flow.children].map((u) => Math.round(u.getBoundingClientRect().height))) : undefined,
      fresh_flow_px: fresh.length ? fresh.map((pg) => Math.round(pg.flow.getBoundingClientRect().height)) : undefined,
      qr: fresh.flatMap((pg) => [...pg.el.querySelectorAll(".fi-qr")].map((q) => q.dataset.url)),
      charts: fresh.reduce((n, pg) => n + pg.el.querySelectorAll(".fi-chart").length, 0),
      tries,
      errors,
      warnings,
      pages: pages.map((pg) => ({
        kind: pg.kind,
        fill: Math.round(fill(pg) * 100) / 100,
        closing: !!pg.el.querySelector(".closing"),
        footer: pg.foot.querySelector(".foot-right").textContent,
        chars: countChars(pg.el.innerText),
      })),
    };
  }

  // ---- pictures, prepared before run() -----------------------------------------------------

  // The widths a figure prints at: one column, or the whole text area.
  function widths() {
    const pg = frame("cont", { issue: 1, date: "2000-01-01", short_title: "" });
    document.getElementById("edition").appendChild(pg.el);
    const box = pg.flow.getBoundingClientRect();
    const gap = parseFloat(getComputedStyle(pg.flow).columnGap);
    pg.el.remove();
    return { page: box.width, column: (box.width - 2 * gap) / 3 };
  }

  async function measureImages(srcs) {
    const out = {};
    await Promise.all(srcs.map(async (src) => {
      const img = new Image();
      img.src = src;
      try {
        await img.decode();
        // how dark the slide prints: mean gray on a small copy, 0 black to 255 white
        const c = document.createElement("canvas");
        c.width = c.height = 64;
        const g = c.getContext("2d");
        g.drawImage(img, 0, 0, 64, 64);
        const px = g.getImageData(0, 0, 64, 64).data;
        let sum = 0;
        for (let i = 0; i < px.length; i += 4) sum += 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2];
        out[src] = { width: img.naturalWidth, height: img.naturalHeight, gray: Math.round(sum / (px.length / 4)) };
      } catch (e) {
        out[src] = { error: "cannot be decoded" };
      }
    }));
    return { sizes: out, widths: widths() };
  }

  const LABEL_PX = 14;       // mermaid's label size before any shrinking
  const MIN_LABEL_PX = 9;    // smallest label size worth printing

  let mermaidReady = false;
  function initMermaid() {
    if (mermaidReady) return;
    const token = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    const font = '"Newsreader", "Gloock"';
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",  // labels may carry <br/> to break a line
      theme: "base",
      fontFamily: font,
      themeVariables: {
        fontFamily: font, fontSize: LABEL_PX + "px", background: token("--paper"),
        primaryColor: token("--paper"), mainBkg: token("--paper"), primaryTextColor: token("--ink"), textColor: token("--ink"),
        primaryBorderColor: token("--ink"), nodeBorder: token("--ink"), lineColor: token("--ink-2"),
        secondaryColor: token("--track"), tertiaryColor: token("--paper"), clusterBkg: token("--paper"), clusterBorder: token("--rule"),
        edgeLabelBackground: token("--paper"),
      },
      flowchart: { useMaxWidth: true, htmlLabels: true, curve: "basis", padding: 10 },
    });
    mermaidReady = true;
  }

  // Draws every diagram block in a staging box at the width it will print at, checks its glyphs
  // and its label size, and returns where each one sits so build.mjs can photograph it.
  async function stageDiagrams(issue, cmaps) {
    const found = [];
    for (const [part, blocks] of [["front", issue.front], ["results", issue.results && issue.results.blocks]]) {
      (blocks || []).forEach((b, i) => { if (b && b.type === "diagram") found.push({ key: part + "." + i, b }); });
    }
    if (!found.length) return { diagrams: [], errors: [] };
    initMermaid();
    const w = widths();
    const stage = el("div", "stage");
    stage.id = "stage";
    document.body.appendChild(stage);
    const diagrams = [], errors = [];
    for (const [n, { key, b }] of found.entries()) {
      const where = key.replace(".", "[") + "]";
      const box = el("div", "diagram-stage");
      const target = b.wide ? w.page : w.column;
      box.style.width = target + "px";
      stage.appendChild(box);
      try {
        box.innerHTML = (await window.mermaid.render("ce-diagram-" + n, b.mermaid)).svg;
      } catch (e) {
        errors.push(where + ": mermaid cannot draw this diagram: " + String((e && e.message) || e).split("\n")[0]);
        box.remove();
        continue;
      }
      const svg = box.querySelector("svg");
      const natural = svg.viewBox && svg.viewBox.baseVal && svg.viewBox.baseVal.width ? svg.viewBox.baseVal.width : svg.getBoundingClientRect().width;
      const r = svg.getBoundingClientRect();
      const label = LABEL_PX * (r.width / natural);
      if (label < MIN_LABEL_PX - 0.05) {
        errors.push(where + ": at " + (b.wide ? "page" : "column") + " width its labels would print at " + label.toFixed(1) + " px (" + MIN_LABEL_PX +
          " is the least): draw it top-down (flowchart TD), shorten the labels" + (b.wide ? "" : " or make it wide"));
      }
      errors.push(...checkGlyphs([box], cmaps).map((m) => where + ": " + m));
      diagrams.push({ key, x: r.left + window.scrollX, y: r.top + window.scrollY, width: r.width, height: r.height });
    }
    return { diagrams, errors };
  }

  function clearStage() {
    const stage = document.getElementById("stage");
    if (stage) stage.remove();
  }

  window.CoffeeEdition = { configure, run, inline, measureImages, stageDiagrams, clearStage };
})();
