// Clickable answer key editor.
// State: keys[set] = array of answers, one per question on the sheet.
// An answer is "" (not set), "*" (bonus), "A", "AC" (any one of A, C)
// or "A+C" (multiple correct: exactly A and C must be marked).
(function () {
  const data = JSON.parse(document.getElementById("key-data").textContent);
  const questions = data.questions;
  const sets = data.sets.length ? data.sets : ["*"];
  const grid = document.getElementById("key-grid");
  const tabs = document.getElementById("set-tabs");
  const numInput = document.getElementById("num-questions");
  const status = document.getElementById("key-status");
  const copyTarget = document.getElementById("copy-target");
  const defaultMode = document.getElementById("default-mode");

  const keys = {};
  for (const s of sets) {
    const saved = data.keys[s] || [];
    keys[s] = questions.map((_, i) => saved[i] || "");
  }
  let current = sets[0];
  let focused = 0;
  let dirty = false;

  // Remember the toolbar choices between visits
  const pref = (k, v) => (v === undefined ? localStorage.getItem("omr-key-" + k) : localStorage.setItem("omr-key-" + k, v));
  if (pref("default-mode")) defaultMode.value = pref("default-mode");
  if (pref("click-mode")) document.querySelector(`input[name=click-mode][value=${pref("click-mode")}]`).checked = true;
  defaultMode.addEventListener("change", () => pref("default-mode", defaultMode.value));
  document.querySelectorAll("input[name=click-mode]").forEach((r) =>
    r.addEventListener("change", () => pref("click-mode", r.value)));
  const clickMode = () => document.querySelector("input[name=click-mode]:checked").value;

  const numQuestions = () =>
    Math.max(1, Math.min(questions.length, parseInt(numInput.value, 10) || questions.length));

  // --- answer helpers
  const lettersOf = (a) => (a === "*" ? [] : a.replace(/\+/g, "").split("").filter(Boolean));
  const modeOf = (a) => (a.includes("+") ? "all" : "any");
  function build(letters, mode) {
    letters = [...new Set(letters)].sort();
    if (letters.length < 2) return letters.join("");
    return mode === "all" ? letters.join("+") : letters.join("");
  }

  function setAnswer(i, value) {
    keys[current][i] = value;
    dirty = true;
    renderRow(i);
    renderTabs();
    renderStatus();
  }

  function toggleOption(i, opt, additive) {
    const cur = keys[current][i];
    const letters = lettersOf(cur);
    const mode = letters.length >= 2 ? modeOf(cur) : defaultMode.value;
    let next;
    if (!additive) next = letters.length === 1 && letters[0] === opt ? [] : [opt];
    else next = letters.includes(opt) ? letters.filter((l) => l !== opt) : [...letters, opt];
    setAnswer(i, build(next, mode));
  }

  function toggleMode(i) {
    const cur = keys[current][i];
    setAnswer(i, build(lettersOf(cur), modeOf(cur) === "all" ? "any" : "all"));
  }

  // --- rendering
  function renderTabs() {
    tabs.innerHTML = "";
    tabs.classList.toggle("hidden", sets.length === 1 && sets[0] === "*");
    const n = numQuestions();
    for (const s of sets) {
      const done = keys[s].slice(0, n).filter(Boolean).length;
      const b = document.createElement("button");
      b.className = "tab" + (s === current ? " active" : "") + (done === n ? " complete" : "");
      b.innerHTML = `Set ${s} <span>${done}/${n}</span>`;
      b.onclick = () => { current = s; render(); };
      tabs.appendChild(b);
    }
    copyTarget.innerHTML = '<option value="__all">to all other sets</option>' +
      sets.filter((s) => s !== current).map((s) => `<option value="${s}">to set ${s}</option>`).join("");
    for (const el of [copyTarget, document.getElementById("copy-btn")]) {
      el.classList.toggle("hidden", sets.length === 1);
    }
  }

  function renderRow(i) {
    const row = grid.children[i];
    const ans = keys[current][i];
    const letters = lettersOf(ans);
    const multi = letters.length >= 2;
    row.classList.toggle("disabled", i >= numQuestions());
    row.classList.toggle("answered", Boolean(ans));
    row.classList.toggle("focused", i === focused);
    row.classList.toggle("mode-all", multi && modeOf(ans) === "all");
    for (const b of row.querySelectorAll(".opt")) {
      b.classList.toggle("on", ans === "*" || letters.includes(b.dataset.opt));
    }
    row.querySelector(".bonus").classList.toggle("on", ans === "*");
    const chip = row.querySelector(".mode");
    chip.classList.toggle("hidden", !multi);
    if (multi) {
      const m = modeOf(ans);
      chip.className = "mode " + m;
      chip.textContent = m;
      chip.title = m === "all" ? "All selected options must be marked. Click for 'any one'."
        : "Any one of the selected options earns the marks. Click for 'all'.";
    }
  }

  function render() {
    grid.innerHTML = "";
    questions.forEach((q, i) => {
      const row = document.createElement("div");
      row.className = "key-row";
      row.tabIndex = 0;
      row.innerHTML = `<span class="qn">${q.slice(1)}</span>` +
        data.options[q].map((o) => `<button class="opt" data-opt="${o}" tabindex="-1">${o}</button>`).join("") +
        `<button class="bonus" title="Bonus: everyone gets the marks" tabindex="-1">★</button>` +
        `<button class="mode hidden" tabindex="-1"></button>`;
      row.querySelectorAll(".opt").forEach((b) =>
        b.addEventListener("click", (e) => {
          focusRow(i);
          toggleOption(i, b.dataset.opt, e.shiftKey || clickMode() === "many");
        }));
      row.querySelector(".bonus").addEventListener("click", () => {
        focusRow(i);
        setAnswer(i, keys[current][i] === "*" ? "" : "*");
      });
      row.querySelector(".mode").addEventListener("click", () => { focusRow(i); toggleMode(i); });
      row.addEventListener("focus", () => focusRow(i, false));
      grid.appendChild(row);
    });
    questions.forEach((_, i) => renderRow(i));
    renderTabs();
    renderStatus();
  }

  function focusRow(i, move = true) {
    const prev = focused;
    focused = Math.max(0, Math.min(questions.length - 1, i));
    if (grid.children[prev]) renderRow(prev);
    renderRow(focused);
    if (move) grid.children[focused].focus({ preventScroll: false });
  }

  grid.addEventListener("keydown", (e) => {
    const q = questions[focused];
    const key = e.key.toUpperCase();
    if (data.options[q].includes(key)) {
      e.preventDefault();
      if (e.shiftKey || clickMode() === "many") toggleOption(focused, key, true);
      else { setAnswer(focused, key); focusRow(focused + 1); }
    } else if (e.key === "*") {
      e.preventDefault(); setAnswer(focused, "*"); focusRow(focused + 1);
    } else if (e.key === "Backspace" || e.key === "Delete") {
      e.preventDefault(); setAnswer(focused, "");
    } else if (e.key === "ArrowDown" || e.key === "Enter") {
      e.preventDefault(); focusRow(focused + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault(); focusRow(focused - 1);
    }
  });

  function renderStatus(text) {
    if (text) { status.textContent = text; return; }
    const n = numQuestions();
    const missing = sets.filter((s) => keys[s].slice(0, n).some((a) => !a));
    const multi = sets.reduce((c, s) => c + keys[s].slice(0, n).filter((a) => lettersOf(a).length >= 2).length, 0);
    status.textContent = (dirty ? "Unsaved changes. " : "") +
      (missing.length ? `Unanswered questions in ${missing.map((s) => s === "*" ? "the key" : "set " + s).join(", ")}.` : "All questions answered.") +
      (multi ? ` ${multi} question(s) with multiple correct options.` : "");
  }

  // --- quick fill: "ABCD", "A B AC", or "A, B, A/C, B+D, *, -"
  function parseQuick(text) {
    text = text.trim().toUpperCase();
    if (!text) return [];
    if (text.includes(",")) return text.split(",").map((t) => t.trim());
    if (/\s/.test(text)) return text.split(/\s+/);
    return text.split("");
  }

  function parseToken(raw, q) {
    if (raw === "" || raw === "-") return "";
    if (raw === "*") return "*";
    const mode = /[+&]/.test(raw) ? "all" : /[\/|]/.test(raw) ? "any" : defaultMode.value;
    const letters = raw.replace(/[\/|+&\s]/g, "").split("");
    if (!letters.length || !letters.every((c) => data.options[q].includes(c))) return null;
    return build(letters, mode);
  }

  document.getElementById("quick-apply").onclick = () => {
    const input = document.getElementById("quick-fill");
    const items = parseQuick(input.value);
    const bad = [];
    items.slice(0, questions.length).forEach((raw, i) => {
      const a = parseToken(raw, questions[i]);
      if (a === null) bad.push(questions[i]);
      else keys[current][i] = a;
    });
    if (items.length && items.length <= questions.length) numInput.value = Math.max(items.length, 1);
    dirty = true;
    render();
    if (bad.length) renderStatus(`Skipped invalid answers for ${bad.join(", ")}.`);
    if (items.length > questions.length) renderStatus(`Only the first ${questions.length} answers were used.`);
    input.value = "";
  };

  document.getElementById("copy-btn").onclick = () => {
    const targets = copyTarget.value === "__all" ? sets.filter((s) => s !== current) : [copyTarget.value];
    for (const t of targets) keys[t] = keys[current].slice();
    dirty = true;
    renderTabs();
    renderStatus(`Copied to ${targets.map((t) => "set " + t).join(", ")}.`);
  };

  document.getElementById("clear-btn").onclick = () => {
    if (!confirm("Clear all answers in this set?")) return;
    keys[current] = questions.map(() => "");
    dirty = true;
    render();
  };

  numInput.addEventListener("input", () => { dirty = true; questions.forEach((_, i) => renderRow(i)); renderTabs(); renderStatus(); });

  document.getElementById("save-btn").onclick = async () => {
    const n = numQuestions();
    const missing = sets.filter((s) => keys[s].slice(0, n).some((a) => !a) && keys[s].slice(0, n).some(Boolean));
    if (missing.length && !confirm("Some questions have no answer; they won't be scored. Save anyway?")) return;
    renderStatus("Saving and rescoring...");
    const res = await fetch(data.save_url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys: Object.fromEntries(sets.map((s) => [s, keys[s].slice(0, n)])), num_questions: n }),
    });
    const body = await res.json().catch(() => ({ ok: false, error: "Server error" }));
    if (body.ok) { dirty = false; renderStatus(body.message); }
    else renderStatus("Not saved: " + body.error);
  };

  window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

  render();
})();
