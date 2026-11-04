// Two single-series bar charts: how the marks are spread, and how many got each question right
import { Bar, BarChart, CartesianGrid, Cell, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";

const LOW = 0.2; // fewer than this share right usually means a wrong key
const MIN_SHEETS = 5; // below this the share says nothing about the key

function bins(scored, max) {
  const marks = scored.map((x) => x.r.score);
  const lo = Math.min(0, Math.floor(Math.min(...marks)));
  const width = Math.max(1, Math.ceil((max - lo) / 10));
  const out = [];
  for (let a = lo; a <= max; a += width) out.push({ range: width === 1 ? `${a}` : `${a}–${Math.min(a + width - 1, max)}`, a, b: a + width, sheets: 0 });
  for (const m of marks) (out.find((x) => m >= x.a && m < x.b) ?? out.at(-1)).sheets++;
  return out;
}

export default function ExamCharts({ scored, stats, info }) {
  if (!scored.length) return null;
  const right = info.questions.map((q, i) => {
    let c = 0, n = 0;
    for (const { r } of scored) {
      const p = r.perQ[i];
      if (!p || p.result === "dropped" || p.result === "bonus") continue;
      n++;
      c += p.result === "correct";
    }
    return { q: q.slice(1), right: n ? Math.round((c / n) * 100) : null };
  });
  const isLow = (x) => scored.length >= MIN_SHEETS && x.right !== null && x.right < LOW * 100;
  const low = right.filter(isLow);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Score distribution</CardTitle>
          <CardDescription>{stats.scored} marked sheet{stats.scored === 1 ? "" : "s"}, out of {stats.max}</CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer config={{ sheets: { label: "Sheets", color: "var(--chart-2)" } }} className="aspect-auto h-52 w-full">
            <BarChart data={bins(scored, stats.max)} margin={{ left: 0, right: 4 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="range" tickLine={false} axisLine={false} tickMargin={8} interval="preserveStartEnd" />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={40} />
              <ChartTooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltipContent labelFormatter={(l) => `Marks ${l}`} />} />
              <Bar dataKey="sheets" fill="var(--color-sheets)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Right answers by question</CardTitle>
          <CardDescription>
            {low.length
              ? <>Under {LOW * 100}% right (red), check the key: <span className="text-destructive">{low.map((x) => `q${x.q}`).join(", ")}</span></>
              : "Share of sheets with the question fully right"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer config={{ right: { label: "% right", color: "var(--chart-2)" } }} className="aspect-auto h-52 w-full">
            <BarChart data={right} margin={{ left: 0, right: 4 }} barCategoryGap={2}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="q" tickLine={false} axisLine={false} tickMargin={8} interval="preserveStartEnd" />
              <YAxis domain={[0, 100]} ticks={[0, 50, 100]} tickFormatter={(v) => `${v}%`} tickLine={false} axisLine={false} width={40} />
              <ChartTooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltipContent labelFormatter={(l) => `Question ${l}`} />} />
              <Bar dataKey="right" radius={[4, 4, 0, 0]}>
                {right.map((x) => <Cell key={x.q} fill={isLow(x) ? "var(--destructive)" : "var(--color-right)"} />)}
              </Bar>
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>
    </div>
  );
}
