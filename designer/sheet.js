// The OMR sheet: one layout drives both the printed page (SVG, in mm) and the
// template.json the reader uses (in px). Nothing here touches the DOM, so
// scripts/check_designer.py can run it under node.

// ---------- fixed geometry (mm) ----------
const PAGE = { w: 210, h: 297 };
const MARGIN = 20;                 // printed content stays this far from the page edge
const MARKER = { size: 8, inset: 12 }; // corner markers, centred `inset` from each edge
const BUBBLE = 4.2;                // bubble diameter
const ID_COL = 5.2, ID_ROW = 5.6;  // ID grid pitch
const OPT = 5.8, Q_ROW = 5.8;      // question pitch: between options, between questions
const Q_LABEL = 8;                 // room for the question number left of the first bubble
const Q_GUTTER = 4;                // space between question columns
const Q_COLS = 4;                  // spread questions over up to this many columns, more only when they need it
// Spare page is spent on the questions: rows, options and bubbles grow up to these
const Q_ROW_MAX = 12, OPT_MAX = 9, Q_BUBBLE_MAX = 6;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
// BITS ID number as degree (F first degree, H higher degree, P PhD), year, last
// four digits, campus (F20231187H), one string per column listing its symbols top
// to bottom. A one-symbol column is fixed: printed in its box, not bubbled.
// Format: (F/H/P) 2 0 (0-4) (0-9)  (0-9)(0-9)(0-9)(0-9)  (H/P/G)
const D = "0123456789";
const ID_COLUMNS = ["FHP", "2", "0", "01234", D, D, D, D, D, "HPG"];
const PX_PER_MM = 8;               // template resolution; scans are resized to this frame

// The reader warps every scan so the marker centres become the template's corners,
// so template coordinates are measured from the top-left marker centre.
const FRAME = {
  x: MARKER.inset, y: MARKER.inset,
  w: PAGE.w - 2 * MARKER.inset, h: PAGE.h - 2 * MARKER.inset,
};
// Concentric marker: black square, white square at 62.5%, black centre at 31.25%.
// scans_to_csv/omr_to_csv.py draws the same pattern for the matcher; keep them equal.
const MARKER_RINGS = [1, 0.625, 0.3125];

function defaults() {
  return {
    title: "BITS Pilani, Hyderabad Campus",
    exam: "Quiz 1",
    course: "",
    date: "",
    instructions: "Use a blue or black ball-point pen and fill each bubble completely.\nBubble your ID number and set. Do not make stray marks on this sheet.",
    showSet: true,
    sets: "ABCD",
    idTitle: "ID NUMBER",
    questions: 30,
    options: "ABCD",
  };
}

const chars = (s) => [...new Set(String(s || "").replace(/\s+/g, "").toUpperCase())];
const lines = (s) => String(s || "").split("\n").map((l) => l.trim()).filter(Boolean);
const toInt = (v, lo, hi, fallback) => {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : fallback;
};

// Where everything goes. Every bubble is { cx, cy, label }.
// The header band (set, instructions, ID grid) is kept tight so the questions
// get the page; question columns are as many as the option count allows.
function layout(s) {
  const issues = [];
  const left = MARGIN, right = PAGE.w - MARGIN;
  const out = { texts: [], lines: [], boxes: [], bubbles: [], fields: [], markers: [], idColumns: [], issues };

  // header
  out.texts.push({ x: PAGE.w / 2, y: 22, text: s.title, size: 4.6, bold: true, anchor: "middle" });
  const sub = [s.exam, s.course, s.date].map((t) => (t || "").trim()).filter(Boolean).join("   ·   ");
  if (sub) out.texts.push({ x: PAGE.w / 2, y: 28, text: sub, size: 3.4, anchor: "middle" });
  out.lines.push({ x1: left, y1: 32, x2: right, y2: 32, width: 0.3 });

  // ID grid, right-aligned: the heading beside a write-in box over each column, bubbles below
  const idCols = ID_COLUMNS.map(chars);
  const bandTop = 39, boxTop = bandTop - 2;
  const idX0 = right - BUBBLE / 2 - (idCols.length - 1) * ID_COL;
  const idTitleW = (s.idTitle || "").length * 3 * 0.62; // ponytail: bold caps at ~0.62 em
  let idBottom = bandTop;
  if (idCols.length) {
    out.texts.push({ x: idX0 - ID_COL / 2 - 1.5, y: boxTop + 3.8, text: s.idTitle, size: 3, bold: true, anchor: "end" });
    idCols.forEach((symbols, i) => {
      const cx = idX0 + i * ID_COL, top = boxTop + 9.5;
      out.boxes.push({ x: cx - ID_COL / 2 + 0.3, y: boxTop, w: ID_COL - 0.6, h: 5.5 });
      if (symbols.length === 1) { // fixed: the reader puts it back into the ID (template idColumns)
        out.texts.push({ x: cx, y: boxTop + 4, text: symbols[0], size: 3.4, bold: true, anchor: "middle" });
        out.idColumns.push(symbols[0]);
        return;
      }
      const bubbles = symbols.map((label, r) => ({ cx, cy: top + r * ID_ROW, label }));
      out.bubbles.push(...bubbles);
      out.fields.push({ name: `ID${i + 1}`, label: `id${i + 1}`, direction: "vertical", bubbles, gap: ID_ROW });
      out.idColumns.push(`id${i + 1}`);
      idBottom = Math.max(idBottom, bubbles.at(-1).cy + BUBBLE / 2);
    });
  }
  const leftRight = (idCols.length ? idX0 - BUBBLE / 2 : right) - 5; // left column ends here
  if (leftRight - left < 40) issues.push("Too many ID columns: the grid runs into the set box.");

  // left of the grid: set, then instructions
  let y = bandTop;
  const sets = s.showSet ? chars(s.sets) : [];
  if (sets.length) {
    out.texts.push({ x: left, y: y + 1.1, text: "SET", size: 3, bold: true });
    const bubbles = sets.map((label, i) => ({ cx: left + 12 + i * OPT, cy: y, label }));
    out.bubbles.push(...bubbles);
    out.fields.push({ name: "Set", label: "Set", direction: "horizontal", bubbles, gap: OPT });
    if (bubbles.at(-1).cx + BUBBLE / 2 > leftRight - idTitleW) issues.push("Too many sets to fit beside the ID grid.");
    y += 8;
  }
  for (const line of lines(s.instructions)) {
    out.texts.push({ x: left, y, text: line, size: 3, muted: true });
    // ponytail: width guessed at half an em per character; good enough to catch a collision
    if (line.length * 3 * 0.5 > leftRight - left) issues.push(`Instruction too long for the space beside the ID grid: “${line.slice(0, 30)}…”`);
    y += 4.4;
  }

  // write-ins: name, then signature and date side by side
  const blank = (label, x0, x1) => {
    out.texts.push({ x: x0, y, text: label, size: 3 });
    out.lines.push({ x1: x0 + label.length * 1.5 + 2, y1: y + 0.6, x2: x1, y2: y + 0.6, width: 0.2 });
  };
  y += 5;
  const end = left + (leftRight - left) * 0.7, mid = left + (end - left) * 0.62;
  blank("Name", left, end);
  y += 9;
  blank("Signature", left, mid - 4);
  blank("Date", mid, end);
  y += 3;

  // questions, numbered down each column, spread across the width
  const n = toInt(s.questions, 1, 300, 30);
  const opts = chars(s.options);
  const qTop = Math.max(y, idBottom) + 9;
  out.lines.push({ x1: left, y1: qTop - 5, x2: right, y2: qTop - 5, width: 0.3 });
  const lastRow = FRAME.y + FRAME.h - MARKER.size - BUBBLE / 2; // lowest bubble centre
  const rowsFit = Math.max(1, Math.floor((lastRow - qTop) / Q_ROW) + 1);
  const colNeed = Q_LABEL + (opts.length - 1) * OPT + BUBBLE + Q_GUTTER;
  const colsFit = Math.max(1, Math.floor((right - left + Q_GUTTER) / colNeed));
  const cols = Math.min(colsFit, n, Math.max(Q_COLS, Math.ceil(n / rowsFit)));
  const perCol = Math.ceil(n / cols);
  const colW = (right - left) / cols;
  out.fit = { cols, capacity: rowsFit * colsFit };
  if (!opts.length) issues.push("Add at least one answer option.");
  else if (n > rowsFit * colsFit) {
    issues.push(`${n} questions with ${opts.length} options don't fit: at most ${rowsFit * colsFit} do. Cut questions or options.`);
  }
  // fill the page: stretch rows down to the bottom markers, then widen options and
  // grow bubbles into the room that leaves, never letting neighbours touch
  const row = perCol > 1 ? clamp((lastRow - qTop) / (perCol - 1), Q_ROW, Q_ROW_MAX) : Q_ROW;
  let d = clamp(row * 0.55, BUBBLE, Q_BUBBLE_MAX);
  const opt = opts.length > 1 ? clamp((colW - Q_LABEL - Q_GUTTER - d) / (opts.length - 1), OPT, OPT_MAX) : OPT;
  d = clamp(opt - 1.5, BUBBLE, d);
  const numSize = Math.min(3.8, 3 * d / BUBBLE);
  for (let c = 0; c * perCol < n && opts.length; c++) {
    const first = c * perCol + 1, last = Math.min(n, first + perCol - 1);
    const x0 = left + c * colW + Q_LABEL + d / 2;
    const bubbles = [];
    for (let q = first; q <= last; q++) {
      const cy = qTop + (q - first) * row;
      out.texts.push({ x: x0 - d / 2 - 1.8, y: cy + numSize * 0.36, text: String(q), size: numSize, bold: true, anchor: "end" });
      opts.forEach((label, i) => bubbles.push({ cx: x0 + i * opt, cy, label, d }));
    }
    out.bubbles.push(...bubbles);
    out.fields.push({
      name: `Q${first}_${last}`, label: `q${first}..${last}`, direction: "horizontal",
      bubbles, gap: opt, rowGap: row, values: opts, d,
    });
  }

  for (const [sx, sy] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
    out.markers.push({ cx: FRAME.x + sx * FRAME.w, cy: FRAME.y + sy * FRAME.h });
  }
  return out;
}

// ---------- printed page ----------
function esc(t) {
  return String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

function sheetSvg(L) {
  const parts = [];
  for (const m of L.markers) {
    MARKER_RINGS.forEach((k, i) => {
      const a = MARKER.size * k;
      parts.push(`<rect x="${m.cx - a / 2}" y="${m.cy - a / 2}" width="${a}" height="${a}" fill="${i % 2 ? "#fff" : "#000"}"/>`);
    });
  }
  for (const l of L.lines) parts.push(`<line x1="${l.x1}" y1="${l.y1}" x2="${l.x2}" y2="${l.y2}" stroke="#000" stroke-width="${l.width}"/>`);
  for (const b of L.boxes) parts.push(`<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" fill="none" stroke="#000" stroke-width="0.2"/>`);
  for (const b of L.bubbles) {
    const d = b.d || BUBBLE, k = d / BUBBLE;
    parts.push(`<circle cx="${b.cx}" cy="${b.cy}" r="${d / 2}" fill="none" stroke="#333" stroke-width="0.22"/>`);
    parts.push(`<text x="${b.cx}" y="${b.cy + 0.85 * k}" font-size="${2.4 * k}" text-anchor="middle" fill="#999">${esc(b.label)}</text>`);
  }
  for (const t of L.texts) {
    parts.push(`<text x="${t.x}" y="${t.y}" font-size="${t.size}"${t.bold ? ' font-weight="bold"' : ""}${t.anchor ? ` text-anchor="${t.anchor}"` : ""} fill="${t.muted ? "#444" : "#000"}">${esc(t.text)}</text>`);
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" class="sheet" width="${PAGE.w}mm" height="${PAGE.h}mm" viewBox="0 0 ${PAGE.w} ${PAGE.h}" font-family="Helvetica, Arial, sans-serif">
<rect width="${PAGE.w}" height="${PAGE.h}" fill="#fff"/>
${parts.join("\n")}
</svg>`;
}

// ---------- template.json for scans_to_csv ----------
function template(L) {
  const px = (mm) => Math.round(mm * PX_PER_MM * 100) / 100;
  const size = (d) => Math.round(d * PX_PER_MM);
  const box = size(BUBBLE);
  const origin = (b, w) => [Math.round((b.cx - FRAME.x) * PX_PER_MM - w / 2), Math.round((b.cy - FRAME.y) * PX_PER_MM - w / 2)];
  const fieldBlocks = {};
  for (const f of L.fields) {
    const w = f.d ? size(f.d) : box;
    fieldBlocks[f.name] = {
      ...(f.d ? { bubbleDimensions: [w, w] } : {}),
      bubbleValues: f.values || f.bubbles.map((b) => b.label),
      direction: f.direction,
      fieldLabels: [f.label],
      bubblesGap: px(f.gap),
      labelsGap: px(f.rowGap || 0),
      origin: origin(f.bubbles[0], w),
    };
  }
  const ids = L.fields.filter((f) => f.name.startsWith("ID")).map((f) => f.label);
  const qs = L.fields.filter((f) => f.name.startsWith("Q")).flatMap((f) => {
    const [a, b] = f.label.slice(1).split("..").map(Number);
    return Array.from({ length: b - a + 1 }, (_, i) => `q${a + i}`);
  });
  return {
    pageDimensions: [px(FRAME.w), px(FRAME.h)].map(Math.round),
    bubbleDimensions: [box, box],
    preProcessors: [{
      name: "CropOnMarkers",
      options: {
        relativePath: "omr_marker.png",
        sheetToMarkerWidthRatio: PAGE.w / MARKER.size,
        marker_rescale_range: [70, 130],
        marker_rescale_steps: 12,
      },
    }],
    // idColumns is read by omr_to_csv.py (which removes it before the engine sees it)
    // to put the fixed characters back into "ID NO"
    ...(ids.length ? { idColumns: L.idColumns, customLabels: { "ID NO": ids } } : {}),
    fieldBlocks,
    outputColumns: [
      ...(fieldBlocks.Set ? ["Set"] : []),
      ...(ids.length ? ["ID NO"] : []),
      ...qs,
    ],
  };
}

if (typeof module !== "undefined") module.exports = { defaults, layout, sheetSvg, template };
