"""
Input readers for the calm-to-atom converter.

Each reader parses a specific CALM export format (CSV, DSCribe XML, …) and
returns a normalised `(rows, metadata)` tuple:

    rows:      List[Dict[str, str]]  — one dict per CALM record, keyed by
                                       CALM field name (e.g. 'RefNo', 'Title').
                                       This is the shape the existing mapping
                                       logic in core.convert_rows expects.

    metadata:  Dict[str, Any]         — export-level information that isn't
                                       tied to any single record. Keys:
                                         'archon_code'   : Optional[str]   e.g. 'GB 166'
                                         'database_name' : Optional[str]   e.g. 'Catalog'
                                         'record_count'  : int

The uniform contract means core.convert_rows doesn't need to know or care
which format the data originally came from.
"""

from readers.csv_reader import read_calm_csv

__all__ = ["read_calm_csv"]