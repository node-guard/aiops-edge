# experiments/runs

One folder per fault run, plus an append-only index.

```
runs/
├── index.parquet                     # one row per run (git-ignored)
├── 20261107T070758Z-F01-96b8c7/
│   ├── meta.json                     # frozen contract, validated at write time
│   └── window.json                   # params, start/end, duration, HTTP status
├── load-20261107T065722Z/            # Locust output (S2-B3, git-ignored)
└── export-20261109T080825Z-f065dd/   # Prometheus -> Parquet (S2-B5, git-ignored)
    ├── metrics.parquet               # long-format samples + units
    └── manifest.json                 # range, coverage per query, config SHA
```

- `meta.json` is written once by `experiments/harness/run_fault.py` and never
  edited. A run that failed is kept with `valid=false` and a reason.
- `index.parquet` has the columns `run_id`, `fault_id`, `target`, `t_injection`,
  `t_end`, `duration_seconds`, `valid`, `config_hash`, `meta_path`. It is
  single-writer and append-only.
- Per-run folders and `index.parquet` are git-ignored (`*.parquet`,
  `experiments/runs/load-*/`): they are data, not code. Keep only summaries in
  `experiments/NOTES.md` or the thesis tables.
- Large raw data (Prometheus exports, traces) belongs in `raw/` inside the run
  folder, also git-ignored, with a manifest of files and sizes in git.

To rebuild the index from the folders:

```python
import json, pathlib
import pyarrow as pa, pyarrow.parquet as pq

root = pathlib.Path("experiments/runs")
rows = []
for meta_path in sorted(root.glob("*/meta.json")):
    meta = json.loads(meta_path.read_text())
    window_path = meta_path.with_name("window.json")
    window = json.loads(window_path.read_text()) if window_path.exists() else {}
    rows.append(
        {
            "run_id": meta["run_id"],
            "fault_id": meta["fault_id"],
            "target": meta["target"],
            "t_injection": meta["t_injection"],
            "t_end": window.get("t_end", ""),
            "duration_seconds": window.get("duration_seconds", 0.0),
            "valid": meta["valid"],
            "config_hash": meta["config_hash"],
            "meta_path": str(meta_path),
        }
    )
pq.write_table(pa.Table.from_pylist(rows), root / "index.parquet")
```
