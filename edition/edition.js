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
  const RADAR_CELLS = 6;   // a RADAR page: two rows of three cells
  const RADAR_PAGES = 3;

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

  // ---- RADAR: five new methods on a page of their own after the issue ------------------------

  // A card: area and signal, the method's name, what it is, how it works, when to use it,
  // the one number (its source sentence stays in the file, for the check), code and source.
  function radarCard(c, i) {
    const u = el("div", "unit keep card");
    u.appendChild(el("div", "card-top",
      '<span class="card-n">' + (i + 1) + '</span><span class="card-area">' + inline(c.area) + "</span>" +
      (c.signal ? '<span class="card-signal">' + inline(c.signal) + "</span>" : "")));
    u.appendChild(el("div", "card-name", inline(c.name)));
    u.appendChild(el("p", "p card-what", inline(c.what)));
    u.appendChild(el("p", "p", "<strong>" + say("radar_how") + "</strong> " + inline(c.how)));
    u.appendChild(el("p", "p", "<strong>" + say("radar_when") + "</strong> " + inline(c.when)));
    u.appendChild(el("div", "card-number", '<div class="value">' + inline(c.number.value) + '</div><div class="says">' + inline(c.number.says) + "</div>"));
    u.appendChild(el("div", "card-meta",
      // a long link breaks after a slash, never inside a name
      (c.code ? '<span class="card-code">' + esc(c.code).replace(/\//g, "/<wbr>") + "</span>" : "") +
      '<span class="card-source">' + inline(c.source).replace(/arXiv /g, "arXiv\u00a0") + "</span>"));  // the id stays with its name
    return u;
  }

  // The runners-up: one line each, the paper's short name and why it is worth a look.
  function radarAlso(also) {
    const u = el("div", "unit keep also");
    u.appendChild(el("div", "label", say("radar_also")));
    also.forEach((a) => {
      const name = String(a.title).split(": ")[0].replace(/[\u2013\u2014]/g, "-");  // the paper's own name; no dashes print
      u.appendChild(el("p", "p also-item", "<strong>" + inline(name) + "</strong> " + inline(a.text)));
    });
    return u;
  }

  // The free height of each RADAR cell, in px: in a card, the gap above its code and source
  // lines (they sit at the foot of the cell); in the list, the space under the last item.
  // Negative when the content is taller than the cell.
  function radarSlack(pg) {
    return [...pg.flow.querySelectorAll(":scope > .unit")].map((u) => {
      const cell = u.getBoundingClientRect();
      const over = u.scrollHeight - u.clientHeight;
      if (over > 1) return -over;
      if (u.classList.contains("card")) {
        const meta = u.querySelector(".card-meta");
        const above = meta.previousElementSibling.getBoundingClientRect();
        return meta.getBoundingClientRect().top - above.bottom;
      }
      const last = u.lastElementChild.getBoundingClientRect();
      return cell.bottom - last.bottom;
    });
  }

  function radarUnits(radar) {
    const out = radar.items.map(radarCard);
    if (radar.also && radar.also.length) out.push(radarAlso(radar.also));
    return out;
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

  function frame(kind, issue, extra = {}) {
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
      const title = kind === "radar" ? (extra.cont ? say("continued", { title: say("radar_running") }) : say("radar_running"))
        : say("continued", { title: inline(issue.short_title) });
      page.appendChild(el("header", "running",
        '<div><span class="nameplate">' + say("nameplate") + '</span><span class="running-title">' + title + "</span></div>" +
        '<span class="running-meta">' + dateLine(issue.date) + " · " + say("issue", { issue: pad3(issue.issue) }) + "</span>"));
    }
    if (kind === "radar" && !extra.cont) {
      // what was scanned, by kind: papers (HF daily and trending, arXiv), models, repositories, posts (labs, HN, newsletters)
      const r = issue.radar, n = r.scanned, v = (k) => n[k] || 0;
      const kinds = { papers: v("hf") + v("arxiv") + v("trending"), models: v("models"), repos: v("github"), posts: v("blogs") + v("hn") + v("letters") };
      page.appendChild(el("section", "radar-head",
        '<div class="kicker-row"><span class="kicker">' + say("radar_kicker", { count: r.items.length }) + '</span><span class="byline">' +
        say("radar_scanned", kinds) + "</span></div>" +
        "<h2>" + inline(r.headline) + '</h2><p class="standfirst">' + say("radar_standfirst", { total: Object.values(kinds).reduce((a, b) => a + b, 0), count: r.items.length }) + "</p>"));
    }
    if (kind === "results") {
      const r = issue.results;
      const s = el("section", "results");
      s.appendChild(el("div", "results-head", "<h2>" + inline(r.headline) + '</h2><span class="label">' + inline(r.label) + "</span>"));
      s.appendChild(table(r.table, true));
      if (r.caption) s.appendChild(caption(r.caption));
      page.appendChild(s);
    }
    const flow = el("div", kind === "radar" ? "flow radar-grid" : "flow");
    const end = el("div", "flow-end");
    flow.appendChild(end);
    page.appendChild(flow);
    const sources = kind === "front" && issue.sources && issue.sources.length
      ? say("sources") + " " + issue.sources.map((s) => '<a href="' + esc(s.url) + '">' + inline(s.text) + "</a>").join(" · ")
      : kind === "radar" ? say("radar_sources") : "";
    const foot = el("footer", "foot", '<span class="foot-left">' + sources + '</span><span class="foot-right"></span>');
    page.appendChild(foot);
    return { el: page, kind, flow, end, foot };
  }

  // Text that does not fit lands in a column past the flow box's right edge; the end marker follows it there.
  // A wide unit does not move into columns: it overflows when it reaches past the bottom.
  function overflows(pg) {
    const box = pg.flow.getBoundingClientRect();
    // the RADAR page is a grid of six cells: a card overflows when it outgrows its cell or the page
    if (pg.kind === "radar") {
      return [...pg.flow.querySelectorAll(":scope > .unit")].some((u) => {
        const r = u.getBoundingClientRect();
        return r.bottom > box.bottom + 1 || r.right > box.right + 1 || u.scrollHeight > u.clientHeight + 1;
      });
    }
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
    const add = (kind, part, extra) => { const pg = frame(kind, issue, extra); pg.part = part; root.appendChild(pg.el); pages.push(pg); return pg; };
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

    // RADAR comes after the issue (and its closing band): six cells a page, two rows of three, as
    // many pages as the cards need (five to seventeen cards and the list: one to three pages). A cell
    // never breaks; what does not fit stays in its cell, past its edge, so a draft shows how much.
    // `spare` is the room each cell must keep free, in px: a line before the push, where the
    // writer's machine may break a line differently from the Linux build that prints; none in that build.
    let radarError = null;
    if (issue.radar) {
      const cells = radarUnits(issue.radar), rpages = [];
      for (let i = 0; i < cells.length; i += RADAR_CELLS) {
        const pg = add("radar", "radar", { cont: i > 0 });
        cells.slice(i, i + RADAR_CELLS).forEach((u) => pg.flow.insertBefore(u, pg.end));
        rpages.push(pg);
      }
      const need = spare ? lh : 0;
      const short = rpages.flatMap((pg) => radarSlack(pg)).map((free, i) => {
        const lines = Math.max(1, Math.ceil((need - free) / lh));
        return free < need - 0.5 || free < -0.5 ? (i < issue.radar.items.length ? "card " + (i + 1) : "the list") + " by " + lines + " line" + (lines > 1 ? "s" : "") : null;
      }).filter(Boolean);
      if (rpages.length > RADAR_PAGES) radarError = "RADAR runs to " + rpages.length + " pages; at most " + RADAR_PAGES;
      else if (short.length || rpages.some(overflows)) radarError = "the RADAR pages do not fit: " + (short.join(", ") || "too many cells") +
        (spare ? " (shorten the text; before the push every cell keeps one line free)" : " (shorten the text)");
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
      pg.el.querySelectorAll(".step, .formulas, .code > div, table, .bullet, .figure img, .bars > *").forEach((e) => { for (const r of e.getClientRects()) rects.push([r, e]); });
      for (const [r, e] of rects) {
        const what = (e.textContent || "").trim().slice(0, 50) || e.tagName.toLowerCase();
        if (r.left < left || r.right > right) { problems.push("page " + (pi + 1) + ": outside the page: " + what); continue; }
        if (!pg.flow.contains(e)) continue;
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

  // opts.radarSpare: keep a line free in every RADAR cell (build.mjs sets it for --preflight)
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
    const { pages, lh, radarError } = layout(issue, best.lh, !!opts.radarSpare);
    const errors = [], warnings = [];
    if (radarError) errors.push(radarError);
    if (best.short) warnings.push("the last page of a section is less than a quarter full; shortening the text a little would save a page");
    const main = pages.filter((pg) => pg.kind !== "radar").length;  // the RADAR pages come on top of the limit
    if (main > MAX_PAGES) errors.push(main + " pages; more than " + MAX_PAGES + " means the issue is far too long");
    errors.push(...checkBounds(pages));
    if (cmaps) errors.push(...checkGlyphs(pages.map((pg) => pg.el), cmaps));
    const radarPages = pages.filter((pg) => pg.kind === "radar");
    return {
      ok: errors.length === 0,
      leading: lh,
      radar_free_px: radarPages.length ? radarPages.flatMap((pg) => radarSlack(pg)).map((x) => Math.round(x)) : undefined,
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
