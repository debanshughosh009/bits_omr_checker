// Sheet designer form. designer/sheet.js (loaded before this file) draws the
// preview, exactly as designer/index.html does; the server runs the same file
// to make the PDF and template when the form is submitted.
(function () {
  const form = document.getElementById("design-form");
  if (!form) return;
  const sheet = document.getElementById("design-sheet");
  const issues = document.getElementById("design-issues");
  const fit = document.getElementById("design-fit");
  const submit = document.getElementById("design-submit");

  function state() {
    const s = {};
    for (const el of form.elements) {
      if (!el.name || el.name === "name") continue;
      s[el.name] = el.type === "checkbox" ? el.checked : el.value;
    }
    return s;
  }

  function update() {
    const s = state();
    const L = layout({ ...defaults(), ...s });
    sheet.innerHTML = sheetSvg(L);
    const n = chars(s.options).length;
    fit.textContent = n
      ? `Up to ${L.fit.capacity} questions fit with ${n} options; this sheet uses ${L.fit.cols} column${L.fit.cols > 1 ? "s" : ""}.`
      : "";
    issues.replaceChildren(...L.issues.map((t) => Object.assign(document.createElement("li"), { textContent: t })));
    submit.disabled = L.issues.length > 0;
    submit.title = L.issues.length ? "Fix the issues above first" : "";
  }

  function fill(s) {
    for (const el of form.elements) {
      if (!el.name || !(el.name in s)) continue;
      if (el.type === "checkbox") el.checked = !!s[el.name];
      else el.value = s[el.name] ?? "";
    }
    update();
  }

  // Drafts saved from designer/index.html ("Save")
  document.getElementById("open-draft").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      if (data.fieldBlocks) throw new Error("this is a template.json; upload it under 'Upload a custom template'");
      fill({ ...defaults(), ...data });
    } catch (err) {
      issues.replaceChildren(Object.assign(document.createElement("li"), { textContent: `Could not open ${file.name}: ${err.message}` }));
    }
  });

  form.addEventListener("input", update);
  update();
})();
