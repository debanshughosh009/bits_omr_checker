// Evaluate a sheet that wasn't designed here: the pre-designer BITS sheet or any template.json
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { api, go, useExams } from "@/lib/api";

export default function ImportDialog({ open, onClose }) {
  const { reload } = useExams();
  const [name, setName] = useState("");
  const [choice, setChoice] = useState("bits");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName("");
    setChoice("bits");
    setFile(null);
  }, [open]);

  async function create(e) {
    e.preventDefault();
    setBusy(true);
    try {
      let tpl;
      if (choice === "bits") tpl = await (await fetch("/scans_to_csv/template.json")).json();
      else if (!file) throw new Error("choose a template.json");
      else tpl = JSON.parse(await file.text());
      const fallback = choice === "bits" ? "BITS 30-question sheet" : file.name.replace(/(_template)?\.json$/i, "");
      const { id } = await api("exams", { method: "POST", body: { name: name.trim() || fallback, template: tpl } });
      await reload();
      onClose();
      go(`/sheets/${id}`);
      toast.success("Sheet added", { description: "Next: enter the answer key, then add scans." });
    } catch (err) {
      toast.error("Could not add the sheet", { description: err.message });
    } finally {
      setBusy(false);
    }
  }

  const options = [
    { value: "bits", label: "The pre-designer BITS sheet", hint: "The hand-calibrated 30-question sheet" },
    { value: "file", label: "A template.json", hint: "Downloaded from the designer or written by hand" },
  ];

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={create} className="grid gap-6">
          <DialogHeader>
            <DialogTitle>Evaluate a sheet designed elsewhere</DialogTitle>
            <DialogDescription>Scans are read against this layout, so pick the one that was printed.</DialogDescription>
          </DialogHeader>
          <Field>
            <FieldLabel>Layout</FieldLabel>
            <RadioGroup value={choice} onValueChange={setChoice} className="gap-2">
              {options.map((o) => (
                <Label key={o.value} htmlFor={`src-${o.value}`}
                  className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 font-normal has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-muted/50">
                  <RadioGroupItem id={`src-${o.value}`} value={o.value} className="mt-0.5" />
                  <span className="grid gap-1">
                    <span className="font-medium">{o.label}</span>
                    <span className="text-xs text-muted-foreground">{o.hint}</span>
                  </span>
                </Label>
              ))}
            </RadioGroup>
            {choice === "file" && <Input type="file" accept=".json,application/json" onChange={(e) => setFile(e.target.files[0])} />}
          </Field>
          <Field>
            <FieldLabel htmlFor="import-name">Name</FieldLabel>
            <Input id="import-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="EEE F111 Quiz 1" />
            <FieldDescription>Shown on the dashboard.</FieldDescription>
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={busy}>Add sheet</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
