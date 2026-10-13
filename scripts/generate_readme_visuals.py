"""Generate the forecast figures embedded in the project README.

The figures use the project's existing municipal forecast CSVs and official IBGE
municipal boundaries. No case records are downloaded by this script.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.collections import PatchCollection
from matplotlib.patches import FancyBboxPatch, Polygon
from matplotlib.ticker import FuncFormatter
from shapely.geometry import shape
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
FORECAST_DIR = ROOT / "outputs" / "forecasts"
REGISTRY_PATH = ROOT / "data" / "raw" / "north_municipalities.csv"
ASSET_DIR = ROOT / "docs" / "assets"
IBGE_MUNICIPAL_MALHA_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/regioes/1"
    "?formato=application/vnd.geo+json&intrarregiao=municipio"
)

DISEASES = ("dengue", "chikungunya", "zika")
DISEASE_LABELS = {
    "dengue": "Dengue",
    "chikungunya": "Chikungunya",
    "zika": "Zika",
}
BACKGROUND = "#F6F4EE"
PANEL = "#FCFBF7"
INK = "#183331"
MUTED = "#64736D"
ACCENT = "#236F68"
PALETTE = ["#ECE9DD", "#C3D6BD", "#72AAA0", "#2B7B73", "#F0BE67"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--origin-date",
        help="Forecast file date in YYYY-MM-DD format; defaults to the latest date available.",
    )
    parser.add_argument(
        "--boundary-file",
        type=Path,
        help="Optional local IBGE GeoJSON file; if omitted, the official IBGE API is queried.",
    )
    return parser.parse_args()


def find_forecast_date(requested: str | None) -> str:
    if requested:
        date.fromisoformat(requested)
        missing = [
            disease
            for disease in DISEASES
            if not (FORECAST_DIR / f"{disease}_{requested}_municipality.csv").is_file()
        ]
        if missing:
            raise FileNotFoundError(
                f"No municipal forecast for {', '.join(missing)} at {requested} in {FORECAST_DIR}"
            )
        return requested

    available: dict[str, set[str]] = defaultdict(set)
    pattern = re.compile(r"(dengue|chikungunya|zika)_(\d{4}-\d{2}-\d{2})_municipality\.csv")
    for path in FORECAST_DIR.glob("*_municipality.csv"):
        match = pattern.fullmatch(path.name)
        if match:
            available[match.group(2)].add(match.group(1))
    complete_dates = [
        origin for origin, diseases in available.items() if set(DISEASES).issubset(diseases)
    ]
    if not complete_dates:
        raise FileNotFoundError(
            f"No complete set of municipal forecasts found in {FORECAST_DIR}. "
            "Run the model first, then regenerate the figures."
        )
    return max(complete_dates)


def load_registry() -> pd.DataFrame:
    if not REGISTRY_PATH.is_file():
        raise FileNotFoundError(
            f"Municipality registry not found at {REGISTRY_PATH}; run `arboviroses prepare` first."
        )
    registry = pd.read_csv(REGISTRY_PATH, dtype={"uf": "string"})
    registry["municipality_code_sinan"] = registry["municipality_code_sinan"].astype(str).str.zfill(6)
    registry["municipality_code_ibge"] = registry["municipality_code_ibge"].astype(str).str.zfill(7)
    return registry


def load_boundaries(boundary_file: Path | None) -> list[dict[str, Any]]:
    if boundary_file is None:
        response = requests.get(
            IBGE_MUNICIPAL_MALHA_URL,
            headers={"User-Agent": "arboviroses-norte-forecast README figure generator"},
            timeout=(20, 120),
        )
        response.raise_for_status()
        geojson = response.json()
    else:
        with boundary_file.open(encoding="utf-8") as handle:
            geojson = json.load(handle)

    features = geojson.get("features", [])
    if not features:
        raise ValueError("The IBGE GeoJSON contains no municipal features.")
    boundaries = []
    for feature in features:
        ibge_code = str(feature.get("properties", {}).get("codarea", "")).zfill(7)
        if not ibge_code or ibge_code == "0000000":
            continue
        boundaries.append(
            {
                "ibge": ibge_code,
                "uf": ibge_code[:2],
                "geometry": shape(feature["geometry"]),
            }
        )
    if len(boundaries) != 450:
        raise ValueError(f"Expected 450 municipalities in the IBGE North Region malha; got {len(boundaries)}.")
    return boundaries


def load_forecasts(origin: str) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    forecasts: dict[str, pd.DataFrame] = {}
    for disease in DISEASES:
        frame = pd.read_csv(FORECAST_DIR / f"{disease}_{origin}_municipality.csv")
        frame["municipality_code_sinan"] = (
            frame["municipality_code_sinan"].astype(str).str.zfill(6)
        )
        forecasts[disease] = frame
    registry = load_registry()
    return forecasts, registry


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titleweight": "bold",
            "text.color": INK,
            "axes.labelcolor": MUTED,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "savefig.facecolor": BACKGROUND,
            "figure.facecolor": BACKGROUND,
        }
    )


def br_number(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def format_small(value: float, disease: str) -> str:
    if disease == "dengue":
        return br_number(value, 0)
    if disease == "chikungunya":
        return br_number(value, 2)
    return br_number(value, 4)


def polygon_parts(geometry: Any) -> list[Any]:
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type == "MultiPolygon":
        return list(geometry.geoms)
    return []


def add_polygon_edges(axis: Any, geometry: Any, color: str, linewidth: float, alpha: float = 1.0) -> None:
    for polygon in polygon_parts(geometry):
        x, y = polygon.exterior.xy
        axis.plot(x, y, color=color, linewidth=linewidth, alpha=alpha, zorder=3)


def make_dengue_map(
    origin: str,
    boundaries: list[dict[str, Any]],
    forecasts: dict[str, pd.DataFrame],
    registry: pd.DataFrame,
) -> Path:
    dengue = forecasts["dengue"]
    weekly = (
        dengue.groupby(["municipality_code_sinan", "uf"], as_index=False)["expected_cases"]
        .sum()
        .rename(columns={"expected_cases": "four_week_expected"})
    )
    target_weeks = dengue[["target_epi_year", "target_epi_week"]].drop_duplicates().sort_values(
        ["target_epi_year", "target_epi_week"]
    )
    first_target = target_weeks.iloc[0]
    last_target = target_weeks.iloc[-1]
    week_count = len(target_weeks)
    if int(first_target.target_epi_year) == int(last_target.target_epi_year):
        period_label = (
            f"SE {int(first_target.target_epi_week)}–{int(last_target.target_epi_week)}"
            f"/{int(first_target.target_epi_year)}"
        )
    else:
        period_label = (
            f"SE {int(first_target.target_epi_week)}/{int(first_target.target_epi_year)}–"
            f"SE {int(last_target.target_epi_week)}/{int(last_target.target_epi_year)}"
        )
    municipality_data = registry.merge(weekly, on="municipality_code_sinan", how="left")
    municipality_data["four_week_expected"] = municipality_data["four_week_expected"].fillna(0)
    municipality_data["municipality_code_ibge"] = municipality_data[
        "municipality_code_ibge"
    ].astype(str).str.zfill(7)
    if municipality_data["four_week_expected"].isna().any():
        missing_count = int(municipality_data["four_week_expected"].isna().sum())
        raise ValueError(f"Forecast is missing for {missing_count} municipalities in the IBGE registry.")
    if not municipality_data["municipality_code_ibge"].is_unique:
        raise ValueError("The municipality registry has duplicate IBGE codes.")
    boundary_codes = {item["ibge"] for item in boundaries}
    registry_codes = set(municipality_data["municipality_code_ibge"])
    if registry_codes != boundary_codes:
        raise ValueError("Forecast registry and IBGE boundary codes do not match exactly.")
    data_by_ibge = municipality_data.set_index("municipality_code_ibge").to_dict("index")

    palette = LinearSegmentedColormap.from_list("arboviroses_forecast", PALETTE)
    norm = LogNorm(vmin=0.001, vmax=100)
    patches: list[Polygon] = []
    patch_values: list[float] = []
    boundary_by_uf: dict[str, list[Any]] = defaultdict(list)
    all_geometries = []
    for item in boundaries:
        geometry = item["geometry"]
        all_geometries.append(geometry)
        boundary_by_uf[item["uf"]].append(geometry)
        row = data_by_ibge.get(item["ibge"])
        if row is None:
            continue
        value = max(float(row["four_week_expected"]), 0.001)
        for polygon in polygon_parts(geometry):
            patches.append(Polygon(np.asarray(polygon.exterior.coords), closed=True))
            patch_values.append(value)
    if not patches:
        raise ValueError("No forecast municipalities could be joined to the IBGE boundaries.")

    fig = plt.figure(figsize=(15, 9), dpi=180, facecolor=BACKGROUND)
    fig.text(0.055, 0.94, "PREVISÃO MUNICIPAL  ·  REGIÃO NORTE", fontsize=10, weight="bold", color=ACCENT)
    fig.text(
        0.055,
        0.895,
        f"Dengue | {week_count} semanas à frente",
        fontsize=28,
        weight="bold",
        fontfamily="DejaVu Serif",
        color=INK,
    )
    fig.text(
        0.057,
        0.858,
        f"Casos esperados por município  ·  origem {pd.Timestamp(origin).strftime('%d/%m/%Y')}  ·  {period_label}",
        fontsize=10.5,
        color=MUTED,
    )

    map_axis = fig.add_axes([0.045, 0.16, 0.62, 0.66], facecolor=BACKGROUND)
    collection = PatchCollection(
        patches,
        cmap=palette,
        norm=norm,
        edgecolor="#F8F6EF",
        linewidth=0.26,
        zorder=2,
    )
    collection.set_array(np.asarray(patch_values))
    map_axis.add_collection(collection)
    for uf_code, geometries in boundary_by_uf.items():
        add_polygon_edges(map_axis, unary_union(geometries), "#294643", 1.05, 0.9)
    bounds = unary_union(all_geometries).bounds
    pad_x = (bounds[2] - bounds[0]) * 0.025
    pad_y = (bounds[3] - bounds[1]) * 0.025
    map_axis.set_xlim(bounds[0] - pad_x, bounds[2] + pad_x)
    map_axis.set_ylim(bounds[1] - pad_y, bounds[3] + pad_y)
    map_axis.set_aspect("equal", adjustable="box")
    map_axis.axis("off")

    state_labels = {"11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO"}
    for uf_code, geometries in boundary_by_uf.items():
        if uf_code not in state_labels:
            continue
        point = unary_union(geometries).representative_point()
        map_axis.text(
            point.x,
            point.y,
            state_labels[uf_code],
            ha="center",
            va="center",
            fontsize=8,
            weight="bold",
            color=INK,
            bbox={"boxstyle": "round,pad=0.25", "facecolor": PANEL, "edgecolor": "none", "alpha": 0.84},
            zorder=5,
        )

    color_axis = fig.add_axes([0.13, 0.105, 0.36, 0.018])
    colorbar = fig.colorbar(collection, cax=color_axis, orientation="horizontal")
    colorbar.set_ticks([0.001, 0.01, 0.1, 1, 10, 100])
    colorbar.set_ticklabels(["0,001", "0,01", "0,1", "1", "10", "100"])
    colorbar.ax.tick_params(length=0, labelsize=8, pad=3)
    colorbar.outline.set_visible(False)
    fig.text(0.13, 0.132, "Casos esperados no horizonte · escala logarítmica", fontsize=8.5, color=MUTED)

    # Sidebar with a single interpretable regional value and the highest municipal means.
    side_x = 0.70
    sidebar = FancyBboxPatch(
        (side_x, 0.16),
        0.255,
        0.66,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        transform=fig.transFigure,
        facecolor=PANEL,
        edgecolor="#E6E2D8",
        linewidth=0.8,
        zorder=0,
    )
    fig.add_artist(sidebar)
    total = float(municipality_data["four_week_expected"].sum())
    fig.text(side_x + 0.025, 0.765, f"SOMA REGIONAL · {week_count} SEMANAS", fontsize=8.5, weight="bold", color=ACCENT)
    fig.text(side_x + 0.022, 0.692, br_number(total, 1), fontsize=35, weight="bold", fontfamily="DejaVu Serif", color=INK)
    fig.text(side_x + 0.025, 0.66, "casos esperados de dengue", fontsize=10, color=MUTED)
    fig.text(side_x + 0.025, 0.615, "PROJEÇÕES MUNICIPAIS MAIS ALTAS", fontsize=8.2, weight="bold", color=ACCENT)

    top = municipality_data.nlargest(5, "four_week_expected").sort_values(
        "four_week_expected", ascending=False
    )
    max_value = max(float(top["four_week_expected"].max()), 1.0)
    for i, row in enumerate(top.itertuples(index=False)):
        y = 0.55 - i * 0.065
        fig.text(side_x + 0.025, y + 0.02, str(row.municipality_name), fontsize=9.1, weight="bold", color=INK)
        fig.text(side_x + 0.225, y + 0.02, br_number(float(row.four_week_expected), 1), ha="right", fontsize=9, weight="bold", color=INK)
        bar_bg = FancyBboxPatch(
            (side_x + 0.025, y - 0.004),
            0.20,
            0.009,
            boxstyle="round,pad=0.001,rounding_size=0.005",
            transform=fig.transFigure,
            facecolor="#EAE8DF",
            edgecolor="none",
            zorder=2,
        )
        bar_fill = FancyBboxPatch(
            (side_x + 0.025, y - 0.004),
            0.20 * float(row.four_week_expected) / max_value,
            0.009,
            boxstyle="round,pad=0.001,rounding_size=0.005",
            transform=fig.transFigure,
            facecolor=ACCENT,
            edgecolor="none",
            zorder=3,
        )
        fig.add_artist(bar_bg)
        fig.add_artist(bar_fill)

    fig.text(side_x + 0.025, 0.203, "A cor usa escala logarítmica para tornar", fontsize=8, color=MUTED)
    fig.text(side_x + 0.025, 0.184, "visíveis as diferenças entre municípios.", fontsize=8, color=MUTED)
    fig.text(
        0.055,
        0.055,
        f"Média prevista (pode ser fracionária), não contagem observada. Limites: IBGE, Malhas Territoriais (API v3; consulta em {date.today().strftime('%d/%m/%Y')}).",
        fontsize=7.5,
        color=MUTED,
    )
    fig.text(0.94, 0.055, "arboviroses-norte-forecast", fontsize=7.5, ha="right", color=MUTED)

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    output_path = ASSET_DIR / "north_dengue_forecast.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight", pad_inches=0.16)
    plt.close(fig)
    return output_path


def make_weekly_figure(origin: str, forecasts: dict[str, pd.DataFrame]) -> Path:
    weekly_by_disease: dict[str, pd.DataFrame] = {}
    for disease, frame in forecasts.items():
        weekly_by_disease[disease] = (
            frame.groupby(["target_epi_year", "target_epi_week"], as_index=False)["expected_cases"]
            .sum()
            .sort_values(["target_epi_year", "target_epi_week"])
        )

    fig = plt.figure(figsize=(15, 6.8), dpi=180, facecolor=BACKGROUND)
    fig.text(0.055, 0.93, "VISÃO REGIONAL  ·  450 MUNICÍPIOS", fontsize=10, weight="bold", color=ACCENT)
    fig.text(
        0.055,
        0.875,
        "A previsão, semana a semana",
        fontsize=27,
        weight="bold",
        fontfamily="DejaVu Serif",
        color=INK,
    )
    fig.text(
        0.057,
        0.835,
        f"Soma das médias municipais  ·  origem {pd.Timestamp(origin).strftime('%d/%m/%Y')}  ·  cada painel tem escala própria",
        fontsize=10.5,
        color=MUTED,
    )

    colors = {"dengue": "#236F68", "chikungunya": "#D68B55", "zika": "#8A789F"}
    for index, disease in enumerate(DISEASES):
        left = 0.055 + index * 0.31
        axis = fig.add_axes([left, 0.205, 0.27, 0.53], facecolor=PANEL)
        for spine in axis.spines.values():
            spine.set_color("#E8E4DA")
            spine.set_linewidth(0.8)
        data = weekly_by_disease[disease]
        positions = np.arange(len(data))
        values = data["expected_cases"].to_numpy(dtype=float)
        bars = axis.bar(
            positions,
            values,
            width=0.58,
            color=colors[disease],
            alpha=0.94,
            edgecolor="none",
            zorder=3,
        )
        axis.grid(axis="y", color="#E7E4DC", linewidth=0.8, zorder=0)
        axis.set_axisbelow(True)
        axis.set_xticks(positions, [f"SE {int(week)}" for week in data["target_epi_week"]])
        axis.tick_params(axis="x", length=0, labelsize=8.5, pad=8)
        axis.tick_params(axis="y", length=0, labelsize=8, pad=5)
        axis.set_ylabel("casos esperados", fontsize=8.5, labelpad=9)
        axis.set_title(DISEASE_LABELS[disease].upper(), loc="left", fontsize=11, weight="bold", color=INK, pad=15)
        axis.set_ylim(0, float(values.max()) * 1.28 if len(values) else 1)
        tick_decimals = {"dengue": 0, "chikungunya": 2, "zika": 3}[disease]
        axis.yaxis.set_major_formatter(
            FuncFormatter(lambda value, _, decimals=tick_decimals: br_number(value, decimals))
        )
        for bar, value in zip(bars, values, strict=True):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + float(values.max()) * 0.045,
                format_small(float(value), disease),
                ha="center",
                va="bottom",
                fontsize=9,
                weight="bold",
                color=INK,
            )

    fig.text(
        0.055,
        0.095,
        "Os valores de cada doença são lidos na escala do próprio painel. São médias previstas agregadas, não notificações observadas.",
        fontsize=9,
        color=MUTED,
    )
    fig.text(
        0.055,
        0.062,
        "Modelo: saída municipal agregada por semana epidemiológica brasileira. Previsões em outputs/forecasts/.",
        fontsize=8,
        color=MUTED,
    )
    fig.text(0.94, 0.062, "arboviroses-norte-forecast", fontsize=7.5, ha="right", color=MUTED)

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    output_path = ASSET_DIR / "regional_forecast_by_disease.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight", pad_inches=0.16)
    plt.close(fig)
    return output_path


def main() -> None:
    args = parse_args()
    configure_style()
    origin = find_forecast_date(args.origin_date)
    forecasts, registry = load_forecasts(origin)
    boundaries = load_boundaries(args.boundary_file)
    map_path = make_dengue_map(origin, boundaries, forecasts, registry)
    weekly_path = make_weekly_figure(origin, forecasts)
    print(f"Created {map_path.relative_to(ROOT)}")
    print(f"Created {weekly_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
