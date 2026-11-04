// Scoring: answer keys and the marking scheme turn a read sheet into marks.
// Nothing here touches the DOM, so scripts/check_score.mjs can run it under node.
//
// A key is one answer per question, in order or numbered ("12 AC"), separated by
// spaces, commas or new lines:
//   B     single correct
//   AC    multiple correct: scored by the multiple-correct rules
//   A+    multiple correct with only A right (a one-letter key is otherwise single correct)
//   A/C   single correct, either answer accepted
//   *     bonus: full marks to everyone
//   -     dropped: no marks for anyone, left out of the maximum

function defaultRules() {
  return {
    single: { correct: 4, wrong: -1, blank: 0, multi: "wrong" }, // multi: a multi-marked answer counts as "wrong" or "zero"
    multiple: { mode: "partial", correct: 4, wrong: -2, blank: 0, partial: 1 },
  };
}

// Saved rules over the defaults, so older exams pick up new settings
function withDefaults(rules = {}) {
  const d = defaultRules();
  return { single: { ...d.single, ...rules.single }, multiple: { ...d.multiple, ...rules.multiple } };
}

// Multiple-correct modes. `marked`/`right` are option sets; `n` = right options marked.
const MULTI_MODES = {
  exact: "All or nothing: full marks only for exactly the right options, otherwise the wrong marks",
  partial: "Partial: full marks for exactly right; per-option marks for each right option when no wrong one is marked; any wrong option gets the wrong marks",
  proportional: "Proportional: full marks × share of right options marked, when no wrong one is marked; any wrong option gets the wrong marks",
  perOption: "Per option: per-option marks for each right option marked, plus the wrong marks for each wrong option marked",
};

const letters = (s) => [...new Set(String(s || "").toUpperCase().replace(/[^A-Z]/g, ""))];

// Options, sets and question columns, straight from the template the sheets were printed from
function sheetInfo(tpl) {
  const qs = tpl.outputColumns.filter((c) => /^q\d+$/.test(c));
  const blocks = Object.values(tpl.fieldBlocks);
  const qBlock = blocks.find((b) => b.fieldLabels.some((l) => /^q\d/.test(l)));
  const setBlock = tpl.fieldBlocks.Set;
  return {
    questions: qs,
    options: qBlock ? qBlock.bubbleValues : [],
    sets: tpl.outputColumns.includes("Set") && setBlock ? setBlock.bubbleValues : [],
  };
}

// Key text -> { answers: [{key, kind}] (one per question, null = not given), issues }
function parseKey(text, info) {
  const n = info.questions.length;
  const answers = Array(n).fill(null);
  const issues = [];
  let next = 0;
  for (const line of String(text || "").split("\n")) {
    const numbered = line.trim().match(/^(\d+)\s*[.):,\t ]\s*(\S+)$/);
    const tokens = numbered ? [numbered[2]] : line.split(/[\s,;]+/).filter(Boolean);
    if (numbered) next = +numbered[1] - 1;
    for (const t of tokens) {
      if (next >= n) {
        issues.push(`more answers than the ${n} questions on the sheet`);
        return { answers, issues };
      }
      answers[next] = keyToken(t.toUpperCase(), info.options, next + 1, issues);
      next++;
    }
  }
  const missing = answers.filter((a) => !a).length;
  if (missing) issues.push(`${missing} question${missing > 1 ? "s have" : " has"} no answer (scored as dropped)`);
  return { answers, issues };
}

function keyToken(token, options, q, issues) {
  if (token === "*") return { kind: "bonus" };
  if (token === "-") return { kind: "dropped" };
  const multi = token.endsWith("+");
  const t = multi ? token.slice(0, -1) : token;
  const bad = letters(t).filter((c) => !options.includes(c));
  if (bad.length || !(multi ? /^[A-Z]+$/ : /^[A-Z]+(\/[A-Z]+)*$/).test(t)) {
    issues.push(`q${q}: "${token}" is not an answer (options are ${options.join("")})`);
    return null;
  }
  if (t.includes("/")) return { kind: "single", accept: t.split("/") };
  return t.length > 1 || multi ? { kind: "multiple", right: letters(t) } : { kind: "single", accept: [t] };
}

// Marks for one question: { marks, result } with result correct|partial|wrong|blank|bonus|dropped
function scoreQuestion(response, a, rules) {
  const marked = letters(response);
  if (!a || a.kind === "dropped") return { marks: 0, result: "dropped" };
  if (a.kind === "bonus") return { marks: +rules.single.correct, result: "bonus" };

  if (a.kind === "single") {
    const r = rules.single;
    if (!marked.length) return { marks: +r.blank, result: "blank" };
    if (marked.length > 1) return r.multi === "zero" ? { marks: 0, result: "wrong" } : { marks: +r.wrong, result: "wrong" };
    return a.accept.includes(marked[0]) ? { marks: +r.correct, result: "correct" } : { marks: +r.wrong, result: "wrong" };
  }

  const r = rules.multiple;
  if (!marked.length) return { marks: +r.blank, result: "blank" };
  const n = marked.filter((c) => a.right.includes(c)).length;
  const extra = marked.length - n;
  const exact = !extra && n === a.right.length;
  if (r.mode === "perOption") {
    const marks = n * r.partial + extra * r.wrong;
    return { marks, result: exact ? "correct" : marks > 0 ? "partial" : "wrong" };
  }
  if (exact) return { marks: +r.correct, result: "correct" };
  if (extra || r.mode === "exact") return { marks: +r.wrong, result: "wrong" };
  const marks = r.mode === "proportional" ? Math.round((r.correct * n / a.right.length) * 100) / 100 : n * r.partial;
  return { marks, result: "partial" };
}

// Highest possible marks for a question
function maxMarks(a, rules) {
  if (!a || a.kind === "dropped") return 0;
  if (a.kind === "multiple") return rules.multiple.mode === "perOption" ? a.right.length * rules.multiple.partial : +rules.multiple.correct;
  return +rules.single.correct;
}

// The key a sheet is scored against: its set's, or the only one there is
function keyFor(sheetSet, keys) {
  const sets = Object.keys(keys);
  if (sets.length === 1 && (!sheetSet || sets[0] === "")) return sets[0];
  return keys[sheetSet] ? sheetSet : null;
}

// One sheet. `keys` = { set: parsed key }. Returns totals, per-question detail and a reason when unscored.
function scoreSheet(data, keys, rules, info) {
  const set = keyFor(String(data.Set || "").trim(), keys);
  if (set === null) {
    return { score: null, max: null, reason: data.Set ? `no key for set ${data.Set}` : "set not marked", perQ: [] };
  }
  const t = { score: 0, max: 0, correct: 0, partial: 0, wrong: 0, blank: 0, keySet: set, perQ: [] };
  info.questions.forEach((q, i) => {
    const a = keys[set].answers[i];
    const s = scoreQuestion(data[q], a, rules);
    t.score += s.marks;
    t.max += maxMarks(a, rules);
    if (s.result in t) t[s.result]++;
    if (s.result === "bonus") t.correct++;
    t.perQ.push({ q, response: data[q] || "", key: a, ...s });
  });
  t.score = Math.round(t.score * 100) / 100;
  return t;
}

const keyText = (a) => (!a ? "" : a.kind === "bonus" ? "*" : a.kind === "dropped" ? "-"
  : a.kind === "multiple" ? a.right.join("") + (a.right.length === 1 ? "+" : "") : a.accept.join("/"));

// Answers back to key text, numbered so unanswered questions keep their place
const keyToText = (answers) => answers.map((a, i) => a && `${i + 1} ${keyText(a)}`).filter(Boolean).join("\n");

export { keyToText, defaultRules, withDefaults, MULTI_MODES, sheetInfo, parseKey, scoreQuestion, maxMarks, scoreSheet, keyText };
