"""
CSV reader for CALM exports.

This is a thin wrapper around csv.DictReader that returns the same
(rows, metadata) contract as the XML reader, so downstream code
(core.convert_rows) is source-agnostic.
"""

import csv
import logging
from typing import Any, Dict, List, Tuple


def read_calm_csv(input_path: str) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Parse a CALM CSV export into a list of row dicts plus a small metadata dict.

    :param input_path: Path to the CALM CSV export.
    :returns: (rows, metadata). rows is a list of dicts keyed by CALM field name;
              metadata carries export-level context (empty for CSV inputs).
    :raises FileNotFoundError: If the input file does not exist.
    """
    logging.info(f"Reading CALM data from {input_path}")

    # 'utf-8-sig' transparently strips the BOM that Excel sometimes writes.
    with open(input_path, mode="r", encoding="utf-8-sig") as infile:
        rows: List[Dict[str, str]] = list(csv.DictReader(infile))

    metadata: Dict[str, Any] = {
        "archon_code": None,       # CSV exports don't carry Country/Repository codes.
        "database_name": None,     # CSV has no root <DScribeDatabase Name="..."> equivalent.
        "record_count": len(rows),
    }

    return rows, metadata