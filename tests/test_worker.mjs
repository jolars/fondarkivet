import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";

const header = "isin,date,nav,currency,source_url\n";
const isin = "SE0001184961";
const base = "https://fondarkivet.se";
const csvUrl = `${base}/v1/nav/${isin}.csv`;
const catalog = [{ isin, name: "Example fund", latest_date: "2025-09-07" }];

test("the Worker streams a 50-year history and serves the matching snapshots", async (t) => {
  const runtime = new Miniflare(convertV4MiniflareOptions({
    name: "fondarkivet",
    modules: true,
    scriptPath: fileURLToPath(new URL("../src/fondarkivet/web/worker.js", import.meta.url)),
    compatibilityDate: "2026-11-23",
    r2Buckets: ["NAV_ARCHIVE"],
  }));
  t.after(() => runtime.dispose());
  const bucket = await runtime.getR2Bucket("NAV_ARCHIVE");

  const unavailable = await runtime.dispatchFetch(csvUrl);
  assert.equal(unavailable.status, 503);
  await unavailable.text();

  const chunks = {};
  const expected = [header];
  let latest;
  for (let year = 1976; year <= 2025; year++) {
    const rows = Array.from({ length: 250 }, (_, index) => {
      const day = new Date(Date.UTC(year, 0, index + 1)).toISOString().slice(0, 10);
      return `${isin},${day},101.5000,SEK,https://example.org/fund\n`;
    });
    chunks[year] = `objects/${year}/chunk.csv`;
    await bucket.put(chunks[year], header + rows.join(""));
    expected.push(...rows);
    latest = rows.at(-1);
  }
  const release = {
    shards: { "61": "objects/shard/61.json" },
    catalog: "objects/catalog/funds.json",
    latest: "objects/latest/latest.csv",
  };
  await bucket.put(release.shards["61"], JSON.stringify({
    [isin]: { history: "objects/history/manifest.json" },
  }));
  await bucket.put("objects/history/manifest.json", JSON.stringify(chunks));
  await bucket.put(release.catalog, JSON.stringify(catalog));
  await bucket.put(release.latest, header + latest);
  await bucket.put("objects/first/release.json", JSON.stringify(release));
  await bucket.put("active.json", JSON.stringify({ current: "objects/first/release.json" }));

  const history = await runtime.dispatchFetch(csvUrl);
  assert.equal(history.status, 200);
  assert.equal(history.headers.get("access-control-allow-origin"), "*");
  const validator = history.headers.get("etag");
  assert.equal(validator, '"history"');

  const decoder = new TextDecoder();
  const expectedText = expected.join("");
  let offset = 0;
  let parts = 0;
  for await (const part of history.body) {
    const text = decoder.decode(part, { stream: true });
    assert.equal(text, expectedText.slice(offset, offset + text.length));
    offset += text.length;
    parts++;
  }
  assert.equal(offset, expectedText.length);
  assert.ok(parts > 1);

  const funds = await runtime.dispatchFetch(`${base}/v1/funds.json`);
  assert.deepEqual(await funds.json(), catalog);
  const snapshot = await runtime.dispatchFetch(`${base}/v1/nav/latest.csv`);
  assert.equal(await snapshot.text(), header + latest);

  const head = await runtime.dispatchFetch(csvUrl, { method: "HEAD" });
  assert.equal(head.status, 200);
  assert.equal(head.headers.get("etag"), validator);
  assert.equal(await head.text(), "");

  const nextRelease = { ...release, latest: "objects/new-latest/latest.csv" };
  await bucket.put("objects/second/release.json", JSON.stringify(nextRelease));
  await bucket.put("active.json", JSON.stringify({ current: "objects/second/release.json" }));
  const cached = await runtime.dispatchFetch(csvUrl, { headers: { "If-None-Match": validator } });
  assert.equal(cached.status, 304);
  assert.equal(await cached.text(), "");

  const unknown = await runtime.dispatchFetch(`${base}/v1/nav/SE0001184061.csv`);
  assert.equal(unknown.status, 404);
  await unknown.text();
});
