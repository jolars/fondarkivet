import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
from botocore.stub import Stubber

from fondarkivet.r2 import (
    ACTIVE,
    Conflict,
    Release,
    Store,
    csv_bytes,
    import_batches,
    json_bytes,
    prune,
    publish,
    read_rows,
    verify,
)

ISIN = "SE0001184961"
OTHER = "SE0004297927"
SOURCE = "https://example.org/fund"
FUND = {"name": "Example fund", "source_url": SOURCE}


def row(isin, day, nav="101.50"):
    return {
        "isin": isin,
        "date": day,
        "nav": nav,
        "currency": "SEK",
        "source_url": SOURCE,
    }


class MemoryStore:
    def __init__(self):
        self.data = {}
        self.versions = {}
        self.now = datetime.now(UTC)
        self.before_commit = None

    def read(self, key):
        if key in self.data:
            return self.data[key][0], self.versions[key]

    def require(self, key):
        return self.data[key][0]

    def put(self, key, content, etag=None):
        if key == ACTIVE and self.before_commit:
            before_commit, self.before_commit = self.before_commit, None
            before_commit()
        if self.versions.get(key) != etag:
            raise Conflict(key)
        self.data[key] = content, self.now
        self.versions[key] = content.hex()

    def objects(self):
        return [
            {"Key": key, "LastModified": timestamp}
            for key, (_, timestamp) in self.data.items()
            if key != ACTIVE
        ]

    def delete(self, keys):
        for key in keys:
            del self.data[key]
            del self.versions[key]


class R2ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()

    def publish(self, *batches):
        publish(
            self.store,
            lambda: (
                (isin, FUND, {item["date"]: item for item in rows})
                for isin, *rows in batches
            ),
        )

    def release(self):
        return Release.load(self.store)

    def entry(self, isin=ISIN):
        return self.release().shards[isin[-2:]][isin]

    def test_retries_are_noops_and_backfills_preserve_latest_and_missing_funds(self):
        older = row(ISIN, "1999-12-31", "5.12345678")
        recent = row(ISIN, "2025-01-01")
        other = row(OTHER, "2025-01-02")
        self.publish((ISIN, recent, older), (OTHER, other))
        old_entry = self.entry(OTHER)
        before = self.store.data.copy()
        self.publish((ISIN, recent, older))
        self.assertEqual(self.store.data, before)

        corrected = older | {"nav": "5.12345679"}

        old_chunks = json.loads(self.store.require(self.entry()["history"]))
        self.publish((ISIN, corrected))
        entry = self.entry()
        chunks = json.loads(self.store.require(entry["history"]))
        self.assertEqual(chunks["2025"], old_chunks["2025"])
        self.assertEqual(
            read_rows(self.store.require(chunks["1999"])), {older["date"]: corrected}
        )
        self.assertEqual(entry["latest"], recent)
        self.assertEqual(self.entry(OTHER), old_entry)
        amended = recent | {"nav": "102.5000"}
        self.publish((ISIN, amended))
        self.assertEqual(self.entry()["latest"], amended)

    def test_failed_upload_leaves_the_active_release_unchanged(self):
        original = row(ISIN, "2025-01-01")
        self.publish((ISIN, original))
        before = self.release().key

        def fail_commit():
            raise OSError("simulated upload failure")

        self.store.before_commit = fail_commit
        with self.assertRaises(OSError):
            self.publish((ISIN, row(ISIN, "2025-01-02")))
        self.assertEqual(self.release().key, before)
        self.assertEqual(self.entry()["latest"], original)

    def test_conflicting_publish_rebases_the_batch(self):
        self.publish((ISIN, row(ISIN, "2025-01-01")))
        other = row(OTHER, "2025-01-02")
        self.store.before_commit = lambda: self.publish((OTHER, other))
        recent = row(ISIN, "2025-01-03")
        self.publish((ISIN, recent))
        self.assertEqual(self.entry()["latest"], recent)
        self.assertEqual(self.entry(OTHER)["latest"], other)

    def test_imports_legacy_rows_and_verifies_exact_values(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory)
            past = row(ISIN, "1988-08-08", "5.5000")
            recent = row(ISIN, "2025-01-02")
            other = row(OTHER, "2025-01-01")
            (archive / f"{ISIN}.csv").write_bytes(csv_bytes([recent, past]))
            (archive / f"{OTHER}.csv").write_bytes(csv_bytes([other]))
            (archive / "funds.json").write_bytes(json_bytes({ISIN: FUND}))
            publish(self.store, lambda: import_batches(archive))
            verify(self.store, archive)
            self.assertEqual(self.entry(OTHER)["fund"]["name"], OTHER)
            (archive / f"{ISIN}.csv").write_bytes(csv_bytes([recent]))
            with self.assertRaisesRegex(ValueError, "observations differ"):
                verify(self.store, archive)

    def test_prune_keeps_both_releases_and_recent_orphans(self):
        self.store.now -= timedelta(days=10)
        self.publish((ISIN, row(ISIN, "1980-01-02")))
        first = self.release().key
        shared = self.entry()["history"]
        self.publish((OTHER, row(OTHER, "2025-01-01")))
        previous = self.release().key
        self.publish((OTHER, row(OTHER, "2025-01-02")))
        active = self.release().key
        self.store.now += timedelta(days=10)
        self.store.put("objects/recent-orphan", b"orphan")
        self.assertGreater(prune(self.store, self.store.now), 0)
        self.assertIsNone(self.store.read(first))
        for key in (active, previous, shared, "objects/recent-orphan"):
            self.assertIsNotNone(self.store.read(key))

    def test_s3_adapter_uses_create_only_and_compare_and_swap(self):
        client = boto3.client(
            "s3",
            region_name="auto",
            endpoint_url="https://example.org",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
        store = Store(client, "test-bucket")
        params = {"Bucket": "test-bucket", "Key": ACTIVE, "Body": b"{}"}
        with Stubber(client) as stub:
            stub.add_client_error("get_object", "NoSuchKey", http_status_code=404)
            stub.add_response("put_object", {}, params | {"IfNoneMatch": "*"})
            stub.add_client_error(
                "put_object",
                "PreconditionFailed",
                http_status_code=412,
                expected_params=params | {"IfMatch": '"old-etag"'},
            )
            self.assertIsNone(store.read(ACTIVE))
            store.put(ACTIVE, b"{}")
            with self.assertRaises(Conflict):
                store.put(ACTIVE, b"{}", '"old-etag"')
            stub.assert_no_pending_responses()
