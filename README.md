# Genomic Hit Locator

This document is the living guide for the Genomic Hit Locator app. We will keep updating it as the app evolves so the public tool, the local deployment, and the repository documentation stay aligned.

## What the app does

The Genomic Hit Locator is a standalone Python web app for plotting genome-wide gene effects across the human genome and then visually highlighting primary and secondary hit sets.

At the moment it can:

- accept one genome-wide results file containing the full tested gene set
- derive primary hits directly from that file using effect size, p-value, or a combined rule
- optionally accept a second uploaded file for secondary hits
- fall back to built-in sample files if users leave both upload pickers empty
- merge all plotted genes against a local human annotation table with chromosome and genomic start-position data
- draw an interactive Appenzeller plot across concatenated chromosomes
- color all three plotted layers by p-value intensity
- show per-layer p-value scale bars alongside the plot
- label manually entered genes and optionally auto-label the strongest positive and negative hits
- export the resulting figure as SVG at several publication-friendly canvas sizes

## Public entry points

- Public app: `https://genomic-hit-locator.isab.science`
- Website embed page: `https://isab.science/for_researchers/genomic-hit-locator`
- In-app guide: `/readme`

## Input model

The UI is currently organized into three rounded input sections:

- `Genome-wide results`
- `Primary hits`
- `Secondary hits`

### 1. Genome-wide results file

This is the main uploaded table. It should contain:

- one gene column
- one effect-size column
- optionally one p-value column

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

Accepted p-value column names currently include:

- `pvalue`
- `pValue`
- `PValue`
- `p_value`
- `P_Value`
- `p-value`
- `P-value`
- `p`
- `p_value_log2`
- `P_value_log2`
- `p_value_raw`
- `p_value_act`
- `p_value_deltaNT`
- `p_value_repro_log2`

The genome-wide section also exposes:

- a radio toggle to show or hide the genome-wide layer
- a y-axis transform selector
- a color picker used as the anchor hue for genome-wide p-value shading

### 2. Primary hits

Primary hits are currently not uploaded separately. They are derived from the genome-wide results file using one of three methods:

- `Largest |effect| (balanced +/-)`
- `Smallest p-value`
- `Strongest combo |effect| * -log10(p)`

The primary-hit section currently lets the user set:

- minimum absolute effect size
- maximum p-value
- primary-hit color

The primary-hit color is the anchor hue for p-value shading within the primary layer.

### 3. Secondary hits file

This upload is optional. It only needs a gene column. The app uses the same gene-column alias detection as above.

The secondary-hit color is the anchor hue for p-value shading within the secondary layer.

## Built-in sample datasets

If users do not want to upload files, the app can fall back to built-in sample spreadsheets stored on this machine.

Current default sample paths:

- `/home/aag/genomic-hit-locator/sample-data/Primary_screen_filtered_results.xlsx`
- `/home/aag/genomic-hit-locator/sample-data/Secondary screen.xlsx`

If these files are present:

- the genome-wide picker becomes optional
- the secondary-hit picker becomes optional
- the app will automatically use the sample files when the pickers are left empty

The front page reports whether these default sample files are installed.

## Annotation reference

The app uses a local annotation workbook to map genes to chromosome and genomic start position.

Current default path:

`/home/aag/Neuropathology - Manuscripts/TrevisanWang2024/Data/ScreenResults/PrP_genes_and_NT_ordered_AguzziLab.xlsx`

This reference is expected to provide:

- a gene symbol column
- a chromosome column
- a start-position column

The app reports on the front page whether this reference loaded successfully and how many annotated genes are available.

## Plot behavior

### Plot name

The main figure is currently labeled:

- `Genomic Hit Locator (Appenzeller plot)`
- `Appenzeller plot (bidirectional effect size vs genomic location)`

### X-axis

The x-axis represents genomic position across chromosomes, concatenated from chromosome 1 through chromosome Y or M as available.

Each chromosome occupies its own contiguous block on the x-axis.

### Y-axis

Two modes are currently supported:

- `Linear / as supplied log2ratio`
- `Signed log2(|log2ratio| + 1)`

The first mode uses the uploaded effect-size values directly.

The second mode compresses large absolute values while preserving sign.

### Plot layers

The plot can currently contain up to three visible data layers:

- `Genome-wide results`
- `Primary hits`
- `Secondary hits`

Shapes are currently used to distinguish the two highlighted layers:

- primary hits are circles
- secondary hits are diamonds

### P-value coloring

All three data layers are currently colored by p-value intensity.

Current intent:

- weaker significance should begin at a mid-strength tint rather than near-white
- stronger significance should move toward the chosen layer color
- all three layers should use the same genome-wide p-value reference scale so color intensity remains comparable across layers

Each layer also has its own colorbar on the right side of the plot:

- `Genome-wide p`
- `Primary p`
- `Secondary p`

### Hover details

Each point currently shows:

- gene
- chromosome
- genomic start position
- raw uploaded effect size
- p-value
- plotted value

## Label controls

The plot controls above the figure currently support:

- manual gene labels
- choosing whether labels apply to primary hits, secondary hits, or both
- auto-labeling the top positive and top negative strongest genes
- clearing labels without rebuilding the figure

Manual labels currently accept:

- commas
- semicolons
- whitespace

## Output summary

After a plot is generated, the app reports:

- total genome-wide rows retained after gene/effect parsing
- total genes matched to the annotation reference
- number of genes missing from the annotation reference
- number of primary hits found in the plotted data
- number of secondary hits found in the plotted data
- number of secondary-hit genes that were not present in the tested set

This is important because unmatched genes are common when symbols differ between datasets or when entries use transcript-style naming instead of plain gene symbols.

The API summary also records whether the app used uploaded files or the built-in sample defaults.

## Export

The current export control supports SVG output at several presets, including compact, standard, medium, wide, and large figure-panel sizes.

## Current limitations

These are known limitations in the current version:

- annotation matching is symbol-based and does not yet use Entrez or Ensembl fallback matching
- duplicate genes in the genome-wide file are currently reduced to the first retained row
- duplicate genes in the annotation reference are reduced to the first retained position
- the app currently assumes the local annotation file is already present on this machine
- the current p-value color rendering is still being tuned, and visual intensity should be treated as provisional until we complete that refinement
- SVG export is implemented; PNG and PDF export are not yet exposed in the UI
- the right-side colorbar stack can become crowded on smaller screens
- primary hits are currently derived from thresholds and do not yet support a separate uploaded primary-hit file

## Example file-shape notes

### Case A: straightforward gene-symbol input

Works well:

| Column | Meaning |
| --- | --- |
| `Gene_symbol` | gene label used for matching |
| `log2ratio` | uploaded effect size |
| `pValue` | uploaded p-value |

### Case B: TSS-oriented table

If the file contains both:

- `Gene_TSS`
- `All_targeted_genes`

the app currently prefers `All_targeted_genes` for chromosome matching, because transcript-style values like `PRNP_TSS1` usually do not exist in the chromosome reference as-is.

### Case C: log2-specific p-value columns

Files with columns like:

- `log2Ratio`
- `pValue`

or

- `Mean_log2`
- `p_value_log2`

are both expected to work in the current parser.

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
| `GENOMIC_HIT_LOCATOR_DEFAULT_ALL_GENES` | optional override for the built-in genome-wide sample file |
| `GENOMIC_HIT_LOCATOR_DEFAULT_SECONDARY` | optional override for the built-in secondary-hit sample file |

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
- user control over which column is used as the p-value source when multiple candidates are present
- support for additional export formats
- further cleanup of p-value coloring and scale presentation
- persistent session state or saved analyses
- clearer handling of duplicate genes and isoform-level rows

## Maintenance note

This README is intended to be updated alongside the app whenever we refine behavior, add inputs, change defaults, or expose new controls. It should remain the canonical user-facing explanation of how the tool currently works.
