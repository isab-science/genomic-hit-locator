# Genomic Hit Locator

Standalone web application for genomic hit localization at ISAB.

## Current state

- Separate repo and runtime from `crispr-tools`
- Served as its own app on the same machine
- Public hostname: `genomic-hit-locator.isab.science`
- Designed to be embedded inside `isab.science` via `iframe`
- Uses a local human gene annotation workbook for chromosome and genomic-position mapping
- Supports interactive Plotly skyline plots and SVG export

## Local run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8082
```

The app expects a local annotation file containing gene symbol, chromosome, and start-position columns. By default it uses:

`/home/aag/Neuropathology - Manuscripts/TrevisanWang2024/Data/ScreenResults/PrP_genes_and_NT_ordered_AguzziLab.xlsx`

Override with `GENOMIC_HIT_LOCATOR_ANNOTATION_PATH` if needed.

## Deployment notes

Systemd and environment templates live in `deploy/`.
