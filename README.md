# Genomic Hit Locator

This document is the living guide for the Genomic Hit Locator app. We will keep updating it as the app evolves so the public tool, the local deployment, and the repository documentation stay aligned.

## What the app does

The Genomic Hit Locator is a standalone Python web app for plotting screen-wide gene effects across the human genome and then visually highlighting a selected subset of hits.

At the moment it can:

- accept one file containing the full tested gene set and an effect-size column
- optionally accept a second file containing genes to highlight
- alternatively accept a pasted comma-separated or newline-separated list of genes
- merge those genes against a local human annotation table with chromosome and genomic start-position data
- draw an interactive chromosome-spanning skyline plot
- let the user pick the base color for all genes and the highlight color for hits
- export the resulting figure as SVG at several publication-friendly canvas sizes

## Public entry points

- Public app: `https://genomic-hit-locator.isab.science`
- Website embed page: `https://isab.science/for_researchers/genomic-hit-locator`
- In-app guide: `/readme`

## Input model

### 1. All tested genes file

This is the main uploaded table. It should contain:

- one gene column
- one effect-size column

The app accepts several column-name variants.

Accepted gene-like column names currently include:

- `Gene_symbol`
- `Gene symbol`
- `GeneSymbol`
- `All_targeted_genes`
- `Gene`
- `Symbol`
- `gene`
- `Gene_TSS`

Accepted effect-size column names currently include:

- `log2ratio`
- `log2Ratio`
- `Log2Ratio`
- `log2_ratio`
- `Log2_Ratio`
- `Mean_log2FC`
- `Mean_log2`
- `Log2FC`
- `log2fc`
- `effect`
- `effect_size`
- `score`
- `mean`

### 2. Subset hits file

This second upload is optional. It only needs a gene column. The app uses the same gene-column alias detection as above.

### 3. Pasted genes

Instead of, or in addition to, a second file, genes can be pasted into the text box.

Currently supported separators:

- commas
- semicolons
- new lines

The pasted genes are merged with the genes from the optional subset file.

## Annotation reference

The app uses a local annotation workbook to map genes to chromosome and genomic start position.

Current default path:

`/home/aag/Neuropathology - Manuscripts/TrevisanWang2024/Data/ScreenResults/PrP_genes_and_NT_ordered_AguzziLab.xlsx`

This reference is expected to provide:

- a gene symbol column
- a chromosome column
- a start-position column

The app currently reports on the front page whether this reference loaded successfully and how many annotated genes are available.

## Plot behavior

### X-axis

The x-axis represents genomic position across chromosomes, concatenated from chromosome 1 through chromosome Y or M as available.

Each chromosome occupies its own contiguous block on the x-axis.

### Y-axis

Two modes are currently supported:

- `Linear / as supplied log2ratio`
- `Signed log2(|log2ratio| + 1)`

The first mode uses the uploaded effect-size values directly.

The second mode compresses large absolute values while preserving sign.

### Colors

Two color pickers are exposed:

- one for the background cloud of all tested genes
- one for the highlighted hit subset

### Hover details

Each point can show:

- gene
- chromosome
- genomic start position
- raw uploaded effect size
- plotted value

## Output summary

After a plot is generated, the app reports:

- total all-gene rows retained after gene/effect parsing
- total genes matched to the annotation reference
- number of uploaded genes missing from the annotation reference
- number of highlighted hits found in the plotted data
- number of selected genes that were not present in the tested set

This is important because unmatched genes are common when symbols differ between datasets or when entries use transcript-style naming instead of plain gene symbols.

## Current limitations

These are known limitations in the current version:

- annotation matching is symbol-based and does not yet use Entrez or Ensembl fallback matching
- duplicate genes in the all-genes file are currently reduced to the first retained row
- duplicate genes in the annotation reference are reduced to the first retained position
- SVG export is implemented; PNG and PDF export are not yet exposed in the UI
- the app currently assumes the local annotation file is already present on this machine

## Example file-shape notes

### Case A: straightforward gene-symbol input

Works well:

| Column | Meaning |
| --- | --- |
| `Gene_symbol` | gene label used for matching |
| `log2ratio` | uploaded effect size |

### Case B: TSS-oriented table

If the file contains both:

- `Gene_TSS`
- `All_targeted_genes`

the app currently prefers `All_targeted_genes` for chromosome matching, because transcript-style values like `PRNP_TSS1` usually do not exist in the chromosome reference as-is.

## Local run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8082
```

## Environment variables

The important environment variables currently are:

| Variable | Purpose |
| --- | --- |
| `GENOMIC_HIT_LOCATOR_TITLE` | page title |
| `GENOMIC_HIT_LOCATOR_SUBTITLE` | page subtitle |
| `GENOMIC_HIT_LOCATOR_PUBLIC_BASE_URL` | standalone public URL |
| `GENOMIC_HIT_LOCATOR_FRAME_ANCESTORS` | iframe allowlist |
| `GENOMIC_HIT_LOCATOR_ANNOTATION_PATH` | path to the local chromosome annotation workbook |

## Deployment notes

The deployed app runs from:

- repo directory: `/home/aag/genomic-hit-locator`
- local venv: `/home/aag/genomic-hit-locator/.venv`

User services:

- `genomic-hit-locator.service`
- `genomic-hit-locator-lan.service`

Useful commands:

```bash
systemctl --user restart genomic-hit-locator.service genomic-hit-locator-lan.service
systemctl --user status genomic-hit-locator.service --no-pager
journalctl --user -u genomic-hit-locator.service -n 100 --no-pager
```

## Roadmap

Planned refinements we are likely to add next:

- more robust gene matching using Entrez and other identifiers
- user control over which columns are interpreted as gene and effect size
- support for additional export formats
- optional label overlays for selected or strongest genes
- persistent session state or saved analyses
- clearer handling of duplicate genes and isoform-level rows

## Maintenance note

This README is intended to be updated alongside the app whenever we refine behavior, add inputs, change defaults, or expose new controls. It should remain the canonical user-facing explanation of how the tool currently works.
