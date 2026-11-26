"""Load the registry of share classes to collect."""

import json
from dataclasses import dataclass
from pathlib import Path

from .quotes import ISIN

type LookupFields = dict[str, type[str | int]]


@dataclass(frozen=True)
class Fund:
    isin: str
    name: str
    slug: str | None = None
    security_id: str | None = None
    share_class: str | None = None
    page_id: int | None = None


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate key in fund registry: {key!r}")
        result[key] = value
    return result


def load_funds(
    path: Path, lookup_fields: dict[str, LookupFields]
) -> dict[str, list[Fund]]:
    entries = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys
    )
    if not isinstance(entries, dict):
        raise TypeError("The fund registry must be keyed by ISIN")

    funds: dict[str, list[Fund]] = {}
    for isin, entry in entries.items():
        if not ISIN.fullmatch(isin) or not isinstance(entry, dict):
            raise ValueError(f"Invalid fund registry entry for {isin!r}")
        provider = entry.get("provider")
        if not isinstance(provider, str) or provider not in lookup_fields:
            raise ValueError(f"Unknown provider for {isin}: {provider!r}")

        fields = {"name": str} | lookup_fields[provider]
        if unexpected := entry.keys() - fields.keys() - {"provider"}:
            raise ValueError(
                f"Unexpected fields for {isin}: {', '.join(sorted(unexpected))}"
            )
        for field, expected_type in fields.items():
            value = entry.get(field)
            if (
                type(value) is not expected_type
                or (isinstance(value, str) and not value.strip())
                or (isinstance(value, int) and value <= 0)
            ):
                raise ValueError(f"Invalid or missing {field!r} for {isin}")

        fund = Fund(isin=isin, **{field: entry[field] for field in fields})
        funds.setdefault(provider, []).append(fund)
    return funds
