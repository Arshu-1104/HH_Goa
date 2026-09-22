"""
csv_utils.py — Efficient selective CSV column reader.

Problem
-------
csv.DictReader builds a full dict for every row regardless of how many columns
the caller actually needs.  For a 590k × 397-column CSV this means ~590k
397-key dicts are created, most of which are immediately discarded.

Solution
--------
iter_selected_csv_columns():
  1. Reads the header once to discover column positions.
  2. Uses csv.reader (not DictReader) which returns a plain list per row.
  3. Extracts only the positions corresponding to requested columns.
  4. Yields a small dict containing only those columns.

This avoids building the 397-key intermediate dict entirely and is
measurably faster on large CSVs.

Usage
-----
    from mcp.server.csv_utils import iter_selected_csv_columns

    for row in iter_selected_csv_columns(path, ("TransactionID", "customer_id", "ts")):
        print(row["TransactionID"], row["customer_id"])
"""

import csv
from pathlib import Path
from typing import Iterator


def iter_selected_csv_columns(
    path: Path,
    cols: tuple[str, ...] | list[str],
    limit: int | None = None,
) -> Iterator[dict[str, str]]:
    """
    Stream a CSV file and yield only the requested columns as dicts.

    Parameters
    ----------
    path : Path
        CSV file to read.
    cols : tuple[str, ...] | list[str]
        Column names to include in each yielded dict.
        Columns not found in the file are silently omitted.
    limit : int | None
        If given, stop after this many data rows (not counting the header).

    Yields
    ------
    dict[str, str]
        One dict per data row, containing only the requested columns.

    Notes
    -----
    * Uses csv.reader internally — no 397-key dict is ever created.
    * Preserves insertion order of cols in the yielded dicts.
    * Thread-safe as long as the file is not modified while iterating.
    """
    if not path.exists():
        return

    want = list(cols)  # preserve order

    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)

        # Read header once
        try:
            header = next(reader)
        except StopIteration:
            return  # empty file

        # Map column names → positions (only for the ones we want)
        col_positions: list[tuple[str, int]] = []
        header_map = {name: idx for idx, name in enumerate(header)}
        for col in want:
            if col in header_map:
                col_positions.append((col, header_map[col]))
            # Silently skip columns not in file — caller gets partial dict

        if not col_positions:
            return  # nothing useful to yield

        # Pre-compute max index needed so we can safely slice
        max_idx = max(idx for _, idx in col_positions)

        for row_num, raw_row in enumerate(reader):
            if limit is not None and row_num >= limit:
                return
            if len(raw_row) <= max_idx:
                # Short row — fill missing positions with ""
                yield {col: (raw_row[idx] if idx < len(raw_row) else "")
                       for col, idx in col_positions}
            else:
                yield {col: raw_row[idx] for col, idx in col_positions}
