// The form. sheet.js owns the layout; this file only reads the form, draws the
// preview, and saves, opens, prints and exports.

const STORE = "omr-designer";
const form = document.getElementById("form");
let state = load();

function load() {
  try {
    return { ...defaults(), ...JSON.parse(localStorage.getItem(STORE) || "{}") };
  } catch {
    return defaults();
  }
}

function fillForm() {
  for (const input of form.elements) {
    if (!input.name) continue;
    if (input.type === "checkbox") input.checked = !!state[input.name];
    else input.value = state[input.name] ?? "";
  }
}

function update() {
  const L = layout(state);
  document.getElementById("sheet").innerHTML = sheetSvg(L);
  document.getElementById("fit").textContent = chars(state.options).length
    ? `Up to ${L.fit.capacity} questions fit with ${chars(state.options).length} options; this sheet uses ${L.fit.cols} column${L.fit.cols > 1 ? "s" : ""}.`
    : "";
  document.getElementById("issues").replaceChildren(
    ...L.issues.map((t) => Object.assign(document.createElement("li"), { textContent: t })),
  );
  try {
    localStorage.setItem(STORE, JSON.stringify(state));
  } catch {} // private window: the draft just isn't kept
  return L;
}

form.addEventListener("input", (e) => {
  const t = e.target;
  if (!t.name) return;
  state[t.name] = t.type === "checkbox" ? t.checked : t.value;
  update();
});

// ---------- toolbar ----------

function download(name, text, type = "application/json") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

function fileBase() {
  return [state.course, state.exam].filter(Boolean).join(" ").replace(/[^\w-]+/g, "_") || "omr-sheet";
}

document.getElementById("new").addEventListener("click", () => {
  if (!confirm("Start a new sheet? The current draft will be cleared (save it first if you need it).")) return;
  state = defaults();
  fillForm();
  update();
});

document.getElementById("save").addEventListener("click", () => download(`${fileBase()}.json`, JSON.stringify(state, null, 2)));

document.getElementById("open").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (data.fieldBlocks) throw new Error("this is a template.json; open a saved draft instead");
    state = { ...defaults(), ...data };
    fillForm();
    update();
  } catch (err) {
    alert(`Could not open ${file.name}: ${err.message}`);
  }
});

function blocked(L, what) {
  if (!L.issues.length) return false;
  alert(`Fix these before you ${what}:\n\n- ${L.issues.join("\n- ")}`);
  return true;
}

document.getElementById("template").addEventListener("click", () => {
  const L = layout(state);
  if (blocked(L, "download the template")) return;
  download(`${fileBase()}_template.json`, JSON.stringify(template(L), null, 2));
});

document.getElementById("print").addEventListener("click", () => {
  if (blocked(update(), "print")) return;
  const title = document.title;
  document.title = fileBase(); // browsers use this as the PDF file name
  window.print();
  document.title = title;
});

fillForm();
update();
