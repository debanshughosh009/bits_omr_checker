// Answer keys, one set at a time: each question gets a type, then its right
// option(s) picked like bubbles: one for single correct, any number for multiple.
// Keys are stored as text (see score.js).
import { useState } from "react";
import { Copy, Eraser, ListChecks, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { keyToText } from "@/lib/score";
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
  const [types, setTypes] = useState({}); // "set:index" -> the type chosen for that question
  const [fallback, setFallback] = useState({}); // set -> type for questions with nothing picked yet
  const answers = parsed[set].answers;
  const order = (o) => [...o].sort((a, b) => info.options.indexOf(a) - info.options.indexOf(b));

  const write = (s, next) => setKeyTexts((t) => ({ ...t, [s]: keyToText(next) }));
  // The type chosen for a question, as long as its answer still fits it: one option picked
  // under "either accepted" is stored like single correct, and must stay "either accepted"
  const rowType = (i) => {
    const chosen = types[`${set}:${i}`], a = answers[i];
    if (chosen && (!a || typeOf(a) === chosen || (chosen === "any" && a.kind === "single"))) return chosen;
    return typeOf(a) ?? fallback[set] ?? "single";
  };

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
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16 text-right">Question</TableHead>
                <TableHead className="w-48">Type</TableHead>
                <TableHead>Answer</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {info.questions.map((q, i) => {
                const type = rowType(i);
                const a = answers[i];
                const opts = picked(a);
                return (
                  <TableRow key={q} className={cn(!a && "bg-muted/30")}>
                    <TableCell className="text-right font-semibold tabular-nums">{i + 1}</TableCell>
                    <TableCell>
                      <Select value={type} onValueChange={(t) => change(i, t, opts)}>
                        <SelectTrigger size="sm" className="w-44 text-xs" aria-label={`Question ${i + 1} type`}><SelectValue /></SelectTrigger>
                        <SelectContent>{Object.entries(TYPES).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
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
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>

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
