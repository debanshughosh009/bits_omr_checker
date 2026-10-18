"""Generate template.json for the BITS Hyderabad 30Q OMR sheet (1791x2576 px scans).
Coordinates were measured from a real scan; see README for how to re-calibrate."""
import json, sys
W, H = 1791, 2576
B = 38                      # bubble box (px); printed circles are ~42px outer, ~38 inner
h = B / 2

def o(cx, cy):              # OMRChecker origin = top-left of the first bubble box
    return [round(cx - h), round(cy - h)]

# --- calibrated grid (centres, px) ---
ID_X0, ID_DX = 872.0, 62.4          # centre of ID column 1, column pitch
ID_Y0, ID_DY = 722.0, 56.0          # centre of ID row 0, row pitch
SET_X0, SET_Y, SET_DX = 1436.0, 498.0, 62.4
QL_X0, QR_X0, Q_DX = 263.5, 1349.0, 62.4
Q_Y0, Q_DY = 1506.0, 56.14

ID_COLS = [  # per-column printed bubble labels, top -> bottom
    ["2"],                                        # 1  pre-printed
    ["0"],                                        # 2  pre-printed
    ["1", "2"],                                   # 3  year (hundreds)
    list("0123456789"),                           # 4  year (units)
    ["A", "B", "H", "P"],                         # 5  degree/branch letter
    ["1", "2", "3", "4", "5", "7", "8", "A", "H"],# 6
    ["P", "T", "A", "B", "X", "0", "1", "2", "4"],# 7
    ["A", "F", "P", "S"] + list("012345789"),     # 8
    list("0123456789"), list("0123456789"),       # 9,10
    list("0123456789"), list("0123456789"),       # 11,12
    ["H"],                                        # 13 pre-printed
]

blocks, labels = {}, []
blocks["Set"] = {"bubbleValues": ["A", "B", "C", "D"], "direction": "horizontal",
                 "fieldLabels": ["Set"], "bubblesGap": SET_DX, "labelsGap": 0,
                 "origin": o(SET_X0, SET_Y)}
for i, vals in enumerate(ID_COLS, 1):
    blocks[f"ID{i}"] = {"bubbleValues": vals, "direction": "vertical",
                        "fieldLabels": [f"id{i}"], "bubblesGap": ID_DY, "labelsGap": 0,
                        "origin": o(ID_X0 + (i - 1) * ID_DX, ID_Y0)}
blocks["Q1_15"] = {"fieldType": "QTYPE_MCQ4", "fieldLabels": ["q1..15"],
                   "bubblesGap": Q_DX, "labelsGap": Q_DY, "origin": o(QL_X0, Q_Y0)}
blocks["Q16_30"] = {"fieldType": "QTYPE_MCQ4", "fieldLabels": ["q16..30"],
                    "bubblesGap": Q_DX, "labelsGap": Q_DY, "origin": o(QR_X0, Q_Y0)}

template = {
    "pageDimensions": [W, H],
    "bubbleDimensions": [B, B],
    "preProcessors": [],      # scanner output is already flat; see README for marker-crop option
    "customLabels": {"ID NO": [f"id{i}" for i in range(1, 14)]},
    "fieldBlocks": blocks,
    "outputColumns": ["Set", "ID NO"] + [f"q{i}" for i in range(1, 31)],
}
json.dump(template, open(sys.argv[1] if len(sys.argv) > 1 else "template.json", "w"), indent=2)
print("ok", len(template["fieldBlocks"]), "blocks")
