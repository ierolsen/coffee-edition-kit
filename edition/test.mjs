#!/usr/bin/env node
/**
 * Runs the edition fixtures through build.mjs and checks the page logic end to end:
 * the sample issue (fixtures/raven.edition.json) stays on two pages, a long results part gets
 * a third page at the end, a long front part gets a continuation page before the results
 * page, and broken input (a code line wider than a column, an unknown block, a character no
 * vendored font has) is refused without a PDF. Pictures: a wide picture, a column diagram, a
 * bar chart and wide code lay out and reach the PDF as images; a picture without a caption, a
 * missing picture, one outside notes/, over-long wide code and a diagram too wide to read in a
 * column are refused. Labels: another language's labels (fixtures/labels-tr.json) print in the
 * masthead and footers, capitals follow that language, and a labels file that drops a
 * placeholder is refused.
 *
 * Gates: --check, the browserless check, refuses and accepts the same characters as the
 * browser (labels included). --preflight refuses an issue past four pages where Chrome is and
 * falls back to --check where it is not. scripts/prepare.py runs on a scratch copy of the
 * repository: a good issue becomes a print job at its local print time (America/New_York, so
 * daylight saving time is in play), a broken one stays in inbox/ and is reported; a nightly
 * issue in dry-run is built and archived but never queued, a late one and a second one for the
 * same morning are dropped. Outputs land in edition/out/ for a look.
 *
 *   node edition/test.mjs
 */
import { execFileSync, spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = dirname(HERE);
const OUT = join(HERE, "out");
// The cases print the English labels from the fixtures, so edition/labels.json can be translated
// without breaking them.
const EN = join(HERE, "fixtures", "labels-en.json");
const fixture = JSON.parse(readFileSync(join(HERE, "fixtures", "raven.edition.json"), "utf8"));
const clone = () => JSON.parse(JSON.stringify(fixture));

// Extra paragraphs, numbered so each one is distinct; enough to fill a good part of a page.
const filler = (n) => Array.from({ length: n }, (_, i) => ({
  type: "p",
  text: `Extra paragraph ${i + 1}: this text is here only to test the paginator. When it no longer fits in the columns a new page must open, the lines must carry on there in the same layout, and no sentence may be cut.`,
}));

// Pictures live next to notes; the cases build against a scratch root that has one.
const PICTURES = mkdtempSync(join(tmpdir(), "coffee-edition-pictures-"));
mkdirSync(join(PICTURES, "notes", "fixture"), { recursive: true });
cpSync(join(HERE, "fixtures", "assets", "fixture-slide.png"), join(PICTURES, "notes", "fixture", "fixture-slide.png"));
const SLIDE = { type: "image", src: "notes/fixture/fixture-slide.png" };
const DIAGRAM = { type: "diagram", mermaid: "flowchart TD\n  Q[\"Question\"] --> R[\"Retrieve: related passages\"]\n  R --> K[\"Rerank: best three\"]\n  K --> G[\"Generate: answer\"]" };
const BARS = { type: "bars", prefix: "%", decimals: 2, max: 100, rows: [["Greedy", 73.66], ["Beam", 28.94], ["Human", 0.28]], accent: [0] };
const WIDE_CODE = { type: "code", wide: true, lines: ["model = get_peft_model(model, LoraConfig(r=8, lora_alpha=8, target_modules=[\"q\", \"v\"]))"] };
const CODE = { type: "code", lines: ["def total(n):", "    return n * (n + 1) // 2"] };
const cap = (text) => ({ type: "caption", text });
const beforeLabel = (blocks, text) => {
  const at = blocks.findIndex((b) => b.type === "label" && b.text === text);
  if (at < 0) throw new Error("the fixture has no label " + text);
  return at;
};

function build(name, issue, extra = []) {
  const file = join(OUT, `${name}.edition.json`);
  const pdf = join(OUT, `${name}.pdf`);
  const report = join(OUT, `${name}.report.json`);
  writeFileSync(file, JSON.stringify(issue, null, 2));
  rmSync(pdf, { force: true });
  rmSync(report, { force: true });
  const labels = extra.includes("--labels") ? [] : ["--labels", EN];
  const run = spawnSync(process.execPath, [join(HERE, "build.mjs"), file, "--pdf", pdf, "--report", report, "--png", OUT, "--root", PICTURES, ...labels, ...extra], { encoding: "utf8" });
  const rep = existsSync(report) ? JSON.parse(readFileSync(report, "utf8")) : null;
  return { code: run.status, out: run.stdout + run.stderr, report: rep, pdf: existsSync(pdf) };
}

const pdfText = (name, page) => execFileSync("pdftotext", ["-f", String(page), "-l", String(page), join(OUT, `${name}.pdf`), "-"], { encoding: "utf8" });
const FRESH = () => JSON.parse(readFileSync(join(HERE, "fixtures", "fresh-ink.edition.json"), "utf8"));
const OLD_RADAR = () => JSON.parse(readFileSync(join(HERE, "fixtures", "radar.edition.json"), "utf8"));
// pdftotext keeps letter-spaced labels apart (I N S I D E) and breaks lines where the page does
const squeeze = (s) => s.replace(/\s+/g, "");

// The PDF's pages at 300 dpi through a QR reader (edition/qrdecode.py, zxing-cpp): every code the
// layout drew must scan to its card's link. null when the reader is not installed (QR_PYTHON picks the Python).
function qrScans(name, want) {
  const dir = mkdtempSync(join(tmpdir(), "coffee-qr-"));
  try {
    execFileSync("pdftoppm", ["-r", "300", "-gray", "-png", join(OUT, name + ".pdf"), join(dir, "p")]);
    const pngs = readdirSync(dir).filter((f) => f.endsWith(".png")).map((f) => join(dir, f));
    const run = spawnSync(process.env.QR_PYTHON || "python3", [join(HERE, "qrdecode.py"), ...pngs], { encoding: "utf8" });
    if (run.status === 2) return null;
    if (run.status !== 0) return { ok: false, why: "the reader failed: " + run.stderr.trim().split("\n").pop() };
    const got = Object.values(JSON.parse(run.stdout)).flat();
    const missing = want.filter((u) => !got.includes(u));
    return { ok: got.length === want.length && !missing.length, why: got.length + " of " + want.length + " scanned" + (missing.length ? ", not found: " + missing.join(", ") : "") };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const cases = [
  ["the sample issue fits on two pages", "raven", () => clone(), [], (r) => [
    [r.code === 0, "builds"],
    [kinds(r) === "front,results", "pages are front, results: " + kinds(r)],
    [r.report.layout.pages[1].closing, "the takeaway is on page 2"],
    [r.report.layout.pages[0].footer === "Continued on page 2 · 1/2", "page 1 footer: " + r.report.layout.pages[0].footer],
    [r.report.layout.pages[1].footer === "Coffee Edition · Issue 002 · 2/2", "page 2 footer: " + r.report.layout.pages[1].footer],
    [r.report.warnings.length === 0, "no warnings: " + r.report.warnings.join("; ")],
    [r.code === 0 && /ISSUE 002 · PRINTED 07:30/.test(pdfText("raven", 1)) && /SATURDAY, 17 OCTOBER 2026/.test(pdfText("raven", 1)),
      "the masthead says SATURDAY, 17 OCTOBER 2026 and ISSUE 002 · PRINTED 07:30"],
  ]],
  ["a long results part gets a third page at the end", "long-results", () => {
    const d = clone();
    d.results.blocks.splice(beforeLabel(d.results.blocks, "LIMITS"), 0, { type: "label", text: "MORE" }, ...filler(16));
    return d;
  }, [], (r) => [
    [r.code === 0, "builds"],
    [kinds(r) === "front,results,cont", "pages are front, results, cont: " + kinds(r)],
    [r.report.layout.pages[2].closing && !r.report.layout.pages[1].closing, "the takeaway moved to page 3"],
    [r.report.layout.pages[1].footer === "Continued on page 3 · 2/3", "page 2 footer: " + r.report.layout.pages[1].footer],
    [r.report.layout.pages[2].footer === "Coffee Edition · Issue 002 · 3/3", "page 3 footer: " + r.report.layout.pages[2].footer],
  ]],
  ["a long front part gets a continuation page before the results", "long-front", () => {
    const d = clone();
    d.front.push({ type: "label", text: "MORE" }, ...filler(16));
    return d;
  }, [], (r) => [
    [r.code === 0, "builds"],
    [kinds(r) === "front,cont,results", "pages are front, cont, results: " + kinds(r)],
    [r.report.layout.pages[2].closing, "the takeaway is on the results page"],
    [r.report.layout.pages[0].footer === "Continued on page 2 · 1/3", "page 1 footer: " + r.report.layout.pages[0].footer],
  ]],
  ["a code line wider than a column is refused", "wide-code", () => {
    const d = clone();
    d.front.push({ ...CODE, lines: [...CODE.lines, "    return some_function_with_a_long_name(n)"] }, cap("adds the numbers."));
    return d;
  }, [], (r) => refused(r, /characters, a column holds/)],
  ["an unknown block type is refused", "unknown-block", () => {
    const d = clone();
    d.front.push({ type: "video", src: "x.mp4" });
    return d;
  }, [], (r) => refused(r, /unknown block type/)],
  ["a character no vendored font has is refused", "missing-glyph", () => {
    const d = clone();
    d.front.push({ type: "p", text: "A check mark: ✓" });
    return d;
  }, [], (r) => refused(r, /no vendored glyph/)],
  ["pictures lay out: a wide picture, a column diagram, bars and wide code", "pictures", () => {
    const d = clone();
    d.results.blocks.splice(beforeLabel(d.results.blocks, "LIMITS"), 0, { type: "label", text: "PICTURES" }, SLIDE, cap("a test picture, full width."),
      DIAGRAM, cap("the flow reads top to bottom."), BARS, cap("repetition rate, lower is better."), WIDE_CODE, cap("wraps the model with LoRA."));
    return d;
  }, [], (r) => {
    const images = r.pdf ? execFileSync("pdfimages", ["-list", join(OUT, "pictures.pdf")], { encoding: "utf8" }).trim().split("\n").slice(2) : [];
    return [
      [r.code === 0, "builds"],
      [!!r.report.pictures && r.report.pictures.slides === 1 && r.report.pictures.diagrams === 2, "one picture and two diagrams: " + JSON.stringify(r.report.pictures)],
      [images.length >= 3, "the PDF carries the picture and the diagrams as images: " + images.length],
      [r.report.errors.length === 0, "no errors: " + r.report.errors.join("; ")],
    ];
  }],
  ["code without an explanation is refused", "code-bare", () => {
    const d = clone();
    d.front.push({ type: "code", lines: ["x = 1"] }, { type: "p", text: "Not an explanation." });
    return d;
  }, [], (r) => refused(r, /code block needs a caption/)],
  ["broken pictures are refused: no caption, a missing picture, wide code over 88 characters", "pictures-broken", () => {
    const d = clone();
    d.front.push({ type: "image", src: "notes/fixture/missing.webp" }, cap("missing."), { ...SLIDE }, { type: "p", text: "No caption." },
      { type: "code", wide: true, lines: ["x".repeat(89)] });
    return d;
  }, [], (r) => [
    [r.code === 1 && !r.pdf, "exit code 1, no PDF"],
    [r.report.errors.some((e) => /needs a caption/.test(e)), "a picture without a caption is named"],
    [r.report.errors.some((e) => /89 characters, the text area holds 88/.test(e)), "wide code over 88 is named"],
  ]],
  ["a missing picture file is refused", "picture-missing", () => {
    const d = clone();
    d.front.push({ type: "image", src: "notes/fixture/missing.webp" }, cap("missing."));
    return d;
  }, [], (r) => refused(r, /missing\.webp does not exist/)],
  ["a picture outside notes/ is refused", "picture-outside", () => {
    const d = clone();
    d.front.push({ type: "image", src: "notes/../printer.png" }, cap("outside."), { type: "image", src: "edition/fixtures/assets/fixture-slide.png" }, cap("not a note's."));
    return d;
  }, [], (r) => [
    [r.code === 1 && !r.pdf, "exit code 1, no PDF"],
    [r.report.errors.filter((e) => /a picture next to a note/.test(e)).length === 2, "both pictures are named: " + r.report.errors.join("; ")],
  ]],
  ["Fresh Ink: sixteen cards, nine charts and four briefs take four pages, a QR code on each", "fresh-ink", FRESH, [], (r) => {
    const p1 = r.pdf ? pdfText("fresh-ink", 1) : "";
    const qr = r.pdf ? qrScans("fresh-ink", r.report.layout.qr) : null;
    return [
      [r.code === 0, "builds"],
      [kinds(r) === "fresh,fresh,fresh,fresh", "four Fresh Ink pages: " + kinds(r)],
      [r.report.layout.charts === 9, "nine charts: " + r.report.layout.charts],
      [r.report.layout.qr.length === 16 && new Set(r.report.layout.qr).size === 16, "a QR code for each of the sixteen cards: " + r.report.layout.qr.length],
      [r.report.layout.pages[0].footer === "Continued on page 2 · 1/4", "page 1 footer: " + r.report.layout.pages[0].footer],
      [["96 Robots Learn From Each Other", "FRESH INK", "IN BRIEF", "INSIDE", "927 works scanned"].every((w) => squeeze(p1).includes(squeeze(w))), "the front page has its headline, flag, IN BRIEF and INSIDE"],
      [qr === null || qr.ok, qr === null ? "QR scan skipped (no zxing-cpp)" : "every printed QR code scans to its card's link: " + qr.why],
    ];
  }],
  ["Fresh Ink prints another language's labels", "fresh-ink-tr", FRESH, ["--labels", join(HERE, "fixtures", "labels-tr.json")], (r) => {
    const p1 = r.pdf ? pdfText("fresh-ink-tr", 1) : "";
    return [
      [r.code === 0, "builds"],
      [["KISA KISA", "İÇERİDE", "gecenin yeni AI yöntemleri", "Bu sayı için 927 çalışma tarandı"].every((w) => squeeze(p1).includes(squeeze(w))), "the front page labels are Turkish"],
    ];
  }],
  ["an old RADAR file (no headlines, briefs or charts) still prints as Fresh Ink", "radar", OLD_RADAR, [], (r) => [
    [r.code === 0, "builds"],
    [/^fresh(,fresh)?$/.test(kinds(r)), "one or two Fresh Ink pages: " + kinds(r)],
    [r.report.layout.qr.length === 5, "a QR code on each of the five cards: " + r.report.layout.qr.length],
  ]],
  ["Fresh Ink follows an issue on pages of its own, under a running head", "radar-issue", () => {
    const d = clone();
    d.radar = OLD_RADAR().radar;
    return d;
  }, [], (r) => [
    [r.code === 0, "builds"],
    [/^front,results,fresh(,fresh)?$/.test(kinds(r)), "the issue's pages, then Fresh Ink: " + kinds(r)],
  ]],
  ["five Fresh Ink pages are refused, with what to do", "fresh-5", () => {
    const d = FRESH();
    d.radar.items.forEach((c) => delete c.brief);
    return d;
  }, [], (r) => refused(r, /Fresh Ink runs to \d pages; at most 4: mark more cards "brief"/)],
  ["more than four briefs are refused, and a brief has no chart", "fresh-briefs", () => {
    const d = FRESH();
    d.radar.items[8].brief = true;
    d.radar.items[0].brief = true;
    return d;
  }, [], (r) => [
    ...refused(r, /6 cards are "brief"; IN BRIEF holds 4/),
    [r.report.errors.some((e) => /radar\.items\[0\]\.chart: a brief has no room for a chart/.test(e)), "the lead's chart is named"],
  ]],
  ["a chart whose labels leave no room for its bars is refused", "fresh-chart-labels", () => {
    const d = FRESH();
    d.radar.items[2].chart.sub = d.radar.items[2].chart.sub.map((x) => x + " with a data-center grade cooling rack");
    return d;
  }, [], (r) => refused(r, /radar\.items\[2\]\.chart: the labels leave the bars less than 70 px/)],
  ["a malformed chart is refused before layout", "fresh-chart-bad", () => {
    const d = FRESH();
    d.radar.items[0].chart.kind = "pie";
    d.radar.items[1].chart.rows[0] = ["PAR", "high", 95.5];
    d.radar.items[3].chart.series[0].points.push(["extreme", 70]);
    return d;
  }, [], (r) => [
    ...refused(r, /radar\.items\[0\]\.chart\.kind: "bars", "groups" or "line"/),
    [r.report.errors.some((e) => /radar\.items\[1\]\.chart\.rows: 2 to 8 rows/.test(e)), "the bad row is named"],
    [r.report.errors.some((e) => /radar\.items\[3\]\.chart\.series\[0\]\.points\[4\]/.test(e)), "the point off the axis is named"],
  ]],
  ["a blog card without its address is refused, the QR code needs it", "fresh-link", () => {
    const d = FRESH();
    delete d.radar.items[8].link;
    d.radar.items[9].link = "github.com/PKU-VaLuE-Lab/OmniReasoning";
    return d;
  }, [], (r) => [
    ...refused(r, /radar\.items\[8\]\.link: a blog or web card needs its page's address/),
    [r.report.errors.some((e) => /radar\.items\[9\]\.link: the full https:\/\/ address/.test(e)), "a link without https:// is named"],
  ]],
  ["a story too tall for an empty column is refused, naming it", "fresh-long", () => {
    const d = FRESH();
    d.radar.items[5].how = Array(20).fill(d.radar.items[5].how).join(" ");
    return d;
  }, [], (r) => refused(r, /Fresh Ink: radar\.items\[5\] does not fit in an empty column: shorten it/)],
  ["eighteen cards are refused", "radar-18", () => {
    const d = OLD_RADAR();
    const five = d.radar.items;
    d.radar.items = [...five, ...five, ...five, five[0], five[1], five[2]];
    return d;
  }, [], (r) => refused(r, /radar\.items: 5 to 17 cards/)],
  ["a Fresh Ink issue needs five cards with a sourced number each", "radar-short", () => {
    const d = OLD_RADAR();
    d.radar.items.pop();
    delete d.radar.items[0].number.quote;
    return d;
  }, [], (r) => [
    ...refused(r, /radar\.items: 5 to 17 cards/),
    [r.report.errors.some((e) => /radar\.items\[0\]\.number\.quote: required/.test(e)), "the missing quote is named"],
  ]],
  ["a diagram too wide to read in a column is refused", "diagram-wide", () => {
    const d = clone();
    d.front.push({ type: "diagram", mermaid: "flowchart LR\n  A[\"The first long box\"] --> B[\"The second long box\"] --> C[\"The third long box\"] --> D[\"The fourth long box\"]" }, cap("far too wide."));
    return d;
  }, [], (r) => refused(r, /labels would print at/)],
  ["another language's labels print in the masthead and footers", "labels-tr", () => clone(),
    ["--labels", join(HERE, "fixtures", "labels-tr.json")], (r) => [
    [r.code === 0, "builds"],
    [r.report.layout && r.report.layout.pages[0].footer === "Devamı 2. sayfada · 1/2", "page 1 footer: " + (r.report.layout && r.report.layout.pages[0].footer)],
    [r.report.layout && r.report.layout.pages[1].footer === "Coffee Edition · Sayı 002 · 2/2", "page 2 footer: " + (r.report.layout && r.report.layout.pages[1].footer)],
    [r.code === 0 && /CUMARTESİ, 17 EKİM 2026/.test(pdfText("labels-tr", 1)) && /SAYI 002 · BASKI 07:30/.test(pdfText("labels-tr", 1)),
      "the masthead says CUMARTESİ, 17 EKİM 2026 and SAYI 002 · BASKI 07:30"],
  ]],
  ["capitals follow the labels' language", "caps-tr", () => {
    const d = clone();
    d.kicker = "GÜNÜN MAKALESi";
    return d;
  }, ["--labels", join(HERE, "fixtures", "labels-tr.json")], (r) => refused(r, /type it in capitals: "GÜNÜN MAKALESİ"/)],
  ["a labels file that drops a placeholder is refused", "labels-broken", () => clone(), ["--labels", (() => {
    const labels = JSON.parse(readFileSync(EN, "utf8"));
    labels.continues = "Continued on the next page";
    labels.weekdays = labels.weekdays.slice(1);
    const file = join(PICTURES, "labels-broken.json");
    writeFileSync(file, JSON.stringify(labels));
    return file;
  })()], (r) => [
    [r.code === 1 && !r.pdf, "exit code 1, no PDF"],
    [r.report.errors.some((e) => /labels\.continues: keep \{next\} in it/.test(e)), "the missing {next} is named"],
    [r.report.errors.some((e) => /labels\.weekdays: 7 names/.test(e)), "the short weekday list is named"],
  ]],
];

// --check runs where there is no browser; it must agree with the browser's glyph check.
function checkAgrees() {
  const variants = [
    ["Greek in prose", (d) => { d.front[1].text += " θ"; }, false],
    ["an arrow in prose (Gloock draws it)", (d) => { d.front[1].text += " a → b"; }, true],
    ["a check mark in prose", (d) => { d.front[1].text += " ✓"; }, false],
    ["a check mark in code", (d) => { d.front.push({ ...CODE, lines: ["x = 1  # ✓"] }, cap("sets x.")); }, true],
    ["a check mark in backticks", (d) => { d.front[1].text += " `✓`"; }, true],
    ["subscript zero in a label", (d) => { d.front[0].text = "IN SHORT ₀"; }, true],
  ];
  const labelVariants = [
    ["a check mark in a footer label", (l) => { l.last_page += " ✓"; }, true],
    ["Greek in a caption lead", (l) => { l.shows = "θ:"; }, false],
  ];
  const checks = [];
  let out = "";
  const both = (name, file, ok, extra = ["--labels", EN]) => {
    const fast = spawnSync(process.execPath, [join(HERE, "build.mjs"), file, "--check", ...extra], { encoding: "utf8" });
    const full = spawnSync(process.execPath, [join(HERE, "build.mjs"), file, ...extra], { encoding: "utf8" });
    out += fast.stdout + full.stdout;
    checks.push([(fast.status === 0) === ok && (full.status === 0) === ok,
      `${name}: --check ${fast.status === 0 ? "accepts" : "refuses"}, the browser ${full.status === 0 ? "accepts" : "refuses"}, both should ${ok ? "accept" : "refuse"}`]);
  };
  const file = join(OUT, "glyph-variant.edition.json");
  for (const [name, edit, ok] of variants) {
    const d = clone();
    edit(d);
    writeFileSync(file, JSON.stringify(d));
    both(name, file, ok);
  }
  writeFileSync(file, JSON.stringify(clone()));
  const labelsFile = join(PICTURES, "labels-variant.json");
  for (const [name, edit, ok] of labelVariants) {
    const labels = JSON.parse(readFileSync(EN, "utf8"));
    edit(labels);
    writeFileSync(labelsFile, JSON.stringify(labels));
    both(name, file, ok, ["--labels", labelsFile]);
  }
  rmSync(file, { force: true });
  return { out, checks };
}

// --preflight: the full build where the machine can run it, --check where it cannot.
function preflightGate() {
  const good = join(OUT, "preflight-good.edition.json");
  const long = join(OUT, "preflight-long.edition.json");
  writeFileSync(good, JSON.stringify(clone()));
  const d = clone();
  d.front.splice(2, 0, ...filler(140));
  writeFileSync(long, JSON.stringify(d));
  const small = join(OUT, "preflight-small-diagram.edition.json");
  const t = clone();
  t.front.push({ type: "diagram", mermaid: "flowchart LR\n  A[\"The first long box\"] --> B[\"The second long box\"] --> C[\"The third long box\"] --> D[\"The fourth long box\"]" }, cap("far too wide."));
  writeFileSync(small, JSON.stringify(t));
  const run = (file, env = {}) => {
    const r = spawnSync(process.execPath, [join(HERE, "build.mjs"), file, "--preflight", "--labels", EN], { encoding: "utf8", env: { ...process.env, ...env } });
    return { code: r.status, out: r.stdout + r.stderr };
  };
  const full = run(good), over = run(long);
  const noChrome = run(good, { COFFEE_NO_CHROME: "1" }), overNoChrome = run(long, { COFFEE_NO_CHROME: "1" });
  const dead = run(good, { CHROME: "/usr/bin/false" });
  const noPoppler = run(good, { COFFEE_NO_POPPLER: "1" }), overNoPoppler = run(long, { COFFEE_NO_POPPLER: "1" });
  const smallNoPoppler = run(small, { COFFEE_NO_POPPLER: "1" });
  for (const f of [good, long, small]) rmSync(f, { force: true });
  return {
    out: [full, over, noChrome, overNoChrome, dead, noPoppler, overNoPoppler, smallNoPoppler].map((r) => r.out).join("\n"),
    checks: [
      [full.code === 0 && /preflight: full build/.test(full.out) && /pdf: 2 page\(s\)/.test(full.out), "with Chrome the good issue gets the full build and passes"],
      [over.code === 1 && /preflight: full build/.test(over.out) && /more than 4 means the issue is far too long/.test(over.out), "with Chrome an issue past four pages is refused before the push"],
      [noChrome.code === 0 && /check only, Chrome not found/.test(noChrome.out), "without Chrome the good issue passes the browserless check"],
      [overNoChrome.code === 0 && /check only/.test(overNoChrome.out), "without Chrome the long issue still passes (only the full build sees pages)"],
      [dead.code === 0 && /could not run here \(Chrome did not start\)/.test(dead.out), "a Chrome that does not start falls back to the browserless check"],
      [noPoppler.code === 0 && /preflight: layout only, pdfinfo, pdftotext not found/.test(noPoppler.out) && !/pdf: \d+ page/.test(noPoppler.out),
        "with Chrome but no poppler the layout is checked and the PDF checks are left to prepare"],
      [overNoPoppler.code === 1 && /more than 4 means the issue is far too long/.test(overNoPoppler.out), "without poppler an issue past four pages is still refused"],
      [smallNoPoppler.code === 1 && /labels would print at/.test(smallNoPoppler.out), "without poppler a diagram too small to read is still refused"],
    ],
  };
}

// A scratch copy of the repository for the print step, never the real inbox/.
function scratchRepo(prefix, settings) {
  const root = mkdtempSync(join(tmpdir(), prefix));
  cpSync(join(REPO, "scripts"), join(root, "scripts"), { recursive: true });
  cpSync(HERE, join(root, "edition"), { recursive: true, filter: (src) => !src.startsWith(OUT) });
  const cfg = JSON.parse(readFileSync(join(REPO, "printer.json"), "utf8"));
  writeFileSync(join(root, "printer.json"), JSON.stringify({ ...cfg, ...settings }));
  mkdirSync(join(root, "inbox"));
  return root;
}

function readLog(root) {
  const events = existsSync(join(root, "log", "prints.jsonl"))
    ? readFileSync(join(root, "log", "prints.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l)) : [];
  const table = existsSync(join(root, "log", "prints.md")) ? readFileSync(join(root, "log", "prints.md"), "utf8") : "";
  return { events, table };
}

// The print step: a hand-dropped issue (no note) prints at its local time in New York.
function prepareGate() {
  const root = scratchRepo("coffee-edition-prepare-", { timezone: "America/New_York" });
  try {
    const { note, ...plain } = fixture;  // eslint-disable-line no-unused-vars
    writeFileSync(join(root, "inbox", "good.edition.json"), JSON.stringify(plain));
    const broken = { ...plain, front: [...plain.front, { ...CODE, lines: [...CODE.lines, "    return some_function_with_a_long_name(n)"] }, cap("adds.")] };
    writeFileSync(join(root, "inbox", "broken.edition.json"), JSON.stringify(broken));
    const run = spawnSync("python3", [join(root, "scripts", "prepare.py"), "--root", root], { encoding: "utf8" });
    const index = JSON.parse(readFileSync(join(root, "queue", "index.json"), "utf8"));
    const wanted = JSON.parse(readFileSync(join(REPO, "printer.json"), "utf8")).formats;
    const job = index.jobs[0];
    const failures = existsSync(join(root, "edition-failures.txt")) ? readFileSync(join(root, "edition-failures.txt"), "utf8") : "";
    const { events, table } = readLog(root);
    const queued = events.find((e) => e.event === "queued");
    const rejected = events.find((e) => e.event === "rejected");
    return {
      out: run.stdout + run.stderr,
      checks: [
        [run.status === 0, "prepare.py exits 0 (the workflow fails later, after the queue commit)"],
        [index.jobs.length === 1 && /good$/.test(job.id), "exactly one job, for the good issue: " + index.jobs.map((j) => j.id).join(", ")],
        [!!job && wanted.every((f) => (job.formats[f] || []).length > 0) && Object.keys(job.formats).length === wanted.length,
          "the job carries exactly the formats printer.json asks for (" + wanted.join(", ") + "): " + (job ? Object.keys(job.formats).join(", ") : "no job")],
        [readdirSync(join(root, "inbox")).join(",") === "broken.edition.json", "only the broken issue is left in inbox/: " + readdirSync(join(root, "inbox")).join(",")],
        [/broken\.edition\.json/.test(failures) && /a column holds/.test(failures), "edition-failures.txt names the broken issue and why"],
        [!!queued && queued.job === (job && job.id) && queued.pages === 2 && queued.title === fixture.headline,
          "the print log has a queued line with the title and 2 pages: " + JSON.stringify(queued)],
        [!!rejected && rejected.source === "broken.edition.json" && /a column holds/.test(rejected.error), "the print log has the broken issue as rejected, with its first error"],
        [!!job && job.print_at === "2026-10-17T11:30:00+00:00" && job.print_local === "17 Oct 2026 07:30 America/New_York" && queued && queued.print_at === job.print_at,
          "07:30 in New York in October (summer time, UTC-4) is 11:30 UTC, and the job says so: " + (job && job.print_at + " / " + job.print_local)],
        [table.includes(fixture.headline) && table.includes("queued · prints 17 Oct 2026 07:30") && table.includes("(America/New_York)"),
          "log/prints.md shows the issue as queued for 07:30 New York time"],
        [table.includes("rejected · "), "log/prints.md shows the rejection"],
      ],
    };
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

// The nightly path: drafts in dry-run, late and second issues dropped, the note's picture used.
function nightlyGate() {
  const root = scratchRepo("coffee-edition-nightly-", { nightly: "dry-run" });
  try {
    mkdirSync(join(root, "notes", "fixture"), { recursive: true });
    cpSync(join(PICTURES, "notes", "fixture", "fixture-slide.png"), join(root, "notes", "fixture", "fixture-slide.png"));
    const ahead = new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10);
    const nightly = (date) => ({ ...clone(), date, note: "notes/002-raven.md" });
    writeFileSync(join(root, "inbox", "a-late.edition.json"), JSON.stringify(nightly("2026-10-02")));
    const withPicture = nightly(ahead);
    withPicture.front.push(SLIDE, cap("a test picture."));
    writeFileSync(join(root, "inbox", "b-next.edition.json"), JSON.stringify(withPicture));
    writeFileSync(join(root, "inbox", "c-twin.edition.json"), JSON.stringify(nightly(ahead)));
    const archive = join(root, "archive-root");
    const run = spawnSync("python3", [join(root, "scripts", "prepare.py"), "--root", root, "--archive-root", archive], { encoding: "utf8" });
    const index = JSON.parse(readFileSync(join(root, "queue", "index.json"), "utf8"));
    const { events, table } = readLog(root);
    const pdfs = execFileSync("find", [archive, "-name", "*.pdf"], { encoding: "utf8" }).trim().split("\n").filter(Boolean);
    const by = (source) => events.find((e) => e.source === source) || {};
    return {
      out: run.stdout + run.stderr,
      checks: [
        [run.status === 0, "prepare.py exits 0"],
        [index.jobs.length === 0, "nothing is queued in dry-run: " + index.jobs.map((j) => j.id).join(", ")],
        [readdirSync(join(root, "inbox")).length === 0, "inbox/ is empty: " + readdirSync(join(root, "inbox")).join(",")],
        [by("a-late.edition.json").event === "skipped" && /past its print time/.test(by("a-late.edition.json").reason), "the late issue is skipped"],
        [by("b-next.edition.json").event === "drafted" && by("b-next.edition.json").pages >= 2 && by("b-next.edition.json").date === ahead
          && by("b-next.edition.json").note === "notes/002-raven.md" && /^[0-9a-f]{40}$/.test(by("b-next.edition.json").blob || ""),
          "the next issue, with its note's picture, is drafted with its note, date and blob id: " + JSON.stringify(by("b-next.edition.json"))],
        [by("c-twin.edition.json").event === "skipped" && /already has an issue/.test(by("c-twin.edition.json").reason), "a second issue for the same date is skipped"],
        [pdfs.length === 1, "the draft's PDF is archived: " + pdfs.join(", ")],
        [existsSync(join(root, "issues", ahead.slice(0, 4), ahead.slice(5, 7), "b-next.edition.json")), "the drafted issue is kept under issues/YYYY/MM/"],
        [table.includes("draft · not printed") && table.includes("skipped · "), "log/prints.md shows the draft and the skips"],
      ],
    };
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

function kinds(r) { return r.report && r.report.layout ? r.report.layout.pages.map((p) => p.kind).join(",") : "none"; }
function refused(r, pattern) {
  return [
    [r.code === 1, "exit code 1"],
    [!r.pdf, "no PDF written"],
    [!!r.report && r.report.errors.some((e) => pattern.test(e)), "error matches " + pattern + ": " + (r.report ? r.report.errors.join("; ") : "no report")],
  ];
}

mkdirSync(OUT, { recursive: true });
let failed = 0;
try {
  for (const [title, name, make, extra, expect] of cases) {
    const r = build(name, make(), extra);
    const checks = r.report ? expect(r) : [[false, "no report written:\n" + r.out]];
    const bad = checks.filter(([ok]) => !ok);
    console.log((bad.length ? "FAIL  " : "ok    ") + title);
    for (const [, what] of bad) console.log("      " + what);
    if (bad.length) { console.log(r.out.split("\n").map((l) => "      | " + l).join("\n")); failed++; }
  }
  const gates = [
    ["--check refuses and accepts the same characters as the browser, labels included", checkAgrees],
    ["--preflight builds in full where Chrome is, checks the layout without poppler, falls back to --check without Chrome", preflightGate],
    ["the print step queues a good issue at its local time and keeps a broken one back", prepareGate],
    ["a nightly issue in dry-run is archived, never queued; late and second issues are dropped", nightlyGate],
  ];
  for (const [title, run] of gates) {
    const gate = run();
    const bad = gate.checks.filter(([ok]) => !ok);
    console.log((bad.length ? "FAIL  " : "ok    ") + title);
    for (const [, what] of bad) console.log("      " + what);
    if (bad.length) { console.log(gate.out.split("\n").map((l) => "      | " + l).join("\n")); failed++; }
  }
  const total = cases.length + gates.length;
  console.log(failed ? `\n${failed} of ${total} cases failed` : `\nall ${total} cases passed`);
} finally {
  rmSync(PICTURES, { recursive: true, force: true });
}
process.exit(failed ? 1 : 0);
