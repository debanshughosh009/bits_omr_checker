// Checks web/src/lib/score.js: key parsing and every marking rule.
//     node scripts/check_score.mjs
import assert from "node:assert";
import * as S from "../web/src/lib/score.js";

const info = { questions: ["q1", "q2", "q3", "q4", "q5", "q6"], options: ["A", "B", "C", "D"], sets: ["A", "B"] };
const rules = S.defaultRules();
const q = (resp, key, r = rules) => S.scoreQuestion(resp, S.parseKey(key, { ...info, questions: ["q1"] }).answers[0], r);

// key parsing: flat, numbered, alternatives, bonus, dropped, bad letters, gaps
let k = S.parseKey("B, AC\nA/C * -", info);
assert.deepStrictEqual(k.answers.map(S.keyText), ["B", "AC", "A/C", "*", "-", ""]);
assert.match(k.issues[0], /1 question has no answer/);
k = S.parseKey("1. B\n3\tCD\n6) a", info);
assert.deepStrictEqual(k.answers.map(S.keyText), ["B", "", "CD", "", "", "A"]);
assert.match(S.parseKey("B E", info).issues[0], /q2: "E"/);
assert.match(S.parseKey("A A A A A A A", info).issues[0], /more answers/);
k = S.parseKey("C+ A/C - BD", info);
assert.deepStrictEqual(k.answers.map(S.keyText), ["C+", "A/C", "-", "BD", "", ""]);
assert.deepStrictEqual(S.parseKey(S.keyToText(k.answers), info).answers, k.answers); // round trip keeps gaps
assert.match(S.parseKey("A/C+", info).issues[0], /q1/);

// single correct
assert.deepStrictEqual(q("B", "B"), { marks: 4, result: "correct" });
assert.deepStrictEqual(q("C", "B"), { marks: -1, result: "wrong" });
assert.deepStrictEqual(q("", "B"), { marks: 0, result: "blank" });
assert.deepStrictEqual(q("BC", "B"), { marks: -1, result: "wrong" });
assert.deepStrictEqual(q("BC", "B", { ...rules, single: { ...rules.single, multi: "zero" } }), { marks: 0, result: "wrong" });
assert.deepStrictEqual(q("C", "A/C"), { marks: 4, result: "correct" });
assert.deepStrictEqual(q("", "*"), { marks: 4, result: "bonus" });
assert.deepStrictEqual(q("A", "-"), { marks: 0, result: "dropped" });

// multiple correct, key ACD
const mode = (m) => ({ ...rules, multiple: { ...rules.multiple, mode: m } });
assert.deepStrictEqual(q("ACD", "ACD"), { marks: 4, result: "correct" });
assert.deepStrictEqual(q("AC", "ACD"), { marks: 2, result: "partial" });
assert.deepStrictEqual(q("AB", "ACD"), { marks: -2, result: "wrong" });
assert.deepStrictEqual(q("", "ACD"), { marks: 0, result: "blank" });
assert.deepStrictEqual(q("AC", "ACD", mode("exact")), { marks: -2, result: "wrong" });
assert.deepStrictEqual(q("AC", "ACD", mode("proportional")), { marks: 2.67, result: "partial" });
assert.deepStrictEqual(q("ABC", "ACD", mode("perOption")), { marks: 0, result: "wrong" });
assert.deepStrictEqual(q("ACD", "ACD", mode("perOption")), { marks: 3, result: "correct" });
assert.deepStrictEqual(q("C", "C+"), { marks: 4, result: "correct" });       // one-option multiple correct
assert.deepStrictEqual(q("CD", "C+"), { marks: -2, result: "wrong" });
assert.strictEqual(S.maxMarks(S.parseKey("ACD", info).answers[0], mode("perOption")), 3);

// whole sheet: set picks the key, dropped leaves the maximum
const keys = { A: S.parseKey("B AC A/C * - D", info), B: S.parseKey("A A A A A A", info) };
const t = S.scoreSheet({ Set: "A", q1: "B", q2: "A", q3: "", q4: "", q5: "C", q6: "BD" }, keys, rules, info);
assert.deepStrictEqual([t.score, t.max, t.correct, t.partial, t.wrong, t.blank], [8, 20, 2, 1, 1, 1]);
assert.strictEqual(S.scoreSheet({ Set: "", q1: "A" }, keys, rules, info).reason, "set not marked");
assert.strictEqual(S.scoreSheet({ Set: "C" }, keys, rules, info).reason, "no key for set C");
assert.strictEqual(S.scoreSheet({ Set: "", q1: "B" }, { "": keys.A }, rules, info).score, 8);

// template -> sheet info
const tpl = { outputColumns: ["Set", "ID NO", "q1", "q2"], fieldBlocks: { Set: { bubbleValues: ["A", "B"], fieldLabels: ["Set"] }, Q1: { bubbleValues: ["A", "B", "C"], fieldLabels: ["q1..2"] } } };
assert.deepStrictEqual(S.sheetInfo(tpl), { questions: ["q1", "q2"], options: ["A", "B", "C"], sets: ["A", "B"] });

console.log("ok: score.js key parsing and marking rules");
