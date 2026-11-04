// One exam: its scans and marks, its answer keys, its marking scheme.
// app/server.py stores and reads; score.js marks; this page edits and shows.
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Calculator, CheckCircle2, FileSpreadsheet, KeyRound, Pencil, Loader2, ScanLine, Search, Sigma, Trash2, TriangleAlert, Upload, Users } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import AnswerKey from "@/components/AnswerKey";
import ExamCharts from "@/components/ExamCharts";
import SheetDialog from "@/components/SheetDialog";
import Stat from "@/components/Stat";
import { PageHeader } from "@/App";
import { api, download, go, useExams } from "@/lib/api";
import { examResults, fmt } from "@/lib/results";
import { MULTI_MODES, parseKey, scoreQuestion } from "@/lib/score";
import { cn } from "@/lib/utils";

export default function Exam({ id }) {
  const { reload } = useExams();
  const [exam, setExam] = useState(null);
  const [keyTexts, setKeyTexts] = useState({});
  const [rules, setRules] = useState({});
  const [name, setName] = useState("");
  const [tab, setTab] = useState("results");
  const [deleting, setDeleting] = useState(false);
  const loaded = useRef(false);

  const fetchExam = () => api(`exams/${id}`).then((e) => {
    setExam(e);
    return e;
  });

  useEffect(() => {
    fetchExam().then((e) => {
      setKeyTexts(e.keys);
      setRules(e.rules);
      setName(e.name);
      if (!Object.values(e.keys).some((t) => t.trim())) setTab("key");
      loaded.current = true;
    }, (err) => { toast.error(err.message); go("/"); });
  }, [id]);

  // Save edits a moment after the last keystroke
  useEffect(() => {
    if (!loaded.current) return;
    const t = setTimeout(() => {
      api(`exams/${id}`, { method: "PUT", body: { name: name.trim() || "Untitled sheet", keys: keyTexts, rules } })
        .then(reload, (err) => toast.error("Could not save", { description: err.message }));
    }, 500);
    return () => clearTimeout(t);
  }, [keyTexts, rules, name]);

  const results = useMemo(() => exam && examResults(exam, keyTexts, rules), [exam, keyTexts, rules]);
  if (!exam || !results) return <div className="grid gap-4 p-8"><Skeleton className="h-10 w-72" /><Skeleton className="h-28" /><Skeleton className="h-96" /></div>;

  const { info, stats } = results;
  const hasKey = Object.keys(results.keys).length > 0;

  function exportCsv() {
    const head = ["file", "ID NO", "Set", "score", "max", "correct", "partial", "wrong", "blank", "check", ...info.questions];
    const cell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const rows = results.rows.map(({ sheet, r, flags }) => [sheet.file, sheet.data["ID NO"], sheet.data.Set, r.score, r.max, r.correct, r.partial, r.wrong, r.blank,
      [...flags, sheet.edited && "edited"].filter(Boolean).join(", "), ...info.questions.map((q) => sheet.data[q])]);
    download(`${name.replace(/[^\w-]+/g, "_")}_marks.csv`, [head, ...rows].map((r) => r.map(cell).join(",")).join("\n"), "text/csv");
  }

  async function remove() {
    await api(`exams/${id}`, { method: "DELETE" });
    await reload();
    go("/");
    toast.success(`Deleted ${exam.name}`);
  }

  const keyedSets = (info.sets.length ? info.sets : [""]).filter((s) => (keyTexts[s] || "").trim());
  const nav = [
    { id: "results", label: "Scans & marks", icon: ScanLine, note: stats.sheets ? `${stats.sheets} read${exam.waiting ? `, ${exam.waiting} waiting` : ""}` : exam.waiting ? `${exam.waiting} waiting` : "No scans yet" },
    { id: "key", label: "Answer key", icon: KeyRound, note: info.sets.length ? `${keyedSets.length} of ${info.sets.length} sets` : keyedSets.length ? "Entered" : "Not entered", alert: !hasKey },
    { id: "scheme", label: "Marking scheme", icon: Calculator, note: `${fmt(results.rules.single.correct)} / ${fmt(results.rules.single.wrong)} · ${MULTI_MODES[results.rules.multiple.mode].split(":")[0]}` },
  ];

  return (
    <div className="flex flex-1 flex-col md:flex-row">
      <PageHeader title={name || exam.name} actions={<>
        {exam.design && <Button variant="ghost" size="sm" onClick={() => go(`/design/${id}`)}><Pencil /><span className="hidden sm:inline">Edit design</span></Button>}
        <Button variant="ghost" size="icon-sm" aria-label="Delete sheet" onClick={() => setDeleting(true)}><Trash2 /></Button>
        <Button size="sm" onClick={exportCsv} disabled={!stats.sheets}><FileSpreadsheet />Export CSV</Button>
      </>} />

      <aside className="shrink-0 border-b bg-muted/30 md:sticky md:top-14 md:h-[calc(100svh-3.5rem)] md:w-64 md:border-r md:border-b-0">
        <div className="grid gap-4 p-3 md:p-4">
          <div className="grid gap-1 px-1">
            <Input value={name} onChange={(e) => setName(e.target.value)} aria-label="Sheet name"
              className="h-8 border-transparent bg-transparent px-1.5 -mx-1.5 font-semibold shadow-none hover:border-input focus-visible:border-input dark:bg-transparent" />
            <p className="text-xs text-muted-foreground">
              {info.questions.length} questions · {info.options.join("")}{info.sets.length ? ` · sets ${info.sets.join("")}` : ""}
            </p>
          </div>
          <nav aria-label="Sections" className="flex gap-1 overflow-x-auto md:grid">
            {nav.map((n) => (
              <button key={n.id} onClick={() => setTab(n.id)} aria-current={tab === n.id ? "page" : undefined}
                className={cn("flex shrink-0 items-start gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-accent",
                  tab === n.id && "bg-accent font-medium text-accent-foreground")}>
                <n.icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <span className="grid">
                  <span className="flex items-center gap-2">{n.label}{n.alert && <span className="size-1.5 rounded-full bg-destructive" />}</span>
                  <span className="hidden text-xs font-normal text-muted-foreground md:block">{n.note}</span>
                </span>
              </button>
            ))}
          </nav>
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        {tab === "results" && (
          <div className="grid gap-6 p-4 md:p-6">
            {!hasKey && (
              <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-muted/40 p-4 text-sm">
                <TriangleAlert className="size-4 text-muted-foreground" />
                <span className="flex-1">There is no answer key yet, so sheets are read but not marked.</span>
                <Button size="sm" variant="outline" onClick={() => setTab("key")}>Enter the key</Button>
              </div>
            )}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Stat icon={Users} label="Sheets" value={stats.sheets} hint={exam.waiting ? `${exam.waiting} waiting to be read` : null} />
              <Stat icon={Sigma} label="Mean" value={stats.mean === null ? "–" : fmt(stats.mean, 2)} hint={stats.max ? `out of ${stats.max}` : "Needs a key and scans"} />
              <Stat icon={CheckCircle2} label="High / low" value={stats.high === null ? "–" : `${fmt(stats.high)} / ${fmt(stats.low)}`} />
              <Stat icon={TriangleAlert} label="Need review" value={stats.review} hint="Flagged by the reader or not marked" />
            </div>
            <Scans exam={exam} onRead={fetchExam} />
            <ExamCharts scored={results.scored} stats={stats} info={info} />
            <Results results={results} onChange={fetchExam} />
          </div>
        )}
        {tab === "key" && <AnswerKey info={info} keyTexts={keyTexts} setKeyTexts={setKeyTexts} parsed={results.parsed} />}
        {tab === "scheme" && <div className="p-4 md:p-6"><Scheme rules={results.rules} setRules={setRules} /></div>}
      </main>

      <AlertDialog open={deleting} onOpenChange={setDeleting}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {exam.name}?</AlertDialogTitle>
            <AlertDialogDescription>The design, its {stats.sheets} read sheets and their scans, the answer keys and the marking scheme are removed from this computer. This cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={remove}>Delete sheet</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ---------- scans ----------

function Scans({ exam, onRead }) {
  const [over, setOver] = useState(false);
  const [upload, setUpload] = useState(null); // {done, total}
  const [reading, setReading] = useState(false);
  const input = useRef();

  async function add(files) {
    files = [...files];
    let bad = 0;
    for (let i = 0; i < files.length; i++) {
      setUpload({ done: i, total: files.length });
      try {
        await api(`exams/${exam.id}/scans?name=${encodeURIComponent(files[i].name)}`, { method: "POST", body: files[i] });
      } catch (err) {
        bad++;
        toast.error(err.message);
      }
    }
    setUpload(null);
    if (files.length - bad) toast.success(`Added ${files.length - bad} scan${files.length - bad === 1 ? "" : "s"}`, { description: "Press Read scans when they are all in." });
    onRead();
  }

  async function read() {
    setReading(true);
    try {
      const r = await api(`exams/${exam.id}/read`, { method: "POST" });
      if (r.missed.length) toast.warning(`Read ${r.read}; could not line up ${r.missed.length}`, { description: `${r.missed.join(", ")}: check all four corner markers are in the scan, then read again.`, duration: 15000 });
      else toast.success(`Read ${r.read} sheet${r.read === 1 ? "" : "s"}`);
      await onRead();
    } catch (err) {
      toast.error("Reading failed", { description: err.message, duration: 15000 });
    } finally {
      setReading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Scans</CardTitle>
        <CardDescription>JPG, PNG or PDF (one sheet per page). Scan at 200 dpi or more with all four corner markers in the frame.</CardDescription>
        <CardAction>
          <Button onClick={read} disabled={reading || !exam.waiting}>
            {reading ? <Loader2 className="animate-spin" /> : <ScanLine />}
            {reading ? "Reading…" : exam.waiting ? `Read ${exam.waiting} scan${exam.waiting === 1 ? "" : "s"}` : "Read scans"}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        <button type="button" onClick={() => input.current.click()}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); }}
          className={cn("grid w-full place-items-center gap-2 rounded-lg border-2 border-dashed px-4 py-8 text-center text-sm transition-colors hover:bg-muted/50", over && "border-primary bg-muted/50")}>
          <span className="grid size-10 place-items-center rounded-full bg-muted"><Upload className="size-5 text-muted-foreground" /></span>
          <span><span className="font-medium">Drop scans here</span> <span className="text-muted-foreground">or click to choose files</span></span>
          {reading && <span className="text-xs text-muted-foreground">About a second a sheet. Keep this page open.</span>}
        </button>
        <input ref={input} type="file" multiple accept=".jpg,.jpeg,.png,.pdf" hidden onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
        {upload && (
          <div className="mt-4 grid gap-1.5 text-xs text-muted-foreground">
            Uploading {upload.done + 1} of {upload.total}
            <Progress value={(upload.done / upload.total) * 100} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------- results table ----------

function Results({ results, onChange }) {
  const [q, setQ] = useState("");
  const [only, setOnly] = useState("all");
  const [open, setOpen] = useState(null); // sheet id
  const rows = results.rows.filter((x) =>
    (only === "all" || x.flags.length) &&
    (!q || `${x.sheet.file} ${x.sheet.data["ID NO"] || ""}`.toLowerCase().includes(q.toLowerCase())));
  const current = results.rows.find((x) => x.sheet.id === open);

  async function save(sheet, data) {
    try {
      await api(`sheets/${sheet.id}`, { method: "PUT", body: { data } });
      await onChange();
      toast.success("Corrections saved");
    } catch (err) {
      toast.error("Could not save", { description: err.message });
    }
  }

  async function remove(sheet) {
    await api(`sheets/${sheet.id}`, { method: "DELETE" });
    setOpen(null);
    await onChange();
    toast.success(`Removed ${sheet.file}`);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Marks</CardTitle>
        <CardDescription>Click a sheet to see what the reader saw and correct it.</CardDescription>
        <CardAction className="flex gap-2">
          <div className="relative">
            <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="File or email" className="w-40 pl-8 sm:w-52" />
          </div>
          <Select value={only} onValueChange={setOnly}>
            <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sheets</SelectItem>
              <SelectItem value="review">Need review</SelectItem>
            </SelectContent>
          </Select>
        </CardAction>
      </CardHeader>
      <CardContent>
        {!results.rows.length ? (
          <p className="py-10 text-center text-sm text-muted-foreground">No sheets read yet. Add scans above and press Read.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Set</TableHead>
                <TableHead className="text-right">Score</TableHead>
                <TableHead className="text-right" title="Right / partly right / wrong / blank">R / P / W / B</TableHead>
                <TableHead>Review</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map(({ sheet, r, flags }) => (
                <TableRow key={sheet.id} tabIndex={0} className="cursor-pointer" onClick={() => setOpen(sheet.id)} onKeyDown={(e) => e.key === "Enter" && setOpen(sheet.id)}>
                  <TableCell className="font-medium">{sheet.file}</TableCell>
                  <TableCell className="font-mono text-xs">{sheet.data["ID NO"] || <span className="text-muted-foreground">–</span>}</TableCell>
                  <TableCell>{sheet.data.Set || <span className="text-muted-foreground">–</span>}</TableCell>
                  <TableCell className="text-right font-medium tabular-nums">{r.score === null ? <span className="text-muted-foreground">–</span> : <>{fmt(r.score, 2)}<span className="text-muted-foreground"> / {r.max}</span></>}</TableCell>
                  <TableCell className="text-right text-muted-foreground tabular-nums">{r.score === null ? "" : `${r.correct} / ${r.partial} / ${r.wrong} / ${r.blank}`}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {flags.map((f) => <Badge key={f} variant="destructive">{f}</Badge>)}
                      {sheet.edited && <Badge variant="outline">edited</Badge>}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {!rows.length && <TableRow><TableCell colSpan={6} className="py-8 text-center text-muted-foreground">Nothing matches.</TableCell></TableRow>}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <SheetDialog row={current} results={results} onSave={save} onRemove={remove} onClose={() => setOpen(null)} />
    </Card>
  );
}

// ---------- marking scheme ----------

function Num({ label, value, onChange, hint }) {
  const id = `n-${label.replace(/\W/g, "")}`;
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input id={id} type="number" step="any" value={value} onChange={(e) => onChange(e.target.value === "" ? 0 : +e.target.value)} className="tabular-nums" />
      {hint && <FieldDescription>{hint}</FieldDescription>}
    </Field>
  );
}

function Scheme({ rules, setRules }) {
  const set = (g, k, v) => setRules({ ...rules, [g]: { ...rules[g], [k]: v } });
  const s = rules.single, m = rules.multiple;
  const info = { questions: ["q1"], options: ["A", "B", "C", "D"] };
  const example = (key, responses) => {
    const a = parseKey(key, info).answers[0];
    return responses.map((resp) => ({ resp, ...scoreQuestion(resp, a, rules) }));
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Single correct</CardTitle>
          <CardDescription>Questions whose key is one letter, or alternatives like <code>A/C</code>.</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <div className="grid grid-cols-3 gap-4">
              <Num label="Correct" value={s.correct} onChange={(v) => set("single", "correct", v)} />
              <Num label="Wrong" value={s.wrong} onChange={(v) => set("single", "wrong", v)} />
              <Num label="Blank" value={s.blank} onChange={(v) => set("single", "blank", v)} />
            </div>
            <Field>
              <FieldLabel>More than one option marked</FieldLabel>
              <Select value={s.multi} onValueChange={(v) => set("single", "multi", v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="wrong">Counts as wrong (gets the wrong marks)</SelectItem>
                  <SelectItem value="zero">Scores zero</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Example rows={example("B", ["B", "C", "BC", ""])} keyLabel="B" />
          </FieldGroup>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Multiple correct</CardTitle>
          <CardDescription>Questions whose key has more than one letter, like <code>ACD</code>.</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <RadioGroup value={m.mode} onValueChange={(v) => set("multiple", "mode", v)} className="gap-2">
              {Object.entries(MULTI_MODES).map(([k, d]) => {
                const [title, ...rest] = d.split(": ");
                return (
                  <Label key={k} htmlFor={`mode-${k}`} className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 font-normal has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-muted/50">
                    <RadioGroupItem id={`mode-${k}`} value={k} className="mt-0.5" />
                    <span className="grid gap-0.5">
                      <span className="font-medium">{title}</span>
                      <span className="text-xs text-muted-foreground first-letter:uppercase">{rest.join(": ")}</span>
                    </span>
                  </Label>
                );
              })}
            </RadioGroup>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              {m.mode !== "perOption" && <Num label="All right" value={m.correct} onChange={(v) => set("multiple", "correct", v)} />}
              {(m.mode === "partial" || m.mode === "perOption") && <Num label="Per right option" value={m.partial} onChange={(v) => set("multiple", "partial", v)} />}
              <Num label={m.mode === "perOption" ? "Per wrong option" : "Wrong"} value={m.wrong} onChange={(v) => set("multiple", "wrong", v)} />
              <Num label="Blank" value={m.blank} onChange={(v) => set("multiple", "blank", v)} />
            </div>
            <Example rows={example("ACD", ["ACD", "AC", "A", "AB", "ABCD", ""])} keyLabel="ACD" />
          </FieldGroup>
        </CardContent>
      </Card>
    </div>
  );
}

function Example({ rows, keyLabel }) {
  return (
    <div className="rounded-lg border">
      <div className="border-b px-3 py-2 text-xs text-muted-foreground">With the key <span className="font-mono font-medium text-foreground">{keyLabel}</span>, a sheet that marks…</div>
      <div className="grid grid-cols-2 sm:grid-cols-3">
        {rows.map((x) => (
          <div key={x.resp} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
            <span className="font-mono">{x.resp || <span className="font-sans text-muted-foreground">blank</span>}</span>
            <span className={cn("font-medium tabular-nums", x.marks > 0 ? "text-emerald-600 dark:text-emerald-400" : x.marks < 0 ? "text-destructive" : "text-muted-foreground")}>
              {x.marks > 0 ? "+" : ""}{x.marks}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
