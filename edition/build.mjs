#!/usr/bin/env node
/**
 * Builds one Coffee Edition issue into a print-ready PDF, and refuses to write a broken one.
 *
 *   node edition/build.mjs <issue.edition.json> [--pdf out.pdf] [--report out.json] [--png dir] [--draft]
 *   node edition/build.mjs <issue.edition.json> --check
 *   node edition/build.mjs <issue.edition.json> --preflight
 *   any of them with [--labels file] [--root dir]
 *
 * Labels: the words printed around the article (nameplate, weekdays, months, "Continued on page
 * 2", the caption leads) come from edition/labels.json, or --labels for another language.
 *
 * Pictures: an image block shows a picture that sits next to a note, by its path in the repo
 * (notes/002-raven/figure-1.png). It is read from the repository root (--root changes it, for
 * tests) and may not point outside it. A diagram block is mermaid source: the build draws it
 * with the vendored mermaid at the width it prints at, checks its glyphs and label size, and
 * photographs it at 600 dpi, so the PDF carries a picture.
 *
 * --draft still writes the PDF (and PNGs) when checks fail, so a problem can be looked at; the
 * exit code stays 1. Never use it for printing.
 *
 * --check runs step 1 and the glyph check without a browser, for a machine without Chrome. It
 * reads each field's font stack from edition.css and the markup rules from edition.js, so it
 * refuses what the browser check would. Pages are not known until the real build, which
 * prepare.py runs after the push.
 *
 * --preflight is what scripts/commit_issue.sh runs before it pushes: the full build (layout and
 * PDF checks, no PDF kept) when the machine has Chrome and poppler, so the writer sees a page
 * that overflows before prepare does; otherwise the --check above, and the summary says which ran.
 * Only the machine failing (no Chrome, Chrome not starting, fonts not loading, a timeout) falls
 * back to --check; whatever the issue itself gets wrong is refused as in the full build. With
 * Chrome but without poppler it runs the layout checks only (pages, columns, diagrams, glyphs)
 * and leaves the PDF checks to prepare; COFFEE_NO_POPPLER=1 acts as if poppler were missing.
 * COFFEE_NO_CHROME=1 acts as if there were no Chrome.
 *
 * 1. Validates the issue file: required fields, known block types, house style.
 * 2. Lays it out in headless Chrome with the vendored fonts. edition.js paginates (a page is
 *    added whenever text does not fit) and checks page and column bounds and glyph coverage.
 * 3. Prints the PDF and verifies the PDF itself: the same page count as the layout, and each
 *    page carries all of its characters, so nothing was clipped on the way to paper.
 *
 * Exit code 0 means the PDF was written and is safe to print; 1 means no PDF was written and
 * the report says why. Needs Node 22+ (global WebSocket), Chrome or Chromium (set CHROME to
 * pick one), and pdfinfo + pdftotext from poppler.
 */
import { spawn, execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { basename, dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = dirname(HERE);
const FONT_FACES = {
  "Newsreader|normal": "Newsreader-Roman.ttf",
  "Newsreader|italic": "Newsreader-Italic.ttf",
  "IBM Plex Mono|normal": "IBMPlexMono-Regular.ttf",
  "Gloock|normal": "Gloock-Regular.ttf",
  "Grenze Gotisch|normal": "GrenzeGotisch.ttf",
};
const FACE_COUNT = 6;   // @font-face rules in edition.css
const CODE_MAX = 30;    // monospace characters that fit in one column
const CODE_MAX_WIDE = 88; // ... and across the whole text area (wide code)
const PICTURES_MAX = 4; // slides and diagrams in one issue
const IMAGE_MAX_BYTES = 1500000;
const PRINT_SCALE = 600 / 96; // diagrams are photographed at 600 dpi
const SLIDE_DARK = 120;  // mean gray (0 black, 255 white) below which a slide is a block of toner
const SLIDE_DIM = 170;   // ... and below which it prints heavy
const PART_WORDS = 800; // soft budget per part; more usually means an extra page
const TIMEOUT_MS = 120000;
// The house style (edition/STYLE.md) sets no dashes: a comma, a colon or a full stop reads
// better in narrow columns. Add your own words to refuse here.
const FORBIDDEN = [
  [/\u2014/, "em-dash (write a comma, a colon or two sentences)"],
  [/\u2013/, 'en-dash (write "to": "68 to 82", or a comma)'],
];
// The keys of edition/labels.json and the {placeholders} each one must keep.
const LABELS = {
  nameplate: [], date: ["weekday", "day", "month", "year"], issue: ["issue"], print_time: ["time"], continued: ["title"],
  sources: [], takeaway: [], continues: ["next", "page", "pages"], last_page: ["page", "pages"],
  shows: [], does: [], says: [], symbols: [],
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- labels --------------------------------------------------------------------------------

function loadLabels(file) {
  let labels;
  try { labels = JSON.parse(readFileSync(file, "utf8")); } catch (e) { return { errors: [`labels: cannot read ${file}: ${e.message}`] }; }
  const errors = [];
  if (!labels || typeof labels !== "object") return { errors: [`labels: ${file} is not a JSON object`] };
  if (typeof labels.lang !== "string" || !/^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$/.test(labels.lang)) errors.push('labels.lang: a language tag like "en" or "pt-BR"');
  for (const [key, count] of [["weekdays", 7], ["months", 12]]) {
    const v = labels[key];
    if (!Array.isArray(v) || v.length !== count || !v.every((x) => typeof x === "string" && x.trim())) errors.push(`labels.${key}: ${count} names` + (key === "weekdays" ? ", Sunday first" : ""));
  }
  for (const [key, holes] of Object.entries(LABELS)) {
    const v = labels[key];
    if (typeof v !== "string" || !v.trim()) { errors.push(`labels.${key}: required text`); continue; }
    for (const h of holes) if (!v.includes(`{${h}}`)) errors.push(`labels.${key}: keep {${h}} in it`);
  }
  for (const [key, v] of Object.entries(labels)) if (key !== "lang" && key !== "weekdays" && key !== "months" && !(key in LABELS)) errors.push(`labels.${key}: unknown key`);
  return { labels, errors };
}

// ---- validation ----------------------------------------------------------------------------

function walkStrings(value, path, visit) {
  if (typeof value === "string") visit(value, path);
  else if (Array.isArray(value)) value.forEach((v, i) => walkStrings(v, `${path}[${i}]`, visit));
  else if (value && typeof value === "object") for (const [k, v] of Object.entries(value)) walkStrings(v, path ? `${path}.${k}` : k, visit);
}

function words(value) {
  let n = 0;
  walkStrings(value, "", (s, path) => { if (!/\.(mermaid|src)$/.test(path)) n += s.split(/\s+/).filter(Boolean).length; });
  return n;
}

function validate(issue, labels) {
  const errors = [];
  const warnings = [];
  const lang = labels.lang;
  const text = (obj, key, where, optional = false) => {
    const v = obj ? obj[key] : undefined;
    if (v == null && optional) return;
    if (typeof v !== "string" || !v.trim()) errors.push(`${where}.${key}: required text`);
  };
  const caps = (s, where) => {
    if (typeof s === "string" && s !== s.toLocaleUpperCase(lang)) errors.push(`${where}: type it in capitals: "${s.toLocaleUpperCase(lang)}"`);
  };

  function checkTable(t, where, wide) {
    if (!t || !Array.isArray(t.columns) || !t.columns.length || !Array.isArray(t.rows) || !t.rows.length) {
      errors.push(`${where}: needs columns and rows`);
      return;
    }
    t.columns.forEach((c, i) => text(c, "label", `${where}.columns[${i}]`));
    t.rows.forEach((row, i) => {
      if (!Array.isArray(row) || row.length !== t.columns.length) errors.push(`${where}.rows[${i}]: needs ${t.columns.length} cells`);
      else row.forEach((cell, j) => {
        const pair = Array.isArray(cell) && cell.length === 2 && cell.every((x) => typeof x === "number");
        if (!pair && typeof cell !== "string" && typeof cell !== "number") errors.push(`${where}.rows[${i}][${j}]: text, a number or [before, after]`);
      });
    });
    for (const key of ["chart", "delta"]) {
      const spec = t[key];
      if (spec == null) continue;
      if (!wide) { errors.push(`${where}.${key}: only the results table can carry a ${key}`); continue; }
      text(spec, "label", `${where}.${key}`);
      if (!t.rows.every((row) => Array.isArray(row[spec.column]))) errors.push(`${where}.${key}.column: must point at a [before, after] column`);
      if (key === "chart" && !(typeof spec.min === "number" && typeof spec.max === "number" && spec.max > spec.min)) errors.push(`${where}.chart: needs min < max`);
    }
  }

  function checkBlocks(blocks, where) {
    if (!Array.isArray(blocks)) { errors.push(`${where}: list of blocks`); return; }
    blocks.forEach((b, i) => {
      const at = `${where}[${i}]`;
      switch (b && b.type) {
        case "label": text(b, "text", at); caps(b.text, `${at}.text`); break;
        case "p": text(b, "text", at); text(b, "lead", at, true); break;
        case "caption": text(b, "text", at); break;
        case "bullets":
          if (!Array.isArray(b.items) || !b.items.length) errors.push(`${at}.items: list of texts`);
          else b.items.forEach((it, j) => { if (typeof it !== "string" || !it.trim()) errors.push(`${at}.items[${j}]: text`); });
          break;
        case "steps":
          if (!Array.isArray(b.items) || !b.items.length) errors.push(`${at}.items: list of steps`);
          else b.items.forEach((it, j) => { text(it, "text", `${at}.items[${j}]`); text(it, "symbol", `${at}.items[${j}]`, true); });
          break;
        case "formulas":
          text(b, "label", at, true);
          caps(b.label, `${at}.label`);
          text(b, "symbols", at, true);
          if (!Array.isArray(b.items) || !b.items.length) errors.push(`${at}.items: list of formulas`);
          else b.items.forEach((it, j) => ["name", "formula", "says"].forEach((k) => text(it, k, `${at}.items[${j}]`)));
          break;
        case "code": {
          const max = b.wide ? CODE_MAX_WIDE : CODE_MAX;
          if (!Array.isArray(b.lines) || !b.lines.length) errors.push(`${at}.lines: list of code lines`);
          else b.lines.forEach((line, j) => {
            if (typeof line !== "string") errors.push(`${at}.lines[${j}]: text`);
            else if (line.length > max) errors.push(`${at}.lines[${j}]: ${line.length} characters, ${b.wide ? "the text area" : "a column"} holds ${max}` + (b.wide ? "" : ` (or set "wide": true for ${CODE_MAX_WIDE})`));
          });
          if (b.wide != null && typeof b.wide !== "boolean") errors.push(`${at}.wide: true or false`);
          break;
        }
        case "table": checkTable(b, at, false); break;
        case "image":
          text(b, "src", at);
          if (typeof b.src === "string" && !(/^notes\/[^\\]+\.(webp|png|jpe?g)$/i.test(b.src) && !b.src.split("/").includes("..")))
            errors.push(`${at}.src: a picture next to a note, by its path in the repo (notes/002-raven/figure-1.png; webp, png or jpg)`);
          if (b.wide != null && typeof b.wide !== "boolean") errors.push(`${at}.wide: true or false`);
          pictures++;
          break;
        case "diagram":
          text(b, "mermaid", at);
          if (typeof b.mermaid === "string" && b.mermaid.length > 3000) errors.push(`${at}.mermaid: ${b.mermaid.length} characters; keep a diagram under 3000`);
          if (b.wide != null && typeof b.wide !== "boolean") errors.push(`${at}.wide: true or false`);
          pictures++;
          break;
        case "bars":
          if (!Array.isArray(b.rows) || b.rows.length < 2 || b.rows.length > 12) errors.push(`${at}.rows: 2 to 12 rows of [label, number]`);
          else b.rows.forEach((r, j) => {
            if (!Array.isArray(r) || r.length !== 2 || typeof r[0] !== "string" || !r[0].trim() || typeof r[1] !== "number" || !(r[1] >= 0)) errors.push(`${at}.rows[${j}]: [label, a number of 0 or more]`);
          });
          if (b.max != null && !(typeof b.max === "number" && b.max > 0)) errors.push(`${at}.max: a number above 0`);
          for (const k of ["prefix", "suffix"]) if (b[k] != null && typeof b[k] !== "string") errors.push(`${at}.${k}: text`);
          if (b.accent != null && !(Array.isArray(b.accent) && b.accent.every((x) => Number.isInteger(x) && x >= 0 && Array.isArray(b.rows) && x < b.rows.length))) errors.push(`${at}.accent: row numbers, counting from 0`);
          break;
        default: errors.push(`${at}.type: unknown block type ${JSON.stringify(b && b.type)}`);
      }
      // every picture is explained right under it ("What it shows"), and every piece of code too ("What it does")
      if (b && ["image", "diagram", "bars", "code"].includes(b.type) && !(blocks[i + 1] && blocks[i + 1].type === "caption"))
        errors.push(`${at}: the ${b.type} block needs a caption block right after it` + (b.type === "code" ? " (what the code does: input, output, the line that matters)" : ""));
    });
  }
  let pictures = 0;

  if (!issue || typeof issue !== "object") return { errors: ["the issue file is not a JSON object"], warnings };
  if (issue.version !== 1) errors.push("version: must be 1");
  if (issue.note != null && !(typeof issue.note === "string" && /^notes\/[^\\]+\.md$/.test(issue.note) && !issue.note.split("/").includes("..")))
    errors.push("issue.note: the note it was written from, by its path in the repo (notes/002-raven.md)");
  if (!Number.isInteger(issue.issue) || issue.issue < 1) errors.push("issue: the issue number (1, 2, ...)");
  for (const k of ["date", "edition", "short_title", "kicker", "byline", "headline", "standfirst", "takeaway"]) text(issue, k, "issue");
  if (typeof issue.date === "string" && !/^\d{4}-\d{2}-\d{2}$/.test(issue.date)) errors.push("issue.date: YYYY-MM-DD");
  if (issue.print_time != null && !/^([01]\d|2[0-3]):[0-5]\d$/.test(issue.print_time)) errors.push("issue.print_time: HH:MM in printer.json's timezone, like 07:30");
  caps(issue.kicker, "issue.kicker");
  caps(issue.edition, "issue.edition");
  if (!Array.isArray(issue.sources)) errors.push("issue.sources: list of {text, url}");
  else issue.sources.forEach((s, i) => { text(s, "text", `sources[${i}]`); text(s, "url", `sources[${i}]`); });
  if (!Array.isArray(issue.front) || !issue.front.length) errors.push("issue.front: at least one block");
  else checkBlocks(issue.front, "front");
  if (issue.results != null) {
    const r = issue.results;
    text(r, "headline", "results");
    text(r, "label", "results");
    caps(r.label, "results.label");
    text(r, "caption", "results", true);
    checkTable(r.table, "results.table", true);
    if (r.blocks != null) checkBlocks(r.blocks, "results.blocks");
  }
  if (pictures > PICTURES_MAX) errors.push(`${pictures} pictures (slides and diagrams); an issue carries at most ${PICTURES_MAX}`);
  walkStrings(issue, "", (s, path) => { for (const [re, what] of FORBIDDEN) if (re.test(s)) errors.push(`${path}: ${what}`); });
  for (const [part, blocks] of [["front", issue.front], ["results", issue.results && issue.results.blocks]]) {
    const n = words(blocks);
    if (n > PART_WORDS) warnings.push(`${part}: ${n} words against a budget of ${PART_WORDS}; expect an extra page`);
  }
  return { errors, warnings };
}

// ---- fonts ---------------------------------------------------------------------------------

// Code points a TrueType font maps to a glyph (cmap formats 4 and 12).
function cmap(file) {
  const b = readFileSync(file);
  let off = -1;
  for (let i = 0, n = b.readUInt16BE(4); i < n; i++) {
    const rec = 12 + i * 16;
    if (b.toString("latin1", rec, rec + 4) === "cmap") off = b.readUInt32BE(rec + 8);
  }
  if (off < 0) throw new Error("no cmap table in " + file);
  const set = new Set();
  for (let i = 0, n = b.readUInt16BE(off + 2); i < n; i++) {
    const so = off + b.readUInt32BE(off + 4 + i * 8 + 4);
    const format = b.readUInt16BE(so);
    if (format === 4) {
      const seg = b.readUInt16BE(so + 6) / 2;
      const ends = so + 14, starts = ends + seg * 2 + 2, deltas = starts + seg * 2, ranges = deltas + seg * 2;
      for (let s = 0; s < seg; s++) {
        const end = b.readUInt16BE(ends + s * 2), start = b.readUInt16BE(starts + s * 2);
        const delta = b.readInt16BE(deltas + s * 2), ro = b.readUInt16BE(ranges + s * 2);
        for (let c = start; c <= end && c < 0xffff; c++) {
          let g = ro === 0 ? (c + delta) & 0xffff : b.readUInt16BE(ranges + s * 2 + ro + (c - start) * 2);
          if (ro !== 0 && g) g = (g + delta) & 0xffff;
          if (g) set.add(c);
        }
      }
    } else if (format === 12) {
      for (let g = 0, n = b.readUInt32BE(so + 12); g < n; g++) {
        const p = so + 16 + g * 12;
        for (let c = b.readUInt32BE(p), e = Math.min(b.readUInt32BE(p + 4), 0x10ffff); c <= e; c++) set.add(c);
      }
    }
  }
  return set;
}

// ---- glyphs without a browser ----------------------------------------------------------------

// Every text field of the issue with the font stack edition.css sets it in. Keep in step with the
// renderers in edition.js; test.mjs compares this check with the browser's on the fixtures.
function textRuns(issue) {
  const out = [];
  const mono = { mono: true }, italic = { italic: true };
  const add = (text, where, style = {}) => { if (typeof text === "string") out.push({ text, where, ...style }); };
  const table = (t, where) => {
    if (!t) return;
    (t.columns || []).forEach((c, i) => add(c && c.label, `${where}.columns[${i}].label`, mono));
    (t.rows || []).forEach((row, i) => (Array.isArray(row) ? row : []).forEach((cell, j) => add(cell, `${where}.rows[${i}][${j}]`)));
    for (const key of ["chart", "delta"]) if (t[key]) add(t[key].label, `${where}.${key}.label`, mono);
  };
  const blocks = (list, where) => (Array.isArray(list) ? list : []).forEach((b, i) => {
    const at = `${where}[${i}]`;
    if (!b) return;
    if (b.type === "label") add(b.text, at + ".text", mono);
    else if (b.type === "p") { add(b.lead, at + ".lead", mono); add(b.text, at + ".text"); }
    else if (b.type === "caption") add(b.text, at + ".text");
    else if (b.type === "bullets") (b.items || []).forEach((t, j) => add(t, `${at}.items[${j}]`));
    else if (b.type === "steps") (b.items || []).forEach((it, j) => {
      add(it && it.text, `${at}.items[${j}].text`);
      add(it && it.symbol, `${at}.items[${j}].symbol`, it && it.symbol_plain ? {} : italic);
    });
    else if (b.type === "formulas") {
      add(b.label, at + ".label", mono);
      add(b.symbols, at + ".symbols");
      (b.items || []).forEach((it, j) => {
        add(it && it.name, `${at}.items[${j}].name`, mono);
        add(it && it.formula, `${at}.items[${j}].formula`, italic);
        add(it && it.says, `${at}.items[${j}].says`);
      });
    } else if (b.type === "code") (b.lines || []).forEach((line, j) => add(line, `${at}.lines[${j}]`, { mono: true, raw: true }));
    else if (b.type === "table") table(b, at);
    else if (b.type === "diagram") add(b.mermaid, at + ".mermaid", { raw: true });  // labels print in the serif
    else if (b.type === "bars") {
      (b.rows || []).forEach((r, j) => add(Array.isArray(r) ? r[0] : null, `${at}.rows[${j}]`));
      add(b.prefix, at + ".prefix");
      add(b.suffix, at + ".suffix");
    }
  });
  add(issue.edition, "edition", mono);
  add(issue.kicker, "kicker", mono);
  add(issue.byline, "byline", mono);
  add(issue.headline, "headline");
  add(issue.standfirst, "standfirst", italic);
  add(issue.short_title, "short_title", italic);
  add(issue.takeaway, "takeaway", italic);
  (Array.isArray(issue.sources) ? issue.sources : []).forEach((s, i) => add(s && s.text, `sources[${i}].text`, mono));
  blocks(issue.front, "front");
  if (issue.results) {
    const r = issue.results;
    add(r.headline, "results.headline");
    add(r.label, "results.label", mono);
    add(r.caption, "results.caption");
    table(r.table, "results.table");
    blocks(r.blocks, "results.blocks");
  }
  return out;
}

// The labels with the face each one prints in (edition.css): the nameplate in the display
// face, the masthead, running head, footers and the takeaway label in mono, the running title
// in italic, the caption leads in the serif.
function labelRuns(labels) {
  const out = [];
  const add = (text, where, style = {}) => { if (typeof text === "string") out.push({ text: text.replace(/\{\w+\}/g, ""), where: "labels." + where, raw: true, ...style }); };
  add(labels.nameplate, "nameplate", { display: true });
  for (const key of ["date", "issue", "print_time", "sources", "takeaway", "continues", "last_page"]) add(labels[key], key, { mono: true });
  (labels.weekdays || []).forEach((d, i) => add(d, `weekdays[${i}]`, { mono: true }));
  (labels.months || []).forEach((m, i) => add(m, `months[${i}]`, { mono: true }));
  add(labels.nameplate, "nameplate (in the footer)", { mono: true });
  add(labels.continued, "continued", { italic: true });
  for (const key of ["shows", "does", "says", "symbols"]) add(labels[key], key);
  return out;
}

// edition.js's own inline(), run without a page, so the markup rules are the printed ones.
function loadInline() {
  const sandbox = { window: {} };
  vm.runInNewContext(readFileSync(join(HERE, "edition.js"), "utf8"), sandbox);
  return sandbox.window.CoffeeEdition.inline;
}

// The font families of a stack variable in edition.css, like --serif: "Newsreader", "Gloock".
function cssStack(css, name) {
  const m = css.match(new RegExp(`--${name}:\\s*([^;]+);`));
  if (!m) throw new Error(`edition.css has no --${name}`);
  return m[1].split(",").map((f) => f.trim().replace(/^["']|["']$/g, ""));
}

function staticGlyphs(issue, cmaps, labels) {
  const css = readFileSync(join(HERE, "edition.css"), "utf8");
  const stacks = { mono: cssStack(css, "mono"), serif: cssStack(css, "serif"), display: cssStack(css, "display") };
  const sets = Object.fromEntries(Object.entries(cmaps).map(([k, v]) => [k, new Set(v)]));
  const has = (family, italic, cp) => (sets[family + "|" + (italic ? "italic" : "normal")] || sets[family + "|normal"] || new Set()).has(cp);
  const inline = loadInline();
  const missing = new Map();
  for (const run of [...labelRuns(labels), ...textRuns(issue)]) {
    const chars = [];
    if (run.raw) for (const ch of run.text) chars.push([ch, run.display ? "display" : run.mono ? "mono" : "serif", !!run.italic]);
    else {
      // walk the markup inline() makes: <span class="mono"> and <em> change the face, tags hold no text
      const stack = [];
      const re = /<(\/?)([a-z0-9]+)([^>]*)>|([^<]+)/gi;
      for (let m; (m = re.exec(inline(run.text))); ) {
        if (m[4] != null) {
          const text = m[4].replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
          const mono = !!run.mono || stack.some((t) => t.mono), italic = !!run.italic || stack.some((t) => t.italic);
          for (const ch of text) chars.push([ch, mono ? "mono" : "serif", italic]);
        } else if (m[1]) stack.pop();
        else stack.push({ mono: /class="mono"/.test(m[3]), italic: m[2].toLowerCase() === "em" });
      }
    }
    for (const [ch, face, italic] of chars) {
      if (/\s/.test(ch)) continue;
      const cp = ch.codePointAt(0);
      if (!stacks[face].some((f) => has(f, italic, cp)) && !missing.has(ch)) missing.set(ch, run.where);
    }
  }
  return [...missing].map(([ch, where]) => "no vendored glyph for " + JSON.stringify(ch) + " (U+" + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, "0") + ") in: " + where);
}

// ---- pictures ------------------------------------------------------------------------------

// Each image block's file, by its path from the repository root; nothing outside the root.
function resolveImages(issue, root) {
  const found = [], errors = [];
  for (const [part, blocks] of [["front", issue.front], ["results", issue.results && issue.results.blocks]]) {
    (blocks || []).forEach((b, i) => {
      if (!b || b.type !== "image" || typeof b.src !== "string") return;
      const at = `${part}[${i}].src`;
      const path = resolve(root, b.src);
      if (!path.startsWith(resolve(root) + "/")) errors.push(`${at}: ${b.src} points outside the repository`);
      else if (!existsSync(path)) errors.push(`${at}: ${b.src} does not exist`);
      else if (statSync(path).size > IMAGE_MAX_BYTES) errors.push(`${at}: ${b.src} is ${(statSync(path).size / 1e6).toFixed(1)} MB, the most is ${IMAGE_MAX_BYTES / 1e6} MB`);
      else found.push({ block: b, path, where: `${part}[${i}]` });
    });
  }
  return { found, errors };
}

function blockAt(issue, key) {
  const [part, i] = key.split(".");
  return (part === "front" ? issue.front : issue.results.blocks)[Number(i)];
}

// ---- browser -------------------------------------------------------------------------------

function serve(root, extra = new Map()) {
  const types = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".ttf": "font/ttf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };
  const server = createServer((req, res) => {
    const url = decodeURIComponent(new URL(req.url, "http://127.0.0.1").pathname);
    const file = extra.get(url) || resolve(root, "." + url);
    if ((!extra.has(url) && !file.startsWith(root + "/")) || !existsSync(file)) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { "content-type": types[extname(file)] || "application/octet-stream" });
    res.end(readFileSync(file));
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

// Playwright's Chromium, newest revision first: the cloud machine the nightly routine runs on has
// one in /opt/pw-browsers and no Chrome on PATH. The headless shell builds are skipped.
const PLAYWRIGHT_ROOTS = [process.env.PLAYWRIGHT_BROWSERS_PATH, "/opt/pw-browsers", join(homedir(), ".cache", "ms-playwright"),
  join(homedir(), "Library", "Caches", "ms-playwright")];
const PLAYWRIGHT_EXES = ["chrome-linux/chrome", "chrome-linux64/chrome", "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
  "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
  "chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"];

function playwrightChromium() {
  for (const root of PLAYWRIGHT_ROOTS.filter(Boolean)) {
    let revs = [];
    try { revs = readdirSync(root).filter((d) => /^chromium-\d+$/.test(d)).sort((a, b) => Number(b.slice(9)) - Number(a.slice(9))); } catch { continue; }
    for (const rev of revs) {
      const exe = PLAYWRIGHT_EXES.map((rel) => join(root, rev, rel)).find((p) => existsSync(p));
      if (exe) return exe;
    }
  }
  return null;
}

function findChrome() {
  if (process.env.COFFEE_NO_CHROME) throw new Error("Chrome or Chromium not found (COFFEE_NO_CHROME is set)");
  if (process.env.CHROME) return process.env.CHROME;
  const mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  if (existsSync(mac)) return mac;
  for (const exe of ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]) {
    try { return execFileSync("which", [exe], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim(); } catch { /* try the next one */ }
  }
  const pw = playwrightChromium();
  if (pw) return pw;
  throw new Error("Chrome or Chromium not found (set CHROME)");
}

function onPath(exe) {
  try { execFileSync("which", [exe], { stdio: "ignore" }); return true; } catch { return false; }
}

async function launchChrome() {
  const profile = mkdtempSync(join(tmpdir(), "coffee-edition-"));
  const proc = spawn(findChrome(), [
    "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run", "--no-default-browser-check",
    "--use-mock-keychain", "--password-store=basic", "--hide-scrollbars", "--font-render-hinting=none",
    "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank",
  ], { stdio: "ignore" });
  const close = () => {
    try { proc.kill("SIGKILL"); } catch { /* already gone */ }
    try { rmSync(profile, { recursive: true, force: true }); } catch { /* best effort */ }
  };
  let port = null;
  for (let i = 0; i < 150 && !port; i++) {
    await sleep(100);
    try { port = readFileSync(join(profile, "DevToolsActivePort"), "utf8").split("\n")[0].trim() || null; } catch { /* not yet */ }
  }
  if (!port) { close(); throw new Error("Chrome did not start"); }
  let page = null;
  for (let i = 0; i < 50 && !page; i++) {
    try { page = (await fetch(`http://127.0.0.1:${port}/json/list`).then((r) => r.json())).find((t) => t.type === "page"); } catch { /* not yet */ }
    if (!page) await sleep(100);
  }
  if (!page) { close(); throw new Error("Chrome has no page to drive"); }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (!m.id || !pending.has(m.id)) return;
    const { ok, fail } = pending.get(m.id);
    pending.delete(m.id);
    if (m.error) fail(new Error(m.error.message)); else ok(m.result);
  });
  await new Promise((ok, fail) => { ws.addEventListener("open", ok); ws.addEventListener("error", () => fail(new Error("DevTools connection failed"))); });
  const send = (method, params = {}) => new Promise((ok, fail) => {
    const i = ++id;
    pending.set(i, { ok, fail });
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error("page script failed: " + ((r.exceptionDetails.exception && r.exceptionDetails.exception.description) || r.exceptionDetails.text));
    return r.result.value;
  };
  return { send, evaluate, close: () => { try { ws.close(); } catch { /* ignore */ } close(); } };
}

// ---- main ----------------------------------------------------------------------------------

function parseArgs(argv) {
  const args = { file: null, pdf: null, report: null, png: null, labels: join(HERE, "labels.json"), root: REPO, draft: false, check: false, preflight: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--draft") args.draft = true;
    else if (a === "--check") args.check = true;
    else if (a === "--preflight") args.preflight = true;
    else if (a === "--pdf" || a === "--report" || a === "--png" || a === "--labels" || a === "--root") args[a.slice(2)] = argv[++i];
    else if (!args.file) args.file = a;
    else throw new Error("unexpected argument " + a);
  }
  if (!args.file) throw new Error("usage: node edition/build.mjs <issue.edition.json> [--pdf out.pdf] [--report out.json] [--png dir] [--draft] | --check | --preflight, with [--labels file] [--root dir]");
  if (args.check && args.preflight) throw new Error("--check and --preflight do not go together");
  return args;
}

function summary(report) {
  const lines = ["edition: " + report.file];
  if (report.layout && report.layout.pages && report.layout.pages.length) {
    const pages = report.layout.pages;
    lines.push(`  pages: ${pages.length} (${pages.map((p) => p.kind).join(", ")}), leading ${report.layout.leading}px, fill ${pages.map((p) => p.fill).join(" / ")}`);
  }
  if (report.pdf) lines.push(`  pdf: ${report.pdf.pages} page(s), text on every page matches the layout`);
  if (report.preflight) lines.push("  preflight: " + report.preflight);
  if (report.check) lines.push(`  check: fields, glyphs and slide files only, ${report.check.words} words; the real build decides the pages`);
  if (report.pictures && (report.pictures.slides || report.pictures.diagrams)) lines.push(`  pictures: ${report.pictures.slides} slide(s), ${report.pictures.diagrams} diagram(s) at 600 dpi`);
  for (const w of report.warnings) lines.push("  warning: " + w);
  for (const e of report.errors) lines.push("  error: " + e);
  lines.push(report.ok ? "  -> OK" : report.draft ? "  -> FAILED (draft PDF written for inspection, do not print it)" : "  -> FAILED, no PDF written");
  return lines.join("\n");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const report = { file: args.file, ok: false, draft: args.draft, errors: [], warnings: [] };
  let chrome = null, server = null, issue = null, cmaps = null, labels = null, inBrowser = false;
  const finish = (code) => {
    report.ok = code === 0;
    if (args.report) writeFileSync(args.report, JSON.stringify(report, null, 2) + "\n");
    console.log(summary(report));
    if (chrome) chrome.close();
    if (server) server.close();
    process.exit(code);
  };
  // the browserless check: --check, and --preflight where the full build cannot run
  let before = null;  // the report as it stood when the browser started, for a fallback
  const checkOnly = (why, fallback) => {
    if (fallback) {
      for (const key of ["layout", "pictures", "pdf"]) delete report[key];
      report.errors = [];
      report.warnings = [...before];
    }
    if (why) report.preflight = "check only, " + why + "; prepare lays the pages out after the push";
    report.errors.push(...staticGlyphs(issue, cmaps, labels));
    report.check = { words: words([issue.front, issue.results]) };
    return finish(report.errors.length ? 1 : 0);
  };
  const timer = setTimeout(() => {
    if (args.preflight && inBrowser) return checkOnly(`the full build took over ${TIMEOUT_MS / 1000} s on this machine`, true);
    report.errors.push("timed out after " + TIMEOUT_MS / 1000 + " s");
    finish(1);
  }, TIMEOUT_MS);
  timer.unref();

  if (args.preflight) {
    // Chrome lays the pages out; poppler only checks the printed PDF, so without it the layout
    // checks still run, which is where a page that overflows or a diagram too small is caught.
    const poppler = process.env.COFFEE_NO_POPPLER ? ["pdfinfo", "pdftotext"] : ["pdfinfo", "pdftotext"].filter((exe) => !onPath(exe));
    if (!findChromeOrNull()) {
      args.check = true;
      args.missing = ["Chrome", ...poppler];
    } else if (poppler.length) {
      args.layoutOnly = true;
      report.preflight = "layout only, " + poppler.join(", ") + " not found; prepare checks the PDF after the push";
    } else report.preflight = "full build";
  }

  const loaded = loadLabels(args.labels);
  report.errors.push(...loaded.errors);
  if (report.errors.length) return finish(1);
  labels = loaded.labels;
  try { issue = JSON.parse(readFileSync(args.file, "utf8")); } catch (e) { report.errors.push("cannot read the issue: " + e.message); return finish(1); }
  const checked = validate(issue, labels);
  report.errors.push(...checked.errors);
  report.warnings.push(...checked.warnings);
  if (report.errors.length) return finish(1);

  cmaps = Object.fromEntries(Object.entries(FONT_FACES).map(([key, file]) => [key, [...cmap(join(HERE, "fonts", file))]]));
  const imgs = resolveImages(issue, args.root);
  report.errors.push(...imgs.errors);
  if (args.check) return checkOnly(args.preflight ? args.missing.join(", ") + " not found" : null);
  if (report.errors.length) return finish(1);
  if (args.preflight) {
    // a machine that cannot run Chrome is not a verdict on the issue
    before = [...report.warnings];
    inBrowser = true;
    try {
      return await fullBuild(args, report, issue, cmaps, labels, imgs, finish, (c, s) => { chrome = c; server = s; });
    } catch (e) {
      if (chrome) chrome.close();
      if (server) server.close();
      chrome = server = null;
      return checkOnly("the full build could not run here (" + String(e && e.message || e).split("\n")[0] + ")", true);
    }
  }
  return fullBuild(args, report, issue, cmaps, labels, imgs, finish, (c, s) => { chrome = c; server = s; });
}

function findChromeOrNull() {
  try { return findChrome(); } catch { return null; }
}

async function fullBuild(args, report, issue, cmaps, labels, imgs, finish, hold) {
  let chrome = null, server = null;
  const extra = new Map();
  imgs.found.forEach((f, n) => {
    const url = `/assets/${n}${extname(f.path).toLowerCase()}`;
    extra.set(url, f.path);
    f.block._img = { src: url.slice(1) };
  });
  server = await serve(HERE, extra);
  hold(null, server);
  chrome = await launchChrome();
  hold(chrome, server);
  await chrome.send("Page.enable");
  // measure in the mode we print in
  await chrome.send("Emulation.setEmulatedMedia", { media: "print" });
  await chrome.send("Emulation.setDeviceMetricsOverride", { width: 900, height: 1200, deviceScaleFactor: 1, mobile: false });
  await chrome.send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/template.html` });
  for (let i = 0; i < 100; i++) {
    if (await chrome.evaluate("document.readyState === 'complete' && !!window.CoffeeEdition").catch(() => false)) break;
    await sleep(100);
  }
  const faces = await chrome.evaluate(`(async () => {
    await Promise.all([...document.fonts].map((f) => f.load().catch(() => null)));
    await document.fonts.ready;
    return [...document.fonts].map((f) => f.family.replace(/"/g, "") + " " + f.style + " " + f.weight + ": " + f.status);
  })()`);
  const notLoaded = faces.filter((f) => !f.endsWith(": loaded"));
  if (faces.length !== FACE_COUNT || notLoaded.length) {
    const why = "fonts not loaded: " + (notLoaded.join(", ") || `expected ${FACE_COUNT} faces, found ${faces.length}`);
    if (args.preflight) throw new Error(why);
    report.errors.push(why);
    return finish(1);
  }
  await chrome.evaluate(`CoffeeEdition.configure(${JSON.stringify(labels)})`);

  // Slides: their pixel size fixes the aspect ratio before layout; too few pixels prints soft.
  if (imgs.found.length) {
    const m = await chrome.evaluate(`CoffeeEdition.measureImages(${JSON.stringify(imgs.found.map((f) => f.block._img.src))})`);
    for (const f of imgs.found) {
      const size = m.sizes[f.block._img.src];
      if (!size || size.error) { report.errors.push(`${f.where}.src: ${basename(f.path)} cannot be decoded`); continue; }
      Object.assign(f.block._img, { width: size.width, height: size.height });
      if (size.gray < SLIDE_DARK) report.errors.push(`${f.where}.src: ${basename(f.path)} is a dark slide (mean gray ${size.gray} of 255); on a mono laser it prints as a block of toner: pick a light slide or tell it in words`);
      else if (size.gray < SLIDE_DIM) report.warnings.push(`${f.where}: ${basename(f.path)} is a dim slide (mean gray ${size.gray} of 255); it prints heavy`);
      const dpi = size.width / ((f.block.wide === false ? m.widths.column : m.widths.page) / 96);
      if (dpi < 150) report.warnings.push(`${f.where}: ${basename(f.path)} prints at ${Math.round(dpi)} dpi; 150 or more prints sharp`);
    }
    if (report.errors.length) return finish(1);
  }
  // Diagrams: drawn at their print width, then photographed at 600 dpi.
  const staged = await chrome.evaluate(`CoffeeEdition.stageDiagrams(${JSON.stringify(issue)}, ${JSON.stringify(cmaps)})`);
  report.errors.push(...staged.errors);
  if (report.errors.length && !args.draft) return finish(1);
  for (const d of staged.diagrams) {
    const shot = await chrome.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: d.x, y: d.y, width: d.width, height: d.height, scale: PRINT_SCALE } });
    blockAt(issue, d.key)._img = { src: "data:image/png;base64," + shot.data, width: d.width, height: d.height };
  }
  await chrome.evaluate("CoffeeEdition.clearStage()");
  report.pictures = { slides: imgs.found.length, diagrams: staged.diagrams.length };

  report.layout = await chrome.evaluate(`CoffeeEdition.run(${JSON.stringify(issue)}, ${JSON.stringify(cmaps)})`);
  report.errors.push(...report.layout.errors);
  report.warnings.push(...report.layout.warnings);
  if (report.errors.length && !(args.draft && report.layout.pages.length)) return finish(1);
  if (args.layoutOnly) return finish(report.errors.length ? 1 : 0);

  await chrome.evaluate("Promise.all([...document.images].map((i) => i.decode().catch(() => null))).then(() => true)");
  const printed = await chrome.send("Page.printToPDF", { preferCSSPageSize: true, printBackground: true, displayHeaderFooter: false });
  const pdfPath = args.pdf ? resolve(args.pdf) : join(mkdtempSync(join(tmpdir(), "coffee-edition-pdf-")), "edition.pdf");
  const dropPdf = () => rmSync(args.pdf ? pdfPath : dirname(pdfPath), { recursive: true, force: true });
  writeFileSync(pdfPath, Buffer.from(printed.data, "base64"));

  // The PDF is what gets printed, so check it rather than the screen: one PDF page per laid-out
  // page, and every page's characters present (a clipped line would go missing here).
  const pdfPages = Number((execFileSync("pdfinfo", [pdfPath], { encoding: "utf8" }).match(/^Pages:\s+(\d+)/m) || [])[1]);
  if (pdfPages !== report.layout.pages.length) report.errors.push(`the PDF has ${pdfPages} page(s), the layout ${report.layout.pages.length}`);
  else {
    report.layout.pages.forEach((pg, i) => {
      const txt = execFileSync("pdftotext", ["-f", String(i + 1), "-l", String(i + 1), "-enc", "UTF-8", pdfPath, "-"], { encoding: "utf8" });
      pg.pdf_chars = txt.normalize("NFKC").replace(/[\s\-\u00ad\u2010\u2011]+/g, "").length;
      if (pg.pdf_chars !== pg.chars) report.errors.push(`page ${i + 1}: the PDF carries ${pg.pdf_chars} characters, the layout ${pg.chars}`);
    });
  }
  if (report.errors.length && !args.draft) {
    dropPdf();
    return finish(1);
  }
  report.pdf = { pages: pdfPages, path: args.pdf ? pdfPath : null };
  if (args.png) {
    mkdirSync(args.png, { recursive: true });
    execFileSync("pdftoppm", ["-r", "80", "-png", pdfPath, join(args.png, basename(args.file).replace(/\.edition\.json$|\.json$/, ""))]);
  }
  if (!args.pdf) dropPdf();
  return finish(report.errors.length ? 1 : 0);
}

main().catch((e) => {
  console.error("edition: " + (e && e.stack ? e.stack : e));
  process.exit(1);
});
