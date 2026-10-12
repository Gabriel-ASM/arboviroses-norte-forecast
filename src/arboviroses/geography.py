"""Lista municipal oficial do IBGE para prever também localidades sem casos prévios."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import requests

NORTH_STATES = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO"}
IBGE_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{}/municipios?orderBy=id"


def _to_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for municipality in records:
        code = str(municipality["id"])
        state_id = int(code[:2])
        if state_id in NORTH_STATES:
            rows.append(
                {
                    "municipality_code_sinan": code[:6],
                    "municipality_code_ibge": code.zfill(7),
                    "municipality_name": municipality["nome"],
                    "uf": NORTH_STATES[state_id],
                }
            )
    frame = pd.DataFrame(rows).drop_duplicates("municipality_code_sinan")
    if len(frame) < 400 or frame["municipality_code_sinan"].duplicated().any():
        raise ValueError("A lista de municípios do IBGE veio incompleta ou contém códigos duplicados.")
    return frame.sort_values("municipality_code_sinan").reset_index(drop=True)


def ensure_registry(path: Path, mode: str = "auto") -> tuple[pd.DataFrame | None, str | None]:
    """Reusa uma cópia local; baixa uma vez se possível; pode seguir com municípios observados."""
    if mode not in {"auto", "required", "observed"}:
        raise ValueError("Modo de geografia inválido.")
    if mode == "observed":
        return None, "Usando somente municípios presentes na série histórica de notificações."
    if path.exists():
        frame = pd.read_csv(path, dtype={"municipality_code_sinan": "string"})
        required = {"municipality_code_sinan", "municipality_code_ibge", "municipality_name", "uf"}
        if not required.issubset(frame.columns) or len(frame) < 400:
            raise ValueError(f"Cadastro territorial incompleto ou inválido: {path}")
        frame["municipality_code_sinan"] = frame["municipality_code_sinan"].str.zfill(6)
        return frame, None

    session = requests.Session()
    records: list[dict[str, Any]] = []
    try:
        for state_id in NORTH_STATES:
            response = session.get(IBGE_URL.format(state_id), timeout=30)
            response.raise_for_status()
            records.extend(response.json())
        frame = _to_frame(records)
    except (requests.RequestException, ValueError, KeyError) as error:
        if mode == "required":
            raise RuntimeError(
                "Não foi possível obter a lista territorial do IBGE; tente novamente ou use --registry-mode observed."
            ) from error
        return None, f"IBGE indisponível; painel restrito a municípios observados. Detalhe: {error}"

    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame, None
