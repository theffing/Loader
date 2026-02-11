"""Source table mapping for market data providers."""

from __future__ import annotations

SOURCE_TABLES = {
    "tiingo": {
        "data": "ticker_data",
        "meta": "ticker_metadata",
    },
    "fmp": {
        "data": "ticker_data_fmp",
        "meta": "ticker_metadata_fmp",
    },
    "yfinance": {
        "data": "ticker_data_yfinance",
        "meta": "ticker_metadata_yfinance",
    },
}


def normalize_source(source: str | None) -> str:
    if not source:
        return "tiingo"
    return source.strip().lower()


def get_source_tables(source: str | None) -> tuple[str, str]:
    normalized = normalize_source(source)
    tables = SOURCE_TABLES.get(normalized)
    if not tables:
        raise ValueError(f"Unknown source: {source}")
    return tables["data"], tables["meta"]


def list_sources() -> list[str]:
    return sorted(SOURCE_TABLES.keys())
