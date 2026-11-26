# Repository Guidelines

## Project Structure

- `src/fondarkivet/` contains the collector, provider adapters, and static API
  builder. `pyproject.toml` declares dependencies, and `uv.lock` pins them.
- `archive/` holds one CSV per share-class ISIN. `site/` holds the generated
  GitHub Pages site, including `v1/funds.json` and `v1/nav/`. Both directories
  are ignored in the source checkout. The publishing workflow persists
  observations on the `data` branch.
- `.github/workflows/ci.yml` runs quality checks. `.github/workflows/nav.yml`
  collects quotes nightly and publishes them when `PUBLISH_NAV` is enabled.

## Build and Check Locally

- Run `devenv shell` for Python 3.13 and the project tools. Run
  `uv sync --locked` to install the project and its development dependencies.
- Run `uv run --locked fondarkivet archive site` to fetch live quotes, update
  the local archive, and build the site. Pass fresh directories to keep an
  existing local archive intact during a smoke test.
- Run `ruff check` and `ruff format --check` in devenv. CI runs both commands
  through `uv run --locked`. Use `actionlint` for workflow changes and
  `panache format --check README.md` to check Markdown formatting.

## Coding Style

Use four-space Python indentation, `snake_case` for functions and variables, and
uppercase names for module constants. Follow Ruff formatting and the GitHub
Flavored Markdown settings in `panache.toml`. Preserve public output paths and
CSV columns when changing collection logic.

## Verification

Run `uv run --locked python -m unittest discover -s tests` for offline CLI
tests. For collector changes, inspect the generated catalog and CSVs. Verify
that share classes are keyed by ISIN, historical rows are sorted by valuation
date, and the latest CSV contains one row per share class. Check that rebuilding
against the same archive does not duplicate an observation for the same ISIN and
date.

## Commits and Pull Requests

Follow the Conventional Commit style used in history, such as
`feat: collect and publish daily fund NAVs`. In pull requests, describe the
affected providers or outputs, list the checks you ran, and link any related
issue.
