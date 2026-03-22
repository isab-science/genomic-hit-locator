from __future__ import annotations

import io
import json
import math
import os
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import markdown
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


APP_ROOT = Path(__file__).resolve().parent
APP_TITLE = os.getenv("GENOMIC_HIT_LOCATOR_TITLE", "Genomic Hit Locator").strip() or "Genomic Hit Locator"
APP_SUBTITLE = (
    os.getenv(
        "GENOMIC_HIT_LOCATOR_SUBTITLE",
        "Interactive genomic localization for screen-wide effect sizes and focused hit overlays.",
    ).strip()
    or "Interactive genomic localization for screen-wide effect sizes and focused hit overlays."
)
PUBLIC_BASE_URL = os.getenv("GENOMIC_HIT_LOCATOR_PUBLIC_BASE_URL", "https://genomic-hit-locator.isab.science").strip()

GENE_ALIASES = (
    "Gene_symbol",
    "Gene symbol",
    "GeneSymbol",
    "All_targeted_genes",
    "Gene",
    "Symbol",
    "gene",
    "Gene_TSS",
)
EFFECT_ALIASES = (
    "log2ratio",
    "Log2Ratio",
    "log2Ratio",
    "log2_ratio",
    "Log2_Ratio",
    "Mean_log2FC",
    "Mean_log2",
    "Log2FC",
    "log2fc",
    "effect",
    "effect_size",
    "score",
    "mean",
)
CHROM_ALIASES = ("Chromosome", "chromosome", "Chrom", "Chr", "chrom")
POSITION_ALIASES = ("Start_Position", "Start position", "StartPosition", "Start", "pos", "Position")

ANNOTATION_CANDIDATES = [
    os.getenv("GENOMIC_HIT_LOCATOR_ANNOTATION_PATH", "").strip(),
    "/home/aag/Neuropathology - Manuscripts/TrevisanWang2024/Data/ScreenResults/PrP_genes_and_NT_ordered_AguzziLab.xlsx",
]
PLOT_CACHE_LIMIT = 24


def normalize_frame_ancestors(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return "'self' https://isab.science https://www.isab.science"
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    if "selfhttps://" in value:
        return value.replace("selfhttps://", "'self' https://", 1)
    if value.startswith("self "):
        return "'self'" + value[4:]
    if value == "self":
        return "'self'"
    return value


FRAME_ANCESTORS = normalize_frame_ancestors(
    os.getenv(
        "GENOMIC_HIT_LOCATOR_FRAME_ANCESTORS",
        "'self' https://isab.science https://www.isab.science",
    )
)

app = FastAPI(title=APP_TITLE)
templates = Jinja2Templates(directory=str(APP_ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(APP_ROOT / "static")), name="static")
PLOT_CACHE: dict[str, dict[str, Any]] = {}
README_PATH = APP_ROOT / "README.md"


@app.middleware("http")
async def add_frame_policy(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = f"frame-ancestors {FRAME_ANCESTORS};"
    return response


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return text


def _normalize_gene(value: object) -> str:
    return _normalize_text(value).upper()


def _normalize_chromosome_label(chrom: object) -> str | None:
    raw = _normalize_text(chrom)
    if not raw:
        return None
    token = raw.upper().replace("CHR", "")
    if token == "MT":
        token = "M"
    canonical = {str(i) for i in range(1, 23)} | {"X", "Y", "M"}
    return token if token in canonical else None


def _chromosome_sort_key(chrom: str) -> tuple[int, str]:
    token = chrom.upper().replace("CHR", "")
    if token.isdigit():
        return (0, f"{int(token):02d}")
    ordering = {"X": "23", "Y": "24", "M": "25"}
    return (1, ordering.get(token, token))


def _make_lookup(columns: list[object]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for column in columns:
        text = str(column).strip()
        key = text.lower()
        if key and key not in lookup:
            lookup[key] = text
    return lookup


def _resolve_column(columns: list[object], aliases: tuple[str, ...], label: str) -> str:
    lookup = _make_lookup(columns)
    for alias in aliases:
        match = lookup.get(alias.strip().lower())
        if match:
            return match
    preview = ", ".join(str(col) for col in columns[:12])
    raise HTTPException(
        status_code=400,
        detail=f"Could not find a {label} column. Available columns include: {preview}",
    )


def _read_tabular_upload(content: bytes, filename: str | None) -> pd.DataFrame:
    lower_name = (filename or "").lower()
    try:
        if lower_name.endswith((".xlsx", ".xls")):
            return pd.read_excel(io.BytesIO(content))
        sample = content[:4096].decode("utf-8", errors="replace")
        if "\t" in sample and sample.count("\t") >= sample.count(","):
            return pd.read_csv(io.BytesIO(content), sep="\t")
        return pd.read_csv(io.BytesIO(content), sep=None, engine="python")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=f"Could not read '{filename or 'uploaded file'}' as CSV/TSV/XLSX: {exc}",
        ) from exc


def _read_annotation_workbook(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        raise FileNotFoundError(f"Annotation file not found: {path}")
    if path.suffix.lower() in {".csv", ".tsv", ".txt"}:
        if path.suffix.lower() == ".tsv":
            data = pd.read_csv(path, sep="\t")
        else:
            data = pd.read_csv(path, sep=None, engine="python")
        return data, path.name

    workbook = pd.ExcelFile(path)
    for sheet_name in workbook.sheet_names:
        header = pd.read_excel(path, sheet_name=sheet_name, nrows=0)
        columns = list(header.columns)
        try:
            _resolve_column(columns, GENE_ALIASES, "gene")
            _resolve_column(columns, CHROM_ALIASES, "chromosome")
            _resolve_column(columns, POSITION_ALIASES, "genomic position")
        except HTTPException:
            continue
        return pd.read_excel(path, sheet_name=sheet_name), sheet_name
    raise FileNotFoundError(
        f"No compatible annotation sheet found in {path}. Expected gene, chromosome, and start-position columns."
    )


@lru_cache(maxsize=1)
def load_annotation_reference() -> tuple[pd.DataFrame, str]:
    last_error = "No annotation file candidates were checked."
    for candidate in ANNOTATION_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        try:
            raw, source_label = _read_annotation_workbook(path)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            continue

        gene_col = _resolve_column(list(raw.columns), GENE_ALIASES, "gene")
        chrom_col = _resolve_column(list(raw.columns), CHROM_ALIASES, "chromosome")
        pos_col = _resolve_column(list(raw.columns), POSITION_ALIASES, "genomic position")

        ref = raw.rename(
            columns={
                gene_col: "gene",
                chrom_col: "chromosome",
                pos_col: "position",
            }
        )[["gene", "chromosome", "position"]].copy()
        ref["gene"] = ref["gene"].map(_normalize_gene)
        ref["chromosome"] = ref["chromosome"].map(_normalize_chromosome_label)
        ref["position"] = pd.to_numeric(ref["position"], errors="coerce")
        ref = ref.dropna(subset=["chromosome", "position"]).copy()
        ref = ref[ref["gene"] != ""].copy()
        ref = ref.sort_values(["gene", "position"]).drop_duplicates("gene", keep="first").reset_index(drop=True)
        if ref.empty:
            last_error = f"Annotation candidate {path} loaded, but no usable annotated genes were found."
            continue
        return ref, f"{path} [{source_label}]"

    raise RuntimeError(f"Could not load a genomic annotation reference file. Last error: {last_error}")


def _prepare_all_gene_table(raw: pd.DataFrame, scale_mode: str) -> pd.DataFrame:
    gene_col = _resolve_column(list(raw.columns), GENE_ALIASES, "gene")
    effect_col = _resolve_column(list(raw.columns), EFFECT_ALIASES, "effect size (for example log2ratio)")

    data = raw.rename(columns={gene_col: "gene", effect_col: "effect_raw"}).copy()
    data["gene"] = data["gene"].map(_normalize_gene)
    data["effect_raw"] = pd.to_numeric(data["effect_raw"], errors="coerce")
    data = data[(data["gene"] != "") & data["effect_raw"].notna()].copy()
    data = data.sort_values(["gene"]).drop_duplicates("gene", keep="first").reset_index(drop=True)
    if data.empty:
        raise HTTPException(status_code=400, detail="The all-genes file did not contain any usable gene/effect pairs.")

    if scale_mode == "log2":
        data["effect_plot"] = data["effect_raw"].map(lambda value: math.copysign(math.log2(abs(value) + 1.0), value))
        data["y_axis_label"] = "Signed log2(|log2ratio| + 1)"
    else:
        data["effect_plot"] = data["effect_raw"]
        data["y_axis_label"] = "log2ratio"
    return data


def _parse_subset_genes(raw: pd.DataFrame | None, text_input: str | None) -> tuple[set[str], list[str]]:
    selected: set[str] = set()
    source_labels: list[str] = []

    if raw is not None and not raw.empty:
        gene_col = _resolve_column(list(raw.columns), GENE_ALIASES, "subset gene")
        subset_series = raw[gene_col].map(_normalize_gene)
        subset_genes = {gene for gene in subset_series.tolist() if gene}
        if subset_genes:
            selected.update(subset_genes)
            source_labels.append("subset file")

    if text_input:
        manual = {
            _normalize_gene(token)
            for token in text_input.replace("\n", ",").replace(";", ",").split(",")
            if _normalize_gene(token)
        }
        if manual:
            selected.update(manual)
            source_labels.append("typed list")

    return selected, source_labels


def _build_genome_axis(data: pd.DataFrame) -> tuple[pd.DataFrame, list[float], list[str], list[dict[str, Any]]]:
    chrom_order = sorted(data["chromosome"].astype(str).unique(), key=_chromosome_sort_key)
    offsets: dict[str, float] = {}
    tick_vals: list[float] = []
    tick_labels: list[str] = []
    chromosome_bounds: list[dict[str, Any]] = []
    accumulator = 0.0
    gap = 10_000_000.0

    for chrom in chrom_order:
        subset = data[data["chromosome"].astype(str) == chrom]
        min_pos = float(subset["position"].min())
        max_pos = float(subset["position"].max())
        chrom_span = max(1.0, max_pos - min_pos)
        offsets[chrom] = accumulator - min_pos
        tick_vals.append(accumulator + chrom_span / 2.0)
        tick_labels.append(chrom)
        chromosome_bounds.append(
            {
                "chromosome": chrom,
                "start_x": accumulator,
                "end_x": accumulator + chrom_span,
            }
        )
        accumulator += chrom_span + gap

    plotted = data.copy()
    plotted["genome_x"] = plotted.apply(
        lambda row: float(row["position"]) + offsets[str(row["chromosome"])],
        axis=1,
    )
    return plotted, tick_vals, tick_labels, chromosome_bounds


def _hex_with_alpha(color: str, fallback: str) -> str:
    value = _normalize_text(color) or fallback
    return value if value.startswith("#") and len(value) in {4, 7} else fallback


def _build_plot(
    data: pd.DataFrame,
    selected_genes: set[str],
    all_color: str,
    hit_color: str,
) -> go.Figure:
    plot_df, tick_vals, tick_labels, chromosome_bounds = _build_genome_axis(data)
    background_color = _hex_with_alpha(all_color, "#d9dde3")
    accent_color = _hex_with_alpha(hit_color, "#d93f6a")

    hit_df = plot_df[plot_df["gene"].isin(selected_genes)].copy()
    fig = go.Figure()

    for index, bounds in enumerate(chromosome_bounds):
        if index % 2 == 0:
            fig.add_vrect(
                x0=bounds["start_x"],
                x1=bounds["end_x"],
                fillcolor="rgba(15, 23, 42, 0.03)",
                opacity=1,
                line_width=0,
                layer="below",
            )

    fig.add_trace(
        go.Scattergl(
            x=plot_df["genome_x"],
            y=plot_df["effect_plot"],
            mode="markers",
            name="All tested genes",
            marker={"color": background_color, "size": 6, "opacity": 0.35},
            customdata=plot_df[["gene", "chromosome", "position", "effect_raw"]].values,
            hovertemplate=(
                "Gene: %{customdata[0]}<br>"
                "Chr %{customdata[1]}:%{customdata[2]:,.0f}<br>"
                "Raw effect: %{customdata[3]:.4f}<br>"
                "Plotted value: %{y:.4f}<extra></extra>"
            ),
        )
    )

    if not hit_df.empty:
        fig.add_trace(
            go.Scattergl(
                x=hit_df["genome_x"],
                y=hit_df["effect_plot"],
                mode="markers",
                name="Highlighted hits",
                marker={
                    "color": accent_color,
                    "size": 9,
                    "opacity": 0.95,
                    "line": {"color": "#ffffff", "width": 1},
                },
                text=hit_df["gene"],
                customdata=hit_df[["gene", "chromosome", "position", "effect_raw"]].values,
                hovertemplate=(
                    "Hit: %{customdata[0]}<br>"
                    "Chr %{customdata[1]}:%{customdata[2]:,.0f}<br>"
                    "Raw effect: %{customdata[3]:.4f}<br>"
                    "Plotted value: %{y:.4f}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        template="plotly_white",
        height=760,
        margin={"l": 72, "r": 26, "t": 44, "b": 90},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend={"orientation": "h", "x": 0.01, "y": 1.08},
        xaxis={
            "title": "Chromosomal location",
            "tickmode": "array",
            "tickvals": tick_vals,
            "ticktext": tick_labels,
            "showgrid": False,
            "zeroline": False,
        },
        yaxis={
            "title": str(plot_df["y_axis_label"].iloc[0]),
            "gridcolor": "rgba(15, 23, 42, 0.10)",
            "zerolinecolor": "rgba(15, 23, 42, 0.18)",
        },
    )
    return fig


def _store_plot(fig: go.Figure, summary: dict[str, Any]) -> str:
    plot_id = uuid.uuid4().hex
    figure_payload = json.loads(fig.to_json())
    PLOT_CACHE[plot_id] = {
        "created_at": time.time(),
        "figure": figure_payload,
        "summary": summary,
    }
    if len(PLOT_CACHE) > PLOT_CACHE_LIMIT:
        oldest = sorted(PLOT_CACHE.items(), key=lambda item: item[1]["created_at"])[: len(PLOT_CACHE) - PLOT_CACHE_LIMIT]
        for stale_id, _ in oldest:
            PLOT_CACHE.pop(stale_id, None)
    return plot_id


def _resolve_plot_state(plot_id: str) -> dict[str, Any]:
    state = PLOT_CACHE.get(plot_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Plot not found or expired. Generate it again before exporting.")
    return state


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    annotation_status = {"ok": True, "source": "", "gene_count": 0, "error": ""}
    try:
        annotation, source = load_annotation_reference()
        annotation_status["source"] = source
        annotation_status["gene_count"] = int(annotation.shape[0])
    except Exception as exc:  # noqa: BLE001
        annotation_status = {"ok": False, "source": "", "gene_count": 0, "error": str(exc)}

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": APP_TITLE,
            "subtitle": APP_SUBTITLE,
            "public_base_url": PUBLIC_BASE_URL,
            "readme_url": "/readme",
            "annotation_status": annotation_status,
        },
    )


@app.get("/readme", response_class=HTMLResponse)
async def readme(request: Request) -> HTMLResponse:
    try:
        markdown_source = README_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="README.md not found.") from exc

    rendered = markdown.markdown(
        markdown_source,
        extensions=["tables", "fenced_code", "toc"],
        output_format="html5",
    )
    return templates.TemplateResponse(
        request,
        "readme.html",
        {
            "title": f"{APP_TITLE} README",
            "subtitle": "Living guide for using and evolving the Genomic Hit Locator.",
            "readme_html": rendered,
        },
    )


@app.post("/api/plot")
async def api_plot(
    all_genes_file: UploadFile = File(...),
    subset_file: UploadFile | None = File(default=None),
    subset_genes_text: str = Form(default=""),
    scale_mode: str = Form(default="linear"),
    all_genes_color: str = Form(default="#d9dde3"),
    hit_genes_color: str = Form(default="#d93f6a"),
) -> JSONResponse:
    annotation, annotation_source = load_annotation_reference()

    all_gene_bytes = await all_genes_file.read()
    if not all_gene_bytes:
        raise HTTPException(status_code=400, detail="The all-genes file is empty.")
    all_raw = _read_tabular_upload(all_gene_bytes, all_genes_file.filename)
    prepared = _prepare_all_gene_table(all_raw, "log2" if scale_mode == "log2" else "linear")

    subset_raw: pd.DataFrame | None = None
    if subset_file is not None and subset_file.filename:
        subset_bytes = await subset_file.read()
        if subset_bytes:
            subset_raw = _read_tabular_upload(subset_bytes, subset_file.filename)

    selected_genes, subset_sources = _parse_subset_genes(subset_raw, subset_genes_text)

    merged = prepared.merge(annotation, on="gene", how="left")
    merged = merged.dropna(subset=["chromosome", "position"]).copy()
    if merged.empty:
        raise HTTPException(
            status_code=400,
            detail="None of the genes from the all-genes file could be matched to the local chromosome annotation reference.",
        )

    missing_annotation = int(prepared.shape[0] - merged.shape[0])
    selected_in_merged = {gene for gene in selected_genes if gene in set(merged["gene"])}
    missing_subset = sorted(selected_genes - selected_in_merged)

    figure = _build_plot(
        data=merged,
        selected_genes=selected_in_merged,
        all_color=all_genes_color,
        hit_color=hit_genes_color,
    )
    figure_payload = json.loads(figure.to_json())
    summary = {
        "all_genes_total": int(prepared.shape[0]),
        "annotated_genes_total": int(merged.shape[0]),
        "missing_annotation_total": missing_annotation,
        "selected_hits_total": len(selected_in_merged),
        "missing_selected_total": len(missing_subset),
        "missing_selected_preview": missing_subset[:20],
        "subset_sources": subset_sources,
        "annotation_source": annotation_source,
        "scale_mode": "log2" if scale_mode == "log2" else "linear",
        "y_axis_label": str(merged["y_axis_label"].iloc[0]),
    }
    plot_id = _store_plot(figure, summary)
    return JSONResponse(
        {
            "plot_id": plot_id,
            "figure": figure_payload,
            "summary": summary,
        }
    )


@app.get("/api/export/{plot_id}.svg")
async def export_svg(
    plot_id: str,
    width: int = 1600,
    height: int = 900,
    scale: int = 1,
) -> Response:
    state = _resolve_plot_state(plot_id)
    width = max(600, min(width, 6000))
    height = max(400, min(height, 4000))
    scale = max(1, min(scale, 4))
    fig = go.Figure(state["figure"])
    try:
        svg_bytes = pio.to_image(fig, format="svg", width=width, height=height, scale=scale)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"SVG export failed: {exc}") from exc
    return Response(
        content=svg_bytes,
        media_type="image/svg+xml",
        headers={"Content-Disposition": f'attachment; filename="genomic-hit-locator-{plot_id}.svg"'},
    )


@app.get("/healthz")
async def healthz() -> JSONResponse:
    annotation_ok = True
    annotation_source = ""
    try:
        _, annotation_source = load_annotation_reference()
    except Exception:
        annotation_ok = False
    return JSONResponse(
        {
            "ok": True,
            "app": "genomic-hit-locator",
            "annotation_ready": annotation_ok,
            "annotation_source": annotation_source,
        }
    )
