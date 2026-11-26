# Fondarkivet

Fondarkivet records the latest published NAV from Spiltan Fonder, AMF Fonder,
and Handelsbanken Fonder. Each nightly run records one quote per configured
share class, using the fund's valuation date. The archive starts with the first
successful collection. A missed refresh can leave a gap if a fund manager
replaces a quote before the next successful run.

## API

When publishing is enabled, the GitHub Pages site serves these files without an
API key.

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

The collector keeps observations in `archive` and generates the API files in
`site`. Run `uv build` to create a wheel and source distribution in `dist/`.

On GitHub, run **Refresh NAVs** manually to check collection from a hosted
runner. The workflow runs nightly at 03:17 UTC. To enable archiving and
deployment, select GitHub Actions as the Pages source and set the repository
variable `PUBLISH_NAV` to `true`.
