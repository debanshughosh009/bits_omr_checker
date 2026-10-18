"""Dependency-light sanity check: overlay the template on a scan and read each bubble the same
way OMRChecker does (mean grey level inside the bubble box). Not a replacement for main.py."""
import json, sys, cv2, numpy as np
tpl = json.load(open(sys.argv[1])); img = cv2.imread(sys.argv[2], 0)
assert list(img.shape[::-1]) == tpl["pageDimensions"], (img.shape, tpl["pageDimensions"])
bw, bh = tpl["bubbleDimensions"]
FT = {"QTYPE_MCQ4": (list("ABCD"), "horizontal")}
out = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR); fields = {}
for name, b in tpl["fieldBlocks"].items():
    vals, d = (b["bubbleValues"], b["direction"]) if "bubbleValues" in b else FT[b["fieldType"]]
    labs = []
    for l in b["fieldLabels"]:
        m = __import__("re").fullmatch(r"([^\d]+)(\d+)\.\.(\d+)", l)
        labs += [f"{m[1]}{i}" for i in range(int(m[2]), int(m[3]) + 1)] if m else [l]
    ox, oy = b["origin"]
    for li, lab in enumerate(labs):
        row = []
        for vi, v in enumerate(vals):
            x = ox + (vi * b["bubblesGap"] if d == "horizontal" else li * b["labelsGap"])
            y = oy + (li * b["labelsGap"] if d == "horizontal" else vi * b["bubblesGap"])
            x, y = round(x), round(y)
            mean = float(img[y:y+bh, x:x+bw].mean()); row.append((v, mean))
            cv2.rectangle(out, (x, y), (x+bw, y+bh), (0, 160, 0), 1)
        fields[lab] = row
THR = float(sys.argv[4]) if len(sys.argv) > 4 else 130
res = {}
for lab, row in fields.items():
    marked = [v for v, m in row if m < THR]
    res[lab] = "".join(marked)
    for v, m in row:
        if m < THR:
            x = None
cv2.imwrite(sys.argv[3], out)
print("Set   :", res["Set"]); print("ID NO :", "".join(res[f"id{i}"] for i in range(1, 14)))
print("Q1-10 :", [res[f"q{i}"] or "-" for i in range(1, 11)])
print("Q11-30:", [res[f"q{i}"] or "-" for i in range(11, 31)])
darkest_unmarked = min(m for r in fields.values() for v, m in r if m >= THR)
lightest_marked = max([m for r in fields.values() for v, m in r if m < THR] or [0])
print(f"threshold {THR}: lightest marked={lightest_marked:.0f}  darkest unmarked={darkest_unmarked:.0f}")
