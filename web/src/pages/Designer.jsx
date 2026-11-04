// The designer. sheet.js owns the layout; this page edits the form, draws the
// preview, saves the sheet on this computer, and prints and exports.
// #/design edits the unsaved draft (kept in browser storage); #/design/3 edits saved sheet 3.
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import { ArrowRight, Download, FileDown, FolderOpen, Scissors, Printer, RotateCcw, Save, TriangleAlert } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/App";
import { api, download, go, useExams } from "@/lib/api";
import { loadDraft, saveDraft, draftName, upgradeDraft } from "@/lib/draft";
import { chars, defaults, layout, printSvg, template } from "@/lib/sheet";

function Text({ state, set, name, label, hint, ...props }) {
  return (
    <Field>
      <FieldLabel htmlFor={`d-${name}`}>{label}</FieldLabel>
      <Input id={`d-${name}`} value={state[name] ?? ""} onChange={(e) => set(name, e.target.value)} {...props} />
      {hint && <FieldDescription>{hint}</FieldDescription>}
    </Field>
  );
}

export default function Designer({ id }) {
  const { reload } = useExams();
  const [state, setState] = useState(id ? null : loadDraft);
  const [saved, setSaved] = useState(null); // the stored sheet being edited: {id, name, design, sheets}
  const [naming, setNaming] = useState(null); // save dialog: null, or what to do after saving
  const [name, setName] = useState("");
  const [resetting, setResetting] = useState(false);
  const openRef = useRef();
  const set = (k, v) => setState((s) => ({ ...s, [k]: v }));

  useEffect(() => {
    if (!id) return;
    api(`exams/${id}`).then((e) => {
      if (!e.design) throw new Error("this sheet was imported from a template.json, so it has no design to edit");
      setSaved({ id: e.id, name: e.name, design: e.design, sheets: e.sheets.length });
      setState(upgradeDraft(e.design));
    }).catch((err) => { toast.error("Cannot open the design", { description: err.message }); go("/"); });
  }, [id]);

  // a new sheet counts as unsaved once it differs from the default one
  const dirty = !!state && JSON.stringify(state) !== JSON.stringify(saved ? upgradeDraft(saved.design) : defaults());
  useEffect(() => { if (state && !id) saveDraft(state); }, [state, id]);

  // Ask before closing the tab with unsaved work. Leaving for another page of the
  // app asks too for a saved sheet; a new sheet's draft is kept in the browser.
  useEffect(() => {
    if (!dirty) return;
    const unload = (e) => e.preventDefault();
    const click = (e) => {
      const a = e.target.closest?.("a[href^='#']");
      if (saved && a && !confirm("Leave without saving your changes to this sheet?")) e.preventDefault();
    };
    addEventListener("beforeunload", unload);
    document.addEventListener("click", click, true);
    return () => { removeEventListener("beforeunload", unload); document.removeEventListener("click", click, true); };
  }, [saved, dirty]);

  // a half sheet holds fewer questions: cut the count to what fits
  const setTwoUp = (v) => setState((s) => {
    const next = { ...s, twoUp: v };
    return { ...next, questions: Math.min(+next.questions || 1, layout(next).fit.capacity) };
  });

  const L = useMemo(() => state && layout(state), [state]);
  const svg = useMemo(() => L && printSvg(L), [L]);
  if (!state) return <div className="grid gap-4 p-8"><Skeleton className="h-10 w-96" /><Skeleton className="h-96" /></div>;

  const base = (saved?.name || draftName(state)).replace(/[^\w-]+/g, "_") || "omr-sheet";
  const nOpts = chars(state.options).length;
  // short quizzes fit twice on a page: suggest it
  const halfFits = !state.twoUp && !L.issues.length && (+state.questions || 0) <= layout({ ...state, twoUp: true }).fit.capacity;

  function blocked(what) {
    if (!L.issues.length) return false;
    toast.error(`Fix the sheet before you ${what}`, { description: L.issues.join(" ") });
    return true;
  }

  async function create(sheetName, then) {
    const { id: newId } = await api("exams", { method: "POST", body: { name: sheetName, template: template(L), design: state } });
    if (!saved) saveDraft(defaults()); // the draft is now a saved sheet; the next new design starts clean
    await reload();
    toast.success(`Saved “${sheetName}”`, { description: "Kept on this computer and listed on the dashboard." });
    go(then === "evaluate" ? `/sheets/${newId}` : `/design/${newId}`);
  }

  // then: "evaluate" to open the evaluator afterwards
  async function save(then) {
    if (blocked("save")) return;
    if (!saved) {
      setName(draftName(state));
      return setNaming(then || "stay");
    }
    try {
      if (dirty) {
        await api(`exams/${saved.id}`, { method: "PUT", body: { template: template(L), design: state } });
        setSaved({ ...saved, design: state });
        await reload();
        toast.success(`Saved “${saved.name}”`);
      }
      if (then === "evaluate") go(`/sheets/${saved.id}`);
    } catch (err) {
      if (!/already read/.test(err.message)) return toast.error("Could not save", { description: err.message });
      toast.warning("Scans were already read against the saved layout", {
        description: "Changing it would misread them. Save this version as a new sheet instead.",
        action: { label: "Save as new", onClick: () => create(`${saved.name} (revised)`, then).catch((e) => toast.error(e.message)) },
        duration: 15000,
      });
    }
  }

  async function confirmName(e) {
    e.preventDefault();
    const then = naming;
    setNaming(null);
    try {
      await create(name.trim() || "Untitled sheet", then);
    } catch (err) {
      toast.error("Could not save", { description: err.message });
    }
  }

  async function open(e) {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      if (data.fieldBlocks) throw new Error("this is a template.json; open a saved draft instead");
      setState(upgradeDraft(data));
      toast.success(`Opened ${file.name}`);
    } catch (err) {
      toast.error(`Could not open ${file.name}`, { description: err.message });
    }
  }

  function print() {
    if (blocked("print")) return;
    const title = document.title;
    document.title = base; // browsers use this as the PDF file name
    window.print();
    document.title = title;
  }

  return (
    <main className="grid flex-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <PageHeader
        title={saved ? saved.name : "New sheet"}
        badge={dirty && <Badge variant="destructive" className="shrink-0">{saved ? "Unsaved changes" : "Not saved"}</Badge>}
        actions={<>
          {/* labels give way to icons (with tooltips) on narrow windows */}
          <Button variant="ghost" size="sm" title="Start over" onClick={() => setResetting(true)}><RotateCcw /><span className="hidden xl:inline">Start over</span></Button>
          <Button variant="ghost" size="sm" title="Open a saved draft file" onClick={() => openRef.current.click()}><FolderOpen /><span className="hidden xl:inline">Open draft</span></Button>
          <Button variant="ghost" size="sm" title="Download this draft as a file" onClick={() => download(`${base}.json`, JSON.stringify(state, null, 2))}><FileDown /><span className="hidden xl:inline">Save draft</span></Button>
          <Button variant="ghost" size="sm" title="Download the template.json the reader needs for this sheet"
            onClick={() => !blocked("download the template") && download(`${base}_template.json`, JSON.stringify(template(L), null, 2))}>
            <Download /><span className="hidden lg:inline">JSON</span>
          </Button>
          <span className="mx-1 h-5 w-px bg-border" aria-hidden />
          <Button variant="outline" size="sm" onClick={print}><Printer /><span className="hidden sm:inline">Print / PDF</span></Button>
          <Button variant="outline" size="sm" onClick={() => save()} disabled={!!saved && !dirty}><Save />Save</Button>
          <Button size="sm" onClick={() => save("evaluate")}>Evaluate<ArrowRight /></Button>
        </>}
      />
      <input ref={openRef} type="file" accept=".json,application/json" hidden onChange={open} />

      <div className="grid content-start gap-6 p-4 md:p-8 print:hidden">
        {saved?.sheets > 0 && (
          <p className="rounded-lg border bg-muted/40 p-3 text-sm text-muted-foreground">
            {saved.sheets} scan{saved.sheets === 1 ? " was" : "s were"} read against this layout. Saving changes to it makes a new sheet; the evaluated one stays as it is.
          </p>
        )}
        {halfFits && (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-muted/40 p-4 text-sm">
            <Scissors className="size-4 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1">{state.questions} questions fit on half a page. Print two sheets per page and cut them apart to use half the paper.</span>
            <Button size="sm" variant="outline" onClick={() => setTwoUp(true)}>Two per page</Button>
          </div>
        )}
        {L.issues.length > 0 && (
          <div role="alert" className="flex gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" />
            <ul className="grid gap-1">{L.issues.map((t) => <li key={t}>{t}</li>)}</ul>
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Header</CardTitle>
            <CardDescription>Printed across the top of the sheet.</CardDescription>
          </CardHeader>
          <CardContent>
            <FieldGroup>
              <Text state={state} set={set} name="title" label="Title" />
              <div className="grid gap-4 sm:grid-cols-3">
                <Text state={state} set={set} name="exam" label="Exam" />
                <Text state={state} set={set} name="course" label="Course" placeholder="EEE F111 Electrical Sciences" />
                <Text state={state} set={set} name="date" label="Date" placeholder="12 Sep 2026" />
              </div>
              <Field>
                <FieldLabel htmlFor="d-instructions">Instructions</FieldLabel>
                <Textarea id="d-instructions" rows={3} value={state.instructions} onChange={(e) => set("instructions", e.target.value)} />
                <FieldDescription>One per line, printed small beside the ID grid.</FieldDescription>
              </Field>
            </FieldGroup>
          </CardContent>
        </Card>

        <div className="grid gap-6 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Set</CardTitle>
              <CardDescription>Different papers in the same exam.</CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <Field orientation="horizontal">
                  <Checkbox id="d-showSet" checked={!!state.showSet} onCheckedChange={(v) => set("showSet", !!v)} />
                  <FieldLabel htmlFor="d-showSet" className="font-normal">Print a set box</FieldLabel>
                </Field>
                <Text state={state} set={set} name="sets" label="Sets" hint="One letter each." disabled={!state.showSet} />
              </FieldGroup>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Email</CardTitle>
              <CardDescription>Bubbled as degree, year, last four digits, @ and campus, as in F20231187@H. Students also write their ID number by hand under their name.</CardDescription>
            </CardHeader>
            <CardContent>
              <FieldGroup>
                <Text state={state} set={set} name="idTitle" label="Heading" />
                <FieldDescription>The “20” and “@” are printed; every other column is bubbled, with a box above it to write the character in.</FieldDescription>
              </FieldGroup>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Questions</CardTitle>
            <CardDescription>
              {nOpts ? `Up to ${L.fit.capacity} questions fit with ${nOpts} options; this sheet uses ${L.fit.cols} column${L.fit.cols > 1 ? "s" : ""}.` : "Add at least one option."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <FieldGroup>
              <div className="grid gap-4 sm:grid-cols-2">
                <Text state={state} set={set} name="options" label="Options" hint="One letter each." />
                <Text state={state} set={set} name="questions" label="Number of questions" type="number" min={1} max={L.fit.capacity} />
              </div>
              <Field orientation="horizontal" className="items-start">
                <Checkbox id="d-twoUp" checked={!!state.twoUp} onCheckedChange={(v) => setTwoUp(!!v)} className="mt-0.5" />
                <div className="grid gap-1">
                  <FieldLabel htmlFor="d-twoUp" className="font-normal">Two sheets per page, for short quizzes</FieldLabel>
                  <FieldDescription>Prints two half-height sheets one above the other on an A4, with a dotted line and scissors to cut along. Bubbles stay full size; a half holds fewer questions. Cut the pages before scanning.</FieldDescription>
                </div>
              </Field>
            </FieldGroup>
          </CardContent>
        </Card>
      </div>

      <section aria-label="Printed sheet" className="border-t bg-muted/40 xl:sticky xl:top-14 xl:h-[calc(100svh-3.5rem)] xl:border-t-0 xl:border-l print:hidden">
        <div className="flex h-full flex-col">
          <div className="flex items-center gap-2 border-b bg-background px-4 py-2.5 text-sm">
            <span className="font-medium">Preview</span>
            <span className="text-muted-foreground">{L.twoUp ? "A4, two per page, exactly as printed" : "A4, exactly as printed"}</span>
          </div>
          <div className="flex-1 overflow-auto p-4 md:p-6">
            <div className="mx-auto max-w-[720px] [&_svg]:block [&_svg]:h-auto [&_svg]:w-full [&_svg]:bg-white [&_svg]:shadow-md [&_svg]:ring-1 [&_svg]:ring-black/5"
              dangerouslySetInnerHTML={{ __html: svg }} />
          </div>
        </div>
      </section>

      {createPortal(<div className="print-sheet">
        <div dangerouslySetInnerHTML={{ __html: svg }} />
      </div>, document.body)}

      <Dialog open={!!naming} onOpenChange={(o) => !o && setNaming(null)}>
        <DialogContent className="sm:max-w-md">
          <form onSubmit={confirmName} className="grid gap-6">
            <DialogHeader>
              <DialogTitle>Save sheet</DialogTitle>
              <DialogDescription>Kept on this computer and listed on the dashboard, where you can evaluate its scans.</DialogDescription>
            </DialogHeader>
            <Field>
              <FieldLabel htmlFor="save-name">Name</FieldLabel>
              <Input id="save-name" value={name} onChange={(e) => setName(e.target.value)} onFocus={(e) => e.target.select()} placeholder="EEE F111 Quiz 1" autoFocus />
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setNaming(null)}>Cancel</Button>
              <Button type="submit">{naming === "evaluate" ? "Save and evaluate" : "Save"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={resetting} onOpenChange={setResetting}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Start over?</AlertDialogTitle>
            <AlertDialogDescription>The form goes back to the default sheet.{saved ? " The saved sheet is unchanged until you save." : ""}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => setState(defaults())}>Start over</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </main>
  );
}
