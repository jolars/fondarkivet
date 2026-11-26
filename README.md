# Fondarkivet

Fondarkivet records the latest published NAV from Spiltan Fonder, AMF Fonder,
and Handelsbanken Fonder. Each nightly run records one quote per configured
share class, using the fund's valuation date. The archive starts with the first
successful collection. A missed refresh can leave a gap if a fund manager
replaces a quote before the next successful run.

## API

The public API at [fondarkivet.se](https://fondarkivet.se/) serves these files
without an API key.

  | Path                 | Contents                                                                        |
  | -------------------- | ------------------------------------------------------------------------------- |
  | `/v1/funds.json`     | Fund names, share-class ISINs, currencies, latest quote dates, and source links |
  | `/v1/nav/latest.csv` | Latest archived NAV for each share class                                        |
  | `/v1/nav/{isin}.csv` | Archived NAVs for one share class, sorted by valuation date                     |

CSV columns are `isin,date,nav,currency,source_url`. Dates use ISO 8601 and NAVs
use a decimal point. Each row links to its source. The collector reads the
[Spiltan fund list](https://www.spiltanfonder.se/fonder), the fund details
linked from [AMF's fund
list](https://www.amf.se/spara-hos-amf/fonder/fondutbud/), and the quick views
in [Handelsbanken Fonder's own fund
list](https://www.handelsbanken.se/sv/om-oss/svenska-dotterbolag/handelsbanken-fonder/fondlista-komplett).

## Run locally

With [uv](https://docs.astral.sh/uv/) installed, run:

```sh
uv run --locked fondarkivet archive site
```

The collector keeps observations in `archive` and generates the website in
`site`. Run `uv build` to create a wheel and source distribution in `dist/`.

Serve the CSV-backed site locally with
`uv run python -m http.server --directory site`. To preview the Cloudflare
Worker with Node.js 24, run `npm ci` and `npm run preview`. The Worker uses a
local R2 bucket during preview. Run `npm run build` followed by
`npm run deploy:check` to validate the deployment without publishing.

## Publish

Production keeps the archive in a private Cloudflare R2 bucket. Set up
`fondarkivet.se` as an active Cloudflare zone and enable R2 on the account.

1. Create an R2 Standard bucket named `fondarkivet-nav`. Create an [R2 API
   token](https://developers.cloudflare.com/r2/api/tokens/) with Object Read &
   Write permission scoped to that bucket. Add its Access Key ID and Secret
   Access Key to GitHub Actions as `R2_ACCESS_KEY_ID` and
   `R2_SECRET_ACCESS_KEY`.

2. Set `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` as GitHub Actions
   secrets. Use an [Edit Cloudflare Workers
   token](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/)
   for deployment, scoped to the account and zone.

3. Before setting `PUBLISH_NAV`, seed the bucket from the existing CSV archive.
   Use the `data` branch if it exists, or a local copy of the archive otherwise.
   With `CLOUDFLARE_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY`
   available in the local environment, run:

   ```sh
   uv run --locked fondarkivet-r2 import archive
   uv run --locked fondarkivet-r2 verify archive
   ```

4. Set the repository variable `PUBLISH_NAV` to `true` after the new workflows
   are on `main`. Run **Deploy Worker** to attach the custom domain. Run
   **Refresh NAVs** manually to check the first collection and compare the
   public catalog, latest snapshot, and sample histories with the seed and
   current observations.

**Refresh NAVs** runs at 03:17 UTC each night. It updates the affected share
classes and years in R2. It also prunes unreferenced objects weekly. **Deploy
Worker** runs when the Worker or its deployment configuration changes.
