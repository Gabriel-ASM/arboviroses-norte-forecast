"""Calendário epidemiológico brasileiro (domingo a sábado)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import re


def epi_year_start(year: int) -> date:
    """Domingo da semana epidemiológica 1, que contém 4 de janeiro."""
    jan4 = date(year, 1, 4)
    return jan4 - timedelta(days=(jan4.weekday() + 1) % 7)


def weeks_in_epi_year(year: int) -> int:
    return (epi_year_start(year + 1) - epi_year_start(year)).days // 7


def epi_week_start(year: int, week: int) -> date:
    if week < 1 or week > weeks_in_epi_year(year):
        raise ValueError(f"Semana epidemiológica inválida: {year}-W{week:02d}")
    return epi_year_start(year) + timedelta(weeks=week - 1)


def epi_from_date(value: date | datetime) -> tuple[int, int]:
    day = value.date() if isinstance(value, datetime) else value
    year = day.year
    if day < epi_year_start(year):
        year -= 1
    elif day >= epi_year_start(year + 1):
        year += 1
    week = ((day - epi_year_start(year)).days // 7) + 1
    return year, week


def epi_key(year: int, week: int) -> int:
    epi_week_start(year, week)
    return year * 100 + week


def shift_epi(year: int, week: int, steps: int) -> tuple[int, int]:
    return epi_from_date(epi_week_start(year, week) + timedelta(weeks=steps))


def parse_epi_code(value: object) -> tuple[int, int] | None:
    """Interpreta SEM_PRI como AAAASS (ou AAAAS), sem inferir semana ISO."""
    if value is None:
        return None
    raw = re.sub(r"\.0$", "", str(value).strip())
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) not in (5, 6):
        return None
    year, week = int(digits[:4]), int(digits[4:])
    if year < 1900:
        return None
    try:
        epi_week_start(year, week)
    except ValueError:
        return None
    return year, week
