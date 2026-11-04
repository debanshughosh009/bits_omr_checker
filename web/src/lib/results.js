// An exam's sheets, scored with its keys and rules, plus the numbers the pages show
import { parseKey, scoreSheet, sheetInfo, withDefaults } from "@/lib/score";

// The reader's check column, minus multi-marks on questions whose key expects several options
function readerFlags(check = "", r) {
  const multi = new Set(r.perQ.filter((p) => p.key?.kind === "multiple").map((p) => p.q));
  return check.split(", ").filter(Boolean).map((f) => {
    const m = f.match(/^MULTI\((.*)\)$/);
    if (!m) return f;
    const qs = m[1].split(",").filter((q) => !multi.has(q));
    return qs.length ? `MULTI(${qs.join(",")})` : null;
  });
}

export function examResults(exam, keyTexts = exam.keys, rawRules = exam.rules) {
  const info = sheetInfo(exam.template);
  const rules = withDefaults(rawRules);
  const parsed = {};
  for (const s of info.sets.length ? info.sets : [""]) parsed[s] = parseKey(keyTexts[s] || "", info);
  const keys = Object.fromEntries(Object.entries(parsed).filter(([s]) => (keyTexts[s] || "").trim()));
  const rows = exam.sheets.map((sheet) => {
    const r = scoreSheet(sheet.data, keys, rules, info);
    const flags = [...readerFlags(sheet.data.check, r), r.reason].filter(Boolean);
    return { sheet, r, flags };
  });
  const scored = rows.filter((x) => x.r.score !== null);
  const marks = scored.map((x) => x.r.score);
  const max = scored.length ? Math.max(...scored.map((x) => x.r.max)) : 0;
  return {
    info, rules, parsed, keys, rows, scored,
    stats: {
      sheets: rows.length,
      scored: scored.length,
      mean: marks.length ? marks.reduce((a, b) => a + b, 0) / marks.length : null,
      high: marks.length ? Math.max(...marks) : null,
      low: marks.length ? Math.min(...marks) : null,
      max,
      review: rows.filter((x) => x.flags.length).length,
    },
  };
}

export const fmt = (n, d = 1) => (n === null || n === undefined ? "–" : Number.isInteger(n) ? String(n) : n.toFixed(d));
