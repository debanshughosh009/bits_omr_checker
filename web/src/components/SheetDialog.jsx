// One read sheet: the overlay the reader drew, and every answer, editable to fix a misread
import { useEffect, useState } from "react";
import { ExternalLink, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { keyText, scoreSheet } from "@/lib/score";
import { cn } from "@/lib/utils";

// The question number takes the colour of how the answer scored
const TONE = {
  correct: "text-emerald-600 dark:text-emerald-400", bonus: "text-emerald-600 dark:text-emerald-400",
  partial: "text-amber-600 dark:text-amber-400", wrong: "text-red-600 dark:text-red-400",
};

export default function SheetDialog({ row, results, onSave, onRemove, onClose }) {
  const [data, setData] = useState(null);
  useEffect(() => setData(row ? { ...row.sheet.data } : null), [row]);
  if (!row || !data) return <Dialog open={false} />;

  const { info, keys, rules } = results;
  const r = scoreSheet(data, keys, rules, info);
  const set = (k, v) => setData((d) => ({ ...d, [k]: v.toUpperCase().replace(/\s/g, "") }));
  const changed = JSON.stringify(data) !== JSON.stringify(row.sheet.data);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92svh] grid-rows-[auto_minmax(0,1fr)_auto] sm:max-w-6xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            {row.sheet.file}
            {row.sheet.edited && <Badge variant="outline">Corrected by hand</Badge>}
            {row.flags.map((f) => <Badge key={f} variant="destructive">{f}</Badge>)}
          </DialogTitle>
          <DialogDescription>
            {r.score === null ? `Not marked: ${r.reason}.` : `${r.score} / ${r.max} with the set ${r.keySet || ""} key · ${r.correct} right, ${results.hasMulti ? `${r.partial} partly, ` : ""}${r.wrong} wrong, ${r.blank} blank.`}
          </DialogDescription>
        </DialogHeader>

        <div className="grid min-h-0 gap-6 md:grid-cols-2">
          {row.sheet.overlay ? (
            <a href={row.sheet.overlay} target="_blank" rel="noreferrer" className="group relative block min-h-0 overflow-auto rounded-lg border bg-white">
              <img src={row.sheet.overlay} alt="The scan, with the bubbles the reader saw marked" className="w-full" />
              <span className="absolute top-2 right-2 rounded-md bg-background/90 p-1.5 opacity-0 shadow group-hover:opacity-100"><ExternalLink className="size-4" /></span>
            </a>
          ) : (
            <div className="grid place-items-center rounded-lg border border-dashed p-8 text-sm text-muted-foreground">No overlay image for this sheet.</div>
          )}
          <ScrollArea className="min-h-0">
            <div className="grid gap-4 pr-3">
              <div className="grid grid-cols-2 gap-4">
                <Field>
                  <FieldLabel htmlFor="s-id">Email</FieldLabel>
                  <Input id="s-id" value={data["ID NO"] ?? ""} onChange={(e) => set("ID NO", e.target.value)} className="font-mono" />
                </Field>
                <Field>
                  <FieldLabel htmlFor="s-set">Set</FieldLabel>
                  <Input id="s-set" value={data.Set ?? ""} onChange={(e) => set("Set", e.target.value)} className="font-mono" />
                </Field>
              </div>
              <p className="text-xs text-muted-foreground">Type the options actually marked to fix a misread. Reading this file again replaces your corrections.</p>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-1.5">
                {info.questions.map((q, i) => {
                  const p = r.perQ[i];
                  return (
                    <label key={q} className="grid grid-cols-[2rem_4rem_1fr] items-center gap-2 py-0.5 text-sm">
                      <span className={cn("text-right font-semibold tabular-nums", TONE[p?.result] ?? "text-muted-foreground")}>{q.slice(1)}</span>
                      <Input value={data[q] ?? ""} onChange={(e) => set(q, e.target.value)} className="h-7 px-2 font-mono" aria-label={`Question ${q.slice(1)}`} />
                      <span className="truncate font-mono text-xs text-muted-foreground" title="Answer key">{p ? keyText(p.key) || "?" : ""}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          </ScrollArea>
        </div>

        <DialogFooter className="sm:justify-between">
          <Button variant="ghost" className="text-destructive hover:text-destructive" onClick={() => onRemove(row.sheet)}><Trash2 />Remove sheet</Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>Close</Button>
            <Button disabled={!changed} onClick={() => onSave(row.sheet, data)}>Save corrections</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
