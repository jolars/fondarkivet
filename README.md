# Swedish fund NAVs

swefunds records the latest NAVs published by Spiltan Fonder for four Swedish mutual fund share classes. The archive starts with the first successful collection. Each record uses the fund's valuation date. A missed refresh can leave a gap if Spiltan replaces a quote before the next successful run.

## API

The GitHub Pages site serves these files without an API key.

| Path | Contents |
| --- | --- |
| `/v1/funds.json` | Fund names, share-class ISINs, currencies, latest quote dates, and source links |
| `/v1/nav/latest.csv` | Latest archived NAV for each share class |
| `/v1/nav/{isin}.csv` | Archived NAVs for one share class, sorted by valuation date |

CSV columns are `isin,date,nav,currency,source_url`. Dates use ISO 8601 and NAVs use a decimal point. The source is [Spiltan Fonder](https://www.spiltanfonder.se/fonder).

## Run locally

```sh
python -m pip install -r requirements.txt
python collect.py archive site
```

The collector keeps observations in `archive` and generates the API files in `site`.

On GitHub, run **Refresh NAVs** manually to check collection from a hosted runner. The workflow runs nightly at 03:17 UTC. After reviewing the source terms for automated collection and public redistribution, select GitHub Actions as the Pages source and set the repository variable `PUBLISH_NAV` to `true` to enable archiving and deployment.
