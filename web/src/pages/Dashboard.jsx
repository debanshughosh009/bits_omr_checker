// Home: start a new sheet design, or pick a saved sheet to evaluate
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { ArrowRight, FileUp, Pencil, Plus, ScanLine, Trash2, TriangleAlert } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, go, useExams } from "@/lib/api";
import { loadDraft } from "@/lib/draft";
import { examResults, fmt } from "@/lib/results";
import { defaults, layout, sheetSvg } from "@/lib/sheet";

export default function Dashboard() {
  const { exams, reload, importSheet } = useExams();
  const [full, setFull] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const draft = useMemo(loadDraft, []);
  const preview = useMemo(() => sheetSvg(layout(draft)), [draft]);
  const hasDraft = JSON.stringify(draft) !== JSON.stringify(defaults());

  // ponytail: loads every sheet in full to score it; add a summary endpoint if this gets slow with many large exams
  useEffect(() => {
    if (!exams) return;
    Promise.all(exams.map((e) => api(`exams/${e.id}`))).then((list) => setFull(list.map((e) => ({ exam: e, ...examResults(e) }))));
  }, [exams]);

  async function remove() {
    const e = deleting;
    setDeleting(null);
    try {
      await api(`exams/${e.id}`, { method: "DELETE" });
      await reload();
      toast.success(`Deleted ${e.name}`);
    } catch (err) {
      toast.error("Could not delete", { description: err.message });
    }
  }

  return (
    <main className="mx-auto grid w-full max-w-6xl gap-8 p-4 md:p-8">
      <Card className="relative overflow-hidden py-0">
        <div className="grid items-center md:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="grid gap-5 p-6 md:p-10">
            <div className="grid gap-2">
              <h1 className="text-3xl font-semibold tracking-tight">Design an OMR sheet</h1>
              <p className="max-w-lg text-muted-foreground">
                Set the header, the sets and the number of questions, then print it. Save the sheet and it appears below, ready to evaluate the scans.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button size="lg" onClick={() => go("/design")}><Plus />{hasDraft ? "Continue designing" : "Start designing"}</Button>
              <Button size="lg" variant="ghost" onClick={importSheet}><FileUp />Evaluate a sheet designed elsewhere</Button>
            </div>
            {hasDraft && <p className="text-xs text-muted-foreground">You have an unsaved draft{draft.exam ? `, “${[draft.course, draft.exam].filter(Boolean).join(" ")}”` : ""}; it opens where you left it.</p>}
          </div>
          <button type="button" onClick={() => go("/design")} aria-label="Open the designer"
            className="relative hidden h-full min-h-64 overflow-hidden border-l bg-muted/50 md:block">
            <div className="absolute top-8 left-10 w-72 rotate-3 transition-transform duration-300 hover:rotate-1 [&_svg]:h-auto [&_svg]:w-full [&_svg]:rounded-sm [&_svg]:bg-white [&_svg]:shadow-xl [&_svg]:ring-1 [&_svg]:ring-black/10"
              dangerouslySetInnerHTML={{ __html: preview }} />
          </button>
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Saved sheets</CardTitle>
          <CardDescription>Open one to enter its answer key, read the scans and see the marks.</CardDescription>
        </CardHeader>
        <CardContent>
          {exams?.length === 0 ? (
            <div className="grid place-items-center gap-2 rounded-lg border border-dashed py-12 text-center">
              <ScanLine className="size-6 text-muted-foreground" />
              <p className="font-medium">No saved sheets yet</p>
              <p className="max-w-sm text-sm text-muted-foreground">Design a sheet and press Save; it is kept on this computer and listed here.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Sheet</TableHead>
                  <TableHead>Saved</TableHead>
                  <TableHead className="text-right">Scans read</TableHead>
                  <TableHead className="text-right">Mean</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-0" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {!full && exams?.map((e) => (
                  <TableRow key={e.id}><TableCell colSpan={6}><Skeleton className="h-9" /></TableCell></TableRow>
                ))}
                {full?.map(({ exam, stats, keys, info }) => (
                  <TableRow key={exam.id} className="group cursor-pointer" onClick={() => go(`/sheets/${exam.id}`)}>
                    <TableCell>
                      <div className="font-medium">{exam.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {info.questions.length} questions · {info.options.join("")}{info.sets.length ? ` · sets ${info.sets.join("")}` : ""}{exam.design ? "" : " · imported"}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{new Date(exam.created).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</TableCell>
                    <TableCell className="text-right tabular-nums">{stats.sheets || <span className="text-muted-foreground">–</span>}</TableCell>
                    <TableCell className="text-right tabular-nums">{stats.mean === null ? <span className="text-muted-foreground">–</span> : `${fmt(stats.mean)} / ${stats.max}`}</TableCell>
                    <TableCell>
                      {!Object.keys(keys).length ? <Badge variant="outline">No key yet</Badge>
                        : !stats.sheets ? <Badge variant="outline">No scans yet</Badge>
                        : stats.review ? <Badge variant="secondary"><TriangleAlert />{stats.review} to review</Badge>
                        : <Badge variant="secondary">Marked</Badge>}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="icon-sm" title={exam.design ? "Edit the design" : "Imported from a template.json: no design to edit"}
                          disabled={!exam.design} onClick={() => go(`/design/${exam.id}`)}><Pencil /></Button>
                        <Button variant="ghost" size="icon-sm" title="Delete" onClick={() => setDeleting(exam)}><Trash2 /></Button>
                        <Button variant="outline" size="sm" onClick={() => go(`/sheets/${exam.id}`)}>Evaluate<ArrowRight /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {deleting?.name}?</AlertDialogTitle>
            <AlertDialogDescription>The design, its answer keys, marking scheme, read sheets and scans are removed from this computer. This cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={remove}>Delete sheet</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </main>
  );
}
