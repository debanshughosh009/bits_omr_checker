# Master OMR Assets & Architecture

This master directory stores the core reference assets, overarching roadmap, templates, utility scripts, sample datasets, and the upstream reference engine—segregated cleanly from individual stage implementations.

## Directory Structure

```
master/
├── README.md                 # This overview file
├── docs/                     # Project plans and documentation
│   ├── plan.md               # Master multi-milestone architecture & roadmap (M0-M8)
│   ├── OMRChecker_README.md  # Upstream OMRChecker documentation & BITS notes
│   └── bits_omr_README.md    # BITS OMR template instructions & setup
├── templates/                # Production & reference templates
│   ├── template.json         # BITS 30Q JSON template definition
│   ├── config.json           # Detection parameters & thresholds
│   └── overlay.png           # Visual overlay verification image
├── scripts/                  # Utility scripts for templates
│   ├── make_template.py      # Script to generate template.json
│   ├── check_template.py     # Script to check and verify template alignments
│   └── validate_schema.py    # Schema validation against OMRChecker specs
├── samples/                  # Reference test data & outputs
│   ├── inputs/               # 11 sample OMR test scans (normal, multi-mark, cropped)
│   └── baseline_results/     # Baseline evaluation outputs (Results_02AM.csv)
└── reference_engine/         # Full upstream OMRChecker engine & repository
    ├── src/                  # Upstream processing & evaluation pipeline
    ├── main.py               # Upstream entrypoint
    ├── Dockerfile            # Container configuration
    ├── docker-compose.yml
    ├── pyproject.toml
    └── requirements.txt
```

## Stage Segregation

Individual development stages are organized in their own dedicated folders alongside this `master` directory:
- `scans_to_csv/`: **Stage 1** – Standalone CLI wrapper turning scan folders into CSV with validation checks.
- Future stages (Scoring, Review & Flagging, Scaling, OMR Designer) can draw from templates and reference specs in `master/`.
