"""Validate template.json / config.json against OMRChecker's own JSON schemas.
Usage: python3 validate_schema.py <OMRChecker_repo> <template.json> [config.json]
(Stubs rich/dotmap only if they aren't installed; with the real deps this is just a normal import.)"""
import sys, json, types
repo = sys.argv[1]; sys.path.insert(0, repo)
try:
    import rich, dotmap  # noqa
except ImportError:
    for n in ["rich", "rich.console", "rich.table", "rich.logging", "dotmap"]:
        sys.modules[n] = types.ModuleType(n)
    class _Any:
        def __init__(s,*a,**k): pass
        def __getattr__(s,k): return _Any()
        def __call__(s,*a,**k): return _Any()
    import logging
    for n in ["rich.console","rich.table","rich.logging","dotmap"]:
        for a in ["Console","Table","RichHandler","DotMap"]:
            setattr(sys.modules[n], a, dict if a=="DotMap" else type("RH",(logging.NullHandler,),{"__init__":lambda self,*a,**k: logging.NullHandler.__init__(self)}) if a=="RichHandler" else _Any)
    sys.modules["rich"].console = sys.modules["rich.console"]
import jsonschema
from src.schemas.template_schema import TEMPLATE_SCHEMA
t = json.load(open(sys.argv[2])); jsonschema.validate(t, TEMPLATE_SCHEMA); print("template schema: VALID")
if len(sys.argv) > 3:
    from src.schemas.config_schema import CONFIG_SCHEMA
    jsonschema.validate(json.load(open(sys.argv[3])), CONFIG_SCHEMA); print("config schema: VALID")
W, H = t["pageDimensions"]; bw, bh = t["bubbleDimensions"]; bad = 0
for n, b in t["fieldBlocks"].items():
    ox, oy = b["origin"]
    vals = b.get("bubbleValues") or list("ABCD")
    nlab = 15 if n.startswith("Q") else 1
    h_dir = b.get("direction") == "horizontal" or "fieldType" in b
    ex = ox + (b["bubblesGap"]*(len(vals)-1) if h_dir else b["labelsGap"]*(nlab-1)) + bw
    ey = oy + (b["labelsGap"]*(nlab-1) if h_dir else b["bubblesGap"]*(len(vals)-1)) + bh
    if ox < 0 or oy < 0 or ex >= W or ey >= H: bad += 1; print("OVERFLOW", n)
print("blocks overflowing page:", bad)
