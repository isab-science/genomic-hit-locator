# Genomic Hit Locator

Genomic Hit Locator is a small FastAPI web application for turning a screen-wide gene-level results table into an interactive genomic scatter plot. It places genes along a concatenated chromosome axis, plots an effect-size value on the y-axis, derives a primary hit set from thresholds, overlays an optional secondary hit list, and lets the user label genes and export the current figure as SVG.

The UI calls this an "Appenzeller plot". In practice, the app answers a simple question: given a genome-wide screening result table, where do the strongest positive and negative effects sit across the genome, and how do curated hit sets relate to that background?

The name is intentional. Like a Manhattan plot in GWAS, the figure reads as a skyline of peaks across the genome. But this version is bidirectional: strong positive and negative effects rise above and below zero, so the overall silhouette looks less like a city skyline and more like a reflected mountain range. The upper and lower peaks together resemble the Alpstein range near Appenzell mirrored on the surface of Lake Samtisersee, which is why the plot is referred to here as an "Appenzeller plot".

This README is also rendered by the app at `/readme`, so it is meant to be a precise, user-facing description of the current behavior.

## What The App Does

At a high level, the app:

1. loads a genome-wide table containing genes and effect sizes
2. optionally reads p-values from that same table
3. normalizes gene symbols and matches them against a local chromosome-position annotation reference
4. derives a primary hit set from the genome-wide table using user-selected thresholds
5. optionally loads a secondary hit set from a file or pasted gene list
6. plots annotated genes across chromosomes 1-22, X, Y, and M when present
7. colors each visible layer with a p-value-driven gradient when p-values are available
8. supports in-browser gene labeling and SVG export

The result is an interactive Plotly figure with hover details, chromosome striping, layered hit overlays, and summary counts for matched and unmatched genes.

## Main Screens And Routes

- `/`: main application page
- `/readme`: renders this README as HTML inside the app
- `/api/plot`: builds a plot from uploaded data and returns Plotly JSON plus a summary
- `/api/export/current.svg`: exports the current browser-side figure as SVG
- `/api/export/{plot_id}.svg`: exports a cached server-side figure as SVG
- `/healthz`: lightweight health endpoint

## User Workflow

The normal workflow is:

1. open the app
2. confirm the annotation banner says the chromosome annotation reference is ready
3. upload a genome-wide results file, or leave it empty to use the built-in sample if installed
4. choose the y-axis transform and whether to show the full genome-wide layer
5. choose how primary hits should be derived and set the thresholds
6. optionally upload a secondary hit file or paste genes directly
7. pick the color gradients and p-value saturation settings for each layer
8. click `Generate Appenzeller Plot`
9. optionally add manual labels, auto-label top positive and negative genes, and export SVG

## Input Model

The UI is organized into three cards:

- `Genome-wide results`
- `Primary hits`
- `Secondary hits`

Only the genome-wide file is essential for a real analysis. Primary hits are derived from that file. Secondary hits are optional.

## Genome-Wide Results

This is the main dataset. It provides the background layer and the source data used to derive primary hits.

### Required contents

The file must contain:

- one recognizable gene column
- one recognizable effect-size column

The file may also contain:

- one recognizable p-value column

If the app cannot find a usable gene column or effect-size column, plot generation fails with a `400` error. A p-value column is optional overall, but it becomes required for some primary-hit modes and for p-value-based coloring.

### Accepted file types

The parser accepts:

- `.xlsx`
- `.xls`
- `.csv`
- `.tsv`
- `.txt`

If the extension is not decisive, the backend tries to infer a delimiter from the file contents.

### Column-name detection

The backend detects the first matching alias case-insensitively.

Recognized gene aliases:

- `Gene_symbol`
- `Gene symbol`
- `GeneSymbol`
- `All_targeted_genes`
- `Gene`
- `Symbol`
- `gene`
- `Gene_TSS`

Recognized effect-size aliases:

- `log2ratio`
- `Log2Ratio`
- `log2Ratio`
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

Recognized p-value aliases:

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

### Normalization rules

Before plotting, the backend:

- trims whitespace from text values
- treats empty strings and `nan` as missing
- uppercases gene names for matching
- converts effect sizes to numeric values
- converts p-values to numeric values when present
- drops rows with missing genes or missing effect sizes
- keeps only the first row for duplicate genes after sorting by gene symbol

This means duplicate genes are not aggregated. The first retained row wins.

### Genome-wide options in the UI

The `Genome-wide results` card exposes these options:

- `Results file`: upload the main table
- `Y-axis transform`
- `Show on plot`
- `Genome-wide start color`
- `Genome-wide end color`
- `Saturation p-value`

#### `Y-axis transform`

Choices:

- `Linear / as supplied log2ratio`
- `Signed log2(|log2ratio| + 1)`

Behavior:

- `linear`: the plotted y-value is the raw uploaded effect size
- `log2`: the plotted y-value becomes `sign(effect) * log2(abs(effect) + 1)`

The transformed value affects the plot and label ranking, but hover text still shows the raw effect size too.

#### `Show on plot`

Choices:

- `Show`
- `Hide`

Behavior:

- `Show`: draws the full genome-wide point cloud
- `Hide`: suppresses the background layer but still uses the genome-wide file for primary-hit derivation and annotation matching

#### Genome-wide colors

The genome-wide layer uses a gradient from `Genome-wide start color` to `Genome-wide end color`. When p-values are available, weaker significance is shown closer to the start color and stronger significance moves toward the end color.

Defaults:

- start color: `#ffffff`
- end color: `#ff0000`
- saturation p-value: `1e-2`

## Primary Hits

Primary hits are not uploaded as a separate file in the current implementation. They are derived directly from the genome-wide table.

### Primary-hit options in the UI

- `Selection method`
- `Minimum |effect size|`
- `Maximum p-value`
- `Primary-hit start color`
- `Primary-hit end color`
- `Saturation p-value`

### `Selection method`

Choices:

- `Largest |effect| (balanced +/-)` -> backend value `effect_only`
- `Smallest p-value` -> backend value `pvalue_only`
- `Strongest combo |effect| * -log10(p)` -> backend value `combo`

Actual current behavior in code:

- `effect_only`: selects every gene with `abs(effect_raw) >= primary_effect_threshold`
- `pvalue_only`: selects every gene with a detected p-value and `pvalue <= primary_pvalue_threshold`
- `combo`: selects every gene that passes both the effect threshold and the p-value threshold

Important note: the UI labels imply ranking-based selection, but the current backend implementation is threshold-based filtering. There is no balancing of positive versus negative hits and no explicit ranking by a combined score yet.

### Threshold interpretation

`Minimum |effect size|`:

- converted to a float
- absolute value is used internally
- default in the form: `0.2`
- backend default when called without the form value: `1.0`

`Maximum p-value`:

- converted to a float
- default: `0.05`

### P-value requirements for primary-hit modes

- `effect_only` works without a p-value column
- `pvalue_only` fails if the genome-wide file has no detected p-value column
- `combo` fails if the genome-wide file has no detected p-value column

### Primary-hit plot styling

Primary hits are drawn as larger points on top of the background layer.

Current styling:

- marker size: `9`
- opacity: `0.96`
- white outline
- trace name: `Primary hits`

Defaults:

- start color: `#ffffff`
- end color: `#5a00ff`
- saturation p-value: `1e-7`

## Secondary Hits

Secondary hits are optional and can be supplied in one of three ways.

Priority order:

1. uploaded secondary-hit file
2. pasted gene list from the text box
3. built-in default secondary sample file, if installed

If a file is uploaded, the text box is ignored. If no file is uploaded and the text box has content, the pasted genes are used. If both are empty and the default secondary sample exists, the default sample is used.

### Secondary-hit options in the UI

- `Secondary hitlist file`
- `Or enter genes directly (comma separated)`
- `Secondary-hit start color`
- `Secondary-hit end color`
- `Saturation p-value`

### Secondary-hit file requirements

The secondary file only needs a recognizable gene column. The same gene aliases used for the genome-wide file are used here.

### Secondary text input parsing

The pasted gene parser:

- trims whitespace
- uppercases genes
- accepts commas
- converts semicolons to commas before splitting
- removes empty tokens
- de-duplicates repeated genes

The textarea hint says comma-separated, but the parser is more forgiving than that.

### Secondary-hit plot styling

Current styling:

- marker symbol: `diamond`
- marker size: `10`
- opacity: `1.0`
- dark green outline
- trace name: `Secondary hits`

Defaults:

- start color: `#ffffff`
- end color: `#000000`
- saturation p-value: `1e-7`

## Annotation Reference

The plot uses a local annotation table to place genes along chromosomes.

The backend looks for the annotation file in this order:

1. `GENOMIC_HIT_LOCATOR_ANNOTATION_PATH`
2. `/home/aag/Neuropathology - Manuscripts/TrevisanWang2024/Data/ScreenResults/PrP_genes_and_NT_ordered_AguzziLab.xlsx`

### Accepted annotation sources

The annotation loader accepts:

- Excel workbooks
- CSV
- TSV
- plain text tables that pandas can parse as delimited text

For Excel files, it scans sheets until it finds one with a compatible gene, chromosome, and position column set.

### Recognized annotation columns

Gene aliases:

- same list as the main gene aliases

Chromosome aliases:

- `Chromosome`
- `chromosome`
- `Chrom`
- `Chr`
- `chrom`

Position aliases:

- `Start_Position`
- `Start position`
- `StartPosition`
- `Start`
- `pos`
- `Position`

### Annotation normalization rules

The reference loader:

- uppercases gene symbols
- normalizes chromosome labels by stripping `CHR`
- maps `MT` to `M`
- accepts chromosomes `1-22`, `X`, `Y`, and `M`
- converts positions to numeric values
- drops rows with missing chromosome or position
- keeps the first position for duplicate genes after sorting by gene and position

If no genes from the genome-wide table match the annotation table, plot generation fails.

## Sample Data Fallbacks

The app can run without uploads when local sample files are installed.

Default sample paths:

- genome-wide sample: `/home/aag/genomic-hit-locator/sample-data/Primary_screen_filtered_results.xlsx`
- secondary sample: `/home/aag/genomic-hit-locator/sample-data/Secondary screen.xlsx`

These can be overridden with environment variables:

- `GENOMIC_HIT_LOCATOR_DEFAULT_ALL_GENES`
- `GENOMIC_HIT_LOCATOR_DEFAULT_SECONDARY`

Behavior:

- if no genome-wide file is uploaded and the default all-genes sample exists, that file is used
- if no genome-wide file is uploaded and the default sample does not exist, plot generation fails
- if no secondary file is uploaded and no genes are pasted and the default secondary sample exists, that file is used
- if no secondary source is available, the plot simply has no secondary-hit overlay

The landing page reports whether the default sample files are installed.

## Plot Construction

### X-axis

The x-axis is a concatenated genome axis built from annotated genes.

Behavior:

- chromosomes are sorted as `1` through `22`, then `X`, `Y`, `M`
- each chromosome spans from its minimum to maximum observed annotated position
- chromosomes are separated by a fixed gap of `10,000,000`
- the x-axis tick for each chromosome is placed at the midpoint of its span

Alternate chromosome background shading is added behind every other chromosome block.

### Y-axis

The y-axis shows either:

- raw effect size
- signed log2-compressed effect size

The y-axis title changes accordingly:

- `log2ratio`
- `Signed log2(|log2ratio| + 1)`

### Layers

Up to three layers may be visible:

- `Genome-wide results`
- `Primary hits`
- `Secondary hits`

The genome-wide layer may be hidden through the form, but the highlighted layers can still appear.

### Hover details

Each plotted point includes:

- gene
- chromosome
- genomic position
- raw effect size
- p-value
- plotted value

Primary and secondary traces prefix the hover title with `Primary hit` or `Secondary hit`.

## P-Value Coloring

When a layer has at least one valid p-value greater than zero, that layer is colored with a significance gradient.

### How significance intensity is computed

The backend:

- clips p-values into the range `1e-300` to `1.0`
- converts them to `-log10(p)`
- normalizes those scores between a reference minimum and maximum
- maps the normalized values onto a custom RGB colorscale between the chosen start and end colors

### Saturation p-value

Each layer has its own `Saturation p-value` selector. This sets the p-value that should be treated as fully saturated color when possible.

Choices in the UI:

- `1e-12`
- `1e-11`
- `1e-10`
- `1e-9`
- `1e-8`
- `1e-7`
- `1e-6`
- `1e-5`
- `1e-4`
- `1e-3`
- `1e-2`

If the chosen saturation p-value is less extreme than the most significant observed p-value, the plot can still extend its internal score range to cover the observed data. In other words, the chosen value guides the color scale, but the code does not force a hard truncation of the score range.

### Colorbars

When p-values exist for a layer, the app also adds a separate colorbar for that layer:

- `Genome-wide p`
- `Primary p`
- `Secondary p`

Colorbars are drawn as helper traces on the right side of the figure. If a layer has no usable p-values at all, that layer falls back to a flat marker color and no colorbar is shown for it.

## Labels

After a plot is generated, the browser exposes labeling controls without requiring a re-run of the backend.

Available controls:

- `Label genes (comma separated)`
- `Label layer`
- `Top +/- strongest`
- `Apply labels`
- `Clear labels`

### `Label genes`

Manual labels are parsed in the browser. The parser accepts:

- whitespace
- commas
- semicolons

Matching is case-insensitive because the browser uppercases tokens before lookup.

If a gene appears multiple times across eligible traces, the browser labels the point with the largest absolute plotted y-value.

### `Label layer`

Choices:

- `Primary + secondary`
- `Primary hits only`
- `Secondary hits only`

This affects which traces are searched when manual labels or top-hit labels are applied.

### `Top +/- strongest`

Choices:

- `Off`
- `10`
- `20`
- `40`
- `60`

The browser separately takes the top positive and top negative plotted values per gene from the selected highlight layers and adds labels for those genes.

Important details:

- ranking uses the plotted y-value, not the raw effect size column directly
- genome-wide background points are not label candidates
- labels are stored as a dedicated Plotly text trace named `Selected labels`

### `Apply labels` and `Clear labels`

- `Apply labels`: recalculates the label set from the current inputs
- `Clear labels`: empties the label trace without rebuilding the figure

## Summary Panel

After generating a plot, the browser displays summary cards derived from the backend response.

Current summary fields:

- `Genome-wide genes`: total rows retained after parsing gene/effect pairs
- `Annotated genes`: genes that matched the annotation reference and were plotted
- `Unannotated genes`: genes from the parsed genome-wide table that could not be placed on the chromosome map
- `Primary hits`: primary-hit genes that were both selected and annotated
- `Secondary hits`: secondary-hit genes that were present in the annotated plotted dataset

If secondary genes were requested but not found in the tested set, an additional warning card is shown with:

- count of missing secondary-hit genes
- a preview of up to 20 missing genes

## Export

The UI exposes one export format today: SVG.

Available presets:

- `Compact 1200 × 700`
- `Standard 1600 × 900`
- `Medium 1800 × 1200`
- `Wide 2200 × 1200`
- `Figure panel 3000 × 1600`

When the user clicks `Export SVG`, the browser sends the current in-memory Plotly figure to `/api/export/current.svg`. This matters because any client-side label edits are included in the exported file.

### Export limits

`GET /api/export/{plot_id}.svg` clamps export dimensions:

- width: minimum `600`, maximum `6000`
- height: minimum `400`, maximum `4000`
- scale: minimum `1`, maximum `4`

The browser-side export currently uses `POST /api/export/current.svg` and requests `scale = 1`. That endpoint accepts the submitted width, height, and scale directly.

## API Details

### `POST /api/plot`

Consumes multipart form data.

Supported fields:

- `all_genes_file`
- `secondary_hits_file`
- `secondary_hits_text`
- `scale_mode`
- `genomewide_start_color`
- `genomewide_end_color`
- `genomewide_saturation_pvalue`
- `primary_start_color`
- `primary_end_color`
- `primary_saturation_pvalue`
- `secondary_start_color`
- `secondary_end_color`
- `secondary_saturation_pvalue`
- `show_genomewide`
- `primary_mode`
- `primary_effect_threshold`
- `primary_pvalue_threshold`

Successful response includes:

- `plot_id`
- `figure`: Plotly JSON payload
- `summary`

The summary currently contains:

- `all_genes_total`
- `annotated_genes_total`
- `missing_annotation_total`
- `primary_hits_total`
- `secondary_hits_total`
- `missing_secondary_total`
- `missing_secondary_preview`
- `annotation_source`
- `scale_mode`
- `y_axis_label`
- `primary_mode`
- `primary_effect_threshold`
- `primary_pvalue_threshold`
- `show_genomewide`
- `pvalue_scale`
- `data_source`

`data_source` contains:

- `all_genes`
- `secondary_hits`
- `using_default_all_genes`
- `using_default_secondary`

### `GET /api/export/{plot_id}.svg`

Exports a cached plot by `plot_id`.

Query parameters:

- `width`
- `height`
- `scale`

The server keeps a small in-memory plot cache with a limit of `24` entries. If a plot is evicted or the ID is unknown, export fails with `404`.

### `POST /api/export/current.svg`

Consumes JSON with:

- `figure`
- `width`
- `height`
- `scale`
- `filename`

Returns the generated SVG with a `Content-Disposition` attachment filename.

### `GET /healthz`

Returns JSON similar to:

```json
{
  "ok": true,
  "app": "genomic-hit-locator",
  "annotation_ready": true,
  "annotation_source": "/path/to/reference.xlsx [Sheet1]"
}
```

## Error Conditions And Edge Cases

Common failure modes:

- missing genome-wide file when no default sample is installed
- unrecognized gene or effect-size column in the main dataset
- unrecognized gene column in the secondary-hit upload
- `pvalue_only` primary mode without a detectable p-value column
- `combo` primary mode without a detectable p-value column
- zero overlap between the genome-wide dataset and the annotation reference
- unreadable uploaded table
- unreadable or missing annotation reference

Notable edge-case behavior:

- duplicate genes are reduced to the first retained row
- annotation matching is gene-symbol-only
- transcript-like names only match if the normalized symbol exists in the annotation reference
- p-values that are missing, non-numeric, zero, or invalid are ignored for significance coloring; a layer falls back to flat color only if no usable p-values remain
- manual secondary genes that are absent from the tested set are reported but not plotted

## Environment Variables

The app currently reads these variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `GENOMIC_HIT_LOCATOR_TITLE` | HTML/app title | `Genomic Hit Locator` |
| `GENOMIC_HIT_LOCATOR_SUBTITLE` | subtitle shown on the landing page | `Interactive genomic localization for screen-wide effect sizes and focused hit overlays.` |
| `GENOMIC_HIT_LOCATOR_PUBLIC_BASE_URL` | URL used by the "Open standalone app" button | `https://genomic-hit-locator.isab.science` |
| `GENOMIC_HIT_LOCATOR_FRAME_ANCESTORS` | CSP `frame-ancestors` policy value | `'self' https://isab.science https://www.isab.science` |
| `GENOMIC_HIT_LOCATOR_ANNOTATION_PATH` | preferred annotation file path | empty, then falls back to the hard-coded manuscript path |
| `GENOMIC_HIT_LOCATOR_DEFAULT_ALL_GENES` | override path for the default genome-wide sample | `/home/aag/genomic-hit-locator/sample-data/Primary_screen_filtered_results.xlsx` |
| `GENOMIC_HIT_LOCATOR_DEFAULT_SECONDARY` | override path for the default secondary sample | `/home/aag/genomic-hit-locator/sample-data/Secondary screen.xlsx` |

## Local Development

### Requirements

- Python 3
- the packages from `requirements.txt`
- a working local annotation reference
- `kaleido` available for SVG export

### Install and run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8082
```

Then open `http://127.0.0.1:8082/`.

## Deployment Notes

This repository includes user-service and LAN deployment examples.

Relevant files:

- `deploy/genomic-hit-locator.service`
- `deploy/genomic-hit-locator-lan.service`
- `deploy/genomic-hit-locator.lan.nginx.conf`
- `deploy/genomic-hit-locator.env.example`

### Example service behavior

`genomic-hit-locator.service`:

- runs from `/home/aag/genomic-hit-locator`
- loads env vars from `deploy/genomic-hit-locator.env`
- starts Uvicorn on `127.0.1.1:8082`

`genomic-hit-locator-lan.service`:

- runs the same app
- binds to `10.10.20.10:8082`

The included nginx config proxies `genomic-hit-locator.lan` to that LAN listener.

### Useful commands

```bash
systemctl --user restart genomic-hit-locator.service genomic-hit-locator-lan.service
systemctl --user status genomic-hit-locator.service --no-pager
journalctl --user -u genomic-hit-locator.service -n 100 --no-pager
```

## Current Limitations

- primary hits are derived only from the genome-wide table; there is no separate primary-hit upload
- the backend selection logic is threshold-based even though some UI wording still sounds ranking-based
- duplicate genes are reduced to the first retained row rather than being combined
- annotation matching does not use Ensembl, Entrez, transcript collapsing, or synonym fallback logic
- the plot depends on a local annotation file being available on the host
- export in the UI is SVG-only
- the plot cache is in-memory and non-persistent
- colorbars can crowd the right margin when multiple p-value-enabled layers are shown

## Quick Reference

If you only need the short version:

- upload a genome-wide table with gene and effect columns
- optionally include p-values for significance coloring and p-value-based primary-hit modes
- set thresholds to derive primary hits
- optionally upload or paste secondary genes
- generate the plot
- inspect hover details and summary counts
- add labels if needed
- export SVG for figures or slides

## Maintenance Note

Because `/readme` renders this file directly, changes to UI controls, API fields, defaults, parser behavior, or deployment assumptions should be reflected here at the same time as the code change.
