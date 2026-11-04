// Answer keys, one set at a time: each question gets a type, then its right
// option(s) picked like bubbles: one for single correct, any number for multiple.
// Keys are still stored as text (see score.js), so a pasted key works too.
import { useState } from "react";
import { ClipboardPaste, Copy, Eraser, ListChecks, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { keyToText, parseKey } from "@/lib/score";
import { cn } from "@/lib/utils";

const TYPES = {
  single: "Single correct",
  multiple: "Multiple correct",
  any: "Either accepted",
  bonus: "Bonus",
  dropped: "Dropped",
};

const typeOf = (a) => (!a ? null : a.kind === "single" && a.accept.length > 1 ? "any" : a.kind);
const picked = (a) => (!a ? [] : a.kind === "multiple" ? a.right : a.kind === "single" ? a.accept : []);

// The answer for a type and the options picked; null when nothing is picked yet
function answerFor(type, opts) {
  if (type === "bonus" || type === "dropped") return { kind: type };
  if (!opts.length) return null;
  if (type === "multiple") return { kind: "multiple", right: opts };
  return { kind: "single", accept: type === "single" ? opts.slice(0, 1) : opts };
}

export default function AnswerKey({ info, keyTexts, setKeyTexts, parsed }) {
  const sets = info.sets.length ? info.sets : [""];
  const [set, setSet] = useState(sets[0]);
  const [types, setTypes] = useState({}); // "set:index" -> type, for questions with nothing picked yet
  const [fallback, setFallback] = useState({}); // set -> type for questions with nothing picked yet
  const [pasting, setPasting] = useState(null);
  const answers = parsed[set].answers;
  const order = (o) => [...o].sort((a, b) => info.options.indexOf(a) - info.options.indexOf(b));

  const write = (s, next) => setKeyTexts((t) => ({ ...t, [s]: keyToText(next) }));
  const rowType = (i) => typeOf(answers[i]) ?? types[`${set}:${i}`] ?? fallback[set] ?? "single";

  function change(i, type, opts) {
    const next = [...answers];
    next[i] = answerFor(type, order(opts));
    setTypes((t) => ({ ...t, [`${set}:${i}`]: type }));
    write(set, next);
  }

  function allAs(type) {
    setFallback((f) => ({ ...f, [set]: type }));
    setTypes((t) => Object.fromEntries(Object.entries(t).filter(([k]) => !k.startsWith(`${set}:`))));
    write(set, answers.map((a) => (["single", "multiple"].includes(typeOf(a)) ? answerFor(type, picked(a)) : a)));
  }

  const given = (s) => parsed[s].answers.filter(Boolean).length;
  const counts = Object.fromEntries(Object.keys(TYPES).map((t) => [t, answers.filter((a) => typeOf(a) === t).length]));
  const issues = keyTexts[set]?.trim() ? parsed[set].issues.filter((t) => !/no answer/.test(t)) : [];

  return (
    <div className="grid">
      <div className="sticky top-14 z-10 flex flex-wrap items-center gap-x-4 gap-y-2 border-b bg-background/95 px-4 py-2.5 backdrop-blur md:px-6">
        {sets.length > 1 && (
          <div role="tablist" aria-label="Sets" className="flex gap-1 rounded-lg bg-muted p-1">
            {sets.map((s) => (
              <button key={s} role="tab" aria-selected={s === set} onClick={() => setSet(s)}
                className={cn("flex items-center gap-2 rounded-md px-3 py-1 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground",
                  s === set && "bg-background text-foreground shadow-sm")}>
                Set {s}
                <span className={cn("rounded-full px-1.5 text-xs tabular-nums",
                  given(s) === info.questions.length ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" : "bg-muted-foreground/15")}>
                  {given(s)}/{info.questions.length}
                </span>
              </button>
            ))}
          </div>
        )}
        <p className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
          {given(set)} of {info.questions.length} answered
          {Object.entries(counts).filter(([, n]) => n).map(([t, n]) => ` · ${n} ${TYPES[t].toLowerCase()}`).join("")}
        </p>
        <div className="flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="outline" size="sm"><ListChecks />Type for all</Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Every question in {set ? `set ${set}` : "the key"} is…</DropdownMenuLabel>
              <DropdownMenuItem onSelect={() => allAs("single")}>Single correct</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => allAs("multiple")}>Multiple correct</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          {sets.length > 1 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild><Button variant="outline" size="sm"><Copy />Copy from</Button></DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {sets.filter((s) => s !== set).map((s) => (
                  <DropdownMenuItem key={s} disabled={!given(s)} onSelect={() => setKeyTexts((t) => ({ ...t, [set]: t[s] || "" }))}>Set {s}</DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          <Button variant="outline" size="sm" onClick={() => setPasting(keyTexts[set] || "")}><ClipboardPaste />Paste</Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="Clear" disabled={!given(set)}><Eraser /></Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Clear every answer in {set ? `set ${set}` : "the key"}?</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onSelect={() => setKeyTexts((t) => ({ ...t, [set]: "" }))}>Clear</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="grid gap-4 p-4 md:p-6">
        {issues.length > 0 && (
          <ul className="grid gap-1 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
            {issues.map((t) => <li key={t} className="flex gap-2"><TriangleAlert className="mt-0.5 size-4 shrink-0" />{t}</li>)}
          </ul>
        )}
        <div className="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(min(100%,22rem),1fr))]">
          {info.questions.map((q, i) => {
            const type = rowType(i);
            const a = answers[i];
            const opts = picked(a);
            return (
              <div key={q} className={cn("flex items-center gap-3 rounded-lg border bg-card px-3 py-2", !a && "border-dashed bg-transparent")}>
                <span className="w-7 shrink-0 text-right font-semibold tabular-nums">{i + 1}</span>
                <Select value={type} onValueChange={(t) => change(i, t, opts)}>
                  <SelectTrigger size="sm" className="w-36 shrink-0 text-xs" aria-label={`Question ${i + 1} type`}><SelectValue /></SelectTrigger>
                  <SelectContent>{Object.entries(TYPES).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                </Select>
                {type === "bonus" || type === "dropped" ? (
                  <span className="text-xs text-muted-foreground">{type === "bonus" ? "Full marks to everyone" : "No marks, left out of the total"}</span>
                ) : type === "single" ? (
                  <ToggleGroup variant="outline" type="single" value={opts[0] ?? ""} onValueChange={(v) => change(i, type, v ? [v] : [])} aria-label={`Question ${i + 1} answer`}>
                    {info.options.map((o) => <Bubble key={o} o={o} />)}
                  </ToggleGroup>
                ) : (
                  <ToggleGroup variant="outline" type="multiple" value={opts} onValueChange={(v) => change(i, type, v)} aria-label={`Question ${i + 1} answers`}>
                    {info.options.map((o) => <Bubble key={o} o={o} square />)}
                  </ToggleGroup>
                )}
              </div>
            );
          })}
        </div>
        <p className="text-xs text-muted-foreground">
          Round bubbles take one answer; square ones take any number. “Either accepted” gives full marks for any one of the picked options.
        </p>
      </div>

      <Dialog open={pasting !== null} onOpenChange={(o) => !o && setPasting(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Paste {set ? `set ${set}'s` : "the"} key</DialogTitle>
            <DialogDescription>
              One answer per question, in order or numbered (<code>12 AC</code>), separated by spaces, commas or new lines; a spreadsheet column works.
              <code> B</code> single, <code>AC</code> or <code>A+</code> multiple, <code>A/C</code> either, <code>*</code> bonus, <code>-</code> dropped.
            </DialogDescription>
          </DialogHeader>
          <Textarea value={pasting ?? ""} onChange={(e) => setPasting(e.target.value)} rows={8} className="font-mono" autoFocus placeholder="B C AC D A/C * - …" />
          {pasting && (() => {
            const k = parseKey(pasting, info);
            return <p className={cn("text-sm", k.issues.some((t) => !/no answer/.test(t)) ? "text-destructive" : "text-muted-foreground")}>
              {k.answers.filter(Boolean).length} of {info.questions.length} answers read{k.issues.length ? ` · ${k.issues.join(" · ")}` : ""}
            </p>;
          })()}
          <DialogFooter>
            <Button variant="outline" onClick={() => setPasting(null)}>Cancel</Button>
            <Button onClick={() => { write(set, parseKey(pasting, info).answers); setPasting(null); }}>Use this key</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Bubble({ o, square }) {
  return (
    <ToggleGroupItem value={o} aria-label={o}
      className={cn("size-8 min-w-8 rounded-full border font-mono text-xs font-semibold data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-primary-foreground hover:data-[state=on]:bg-primary/90",
        square && "rounded-md")}>
      {o}
    </ToggleGroupItem>
  );
}
