"""Publish incremental NAV releases to Cloudflare R2."""

import csv
import json
import logging
import os
from argparse import ArgumentParser
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from itertools import batched
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .collector import fetch_quotes
from .output import FIELDS
from .quotes import ISIN

ACTIVE = "active.json"
OBJECTS = "objects/"
PARALLELISM = 16
LOG = logging.getLogger(__name__)
type Rows = dict[str, dict[str, str]]
type Batch = tuple[str, dict[str, str], Rows]


class Conflict(Exception):
    """Another publisher advanced the active release."""


class Store:
    def __init__(self, client, bucket: str):
        self.client = client
        self.bucket = bucket

    def read(self, key: str) -> tuple[bytes, str] | None:
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise
        with result["Body"] as body:
            return body.read(), result["ETag"]

    def require(self, key: str) -> bytes:
        item = self.read(key)
        if item is None:
            raise ValueError(f"Archive object is missing: {key}")
        return item[0]

    def put(self, key: str, content: bytes, etag: str | None = None) -> None:
        condition = {"IfMatch": etag} if etag else {"IfNoneMatch": "*"}
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=key, Body=content, **condition
            )
        except ClientError as error:
            if error.response["ResponseMetadata"]["HTTPStatusCode"] in (409, 412):
                raise Conflict(key) from error
            raise

    def objects(self):
        pages = self.client.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=OBJECTS
        )
        for page in pages:
            yield from page.get("Contents", [])

    def delete(self, keys: Sequence[str]) -> None:
        result = self.client.delete_objects(
            Bucket=self.bucket,
            Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
        )
        if result.get("Errors"):
            raise ValueError(f"R2 failed to delete {len(result['Errors'])} objects")


def json_bytes(value) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode()


def csv_bytes(rows: Iterable[dict[str, str]]) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def read_rows(content: bytes) -> Rows:
    reader = csv.DictReader(StringIO(content.decode(), newline=""))
    if tuple(reader.fieldnames or ()) != FIELDS:
        raise ValueError("Unexpected NAV CSV columns")
    return {row["date"]: row for row in reader}


def validate(isin: str, rows: Rows) -> None:
    if ISIN.fullmatch(isin) is None:
        raise ValueError(f"Invalid share-class ISIN: {isin}")
    for day, row in rows.items():
        nav = Decimal(row["nav"])
        if (
            row["isin"] != isin
            or date.fromisoformat(day).isoformat() != day
            or not nav.is_finite()
            or nav <= 0
            or not row["currency"]
            or not row["source_url"]
        ):
            raise ValueError(f"Invalid observation for {isin} on {day}")


@dataclass
class Release:
    store: Store
    key: str | None
    previous: str | None
    etag: str | None
    shards: dict[str, dict]
    index: dict[str, str]

    @classmethod
    def load(cls, store: Store):
        item = store.read(ACTIVE)
        if item is None:
            return cls(store, None, None, None, {}, {})
        body, etag = item
        pointer = json.loads(body)
        key = pointer["current"]
        release = json.loads(store.require(key))
        index = release["shards"]
        shards = {
            suffix: json.loads(store.require(shard)) for suffix, shard in index.items()
        }
        return cls(store, key, pointer["previous"], etag, shards, index)

    def write(self, suffix: str, content: bytes) -> str:
        key = f"{OBJECTS}{uuid4().hex}/{suffix}"
        self.store.put(key, content)
        return key

    def update(self, batch: Batch) -> tuple[str, dict | None]:
        isin, fund, rows = batch
        validate(isin, rows)
        existing = self.shards.get(isin[-2:], {}).get(isin)
        if existing and fund["name"] == isin:
            fund = fund | {"name": existing["fund"]["name"]}
        chunks = json.loads(self.store.require(existing["history"])) if existing else {}
        latest = existing["latest"] if existing else rows[min(rows)]
        changed = False
        years: dict[str, Rows] = {}
        for day, row in rows.items():
            years.setdefault(day[:4], {})[day] = row
            if day >= latest["date"]:
                latest = row

        for year, incoming in years.items():
            archived = (
                read_rows(self.store.require(chunks[year])) if year in chunks else {}
            )
            if any(archived.get(day) != row for day, row in incoming.items()):
                archived.update(incoming)
                content = csv_bytes(archived[day] for day in sorted(archived))
                chunks[year] = self.write(f"{isin}/{year}.csv", content)
                changed = True

        entry = {"fund": fund, "latest": latest, "history": None}
        if changed:
            entry["history"] = self.write(f"{isin}.json", json_bytes(chunks))
        elif existing:
            entry["history"] = existing["history"]
        return isin, entry if entry != existing else None

    def commit(self, changed_shards: set[str]) -> None:
        for suffix in sorted(changed_shards):
            self.index[suffix] = self.write(
                f"index/{suffix}.json", json_bytes(self.shards[suffix])
            )

        entries = [
            (isin, entry)
            for shard in self.shards.values()
            for isin, entry in shard.items()
        ]
        entries.sort()
        catalog = []
        latest = []
        for isin, entry in entries:
            row = entry["latest"]
            latest.append(row)
            catalog.append(
                {
                    "isin": isin,
                    "name": entry["fund"]["name"],
                    "currency": row["currency"],
                    "latest_date": row["date"],
                    "source_url": entry["fund"]["source_url"],
                }
            )
        release = {
            "shards": self.index,
            "catalog": self.write("funds.json", json_bytes(catalog)),
            "latest": self.write("latest.csv", csv_bytes(latest)),
        }
        key = self.write("release.json", json_bytes(release))
        self.store.put(
            ACTIVE, json_bytes({"current": key, "previous": self.key}), self.etag
        )


def publish(store: Store, batches: Callable[[], Iterable[Batch]]) -> None:
    for attempt in range(3):
        release = Release.load(store)
        changed_shards = set()
        changed_funds = 0
        seen = set()
        try:
            with ThreadPoolExecutor(max_workers=PARALLELISM) as executor:
                for group in batched(
                    (batch for batch in batches() if batch[2]), PARALLELISM
                ):
                    for isin, entry in executor.map(release.update, group):
                        if isin in seen:
                            raise ValueError(f"Multiple batches for {isin}")
                        seen.add(isin)
                        if entry is not None:
                            suffix = isin[-2:]
                            release.shards.setdefault(suffix, {})[isin] = entry
                            changed_shards.add(suffix)
                            changed_funds += 1
            if changed_shards:
                release.commit(changed_shards)
            elif release.key is None:
                raise ValueError("Cannot initialize an empty NAV archive")
            LOG.info("Published %d changed share classes", changed_funds)
            return
        except Conflict:
            if attempt == 2:
                raise
            LOG.info("Release changed during publication, retrying")


def import_batches(archive: Path) -> Iterable[Batch]:
    metadata = archive / "funds.json"
    funds = json.loads(metadata.read_bytes()) if metadata.exists() else {}
    histories = sorted(archive.glob("*.csv"))
    if not histories:
        raise ValueError(f"No CSV histories in {archive}")
    for path in histories:
        rows = read_rows(path.read_bytes())
        if rows:
            isin = path.stem
            fund = funds.get(
                isin, {"name": isin, "source_url": rows[max(rows)]["source_url"]}
            )
            yield isin, fund, rows


def verify(store: Store, archive: Path) -> None:
    release = Release.load(store)
    expected = set()
    count = 0
    for isin, fund, rows in import_batches(archive):
        expected.add(isin)
        entry = release.shards.get(isin[-2:], {}).get(isin)
        if entry is None or entry["fund"] != fund or entry["latest"] != rows[max(rows)]:
            raise ValueError(f"Archive metadata differs for {isin}")
        chunks = json.loads(store.require(entry["history"]))
        actual = {}
        for key in chunks.values():
            actual.update(read_rows(store.require(key)))
        if actual != rows:
            raise ValueError(f"Archive observations differ for {isin}")
        count += len(rows)
    if expected != {isin for shard in release.shards.values() for isin in shard}:
        raise ValueError("Archive ISINs differ")
    if release.key is None:
        raise ValueError("No active archive release")
    LOG.info("Verified %d observations across %d share classes", count, len(expected))


def prune(store: Store, now: datetime) -> int:
    release = Release.load(store)
    if release.key is None:
        return 0
    reachable = set()
    for key in (release.key, release.previous):
        if key is None:
            continue
        root = json.loads(store.require(key))
        reachable.update((key, root["catalog"], root["latest"]))
        for shard_key in root["shards"].values():
            if shard_key in reachable:
                continue
            reachable.add(shard_key)
            for entry in json.loads(store.require(shard_key)).values():
                history = entry["history"]
                if history not in reachable:
                    reachable.add(history)
                    reachable.update(json.loads(store.require(history)).values())
    cutoff = now - timedelta(days=7)
    retired = (
        item["Key"]
        for item in store.objects()
        if item["LastModified"] < cutoff and item["Key"] not in reachable
    )
    count = 0
    for keys in batched(retired, 1000):
        store.delete(keys)
        count += len(keys)
    return count


def main(argv: Sequence[str] | None = None) -> None:
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("collect")
    commands.add_parser("prune")
    commands.add_parser("status")
    for name in ("import", "verify"):
        commands.add_parser(name).add_argument("archive", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        region_name="auto",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(max_pool_connections=PARALLELISM),
    )
    store = Store(client, os.environ.get("R2_BUCKET", "fondarkivet-nav"))
    match args.command:
        case "status":
            if Release.load(store).key is None:
                parser.exit(1, "No active archive release\n")
        case "verify":
            verify(store, args.archive)
        case "import":
            publish(store, lambda: import_batches(args.archive))
        case "prune":
            LOG.info("Removed %d unreachable objects", prune(store, datetime.now(UTC)))
        case "collect":
            quotes = fetch_quotes()
            publish(
                store,
                lambda: (
                    (
                        isin,
                        {"name": name, "source_url": row["source_url"]},
                        {row["date"]: row},
                    )
                    for isin, (name, row) in quotes.items()
                ),
            )
