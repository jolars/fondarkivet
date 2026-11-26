const HEADER = new TextEncoder().encode("isin,date,nav,currency,source_url\n");
const HISTORY = /^\/v1\/nav\/([A-Z]{2}[A-Z0-9]{9}[0-9])\.csv$/;

async function requireObject(bucket, key) {
  const object = await bucket.get(key);
  if (!object) throw new Error(`Missing archive object: ${key}`);
  return object;
}

function headersFor(type, version) {
  return new Headers({
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "public, max-age=300",
    "Content-Type": `${type}; charset=utf-8`,
    ETag: `"${version.split("/")[1]}"`,
  });
}

function notModified(request, headers) {
  const validators = request.headers.get("If-None-Match");
  return validators?.split(",").some((value) => {
    const validator = value.trim().replace(/^W\//, "");
    return validator === "*" || validator === headers.get("ETag");
  });
}

async function* historyBody(bucket, chunks) {
  yield HEADER;
  for (const key of chunks) {
    const object = await requireObject(bucket, key);
    const reader = object.body.getReader();
    let remainingHeader = HEADER.length;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const skip = Math.min(remainingHeader, value.length);
        remainingHeader -= skip;
        if (skip < value.length) yield value.subarray(skip);
      }
      if (remainingHeader) throw new Error(`Incomplete archive chunk: ${key}`);
    } finally {
      await reader.cancel();
      reader.releaseLock();
    }
  }
}

function streamHistory(bucket, chunks) {
  const iterator = historyBody(bucket, chunks);
  // Advance the R2 reader only as the client consumes the response.
  return new ReadableStream({
    async pull(controller) {
      const { done, value } = await iterator.next();
      if (done) controller.close();
      else controller.enqueue(value);
    },
    async cancel() {
      await iterator.return();
    },
  });
}

function errorResponse(message, status, extra = {}) {
  return new Response(message, {
    status,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "no-store",
      ...extra,
    },
  });
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (!pathname.startsWith("/v1/")) return env.ASSETS.fetch(request);

    const history = HISTORY.exec(pathname);
    const isCatalog = pathname === "/v1/funds.json";
    const isLatest = pathname === "/v1/nav/latest.csv";
    if (!history && !isCatalog && !isLatest) return errorResponse("Not found", 404);
    if (request.method !== "GET" && request.method !== "HEAD") {
      return errorResponse("Method not allowed", 405, { Allow: "GET, HEAD" });
    }

    try {
      const bucket = env.NAV_ARCHIVE;
      const active = await bucket.get("active.json");
      if (!active) return errorResponse("Archive unavailable", 503);
      const { current } = await active.json();
      const release = await (await requireObject(bucket, current)).json();

      if (history) {
        const isin = history[1];
        const shardKey = release.shards[isin.slice(-2)];
        if (!shardKey) return errorResponse("Not found", 404);
        const shard = await (await requireObject(bucket, shardKey)).json();
        const entry = shard[isin];
        if (!entry) return errorResponse("Not found", 404);

        const headers = headersFor("text/csv", entry.history);
        if (notModified(request, headers)) return new Response(null, { status: 304, headers });
        if (request.method === "HEAD") return new Response(null, { headers });

        const manifest = await (await requireObject(bucket, entry.history)).json();
        const chunks = Object.keys(manifest).sort().map((year) => manifest[year]);
        return new Response(streamHistory(bucket, chunks), { headers });
      }

      const key = isCatalog ? release.catalog : release.latest;
      const headers = headersFor(isCatalog ? "application/json" : "text/csv", key);
      if (notModified(request, headers)) return new Response(null, { status: 304, headers });
      if (request.method === "HEAD") return new Response(null, { headers });
      return new Response((await requireObject(bucket, key)).body, { headers });
    } catch (error) {
      console.error(error);
      return errorResponse("Archive unavailable", 503);
    }
  },
};
