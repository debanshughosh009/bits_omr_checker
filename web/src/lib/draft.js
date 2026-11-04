// The designer's draft, kept in browser storage under the key the old designer used
import { defaults, layout, template } from "@/lib/sheet";

const STORE = "omr-designer";

export function loadDraft() {
  try {
    return upgradeDraft(JSON.parse(localStorage.getItem(STORE) || "{}"));
  } catch {
    return defaults();
  }
}

// A draft or saved design over today's defaults, with the old default wording updated
export function upgradeDraft(d = {}) {
  const s = { ...defaults(), ...d };
  if (s.idTitle === "ID NUMBER") s.idTitle = "EMAIL"; // the bubbled grid is the campus email now
  if (s.instructions === "Use a blue or black ball-point pen and fill each bubble completely.\nBubble your ID number and set. Do not make stray marks on this sheet.") {
    s.instructions = defaults().instructions;
  }
  return s;
}

export function saveDraft(state) {
  try {
    localStorage.setItem(STORE, JSON.stringify(state));
  } catch {
    // private window: the draft just isn't kept
  }
}

// The name a new sheet is saved under: course and exam, then the date
export const draftName = (s) => [[s.course, s.exam].filter(Boolean).join(" "), s.date].map((t) => (t || "").trim()).filter(Boolean).join(" · ");

// template.json for the current draft, or an error naming what to fix
export function draftTemplate(state = loadDraft()) {
  const L = layout(state);
  if (L.issues.length) throw new Error(`the designed sheet has problems: ${L.issues.join("; ")}`);
  return template(L);
}
