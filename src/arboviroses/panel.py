"""Leitura dos arquivos Sinan e agregação por residência e semana epidemiológica."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from .calendar import epi_from_date, parse_epi_code
from .geography import ensure_registry

NORTH_UF_CODES = {"11", "12", "13", "14", "15", "16", "17"}
NORTH_UF_NAMES = {
    "11": "RO",
    "12": "AC",
    "13": "AM",
    "14": "RR",
    "15": "PA",
    "16": "AP",
    "17": "TO",
}
NEEDED_COLUMNS = {
    "tp_not", "classi_fin", "id_mn_resi", "sem_pri", "dt_sin_pri", "nduplic_n"
}


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(column).strip().lstrip("\ufeff").casefold() for column in frame.columns]
    return frame


def _csv_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        return ";" if sample.count(";") >= sample.count(",") else ","


def _read_csv_member(archive: zipfile.ZipFile, member: str) -> Iterator[pd.DataFrame]:
    with archive.open(member) as raw:
        sample = raw.read(65536)
    text = sample.decode("utf-8-sig", errors="replace")
    delimiter = _csv_delimiter(text)
    header = next(csv.reader(io.StringIO(text), delimiter=delimiter), [])
    wanted = {
        str(column).strip().lstrip("\ufeff").casefold()
        for column in header
        if str(column).strip().lstrip("\ufeff").casefold() in NEEDED_COLUMNS
    }
    if not {"tp_not", "classi_fin", "id_mn_resi"}.issubset(wanted):
        raise ValueError(f"Colunas Sinan essenciais ausentes em {member}: {sorted(wanted)}")
    if not {"sem_pri", "dt_sin_pri"}.intersection(wanted):
        raise ValueError(f"Campo temporal SEM_PRI/DT_SIN_PRI ausente em {member}")
    usecols = lambda name: str(name).strip().lstrip("\ufeff").casefold() in wanted  # noqa: E731
    with archive.open(member) as raw:
        try:
            yield from pd.read_csv(
                raw,
                sep=delimiter,
                encoding="latin-1",
                dtype="string",
                usecols=usecols,
                chunksize=250_000,
                low_memory=False,
                on_bad_lines="error",
            )
        except UnicodeDecodeError as error:
            raise ValueError(f"Falha ao decodificar CSV Sinan: {member}") from error


def _read_parquet_member(archive: zipfile.ZipFile, member: str) -> Iterator[pd.DataFrame]:
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("Instale pyarrow para ler o recurso Parquet do catálogo.") from error
    with archive.open(member) as raw:
        parquet = pq.ParquetFile(raw)
        names = {name.casefold(): name for name in parquet.schema.names}
        selected = [names[name] for name in NEEDED_COLUMNS if name in names]
        if not {"tp_not", "classi_fin", "id_mn_resi"}.issubset(
            {name.casefold() for name in selected}
        ):
            raise ValueError(f"Colunas Sinan essenciais ausentes em {member}: {selected}")
        if not {"sem_pri", "dt_sin_pri"}.intersection(
            {name.casefold() for name in selected}
        ):
            raise ValueError(f"Campo temporal SEM_PRI/DT_SIN_PRI ausente em {member}")
        for batch in parquet.iter_batches(columns=selected, batch_size=250_000):
            yield _normalize_columns(batch.to_pandas())


def _members(archive: zipfile.ZipFile) -> list[str]:
    files = [name for name in archive.namelist() if not name.endswith("/")]
    selected = [name for name in files if name.casefold().endswith((".csv", ".parquet"))]
    if not selected:
        raise ValueError(f"ZIP sem CSV/Parquet reconhecível: {files[:5]}")
    return selected


def _read_archive(path: Path) -> Iterator[pd.DataFrame]:
    with zipfile.ZipFile(path) as archive:
        for member in _members(archive):
            if member.casefold().endswith(".csv"):
                yield from (_normalize_columns(frame) for frame in _read_csv_member(archive, member))
            elif member.casefold().endswith(".parquet"):
                yield from _read_parquet_member(archive, member)


def _municipality_code(values: pd.Series) -> pd.Series:
    code = values.fillna("").astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    code = code.str.replace(r"\D", "", regex=True)
    code = code.where(code.str.len().isin((6, 7)))
    return code.str.slice(0, 6)


def _epi_columns(frame: pd.DataFrame, stats: Counter[str]) -> pd.DataFrame:
    sem = frame.get("sem_pri", pd.Series(pd.NA, index=frame.index, dtype="string"))
    sem = sem.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    from_sem = sem.map(parse_epi_code)

    date_values = frame.get("dt_sin_pri", pd.Series(pd.NA, index=frame.index, dtype="string"))
    parsed_dates = pd.to_datetime(date_values, errors="coerce", dayfirst=True, format="mixed")
    fallback: list[tuple[int, int] | None] = []
    for value in parsed_dates:
        fallback.append(None if pd.isna(value) else epi_from_date(value.date()))

    year_values: list[int | None] = []
    week_values: list[int | None] = []
    for primary, secondary in zip(from_sem, fallback):
        chosen = primary or secondary
        year_values.append(chosen[0] if chosen else None)
        week_values.append(chosen[1] if chosen else None)
        if primary and secondary and primary != secondary:
            stats["week_date_mismatch"] += 1
    result = pd.DataFrame({"epi_year": year_values, "epi_week": week_values}, index=frame.index)
    stats["invalid_epidemiological_week"] += int(result["epi_year"].isna().sum())
    return result


def _prepare_chunk(
    frame: pd.DataFrame,
    disease: str,
    case_definition: str,
    stats: Counter[str],
) -> pd.DataFrame:
    frame = _normalize_columns(frame)
    required = {"tp_not", "classi_fin", "id_mn_resi"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Campos obrigatórios ausentes para {disease}: {sorted(missing)}")
    stats["rows_read"] += len(frame)
    tp = (
        frame["tp_not"].fillna("").astype("string").str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    individual = tp == "2"
    stats["non_individual_or_unknown"] += int((~individual).sum())
    frame = frame.loc[individual].copy()
    classification = (
        frame["classi_fin"].fillna("").astype("string").str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    if "nduplic_n" in frame:
        duplicate = (
            frame["nduplic_n"].fillna("").astype("string").str.strip()
            .str.replace(r"\.0$", "", regex=True)
            == "2"
        )
        stats["flagged_duplicates"] += int(duplicate.sum())
        frame = frame.loc[~duplicate].copy()
        classification = classification.loc[~duplicate]
    else:
        stats["records_without_duplicate_flag"] += len(frame)
    if case_definition == "probable":
        discarded = classification == "2"
        stats["discarded_cases"] += int(discarded.sum())
        unknown = ~classification.isin({"", "0", "1", "2", "8", "9"})
        stats["unmapped_classification"] += int(unknown.sum())
        frame = frame.loc[~discarded].copy()
    else:
        confirmed = classification == "1"
        stats["not_confirmed"] += int((~confirmed).sum())
        frame = frame.loc[confirmed].copy()

    codes = _municipality_code(frame["id_mn_resi"])
    valid_code = codes.notna() & codes.str.len().eq(6) & codes.str[:2].isin(NORTH_UF_CODES)
    stats["invalid_or_outside_north_residence"] += int((~valid_code).sum())
    frame = frame.loc[valid_code].copy()
    frame["municipality_code"] = codes.loc[valid_code]

    epi = _epi_columns(frame, stats)
    frame["epi_year"] = epi["epi_year"]
    frame["epi_week"] = epi["epi_week"]
    valid_week = frame["epi_year"].notna() & frame["epi_week"].notna()
    frame = frame.loc[valid_week].copy()
    frame["epi_year"] = frame["epi_year"].astype(int)
    frame["epi_week"] = frame["epi_week"].astype(int)
    stats["records_counted"] += len(frame)
    grouped = (
        frame.groupby(["municipality_code", "epi_year", "epi_week"], as_index=False)
        .size()
        .rename(columns={"size": "cases"})
    )
    grouped.insert(0, "disease", disease)
    grouped["uf"] = grouped["municipality_code"].str[:2].map(NORTH_UF_NAMES)
    return grouped


def build_weekly_panel(
    raw_root: Path,
    output: Path,
    diseases: list[str],
    case_definition: str = "probable",
    registry_mode: str = "auto",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Agrega os arquivos anuais já baixados em contagens de residência × semana."""
    if case_definition not in {"probable", "confirmed"}:
        raise ValueError("case_definition deve ser 'probable' ou 'confirmed'")
    manifest_path = raw_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifesto não encontrado: {manifest_path}; execute download primeiro.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    registry_path = raw_root / "north_municipalities.csv"
    registry, geography_warning = ensure_registry(registry_path, registry_mode)
    if registry is not None:
        registry_hash = hashlib.sha256(registry_path.read_bytes()).hexdigest()
        manifest["geography_registry"] = {
            "source": "IBGE Localidades API",
            "url_pattern": "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{UF}/municipios?orderBy=id",
            "file": registry_path.name,
            "sha256": registry_hash,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    records = manifest.get("files", [])
    all_groups: list[pd.DataFrame] = []
    all_stats: dict[str, Any] = {}

    for disease in diseases:
        stats: Counter[str] = Counter()
        sources = [
            item for item in records
            if item.get("disease") == disease and (raw_root / item["file"]).exists()
        ]
        if not sources:
            raise FileNotFoundError(f"Nenhum arquivo baixado para {disease} em {raw_root}")
        years = {int(item["year"]) for item in sources}
        missing_years = sorted(set(range(min(years), max(years) + 1)) - years)
        if missing_years:
            raise ValueError(
                f"Arquivos anuais ausentes para {disease}: {missing_years[:12]}. "
                "Complete a ingestão antes de tratar semanas sem registros como zero."
            )
        partials: list[pd.DataFrame] = []
        for source in sorted(sources, key=lambda item: item["year"]):
            path = raw_root / source["file"]
            for chunk in _read_archive(path):
                partials.append(_prepare_chunk(chunk, disease, case_definition, stats))
        disease_panel = (
            pd.concat(partials, ignore_index=True)
            .groupby(["disease", "municipality_code", "uf", "epi_year", "epi_week"], as_index=False)["cases"]
            .sum()
        )
        all_groups.append(disease_panel)
        all_stats[disease] = dict(stats)
        print(
            f"{disease}: {len(disease_panel):,} município-semanas; "
            f"{stats['records_counted']:,} registros contabilizados"
        )

    panel = pd.concat(all_groups, ignore_index=True)
    panel = panel.sort_values(["disease", "municipality_code", "epi_year", "epi_week"])
    output.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output, index=False)
    stats_path = output.with_name(output.stem + "_quality.json")
    all_stats["_geography"] = {
        "registry_municipalities": int(len(registry)) if registry is not None else 0,
        "registry_mode": registry_mode,
        "warning": geography_warning,
        "source": "IBGE Localidades API" if registry is not None else "municípios observados no Sinan",
    }
    stats_path.write_text(json.dumps(all_stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return panel, all_stats
