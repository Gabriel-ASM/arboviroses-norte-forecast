"""Descoberta e download dos arquivos anuais publicados pelo Portal do SUS."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass(frozen=True)
class Disease:
    key: str
    slug: str
    name_prefix: str
    file_prefix: str
    first_year: int
    folder: str


DISEASES: dict[str, Disease] = {
    "dengue": Disease("dengue", "arboviroses-dengue", "Dengue", "DENG", 2000, "Dengue"),
    "chikungunya": Disease(
        "chikungunya",
        "arboviroses-febre-de-chikungunya",
        "Febre de Chikungunya",
        "CHIK",
        2015,
        "Chikungunya",
    ),
    "zika": Disease("zika", "arboviroses-zika-virus", "Zika Vírus", "ZIKA", 2016, "Zikavirus"),
}

PORTAL = "https://dadosabertos.saude.gov.br/dataset/{}"
HEADERS = {"User-Agent": "arboviroses-norte-forecast/0.1 (research use)"}


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def catalog_resources(disease: Disease, session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Lê a lista oficial de recursos incorporada na página pública do catálogo."""
    client = session or _session()
    response = client.get(PORTAL.format(disease.slug), timeout=45)
    response.raise_for_status()
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        response.text,
        flags=re.DOTALL,
    )
    if not match:
        raise RuntimeError(f"Não foi possível ler os metadados do catálogo: {disease.slug}")
    payload = json.loads(match.group(1))
    resources = payload.get("props", {}).get("pageProps", {}).get("resources", [])
    if not resources:
        raise RuntimeError(f"O catálogo não retornou recursos para {disease.key}")
    return resources


def annual_resource(resources: list[dict[str, Any]], disease: Disease, year: int) -> dict[str, Any]:
    year_pattern = re.compile(rf"(?<!\d){year}(?!\d)")
    eligible = [
        resource
        for resource in resources
        if year_pattern.search(str(resource.get("name", "")))
        and str(resource.get("format", "")).casefold() in {"csv", "parquet"}
        and str(resource.get("url", "")).startswith("https://")
    ]
    if not eligible:
        raise FileNotFoundError(
            f"O catálogo oficial não lista um arquivo anual CSV/Parquet para {disease.key} {year}."
        )
    priority = {"csv": 0, "parquet": 1}
    eligible.sort(
        key=lambda resource: (
            priority.get(str(resource.get("format", "")).casefold(), 99),
            str(resource.get("metadata_modified", "")),
        ),
        reverse=False,
    )
    top_priority = priority[str(eligible[0]["format"]).casefold()]
    latest = max(
        (r for r in eligible if priority[str(r["format"]).casefold()] == top_priority),
        key=lambda r: str(r.get("metadata_modified", "")),
    )
    return latest


def _download(url: str, destination: Path, session: requests.Session) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(4):
        digest = hashlib.sha256()
        try:
            with session.get(url, stream=True, timeout=(20, 180)) as response:
                response.raise_for_status()
                with partial.open("wb") as stream:
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if block:
                            stream.write(block)
                            digest.update(block)
            partial.replace(destination)
            return digest.hexdigest()
        except requests.RequestException:
            partial.unlink(missing_ok=True)
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("Download interrompido")


def download_years(
    root: Path,
    diseases: list[str],
    start_year: int | None = None,
    end_year: int = 2026,
) -> list[dict[str, Any]]:
    """Baixa um arquivo anual por doença, mantendo ZIP original e SHA-256."""
    session = _session()
    manifest_path = root / "manifest.json"
    manifest: dict[str, Any] = {"source": "Portal de Dados Abertos do SUS", "files": []}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    known = {(item["disease"], item["year"]): item for item in manifest.get("files", [])}
    added: list[dict[str, Any]] = []

    for key in diseases:
        disease = DISEASES[key]
        first = max(disease.first_year, start_year or disease.first_year)
        if first > end_year:
            raise ValueError(
                f"Intervalo sem anos disponíveis para {disease.key}: {first}–{end_year}."
            )
        resources = catalog_resources(disease, session)
        for year in range(first, end_year + 1):
            resource = annual_resource(resources, disease, year)
            extension = str(resource["format"]).casefold()
            destination = root / disease.key / f"{year}.{extension}.zip"
            prior = known.get((disease.key, year))
            if destination.exists() and prior and prior.get("resource_id") == resource.get("id"):
                added.append(prior)
                continue
            sha256 = _download(str(resource["url"]), destination, session)
            record = {
                "disease": disease.key,
                "year": year,
                "file": str(destination.relative_to(root)).replace("\\", "/"),
                "format": extension,
                "sha256": sha256,
                "resource_id": resource.get("id"),
                "resource_name": resource.get("name"),
                "source_url": resource.get("url"),
                "source_updated_at": resource.get("last_modified"),
                "catalog_updated_at": resource.get("metadata_modified"),
                "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            known[(disease.key, year)] = record
            added.append(record)
            manifest["files"] = list(known.values())
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"Baixado {disease.key} {year}: {destination.name}")
    manifest["files"] = list(known.values())
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return added
