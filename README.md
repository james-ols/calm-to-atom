# CALM to AtoM Converter

[![CI](https://github.com/matthewbrutonall/calm-to-atom/actions/workflows/ci.yml/badge.svg)](https://github.com/matthewbrutonall/calm-to-atom/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)

A tool to convert exported CSV data from Axiell CALM to an AtoM (Access to Memory) compatible CSV format. 
Designed for UK archivists migrating away from legacy systems to modern open-source archival platforms.

## Installation

```bash
git clone https://github.com/matthewbrutonall/calm-to-atom.git
cd calm-to-atom
pip install -e .              # installs the `calm2atom` command
pip install -e ".[web]"       # optional: FastAPI web wrapper
pip install -e ".[dev]"       # optional: test tooling (pytest)
```

Once installed you can call the tool as `calm2atom …` anywhere, or run `python cli.py …` from the repo.

## Why this tool?
Migrating from CALM to AtoM requires transforming flattened custom data into strict ISAD(G) hierarchical structures. This tool handles the primary pain points of migration:
- **Version-Specific Templates:** AtoM CSV templates change between releases. This tool bundles the exact headers for **AtoM 2.10 (the current stable release) down through older versions** — the versions we recommend migrating to — as well as the older `2.6`, `2.3`, and `2.1` templates, and guarantees output matches the expected strict structure. `heratio` uses the same 2.8 template.
- **Hierarchical Linking:** Automatically calculates AtoM's required `parentId` field by analyzing your CALM `RefNo` strings (e.g., if it sees `GB 123 ABCD/1/2`, it links it to `GB 123 ABCD/1`).
- **ISAD(G) Mapping:** Maps standard CALM fields to their strict AtoM equivalents (e.g., `AdminHistory` -> `archivalHistory`).
- **Event Linking:** Automatically flags `eventTypes` as `Creation` when encountering `Date` or `CreatorName` for AtoM 2.3+ compatibility.
- **Level Normalization:** Maps UK archival terms (like "Piece") to standard AtoM lowercase equivalents ("item").

## Usage

### Command Line Interface (CLI)

You can run the script directly against a CSV exported from CALM:

```bash
# By default, it outputs a CSV for AtoM 2.8 (the current release)
python cli.py input_calm_export.csv output_atom_import.csv

# Targeting an AtoM Heratio instance:
python cli.py input_calm_export.csv output_atom_import.csv --atom-version heratio

# If your archive is running an older AtoM version, specify it:
python cli.py input_calm_export.csv output_atom_import.csv --atom-version 2.3
```

Supported `--atom-version` values: `2.8` (default), `heratio`, `2.6`, `2.3`, `2.1`. We recommend
migrating to **AtoM 2.8 or Heratio** — the older templates are provided for archives not yet upgraded.

To see detailed logs:
```bash
python cli.py input_calm_export.csv output_atom_import.csv --verbose
```

### Next Steps for Web Wrapper

The core conversion logic is decoupled in `core.py`. A web framework like FastAPI or Flask can be built around it. An example skeleton is provided in `web_app.py`.

```bash
pip install -r requirements.txt
uvicorn web_app:app --reload
```

### Custom Mapping (JSON)

CALM fields vary wildly depending on the archive (e.g. `UserText1`, `CustomBoxRef`). You can override the default mappings by passing a JSON file:

```bash
python cli.py input_calm_export.csv output_atom_import.csv -m example_mapping.json
```

See `example_mapping.json` for an example of how to construct this file.

### Authority Records (ISAAR-CPF)

CALM usually holds Creators (Persons, Organizations, Families) in a separate Persons database. You can convert these exports into AtoM Authority records by passing `-t isaar`:

```bash
python cli.py calm_persons.csv atom_authorities.csv -t isaar
```

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

The core conversion helpers (`resolve_version`, `extract_leaf_identifier`, `compute_parent_id`,
`clean_level`) are unit-tested in `tests/test_core.py` against the shipping code, so regressions in
the hierarchy/identifier logic are caught in CI across Python 3.8–3.12.

## Contributing

Issues and pull requests are welcome — especially additional CALM field mappings from real
institutional exports (CALM field names vary a lot between archives). Please keep tests green.

## License

Released under the [MIT License](LICENSE). © 2026 Archive Hosting UK.
