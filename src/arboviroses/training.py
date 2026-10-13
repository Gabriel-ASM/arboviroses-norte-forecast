"""Backtests, treino global por doença e previsões municipais."""

from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .calendar import epi_from_date, epi_key, epi_week_start, shift_epi, weeks_in_epi_year
from .model import build_model, negative_binomial_nll
from .panel import CLASSIFICATION_CODES, NORTH_UF_NAMES

LOOKBACK = 52
FORECAST_HORIZON = 4
DEFAULT_REPORTING_LAG = 8


def _negative_binomial():
    try:
        from scipy.stats import nbinom
    except ImportError as error:
        raise RuntimeError("Instale as dependências do projeto: python -m pip install -e '.[train]'") from error
    return nbinom


@dataclass
class Examples:
    history: np.ndarray
    regional_history: np.ndarray
    state_features: np.ndarray
    municipality: np.ndarray
    season: np.ndarray
    target: np.ndarray
    target_year: np.ndarray
    target_week: np.ndarray
    sample_uf: np.ndarray
    city_codes: list[str]


def _snapshot_date(raw_root: Path, disease: str) -> date | None:
    path = raw_root / "manifest.json"
    if not path.exists():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    disease_sources = [
        item for item in manifest.get("files", []) if item.get("disease") == disease
    ]
    if not disease_sources:
        return None
    latest_year = max(int(item["year"]) for item in disease_sources)
    candidates: list[date] = []
    for item in disease_sources:
        # An updated historical resource must not move the maturity cutoff for
        # the current surveillance year.
        if int(item["year"]) != latest_year:
            continue
        value = item.get("source_updated_at") or item.get("catalog_updated_at")
        if value:
            try:
                candidates.append(pd.Timestamp(value).date())
            except (TypeError, ValueError):
                pass
    return max(candidates) if candidates else None


def _dense_counts(
    panel: pd.DataFrame,
    disease: str,
    raw_root: Path,
    reporting_lag: int,
    start_year: int = 2016,
) -> tuple[np.ndarray, list[str], list[tuple[int, int]], dict[str, Any]]:
    if start_year < 2016:
        raise ValueError(
            "O treino comparável está validado a partir de 2016; "
            "classificações anteriores precisam de mapeamento histórico."
        )
    frame = panel.loc[panel["disease"] == disease].copy()
    if frame.empty:
        raise ValueError(f"Painel sem registros para {disease}")
    for column in ("epi_year", "epi_week", "cases"):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(int)
    frame = frame.loc[frame["epi_year"] >= start_year].copy()
    if frame.empty:
        raise ValueError(f"Painel sem registros para {disease} a partir de {start_year}")
    frame["municipality_code"] = frame["municipality_code"].astype(str).str.zfill(6)
    frame = frame.groupby(["municipality_code", "epi_year", "epi_week"], as_index=False)["cases"].sum()

    raw_manifest = json.loads((raw_root / "manifest.json").read_text(encoding="utf-8"))
    source_years = [
        int(item["year"])
        for item in raw_manifest.get("files", [])
        if item.get("disease") == disease and int(item["year"]) >= start_year
    ]
    snapshot = _snapshot_date(raw_root, disease)
    cutoff_date = snapshot - timedelta(weeks=reporting_lag) if snapshot else None
    if cutoff_date:
        cutoff_year, cutoff_week = epi_from_date(cutoff_date)
    else:
        last = frame.sort_values(["epi_year", "epi_week"]).iloc[-1]
        cutoff_year, cutoff_week = int(last.epi_year), int(last.epi_week)
    cutoff_key = epi_key(cutoff_year, cutoff_week)

    observed_year = int(frame["epi_year"].min())
    coverage_start_year = min(source_years) if source_years else observed_year
    start = epi_week_start(coverage_start_year, 1)
    observed_end = max(
        epi_week_start(int(row.epi_year), int(row.epi_week))
        for row in frame[["epi_year", "epi_week"]].itertuples(index=False)
    )
    cutoff_start = epi_week_start(cutoff_year, cutoff_week)
    end = max(observed_end, cutoff_start)
    n_weeks = (end - start).days // 7 + 1
    dates = [start + timedelta(weeks=index) for index in range(n_weeks)]
    periods = [epi_from_date(value) for value in dates]
    period_index = {epi_key(year, week): index for index, (year, week) in enumerate(periods)}
    cities = sorted(frame["municipality_code"].unique().tolist())
    registry_path = raw_root / "north_municipalities.csv"
    if registry_path.exists():
        registry = pd.read_csv(registry_path, dtype={"municipality_code_sinan": "string"})
        registry_codes = set(registry["municipality_code_sinan"].str.zfill(6).tolist())
        observed_codes = set(cities)
        unmatched = sorted(observed_codes - registry_codes)
        if unmatched:
            print(f"Aviso: {len(unmatched)} códigos Sinan sem correspondência no cadastro IBGE; serão mantidos.")
        cities = sorted(registry_codes | observed_codes)
    city_index = {city: index for index, city in enumerate(cities)}
    counts = np.zeros((len(cities), n_weeks), dtype=np.float32)
    for row in frame.itertuples(index=False):
        key = epi_key(int(row.epi_year), int(row.epi_week))
        if key in period_index:
            counts[city_index[row.municipality_code], period_index[key]] += float(row.cases)

    # A frequência do feed atualizado define os zeros observados até o limite de maturidade.
    details = {
        "snapshot_date": snapshot.isoformat() if snapshot else None,
        "mature_through": f"{cutoff_year}-W{cutoff_week:02d}",
        "mature_through_key": cutoff_key,
        "first_source_year": coverage_start_year,
        "requested_start_year": start_year,
        "last_source_year": max(source_years) if source_years else observed_year,
        "reporting_lag_weeks": reporting_lag,
        "municipalities": len(cities),
        "source_files": [
            {
                "year": int(item["year"]),
                "sha256": item.get("sha256"),
                "resource_id": item.get("resource_id"),
                "source_updated_at": item.get("source_updated_at"),
            }
            for item in sorted(
                (
                    item for item in raw_manifest.get("files", [])
                    if item.get("disease") == disease and int(item["year"]) >= start_year
                ),
                key=lambda item: int(item["year"]),
            )
        ],
    }
    return counts, cities, periods, details


def _calendar_features(periods: list[tuple[int, int]], indices: np.ndarray) -> np.ndarray:
    values = np.empty((len(indices), FORECAST_HORIZON, 2), dtype=np.float32)
    for row, origin_index in enumerate(indices):
        for horizon in range(FORECAST_HORIZON):
            year, week = periods[origin_index + horizon + 1]
            fraction = (week - 0.5) / weeks_in_epi_year(year)
            angle = 2 * np.pi * fraction
            values[row, horizon, 0] = np.sin(angle)
            values[row, horizon, 1] = np.cos(angle)
    return values.reshape(len(indices), FORECAST_HORIZON * 2)


def build_examples(
    counts: np.ndarray,
    city_codes: list[str],
    periods: list[tuple[int, int]],
    reporting_lag: int,
    lookback: int = LOOKBACK,
) -> Examples:
    first_origin = lookback + reporting_lag - 1
    last_origin = len(periods) - FORECAST_HORIZON - 1
    if last_origin < first_origin:
        raise ValueError("Histórico insuficiente para a janela e horizonte escolhidos")
    origins = np.arange(first_origin, last_origin + 1, dtype=np.int32)
    training_periods = np.asarray([year <= 2024 for year, _ in periods], dtype=bool)
    known_codes = [
        code for city_index, code in enumerate(city_codes)
        if counts[city_index, training_periods].sum() > 0
    ]
    city_category = {code: index + 1 for index, code in enumerate(known_codes)}
    state_codes = sorted(NORTH_UF_NAMES)
    state_position = {code: index for index, code in enumerate(state_codes)}
    state_totals = {
        uf: counts[[index for index, code in enumerate(city_codes) if code[:2] == uf]].sum(axis=0)
        for uf in state_codes
    }
    xs: list[np.ndarray] = []
    regional_xs: list[np.ndarray] = []
    state_xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    cities: list[np.ndarray] = []
    sample_ufs: list[np.ndarray] = []
    season = _calendar_features(periods, origins)
    target_periods = np.asarray(
        [periods[index + 1 : index + FORECAST_HORIZON + 1] for index in origins],
        dtype=np.int32,
    )

    for city_index in range(len(city_codes)):
        city_series = counts[city_index]
        history_end = origins - reporting_lag
        history_start = history_end - lookback + 1
        city_history = np.stack(
            [city_series[left : right + 1] for left, right in zip(history_start, history_end)]
        )
        city_targets = np.stack(
            [city_series[index + 1 : index + FORECAST_HORIZON + 1] for index in origins]
        )
        xs.append(np.log1p(city_history).astype(np.float32))
        uf_code = city_codes[city_index][:2]
        regional_series = state_totals[uf_code]
        regional_features = np.stack(
            [
                regional_series[history_end],
                np.stack([regional_series[end - 3 : end + 1].sum() for end in history_end]),
                np.stack([regional_series[end - 11 : end + 1].sum() for end in history_end]),
                np.stack([regional_series[end - 51 : end + 1].sum() for end in history_end]),
            ],
            axis=1,
        )
        regional_xs.append(np.log1p(regional_features).astype(np.float32))
        state_onehot = np.zeros((len(origins), len(state_codes)), dtype=np.float32)
        state_onehot[:, state_position[uf_code]] = 1.0
        state_xs.append(state_onehot)
        ys.append(city_targets.astype(np.float32))
        cities.append(np.full(len(origins), city_category.get(city_codes[city_index], 0), dtype=np.int64))
        sample_ufs.append(np.full(len(origins), city_codes[city_index][:2], dtype="U2"))

    return Examples(
        history=np.concatenate(xs),
        regional_history=np.concatenate(regional_xs),
        state_features=np.concatenate(state_xs),
        municipality=np.concatenate(cities),
        season=np.tile(season, (len(city_codes), 1)),
        target=np.concatenate(ys),
        target_year=np.tile(target_periods[:, :, 0], (len(city_codes), 1)),
        target_week=np.tile(target_periods[:, :, 1], (len(city_codes), 1)),
        sample_uf=np.concatenate(sample_ufs),
        city_codes=known_codes,
    )


def _mask(examples: Examples, year: int, cutoff_key: int | None = None) -> np.ndarray:
    result = examples.target_year == year
    if cutoff_key is not None:
        keys = examples.target_year.astype(np.int32) * 100 + examples.target_week.astype(np.int32)
        result &= keys <= cutoff_key
    return result


def _dispersion(target: np.ndarray, mask: np.ndarray) -> float:
    values = target[mask]
    if not values.size:
        return 1.0
    mean = float(np.mean(values))
    variance = float(np.var(values))
    if variance <= mean + 1e-8:
        return 100_000.0
    return float(np.clip(mean * mean / (variance - mean), 0.1, 100_000.0))


def _distribution_metrics(
    actual: np.ndarray,
    mean: np.ndarray,
    dispersion: np.ndarray,
    point_prediction: np.ndarray | None = None,
) -> dict[str, float | int]:
    nbinom = _negative_binomial()
    actual = np.asarray(actual, dtype=np.float64)
    mean = np.maximum(np.asarray(mean, dtype=np.float64), 1e-8)
    r = np.maximum(np.asarray(dispersion, dtype=np.float64), 1e-5)
    prob = r / (r + mean)
    pred50 = nbinom.ppf(0.5, r, prob)
    point = mean if point_prediction is None else np.asarray(point_prediction, dtype=np.float64)
    interval_scores: list[np.ndarray] = []
    coverage: dict[str, float] = {}
    width: dict[str, float] = {}
    weighted = 0.5 * np.abs(actual - pred50)
    for confidence, alpha in ((0.8, 0.2), (0.95, 0.05)):
        lower = nbinom.ppf(alpha / 2, r, prob)
        upper = nbinom.ppf(1 - alpha / 2, r, prob)
        interval_score = upper - lower
        interval_score += (2 / alpha) * np.maximum(lower - actual, 0)
        interval_score += (2 / alpha) * np.maximum(actual - upper, 0)
        interval_scores.append(interval_score)
        weighted += (alpha / 2) * interval_score
        suffix = str(int(confidence * 100))
        coverage[f"coverage_{suffix}"] = float(np.mean((actual >= lower) & (actual <= upper)))
        width[f"mean_width_{suffix}"] = float(np.mean(upper - lower))
    wis = weighted / (0.5 + len(interval_scores))
    return {
        "n": int(actual.size),
        "mae": float(np.mean(np.abs(actual - mean))),
        "point_mae": float(np.mean(np.abs(actual - point))),
        "rmse": float(np.mean(np.square(actual - mean)) ** 0.5),
        "wis": float(np.mean(wis)),
        **coverage,
        **width,
    }


def _baseline_means(examples: Examples, lag: int, lookback: int) -> dict[str, np.ndarray]:
    sample_count = len(examples.target)
    histories = np.expm1(examples.history)
    recent = np.maximum(histories[:, -4:], 0)
    persistence = np.repeat(histories[:, -1:], FORECAST_HORIZON, axis=1)
    moving = np.repeat(np.mean(recent, axis=1, keepdims=True), FORECAST_HORIZON, axis=1)
    seasonal = np.empty((sample_count, FORECAST_HORIZON), dtype=np.float32)
    # The input array starts after the lookback, so the 52-week seasonal value is in the window.
    for horizon in range(FORECAST_HORIZON):
        position = lag + horizon
        if 0 <= position < lookback:
            seasonal[:, horizon] = histories[:, position]
        else:
            seasonal[:, horizon] = moving[:, horizon]
    return {
        "always_zero": np.zeros_like(examples.target, dtype=np.float32),
        "persistence": np.maximum(persistence, 0),
        "moving_average_4": np.maximum(moving, 0),
        "seasonal_naive_52": np.maximum(seasonal, 0),
    }


def _metrics_by_horizon(
    examples: Examples,
    prediction: np.ndarray,
    mask: np.ndarray,
    r: float | np.ndarray,
    point_prediction: np.ndarray | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"overall": {}, "horizons": {}}
    global_selected = mask
    if global_selected.any():
        result["overall"] = _distribution_metrics(
            examples.target[global_selected],
            prediction[global_selected],
            np.broadcast_to(r, prediction.shape)[global_selected],
            None if point_prediction is None else point_prediction[global_selected],
        )
    else:
        result["overall"] = {"n": 0, "warning": "Nenhum alvo elegível neste período."}
    for horizon in range(FORECAST_HORIZON):
        selected = mask[:, horizon]
        if selected.any():
            result["horizons"][f"{horizon + 1}_week"] = _distribution_metrics(
                examples.target[selected, horizon],
                prediction[selected, horizon],
                np.broadcast_to(r, prediction.shape)[selected, horizon],
                None if point_prediction is None else point_prediction[selected, horizon],
            )
        else:
            result["horizons"][f"{horizon + 1}_week"] = {"n": 0}
    return result


def _metrics_with_uf(
    examples: Examples,
    prediction: np.ndarray,
    mask: np.ndarray,
    dispersion: float | np.ndarray,
    point_prediction: np.ndarray | None = None,
) -> dict[str, Any]:
    result = _metrics_by_horizon(examples, prediction, mask, dispersion, point_prediction)
    result["by_uf"] = {
        NORTH_UF_NAMES[uf_code]: _metrics_by_horizon(
            examples,
            prediction,
            mask & (examples.sample_uf == uf_code)[:, None],
            dispersion,
            point_prediction,
        )
        for uf_code in sorted(np.unique(examples.sample_uf))
    }
    return result


def _headline_mae_skill(metrics: dict[str, Any]) -> dict[str, Any]:
    """Compare the model's MAE-optimal point forecast with a preselected baseline."""
    baseline_names = (
        "always_zero",
        "persistence",
        "moving_average_4",
        "seasonal_naive_52",
    )
    pooled_errors = {name: 0.0 for name in baseline_names}
    pooled_targets = {name: 0 for name in baseline_names}
    for year_metrics in metrics["backtests"].values():
        for name in baseline_names:
            result = year_metrics[name]["overall"]
            count = int(result.get("n", 0))
            if count:
                pooled_errors[name] += float(result["point_mae"]) * count
                pooled_targets[name] += count

    eligible = [name for name in baseline_names if pooled_targets[name] > 0]
    if not eligible:
        raise ValueError("Os backtests de 2022–2024 não permitem escolher uma referência.")
    reference_name = min(
        eligible,
        key=lambda name: pooled_errors[name] / pooled_targets[name],
    )
    reference_backtest_mae = pooled_errors[reference_name] / pooled_targets[reference_name]
    test = metrics["metrics"]["test_2026_partial"]
    model_result = test["neural_mlp_nb"]["overall"]
    reference_result = test[reference_name]["overall"]
    model_mae = float(model_result["point_mae"])
    reference_mae = float(reference_result["point_mae"])
    if reference_mae <= 0:
        raise ValueError("A MAE da referência é zero; não é possível calcular o skill relativo.")
    unrounded_score = 100.0 * (1.0 - model_mae / reference_mae)
    score = 0.0 if abs(unrounded_score) < 0.05 else round(unrounded_score, 1)
    mature_through = metrics["split"].get("mature_through")
    return {
        "label": "Redução do MAE vs. referência (%)",
        "value_pct": score,
        "unrounded_value_pct": unrounded_score,
        "model_point_mae_cases_per_forecast_target": model_mae,
        "reference_baseline": reference_name,
        "reference_point_mae_cases_per_forecast_target": reference_mae,
        "reference_backtest_mae_2022_2024": reference_backtest_mae,
        "reference_selection_period": (
            "2022–2024; menor MAE agregado entre sempre zero, persistência, "
            "média móvel de 4 semanas e sazonalidade de 52 semanas"
        ),
        "evaluation_period": f"2026 parcial, até {mature_through}",
        "n_forecast_target_pairs": int(model_result["n"]),
        "interpretation": (
            "positivo: erro absoluto menor que a referência; zero: empate; "
            "negativo: erro absoluto maior que a referência"
        ),
        "status": (
            "diagnóstico retrospectivo; 2026 já foi consultado durante o desenvolvimento "
            "e não é uma avaliação independente"
        ),
    }


def write_skill_summary(reports: list[dict[str, Any]], output_root: Path) -> Path:
    """Write one communicable score per disease from this fit invocation."""
    baseline_labels = {
        "always_zero": "sempre zero",
        "persistence": "persistência",
        "moving_average_4": "média móvel de 4 semanas",
        "seasonal_naive_52": "sazonal de 52 semanas",
    }
    rows = []
    for report in reports:
        score = report["headline_score"]
        rows.append(
            {
                "doenca": report["disease"],
                "reducao_mae_pct_vs_referencia": score["value_pct"],
                "referencia": baseline_labels[score["reference_baseline"]],
                "periodo_avaliado": score["evaluation_period"],
                "mae_modelo": score["model_point_mae_cases_per_forecast_target"],
                "mae_referencia": score["reference_point_mae_cases_per_forecast_target"],
                "pares_previsao_alvo": score["n_forecast_target_pairs"],
                "status": score["status"],
            }
        )
    output_path = output_root / "reports" / "disease_skill_summary.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    return output_path


def _torch_modules():
    try:
        import torch
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as error:
        raise RuntimeError(
            "PyTorch não está instalado. Instale com: pip install -e '.[train]'"
        ) from error
    return torch, DataLoader, TensorDataset


def _predict_arrays(model, examples: Examples, device: str, batch_size: int = 4096):
    torch, DataLoader, TensorDataset = _torch_modules()
    data = TensorDataset(
        torch.from_numpy(examples.history),
        torch.from_numpy(examples.regional_history),
        torch.from_numpy(examples.state_features),
        torch.from_numpy(examples.municipality),
        torch.from_numpy(examples.season),
    )
    loader = DataLoader(data, batch_size=batch_size, shuffle=False)
    means: list[np.ndarray] = []
    dispersions: list[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for history, regional, state, city, season in loader:
            mu, r = model(
                history.to(device),
                regional.to(device),
                state.to(device),
                city.to(device),
                season.to(device),
            )
            means.append(mu.cpu().numpy())
            dispersions.append(r.cpu().numpy())
    return np.concatenate(means), np.concatenate(dispersions)


def _train_model(
    examples: Examples,
    train_mask: np.ndarray,
    validation_mask: np.ndarray,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    seed: int,
    device: str,
):
    torch, DataLoader, TensorDataset = _torch_modules()
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    train_rows = train_mask.any(axis=1)
    val_rows = validation_mask.any(axis=1)
    if not train_rows.any() or not validation_mask.any():
        raise ValueError("O split precisa conter alvos de treino e de validação.")
    train_data = TensorDataset(
        torch.from_numpy(examples.history[train_rows]),
        torch.from_numpy(examples.regional_history[train_rows]),
        torch.from_numpy(examples.state_features[train_rows]),
        torch.from_numpy(examples.municipality[train_rows]),
        torch.from_numpy(examples.season[train_rows]),
        torch.from_numpy(examples.target[train_rows]),
        torch.from_numpy(train_mask[train_rows].astype(np.float32)),
    )
    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True)

    val_data = TensorDataset(
        torch.from_numpy(examples.history[val_rows]),
        torch.from_numpy(examples.regional_history[val_rows]),
        torch.from_numpy(examples.state_features[val_rows]),
        torch.from_numpy(examples.municipality[val_rows]),
        torch.from_numpy(examples.season[val_rows]),
        torch.from_numpy(examples.target[val_rows]),
        torch.from_numpy(validation_mask[val_rows].astype(np.float32)),
    )
    val_loader = DataLoader(val_data, batch_size=batch_size * 2, shuffle=False)
    model = build_model(len(examples.city_codes) + 1).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    best_state = None
    best_loss = float("inf")
    best_mae = float("inf")
    best_epoch = 0
    patience = 6
    stale = 0
    history: list[dict[str, float]] = []
    nbinom = _negative_binomial()

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss_total = 0.0
        train_target_count = 0
        for x, regional, state, city, season, target, mask in train_loader:
            x, regional, state = x.to(device), regional.to(device), state.to(device)
            city, season = city.to(device), season.to(device)
            target, mask = target.to(device), mask.to(device)
            optimizer.zero_grad(set_to_none=True)
            mu, dispersion = model(x, regional, state, city, season)
            loss = negative_binomial_nll(mu, dispersion, target, mask)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            batch_target_count = int(mask.sum().item())
            train_loss_total += float(loss.detach().cpu()) * batch_target_count
            train_target_count += batch_target_count

        model.eval()
        validation_loss_total = 0.0
        validation_target_count = 0
        validation_absolute_error_total = 0.0
        with torch.no_grad():
            for x, regional, state, city, season, target, mask in val_loader:
                mu, dispersion = model(
                    x.to(device),
                    regional.to(device),
                    state.to(device),
                    city.to(device),
                    season.to(device),
                )
                batch_target_count = int(mask.sum().item())
                batch_loss = negative_binomial_nll(
                    mu, dispersion, target.to(device), mask.to(device)
                )
                validation_loss_total += float(batch_loss.cpu()) * batch_target_count
                validation_target_count += batch_target_count
                mean_np = np.maximum(mu.cpu().numpy(), 1e-8)
                dispersion_np = np.maximum(dispersion.cpu().numpy(), 1e-5)
                probability_np = dispersion_np / (dispersion_np + mean_np)
                median_np = nbinom.ppf(0.5, dispersion_np, probability_np)
                target_np = target.cpu().numpy()
                valid_np = mask.cpu().numpy().astype(bool)
                validation_absolute_error_total += float(
                    np.abs(target_np - median_np)[valid_np].sum()
                )
        train_loss = train_loss_total / max(train_target_count, 1)
        val_loss = validation_loss_total / max(validation_target_count, 1)
        val_mae = validation_absolute_error_total / max(validation_target_count, 1)
        history.append(
            {
                "epoch": epoch,
                "train_nll": train_loss,
                "validation_nll": val_loss,
                "validation_point_mae": val_mae,
            }
        )
        print(
            f"época {epoch:02d}: NLL treino={train_loss:.4f}; "
            f"NLL validação={val_loss:.4f}; MAE mediana validação={val_mae:.4f}"
        )
        if val_mae < best_mae - 1e-5:
            best_mae = val_mae
            best_loss = val_loss
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                break
    if best_state is None:
        raise RuntimeError("O treino não produziu um checkpoint válido.")
    model.load_state_dict(best_state)
    return model, {
        "best_epoch": best_epoch,
        "selection_metric": "validation median point MAE",
        "best_validation_point_mae": best_mae,
        "best_validation_nll": best_loss,
        "history": history,
    }


def fit_disease(
    panel_path: Path,
    raw_root: Path,
    disease: str,
    output_root: Path,
    reporting_lag: int = DEFAULT_REPORTING_LAG,
    epochs: int = 30,
    batch_size: int = 512,
    learning_rate: float = 1e-3,
    seed: int = 42,
    device: str = "auto",
    start_year: int = 2016,
) -> dict[str, Any]:
    if reporting_lag < 0:
        raise ValueError("lag de notificação não pode ser negativo.")
    if epochs < 1 or batch_size < 1 or learning_rate <= 0:
        raise ValueError("epochs, batch-size e learning-rate devem ser positivos.")
    torch, _, _ = _torch_modules()
    frame = pd.read_csv(panel_path, dtype={"municipality_code": "string", "disease": "string"})
    panel_sha256 = hashlib.sha256(panel_path.read_bytes()).hexdigest()
    quality_path = panel_path.with_name(panel_path.stem + "_quality.json")
    panel_quality: dict[str, Any] = {}
    panel_quality_sha256 = None
    if quality_path.exists():
        panel_quality = json.loads(quality_path.read_text(encoding="utf-8"))
        panel_quality_sha256 = hashlib.sha256(quality_path.read_bytes()).hexdigest()
    case_definition = panel_quality.get("_metadata", {}).get("case_definition", "unknown")
    counts, cities, periods, snapshot_info = _dense_counts(
        frame, disease, raw_root, reporting_lag, start_year
    )
    examples = build_examples(counts, cities, periods, reporting_lag)
    train_mask = examples.target_year <= 2024
    validation_mask = examples.target_year == 2025
    cutoff_key = int(snapshot_info["mature_through_key"])
    test_mask = _mask(examples, 2026, cutoff_key)
    if not test_mask.any():
        raise ValueError(
            f"Não há alvos de 2026 maduros até {snapshot_info['mature_through']} para avaliar."
        )
    train_dispersion = _dispersion(examples.target, train_mask)
    chosen_device = (
        "cuda" if device == "auto" and torch.cuda.is_available() else
        "cpu" if device == "auto" else device
    )
    if chosen_device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("GPU CUDA solicitada, mas não está disponível.")

    model, training_info = _train_model(
        examples,
        train_mask,
        validation_mask,
        epochs,
        batch_size,
        learning_rate,
        seed,
        chosen_device,
    )
    neural_mean, neural_r = _predict_arrays(model, examples, chosen_device)
    neural_probability = neural_r / (neural_r + np.maximum(neural_mean, 1e-8))
    neural_point = _negative_binomial().ppf(0.5, neural_r, neural_probability)
    metrics: dict[str, Any] = {
        "disease": disease,
        "weekly_panel_sha256": panel_sha256,
        "panel_quality_sha256": panel_quality_sha256,
        "preparation": panel_quality.get("_metadata", {}),
        "case_definition": {
            "name": case_definition,
            "individual_notification_tp_not": "2",
            "discarded_classi_fin_by_disease": {
                name: sorted(mapping["discarded"])
                for name, mapping in CLASSIFICATION_CODES.items()
            },
            "other_disease_classi_fin_excluded": {
                name: sorted(mapping["other_disease"])
                for name, mapping in CLASSIFICATION_CODES.items()
            },
            "confirmed_classi_fin_by_disease": {
                name: sorted(mapping["confirmed"])
                for name, mapping in CLASSIFICATION_CODES.items()
            },
        },
        "split": {
            "train_targets": "até 2024",
            "validation_targets": "2025",
            "test_targets": "2026, até a maturidade disponível",
            **snapshot_info,
        },
        "data_limitations": [
            "Dados oficiais usados na versão corrente; snapshots históricos de revisão podem não existir.",
            "A defasagem de entrada é uma aproximação operacional e não reconstitui o estado histórico do Sinan.",
            "O teste de 2026 é parcial; não representa o ano completo.",
        ],
        "training": {
            **training_info,
            "seed": seed,
            "device": chosen_device,
            "lookback_weeks": LOOKBACK,
            "forecast_horizon_weeks": FORECAST_HORIZON,
            "reporting_lag_weeks": reporting_lag,
            "start_year": start_year,
        },
        "metrics": {},
    }
    baseline_predictions = _baseline_means(examples, reporting_lag, LOOKBACK)
    for period_name, mask in (
        ("validation_2025", validation_mask),
        ("test_2026_partial", test_mask),
    ):
        metrics["metrics"][period_name] = {
            "neural_mlp_nb": _metrics_with_uf(
                examples, neural_mean, mask, neural_r, neural_point
            )
        }
        for name, prediction in baseline_predictions.items():
            metrics["metrics"][period_name][name] = _metrics_with_uf(
                examples,
                prediction,
                mask,
                train_dispersion,
            )

    # Backtests das referências usam apenas valores anteriores ao respectivo ano.
    metrics["backtests"] = {}
    for year in (2022, 2023, 2024):
        mask = examples.target_year == year
        fold_training = examples.target_year < year
        fold_r = _dispersion(examples.target, fold_training)
        metrics["backtests"][str(year)] = {
            name: _metrics_with_uf(examples, prediction, mask, fold_r)
            for name, prediction in baseline_predictions.items()
        }
    metrics["headline_score"] = _headline_mae_skill(metrics)

    output_root.mkdir(parents=True, exist_ok=True)
    model_dir = output_root / "models"
    report_dir = output_root / "reports"
    model_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = model_dir / f"{disease}.pt"
    torch.save(
        {
            "state_dict": model.cpu().state_dict(),
            "disease": disease,
            # The embedding vocabulary excludes cities without training cases.
            # Keep this exact order so inference IDs match the trained embedding rows.
            "municipality_codes": examples.city_codes,
            "lookback_weeks": LOOKBACK,
            "forecast_horizon_weeks": FORECAST_HORIZON,
            "reporting_lag_weeks": reporting_lag,
            "start_year": start_year,
            "training_info": training_info,
            "snapshot_info": snapshot_info,
            "weekly_panel_sha256": panel_sha256,
            "seed": seed,
        },
        checkpoint,
    )
    report_path = report_dir / f"{disease}_metrics.json"
    report_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Modelo: {checkpoint}; métricas: {report_path}; "
        f"redução do MAE vs. referência={metrics['headline_score']['value_pct']:+.1f}%"
    )
    return metrics


def _build_forecast_examples(
    frame: pd.DataFrame,
    disease: str,
    raw_root: Path,
    reporting_lag: int,
    as_of: date,
    start_year: int = 2016,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    list[str],
    list[tuple[int, int]],
    tuple[int, int],
]:
    counts, present_cities, periods, info = _dense_counts(
        frame, disease, raw_root, reporting_lag, start_year
    )
    asof_year, asof_week = epi_from_date(as_of)
    required_year, required_week = shift_epi(asof_year, asof_week, -reporting_lag)
    available_key = int(info["mature_through_key"])
    required_key = epi_key(required_year, required_week)
    if required_key > available_key:
        raise ValueError(
            f"Os dados maduros vão até {info['mature_through']}; atualize a fonte ou use uma data de emissão anterior."
        )
    city_index = {city: i for i, city in enumerate(present_cities)}
    periods_index = {epi_key(year, week): i for i, (year, week) in enumerate(periods)}
    history_end_key = epi_key(required_year, required_week)
    if history_end_key not in periods_index:
        raise ValueError("O painel não alcança o fim da janela histórica disponível.")
    end_index = periods_index[history_end_key]
    if end_index < LOOKBACK - 1:
        raise ValueError("Histórico insuficiente para gerar uma previsão de 52 semanas.")
    target_periods = [shift_epi(asof_year, asof_week, step) for step in range(1, 5)]
    cities = present_cities
    season = np.zeros((len(cities), 8), dtype=np.float32)
    for i, (year, week) in enumerate(target_periods):
        fraction = (week - 0.5) / weeks_in_epi_year(year)
        season[:, 2 * i] = np.sin(2 * np.pi * fraction)
        season[:, 2 * i + 1] = np.cos(2 * np.pi * fraction)
    history = np.stack(
        [np.log1p(counts[city_index[city], end_index - LOOKBACK + 1 : end_index + 1]) for city in cities]
    ).astype(np.float32)
    state_codes = sorted(NORTH_UF_NAMES)
    state_position = {code: index for index, code in enumerate(state_codes)}
    city_states = np.asarray([city[:2] for city in cities])
    regional = np.empty((len(cities), 4), dtype=np.float32)
    state = np.zeros((len(cities), len(state_codes)), dtype=np.float32)
    for uf_code, state_index in state_position.items():
        selected = np.flatnonzero(city_states == uf_code)
        state_counts = counts[selected].sum(axis=0)
        regional_values = np.log1p(
            [
                state_counts[end_index],
                state_counts[end_index - 3 : end_index + 1].sum(),
                state_counts[end_index - 11 : end_index + 1].sum(),
                state_counts[end_index - 51 : end_index + 1].sum(),
            ]
        ).astype(np.float32)
        regional[selected] = regional_values
        state[selected, state_index] = 1.0
    return history, regional, state, season, cities, target_periods, (asof_year, asof_week)


def predict_disease(
    panel_path: Path,
    raw_root: Path,
    disease: str,
    output_root: Path,
    as_of: date,
    device: str = "auto",
    level: str = "municipality",
    uf_filter: str | None = None,
    municipality_filter: str | None = None,
) -> pd.DataFrame:
    nbinom = _negative_binomial()
    torch, _, _ = _torch_modules()
    checkpoint_path = output_root / "models" / f"{disease}.pt"
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Modelo não encontrado: {checkpoint_path}; execute fit primeiro.")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    known_cities = checkpoint["municipality_codes"]
    lag = checkpoint["reporting_lag_weeks"]
    start_year = checkpoint.get("start_year", 2016)
    frame = pd.read_csv(panel_path, dtype={"municipality_code": "string", "disease": "string"})
    history, regional, state, season, cities, target_periods, origin = _build_forecast_examples(
        frame, disease, raw_root, lag, as_of, start_year
    )
    city_to_id = {city: index + 1 for index, city in enumerate(known_cities)}
    location = np.asarray([city_to_id.get(city, 0) for city in cities], dtype=np.int64)
    chosen_device = "cuda" if device == "auto" and torch.cuda.is_available() else "cpu" if device == "auto" else device
    model = build_model(len(known_cities) + 1, checkpoint["lookback_weeks"])
    model.load_state_dict(checkpoint["state_dict"])
    model.to(chosen_device).eval()
    with torch.no_grad():
        mean, dispersion = model(
            torch.from_numpy(history).to(chosen_device),
            torch.from_numpy(regional).to(chosen_device),
            torch.from_numpy(state).to(chosen_device),
            torch.from_numpy(location).to(chosen_device),
            torch.from_numpy(season).to(chosen_device),
        )
    mean_np, dispersion_np = mean.cpu().numpy(), dispersion.cpu().numpy()
    records: list[dict[str, Any]] = []
    city_position = {city: index for index, city in enumerate(cities)}
    for city_index, city in enumerate(cities):
        for horizon, (year, week) in enumerate(target_periods, start=1):
            mu, r = float(mean_np[city_index, horizon - 1]), float(dispersion_np[city_index, horizon - 1])
            probability = r / (r + mu)
            records.append(
                {
                    "disease": disease,
                    "territory_level": "municipality",
                    "municipality_code_sinan": city,
                    "uf": NORTH_UF_NAMES[city[:2]],
                    "origin_epi_year": origin[0],
                    "origin_epi_week": origin[1],
                    "horizon_weeks": horizon,
                    "target_epi_year": year,
                    "target_epi_week": week,
                    "expected_cases": mu,
                    "probability_at_least_one_case": 1 - probability**r,
                    "lower_80": int(nbinom.ppf(0.1, r, probability)),
                    "upper_80": int(nbinom.ppf(0.9, r, probability)),
                    "lower_95": int(nbinom.ppf(0.025, r, probability)),
                    "upper_95": int(nbinom.ppf(0.975, r, probability)),
                    "reporting_lag_weeks": lag,
                    "model": "global_mlp_negative_binomial",
                }
            )
    result = pd.DataFrame.from_records(records)
    if municipality_filter:
        requested = municipality_filter.strip().replace(".0", "")
        requested = "".join(character for character in requested if character.isdigit())
        if len(requested) == 7:
            requested = requested[:6]
        result = result.loc[result["municipality_code_sinan"] == requested]
        if result.empty:
            raise ValueError(f"O código municipal {municipality_filter} não está no painel histórico.")
    if uf_filter:
        result = result.loc[result["uf"] == uf_filter.upper()]
        if result.empty:
            raise ValueError(f"Não há municípios no painel para a UF {uf_filter.upper()}.")
    if level == "uf":
        rng = np.random.default_rng(42)
        state_records: list[dict[str, Any]] = []
        for uf, state_frame in result.groupby("uf", sort=True):
            for horizon in range(1, 5):
                group = state_frame.loc[state_frame["horizon_weeks"] == horizon]
                mus = group["expected_cases"].to_numpy(dtype=float)
                dispersions = np.asarray(
                    [float(dispersion_np[city_position[code], horizon - 1])
                     for code in group["municipality_code_sinan"]], dtype=float
                )
                probabilities = dispersions / (dispersions + mus)
                draws = nbinom.rvs(
                    dispersions[:, None],
                    probabilities[:, None],
                    size=(len(mus), 20_000),
                    random_state=rng,
                )
                samples = draws.sum(axis=0, dtype=np.int64)
                year, week = target_periods[horizon - 1]
                state_records.append(
                    {
                        "disease": disease,
                        "territory_level": "uf",
                        "municipality_code_sinan": "",
                        "uf": uf,
                        "origin_epi_year": origin[0],
                        "origin_epi_week": origin[1],
                        "horizon_weeks": horizon,
                        "target_epi_year": year,
                        "target_epi_week": week,
                        "expected_cases": float(mus.sum()),
                        "probability_at_least_one_case": float(1 - np.prod(probabilities**dispersions)),
                        "lower_80": int(np.quantile(samples, 0.1, method="inverted_cdf")),
                        "upper_80": int(np.quantile(samples, 0.9, method="inverted_cdf")),
                        "lower_95": int(np.quantile(samples, 0.025, method="inverted_cdf")),
                        "upper_95": int(np.quantile(samples, 0.975, method="inverted_cdf")),
                        "reporting_lag_weeks": lag,
                        "model": "global_mlp_negative_binomial_independent_municipal_draws",
                    }
                )
        result = pd.DataFrame.from_records(state_records)
    elif level != "municipality":
        raise ValueError("level deve ser 'municipality' ou 'uf'")
    else:
        result["territory_level"] = "municipality"
    level_suffix = "_uf" if level == "uf" else "_municipality"
    path = output_root / "forecasts" / f"{disease}_{as_of.isoformat()}{level_suffix}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(path, index=False)
    print(f"Previsões salvas: {path}")
    return result
