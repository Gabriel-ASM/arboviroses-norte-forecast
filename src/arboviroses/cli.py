"""Comandos de ingestão, painel, treino e consulta de previsões."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .catalog import DISEASES, catalog_resources, download_years


def _disease_list(value: str) -> list[str]:
    diseases = [item.strip().casefold() for item in value.split(",") if item.strip()]
    unknown = sorted(set(diseases) - set(DISEASES))
    if unknown:
        raise argparse.ArgumentTypeError(f"Doenças desconhecidas: {', '.join(unknown)}")
    if not diseases:
        raise argparse.ArgumentTypeError("Informe ao menos uma doença.")
    return diseases


def _add_data_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"), help="Diretório dos ZIPs e manifesto")
    parser.add_argument("--panel", type=Path, default=Path("data/processed/weekly_panel.csv"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arboviroses",
        description="Ingestão e previsão municipal/semanal de arboviroses do Sinan.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    catalog = subparsers.add_parser("catalog", help="Lista os anos e formatos no catálogo oficial")
    catalog.add_argument("--diseases", type=_disease_list, default=_disease_list("dengue,chikungunya,zika"))

    download = subparsers.add_parser("download", help="Baixa arquivos anuais oficiais para uso local")
    download.add_argument("--diseases", type=_disease_list, default=_disease_list("dengue,chikungunya,zika"))
    download.add_argument("--start-year", type=int, default=None, help="Padrão: histórico completo disponível por doença")
    download.add_argument("--end-year", type=int, default=2026)
    download.add_argument("--raw-dir", type=Path, default=Path("data/raw"))

    prepare = subparsers.add_parser("prepare", help="Valida e agrega os registros por município e semana")
    _add_data_paths(prepare)
    prepare.add_argument("--diseases", type=_disease_list, default=_disease_list("dengue,chikungunya,zika"))
    prepare.add_argument("--case-definition", choices=("probable", "confirmed"), default="probable")
    prepare.add_argument(
        "--start-year",
        type=int,
        default=2016,
        help="Ano inicial da janela comparável; classificações anteriores não estão homologadas.",
    )
    prepare.add_argument(
        "--registry-mode",
        choices=("auto", "required", "observed"),
        default="auto",
        help="Obtém o cadastro municipal do IBGE; 'observed' dispensa a conexão externa.",
    )

    fit = subparsers.add_parser("fit", help="Treina baselines, MLP binomial negativo e calcula métricas")
    _add_data_paths(fit)
    fit.add_argument("--diseases", type=_disease_list, default=_disease_list("dengue,chikungunya,zika"))
    fit.add_argument("--output-dir", type=Path, default=Path("outputs"))
    fit.add_argument("--lag-weeks", type=int, default=8)
    fit.add_argument(
        "--start-year",
        type=int,
        default=2016,
        help="Ano inicial do histórico usado pelo modelo (mínimo 2016).",
    )
    fit.add_argument("--epochs", type=int, default=30)
    fit.add_argument("--batch-size", type=int, default=512)
    fit.add_argument("--learning-rate", type=float, default=1e-3)
    fit.add_argument("--seed", type=int, default=42)
    fit.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")

    predict = subparsers.add_parser("predict", help="Gera previsão para as quatro próximas semanas")
    _add_data_paths(predict)
    predict.add_argument("--diseases", type=_disease_list, default=_disease_list("dengue,chikungunya,zika"))
    predict.add_argument("--output-dir", type=Path, default=Path("outputs"))
    predict.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    predict.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    predict.add_argument("--level", choices=("municipality", "uf"), default="municipality")
    predict.add_argument("--uf", choices=("AC", "AP", "AM", "PA", "RO", "RR", "TO"))
    predict.add_argument("--municipality", help="Código Sinan de 6 dígitos ou IBGE de 7 dígitos")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "catalog":
            for disease in args.diseases:
                resources = catalog_resources(DISEASES[disease])
                annual = [
                    resource for resource in resources
                    if str(resource.get("format", "")).casefold() in {"csv", "parquet"}
                    and any(str(year) in str(resource.get("name", "")) for year in range(2000, 2031))
                ]
                print(f"{disease}: {len(annual)} recursos anuais CSV/Parquet")
                for resource in annual:
                    print(
                        f"  {resource.get('name')} | {resource.get('format')} | "
                        f"atualizado {resource.get('last_modified')}"
                    )
            return 0

        if args.command == "download":
            records = download_years(args.raw_dir, args.diseases, args.start_year, args.end_year)
            print(f"Manifesto: {args.raw_dir / 'manifest.json'} ({len(records)} arquivos processados)")
            return 0

        if args.command == "prepare":
            from .panel import build_weekly_panel

            _, stats = build_weekly_panel(
                args.raw_dir,
                args.panel,
                args.diseases,
                args.case_definition,
                args.registry_mode,
                start_year=args.start_year,
            )
            print(json.dumps(stats, ensure_ascii=False, indent=2))
            print(f"Painel salvo: {args.panel}")
            return 0

        if args.command == "fit":
            from .training import fit_disease, write_wape_summary

            reports = []
            for disease in args.diseases:
                reports.append(
                    fit_disease(
                        args.panel,
                        args.raw_dir,
                        disease,
                        args.output_dir,
                        reporting_lag=args.lag_weeks,
                        epochs=args.epochs,
                        batch_size=args.batch_size,
                        learning_rate=args.learning_rate,
                        seed=args.seed,
                        device=args.device,
                        start_year=args.start_year,
                    )
                )
            summary_path = write_wape_summary(reports, args.output_dir)
            print(f"Resumo: {summary_path}")
            return 0

        if args.command == "predict":
            from .training import predict_disease

            for disease in args.diseases:
                predict_disease(
                    args.panel,
                    args.raw_dir,
                    disease,
                    args.output_dir,
                    args.as_of,
                    args.device,
                    args.level,
                    args.uf,
                    args.municipality,
                )
            return 0

    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    return 2
