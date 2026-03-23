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
PVALUE_ALIASES = (
    "pvalue",
    "pValue",
    "PValue",
    "p_value",
    "P_Value",
    "p-value",
    "P-value",
    "p",
    "p_value_log2",
    "P_value_log2",
    "p_value_raw",
    "p_value_act",
    "p_value_deltaNT",
    "p_value_repro_log2",
)
CHROM_ALIASES = ("Chromosome", "chromosome", "Chrom", "Chr", "chrom")
POSITION_ALIASES = ("Start_Position", "Start position", "StartPosition", "Start", "pos", "Position")

ANNOTATION_CANDIDATES = [
    os.getenv("GENOMIC_HIT_LOCATOR_ANNOTATION_PATH", "").strip(),
    "/home/aag/Neuropathology - Manuscripts/TrevisanWang2024/Data/ScreenResults/PrP_genes_and_NT_ordered_AguzziLab.xlsx",
]
DEFAULT_SAMPLE_DIR = APP_ROOT / "sample-data"
DEFAULT_ALL_GENES_SAMPLE = Path(
    os.getenv("GENOMIC_HIT_LOCATOR_DEFAULT_ALL_GENES", str(DEFAULT_SAMPLE_DIR / "Primary_screen_filtered_results.xlsx")).strip()
)
DEFAULT_SECONDARY_SAMPLE = Path(
    os.getenv("GENOMIC_HIT_LOCATOR_DEFAULT_SECONDARY", str(DEFAULT_SAMPLE_DIR / "Secondary screen.xlsx")).strip()
)
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
        if lower_name.endswith(".csv"):
            return pd.read_csv(io.BytesIO(content))
        if lower_name.endswith(".tsv"):
            return pd.read_csv(io.BytesIO(content), sep="\t")
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


def _read_tabular_path(path: Path) -> pd.DataFrame:
    try:
        return _read_tabular_upload(path.read_bytes(), path.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=f"Default sample file not found: {path}") from exc


def _sample_status(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "filename": path.name,
        "available": path.exists(),
    }


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
    pvalue_col = None
    try:
        pvalue_col = _resolve_column(list(raw.columns), PVALUE_ALIASES, "p-value")
    except HTTPException:
        pvalue_col = None

    rename_map = {gene_col: "gene", effect_col: "effect_raw"}
    if pvalue_col:
        rename_map[pvalue_col] = "pvalue_raw"
    data = raw.rename(columns=rename_map).copy()
    data["gene"] = data["gene"].map(_normalize_gene)
    data["effect_raw"] = pd.to_numeric(data["effect_raw"], errors="coerce")
    if "pvalue_raw" in data.columns:
        data["pvalue_raw"] = pd.to_numeric(data["pvalue_raw"], errors="coerce")
    else:
        data["pvalue_raw"] = pd.NA
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


def _parse_uploaded_gene_list(raw: pd.DataFrame | None, label: str) -> set[str]:
    if raw is None or raw.empty:
        return set()
    gene_col = _resolve_column(list(raw.columns), GENE_ALIASES, f"{label} gene")
    genes = {_normalize_gene(value) for value in raw[gene_col].tolist()}
    return {gene for gene in genes if gene}


def _parse_gene_text_list(raw: str | None) -> set[str]:
    tokens = (_normalize_text(raw)).replace("\n", " ").replace("\r", " ").replace("\t", " ")
    if not tokens:
        return set()
    genes = {_normalize_gene(token) for token in tokens.replace(";", ",").split(",")}
    return {gene for gene in genes if gene}


def _derive_primary_hits(
    data: pd.DataFrame,
    selection_mode: str,
    effect_threshold: float | None,
    pvalue_threshold: float | None,
) -> set[str]:
    mode = (selection_mode or "effect_only").strip().lower()
    if mode not in {"effect_only", "pvalue_only", "combo"}:
        raise HTTPException(status_code=400, detail="Primary hit mode must be effect_only, pvalue_only, or combo.")

    effect_cutoff = abs(float(effect_threshold)) if effect_threshold is not None else 0.0
    pvalue_cutoff = float(pvalue_threshold) if pvalue_threshold is not None else 0.05

    effect_mask = data["effect_raw"].abs() >= effect_cutoff
    pvalue_series = pd.to_numeric(data["pvalue_raw"], errors="coerce")
    pvalue_mask = pvalue_series.notna() & (pvalue_series <= pvalue_cutoff)

    if mode == "effect_only":
        selected = data.loc[effect_mask, "gene"]
    elif mode == "pvalue_only":
        if pvalue_series.notna().sum() == 0:
            raise HTTPException(
                status_code=400,
                detail="Primary hits cannot be derived from p-values because the genome-wide file has no detected p-value column.",
            )
        selected = data.loc[pvalue_mask, "gene"]
    else:
        if pvalue_series.notna().sum() == 0:
            raise HTTPException(
                status_code=400,
                detail="Primary hits cannot be derived with combo mode because the genome-wide file has no detected p-value column.",
            )
        selected = data.loc[effect_mask & pvalue_mask, "gene"]
    return {gene for gene in selected.tolist() if _normalize_gene(gene)}


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


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = _hex_with_alpha(color, "#d9dde3")
    if len(value) == 4:
        value = "#" + "".join(ch * 2 for ch in value[1:])
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))


def _blend_rgb(base: tuple[int, int, int], target: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    clipped = max(0.0, min(1.0, float(amount)))
    return tuple(int(round(base[channel] + (target[channel] - base[channel]) * clipped)) for channel in range(3))


def _rgba_string(rgb: tuple[int, int, int], alpha: float = 1.0) -> str:
    clipped = max(0.0, min(1.0, float(alpha)))
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {clipped:.3f})"


def _pvalue_color(
    start_rgb: tuple[int, int, int],
    end_rgb: tuple[int, int, int],
    raw_intensity: float,
) -> str:
    adjusted_rgb = _blend_rgb(start_rgb, end_rgb, raw_intensity)
    return f"rgb({adjusted_rgb[0]}, {adjusted_rgb[1]}, {adjusted_rgb[2]})"


def _format_pvalue_tick(value: float) -> str:
    if value >= 0.1:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if value >= 0.001:
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{value:.1e}"


def _compute_pvalue_scale_context(data: pd.DataFrame) -> dict[str, Any] | None:
    pvalues = pd.to_numeric(data["pvalue_raw"], errors="coerce")
    valid_mask = pvalues.notna() & (pvalues > 0)
    if valid_mask.sum() == 0:
        return None

    clipped = pvalues.clip(lower=1e-300, upper=1.0)
    scores = clipped.map(lambda value: -math.log10(float(value)))  # noqa: C417
    score_min = float(scores[valid_mask].min())
    score_max = float(scores[valid_mask].max())
    score_span = max(score_max - score_min, 1e-9)
    tickvals = [0.0, 0.25, 0.5, 0.75, 1.0]
    ticktext = [_format_pvalue_tick(10 ** (-(score_min + (value * score_span)))) for value in tickvals]
    return {
        "score_min": score_min,
        "score_max": score_max,
        "score_span": score_span,
        "tickvals": tickvals,
        "ticktext": ticktext,
        "pvalue_min": float(clipped[valid_mask].min()),
        "pvalue_max": float(clipped[valid_mask].max()),
    }


def _build_pvalue_marker_config(
    data: pd.DataFrame,
    start_color: str,
    end_color: str,
    colorbar_title: str,
    colorbar_x: float,
    marker_size: float,
    marker_opacity: float,
    scale_context: dict[str, Any] | None = None,
    line: dict[str, Any] | None = None,
    symbol: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    pvalues = pd.to_numeric(data["pvalue_raw"], errors="coerce")
    valid_mask = pvalues.notna() & (pvalues > 0)
    if valid_mask.sum() == 0:
        marker: dict[str, Any] = {"color": end_color, "size": marker_size, "opacity": marker_opacity}
        if line:
            marker["line"] = line
        if symbol:
            marker["symbol"] = symbol
        return (marker, None)

    clipped = pvalues.clip(lower=1e-300, upper=1.0)
    scores = clipped.map(lambda value: -math.log10(float(value)))  # noqa: C417
    observed_score_min = float(scores[valid_mask].min())
    observed_score_max = float(scores[valid_mask].max())
    if scale_context is None:
        scale_context = _compute_pvalue_scale_context(data)
    assert scale_context is not None
    score_min = float(scale_context["score_min"])
    score_max = float(scale_context["score_max"])
    score_span = float(scale_context["score_span"])
    norm = ((scores - score_min) / score_span).fillna(0.0).clip(lower=0.0, upper=1.0)

    start_rgb = _hex_to_rgb(start_color)
    end_rgb = _hex_to_rgb(end_color)
    scale_points = [0.0, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0]
    colorscale = [[point, _pvalue_color(start_rgb, end_rgb, point)] for point in scale_points]
    visible_colors = [_pvalue_color(start_rgb, end_rgb, raw_value) for raw_value in norm.tolist()]

    tickvals = list(scale_context["tickvals"])
    ticktext = list(scale_context["ticktext"])

    marker = {
        "color": visible_colors,
        "size": marker_size,
        "opacity": marker_opacity,
    }
    if line:
        marker["line"] = line
    if symbol:
        marker["symbol"] = symbol
    scale_summary = {
        "enabled": True,
        "pvalue_min": float(clipped[valid_mask].min()),
        "pvalue_max": float(clipped[valid_mask].max()),
        "reference_pvalue_min": float(10 ** (-score_max)),
        "reference_pvalue_max": float(10 ** (-score_min)),
        "observed_score_min": observed_score_min,
        "observed_score_max": observed_score_max,
        "score_min": score_min,
        "score_max": score_max,
        "color_values": norm.tolist(),
        "colorscale": colorscale,
        "colorbar": {
            "title": {"text": colorbar_title, "side": "right"},
            "tickvals": tickvals,
            "ticktext": ticktext,
            "thickness": 18,
            "len": 0.76,
            "y": 0.5,
            "yanchor": "middle",
            "x": colorbar_x,
            "xanchor": "left",
            "outlinewidth": 0.5,
            "outlinecolor": "rgba(20, 50, 76, 0.18)",
        },
        "tickvals": tickvals,
        "ticktext": ticktext,
        "title": colorbar_title,
    }
    return marker, scale_summary


def _add_colorbar_trace(fig: go.Figure, scale_summary: dict[str, Any], trace_name: str) -> None:
    fig.add_trace(
        go.Scatter(
            x=[None, None],
            y=[None, None],
            mode="markers",
            name=f"{trace_name} colorbar",
            marker={
                "size": 0.1,
                "color": [0.0, 1.0],
                "cmin": 0,
                "cmax": 1,
                "colorscale": scale_summary["colorscale"],
                "showscale": True,
                "colorbar": scale_summary["colorbar"],
            },
            hoverinfo="skip",
            showlegend=False,
        )
    )


def _build_plot(
    data: pd.DataFrame,
    show_genomewide: bool,
    primary_genes: set[str],
    secondary_genes: set[str],
    genomewide_start_color: str,
    genomewide_end_color: str,
    primary_start_color: str,
    primary_end_color: str,
    secondary_start_color: str,
    secondary_end_color: str,
) -> tuple[go.Figure, dict[str, Any]]:
    plot_df, tick_vals, tick_labels, chromosome_bounds = _build_genome_axis(data)
    genomewide_start = _hex_with_alpha(genomewide_start_color, "#ffe7ea")
    genomewide_end = _hex_with_alpha(genomewide_end_color, "#ff8f95")
    primary_start = _hex_with_alpha(primary_start_color, "#e7dcff")
    primary_end = _hex_with_alpha(primary_end_color, "#6a3fd9")
    secondary_start = _hex_with_alpha(secondary_start_color, "#dfffd8")
    secondary_end = _hex_with_alpha(secondary_end_color, "#19ff00")
    global_scale_context = _compute_pvalue_scale_context(plot_df)

    primary_df = plot_df[plot_df["gene"].isin(primary_genes)].copy()
    secondary_df = plot_df[plot_df["gene"].isin(secondary_genes)].copy()
    fig = go.Figure()
    scale_summaries: dict[str, Any] = {}

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

    if show_genomewide:
        genomewide_marker, pvalue_scale = _build_pvalue_marker_config(
            plot_df,
            genomewide_start,
            genomewide_end,
            "Genome-wide p",
            1.02,
            6,
            1.0,
            scale_context=global_scale_context,
        )
        if pvalue_scale:
            scale_summaries["genomewide"] = pvalue_scale
        fig.add_trace(
            go.Scattergl(
                x=plot_df["genome_x"],
                y=plot_df["effect_plot"],
                mode="markers",
                name="Genome-wide results",
                marker=genomewide_marker,
                customdata=plot_df[["gene", "chromosome", "position", "effect_raw", "pvalue_raw"]].values,
                hovertemplate=(
                    "Gene: %{customdata[0]}<br>"
                    "Chr %{customdata[1]}:%{customdata[2]:,.0f}<br>"
                    "Raw effect: %{customdata[3]:.4f}<br>"
                    "P-value: %{customdata[4]:.4g}<br>"
                    "Plotted value: %{y:.4f}<extra></extra>"
                ),
            )
        )
        if pvalue_scale:
            _add_colorbar_trace(fig, pvalue_scale, "Genome-wide results")

    if not primary_df.empty:
        primary_marker, primary_scale = _build_pvalue_marker_config(
            primary_df,
            primary_start,
            primary_end,
            "Primary p",
            1.08,
            9,
            0.96,
            scale_context=global_scale_context,
            line={"color": "#ffffff", "width": 1},
        )
        if primary_scale:
            scale_summaries["primary"] = primary_scale
        fig.add_trace(
            go.Scattergl(
                x=primary_df["genome_x"],
                y=primary_df["effect_plot"],
                mode="markers",
                name="Primary hits",
                marker=primary_marker,
                text=primary_df["gene"],
                customdata=primary_df[["gene", "chromosome", "position", "effect_raw", "pvalue_raw"]].values,
                hovertemplate=(
                    "Primary hit: %{customdata[0]}<br>"
                    "Chr %{customdata[1]}:%{customdata[2]:,.0f}<br>"
                    "Raw effect: %{customdata[3]:.4f}<br>"
                    "P-value: %{customdata[4]:.4g}<br>"
                    "Plotted value: %{y:.4f}<extra></extra>"
                ),
            )
        )
        if primary_scale:
            _add_colorbar_trace(fig, primary_scale, "Primary hits")

    if not secondary_df.empty:
        secondary_marker, secondary_scale = _build_pvalue_marker_config(
            secondary_df,
            secondary_start,
            secondary_end,
            "Secondary p",
            1.14,
            10,
            1.0,
            scale_context=global_scale_context,
            line={"color": "#14532d", "width": 1.2},
            symbol="diamond",
        )
        if secondary_scale:
            scale_summaries["secondary"] = secondary_scale
        fig.add_trace(
            go.Scattergl(
                x=secondary_df["genome_x"],
                y=secondary_df["effect_plot"],
                mode="markers",
                name="Secondary hits",
                marker=secondary_marker,
                text=secondary_df["gene"],
                customdata=secondary_df[["gene", "chromosome", "position", "effect_raw", "pvalue_raw"]].values,
                hovertemplate=(
                    "Secondary hit: %{customdata[0]}<br>"
                    "Chr %{customdata[1]}:%{customdata[2]:,.0f}<br>"
                    "Raw effect: %{customdata[3]:.4f}<br>"
                    "P-value: %{customdata[4]:.4g}<br>"
                    "Plotted value: %{y:.4f}<extra></extra>"
                ),
            )
        )
        if secondary_scale:
            _add_colorbar_trace(fig, secondary_scale, "Secondary hits")

    fig.update_layout(
        template="plotly_white",
        height=760,
        margin={"l": 72, "r": 220 if scale_summaries else 26, "t": 44, "b": 90},
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
    return fig, scale_summaries


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
            "default_all_genes_sample": _sample_status(DEFAULT_ALL_GENES_SAMPLE),
            "default_secondary_sample": _sample_status(DEFAULT_SECONDARY_SAMPLE),
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
    all_genes_file: UploadFile | None = File(default=None),
    secondary_hits_file: UploadFile | None = File(default=None),
    secondary_hits_text: str = Form(default=""),
    scale_mode: str = Form(default="linear"),
    genomewide_start_color: str = Form(default="#ffffff"),
    genomewide_end_color: str = Form(default="#ff0000"),
    primary_start_color: str = Form(default="#ffffff"),
    primary_end_color: str = Form(default="#5a00ff"),
    secondary_start_color: str = Form(default="#ffffff"),
    secondary_end_color: str = Form(default="#000000"),
    show_genomewide: str = Form(default="show"),
    primary_mode: str = Form(default="effect_only"),
    primary_effect_threshold: float = Form(default=1.0),
    primary_pvalue_threshold: float = Form(default=0.05),
) -> JSONResponse:
    annotation, annotation_source = load_annotation_reference()

    if all_genes_file is not None and all_genes_file.filename:
        all_gene_bytes = await all_genes_file.read()
        if not all_gene_bytes:
            raise HTTPException(status_code=400, detail="The all-genes file is empty.")
        all_raw = _read_tabular_upload(all_gene_bytes, all_genes_file.filename)
        all_genes_source = all_genes_file.filename
        using_default_all_genes = False
    else:
        if not DEFAULT_ALL_GENES_SAMPLE.exists():
            raise HTTPException(
                status_code=400,
                detail=(
                    "No genome-wide results file was uploaded, and the default sample dataset is not installed yet. "
                    f"Expected: {DEFAULT_ALL_GENES_SAMPLE}"
                ),
            )
        all_raw = _read_tabular_path(DEFAULT_ALL_GENES_SAMPLE)
        all_genes_source = DEFAULT_ALL_GENES_SAMPLE.name
        using_default_all_genes = True
    prepared = _prepare_all_gene_table(all_raw, "log2" if scale_mode == "log2" else "linear")

    secondary_raw: pd.DataFrame | None = None
    using_default_secondary = False
    secondary_gene_text = _normalize_text(secondary_hits_text)
    if secondary_hits_file is not None and secondary_hits_file.filename:
        subset_bytes = await secondary_hits_file.read()
        if subset_bytes:
            secondary_raw = _read_tabular_upload(subset_bytes, secondary_hits_file.filename)
    elif secondary_gene_text:
        secondary_raw = None
    elif DEFAULT_SECONDARY_SAMPLE.exists():
        secondary_raw = _read_tabular_path(DEFAULT_SECONDARY_SAMPLE)
        using_default_secondary = True

    merged = prepared.merge(annotation, on="gene", how="left")
    merged = merged.dropna(subset=["chromosome", "position"]).copy()
    if merged.empty:
        raise HTTPException(
            status_code=400,
            detail="None of the genes from the all-genes file could be matched to the local chromosome annotation reference.",
        )

    primary_genes = _derive_primary_hits(
        prepared,
        selection_mode=primary_mode,
        effect_threshold=primary_effect_threshold,
        pvalue_threshold=primary_pvalue_threshold,
    )
    secondary_genes = (
        _parse_uploaded_gene_list(secondary_raw, "secondary hit")
        if secondary_raw is not None
        else _parse_gene_text_list(secondary_gene_text)
    )

    missing_annotation = int(prepared.shape[0] - merged.shape[0])
    merged_gene_set = set(merged["gene"])
    primary_in_merged = {gene for gene in primary_genes if gene in merged_gene_set}
    secondary_in_merged = {gene for gene in secondary_genes if gene in merged_gene_set}
    missing_secondary = sorted(secondary_genes - secondary_in_merged)

    figure, pvalue_scale = _build_plot(
        data=merged,
        show_genomewide=(show_genomewide or "show").strip().lower() != "hide",
        primary_genes=primary_in_merged,
        secondary_genes=secondary_in_merged,
        genomewide_start_color=genomewide_start_color,
        genomewide_end_color=genomewide_end_color,
        primary_start_color=primary_start_color,
        primary_end_color=primary_end_color,
        secondary_start_color=secondary_start_color,
        secondary_end_color=secondary_end_color,
    )
    figure_payload = json.loads(figure.to_json())
    summary = {
        "all_genes_total": int(prepared.shape[0]),
        "annotated_genes_total": int(merged.shape[0]),
        "missing_annotation_total": missing_annotation,
        "primary_hits_total": len(primary_in_merged),
        "secondary_hits_total": len(secondary_in_merged),
        "missing_secondary_total": len(missing_secondary),
        "missing_secondary_preview": missing_secondary[:20],
        "annotation_source": annotation_source,
        "scale_mode": "log2" if scale_mode == "log2" else "linear",
        "y_axis_label": str(merged["y_axis_label"].iloc[0]),
        "primary_mode": primary_mode,
        "primary_effect_threshold": primary_effect_threshold,
        "primary_pvalue_threshold": primary_pvalue_threshold,
        "show_genomewide": (show_genomewide or "show").strip().lower() != "hide",
        "pvalue_scale": pvalue_scale,
        "data_source": {
            "all_genes": all_genes_source,
            "secondary_hits": (
                secondary_hits_file.filename
                if secondary_hits_file is not None and secondary_hits_file.filename
                else ("manual entry" if secondary_gene_text else (DEFAULT_SECONDARY_SAMPLE.name if using_default_secondary else None))
            ),
            "using_default_all_genes": using_default_all_genes,
            "using_default_secondary": using_default_secondary,
        },
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
