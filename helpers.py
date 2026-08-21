"""Data processing helpers for JSON flattening and table extraction."""

import json
from typing import Any


def flatten_for_csv(
    data: Any,
    parent_key: str = '',
    sep: str = '.',
    _depth: int = 0,
    max_depth: int = 10,
) -> dict[str, Any]:
    """
    Flatten nested dictionaries for CSV export.
    Arrays are converted to JSON strings.
    Stops recursing at max_depth to prevent stack overflow.
    """
    if _depth >= max_depth:
        if isinstance(data, (dict, list)):
            return {parent_key: json.dumps(data)}
        return {parent_key: data}

    items = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f'{parent_key}{sep}{k}' if parent_key else k
            if isinstance(v, dict):
                items.extend(
                    flatten_for_csv(
                        v, new_key, sep=sep, _depth=_depth + 1, max_depth=max_depth
                    ).items()
                )
            elif isinstance(v, list):
                items.append((new_key, json.dumps(v)))
            else:
                items.append((new_key, v))
    else:
        items.append((parent_key, data))
    return dict(items)


# Characters that make a spreadsheet treat a cell as a formula (or let it smuggle
# extra rows/fields past a delimited parser). OWASP lists all seven.
FORMULA_TRIGGERS = ('=', '+', '-', '@', '\t', '\r', '\n')


def serialize_cell_value(value: Any) -> Any:
    """
    Reduce one cell value to the scalar an export writer can emit.

    Containers become their JSON text; everything else is passed through
    unchanged so numbers stay numbers in the workbook.
    """
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def is_formula_trigger(value: Any) -> bool:
    """True when a serialized value would be read as a formula by a spreadsheet."""
    return isinstance(value, str) and value.startswith(FORMULA_TRIGGERS)


def sanitize_cell(value: Any) -> Any:
    """
    Serialize a cell for the delimited formats (CSV/TSV) and defuse formula
    injection (CWE-1236).

    Delimited output has no type channel, so a dangerous value is prefixed with a
    single quote -- the OWASP mitigation for CSV. XLSX does not use this: it has a
    real string type, so `export_xlsx` writes the untouched value and pins the
    cell's data_type instead (see `is_formula_trigger`). Lossless exports (JSONL)
    and Markdown must not call this.
    """
    serialized = serialize_cell_value(value)
    if is_formula_trigger(serialized):
        return "'" + serialized
    return serialized


def flatten_rows(rows: list[Any], max_depth: int = 10) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Flatten every row and collect the column names in a single pass.

    Returns (flattened_rows, sorted_column_names). Previously the caller
    flattened, then walked the result again with get_all_columns -- two full
    passes over the largest structure in the request (P8).

    The names are accumulated in a set and sorted once at the end, which is
    exactly what get_all_columns produces; set iteration order is not relied on.
    """
    flattened = []
    columns = set()
    for row in rows:
        flat = flatten_for_csv(row, max_depth=max_depth)
        flattened.append(flat)
        if isinstance(flat, dict):
            columns.update(flat.keys())
    return flattened, sorted(columns)


def extract_table_data(json_data: Any, _depth: int = 0, max_depth: int = 10) -> list[Any]:
    """
    Extract tabular data from JSON.
    Handles arrays of objects, nested arrays, and single objects.
    Returns a list of row dicts.

    Mirrors flatten_for_csv's depth cap (F8): a payload nested a thousand levels
    deep is valid JSON, and without the cap the descent into nested dicts blows
    the Python stack and turns a client-supplied document into a 500. At the cap
    the remaining structure becomes a single row rather than being explored.
    """
    if _depth >= max_depth:
        return [json_data] if isinstance(json_data, dict) else []

    if isinstance(json_data, list):
        if len(json_data) > 0 and isinstance(json_data[0], dict):
            return json_data
        else:
            return [{'value': item} for item in json_data]

    if isinstance(json_data, dict):
        for value in json_data.values():
            if isinstance(value, list) and len(value) > 0:
                if isinstance(value[0], dict):
                    return value
                else:
                    return [{'value': item} for item in value]

        for value in json_data.values():
            if isinstance(value, dict):
                result = extract_table_data(value, _depth=_depth + 1, max_depth=max_depth)
                if result:
                    return result

        return [json_data]

    return []


def parse_jsonl(text: str) -> list[Any]:
    """
    Parse JSONL (JSON Lines) text into a list of objects.
    Each non-empty line is parsed as a separate JSON value.
    """
    rows = []
    for i, line in enumerate(text.strip().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f'Invalid JSON on line {i}: {e}') from e
    return rows


def extract_by_path(json_data: Any, path: str) -> Any:
    """
    Extract data from JSON using a dot-notation path.
    Numeric parts traverse arrays (e.g. 'data.0.orders').
    """
    if path == '(root)':
        return json_data

    parts = path.split('.')
    current = json_data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
            except ValueError:
                return None
            if 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
        else:
            return None
    return current


def get_all_columns(data: list[Any]) -> list[str]:
    """Get all unique column names from the data, sorted alphabetically."""
    columns = set()
    for row in data:
        if isinstance(row, dict):
            columns.update(row.keys())
    return sorted(columns)


# --- Preview projection (P2.2/P5) -------------------------------------------
#
# `preview` rows carry full-fidelity nested structures, so a 50k-key object or a
# 5 MB string cell is handed straight to the browser and freezes the tab. These
# caps apply to the PREVIEW ONLY: the projection is a copy, so table_data and
# csv_data -- and therefore every export -- keep the original values.

PREVIEW_MAX_STRING = 256
PREVIEW_MAX_ITEMS = 20
PREVIEW_TRUNCATION_SUFFIX = '… (truncated)'


def _truncate_preview_value(
    value: Any, max_string: int, max_items: int, depth: int, max_depth: int
) -> Any:
    """Return a capped copy of one nested value."""
    if isinstance(value, str):
        if len(value) > max_string:
            return value[:max_string] + PREVIEW_TRUNCATION_SUFFIX
        return value

    if isinstance(value, dict):
        if depth >= max_depth:
            return PREVIEW_TRUNCATION_SUFFIX
        truncated = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                truncated[PREVIEW_TRUNCATION_SUFFIX] = f'… and {len(value) - max_items} more keys'
                break
            truncated[key] = _truncate_preview_value(
                item, max_string, max_items, depth + 1, max_depth
            )
        return truncated

    if isinstance(value, list):
        if depth >= max_depth:
            return PREVIEW_TRUNCATION_SUFFIX
        truncated = [
            _truncate_preview_value(item, max_string, max_items, depth + 1, max_depth)
            for item in value[:max_items]
        ]
        if len(value) > max_items:
            truncated.append(f'… and {len(value) - max_items} more items')
        return truncated

    return value


def preview_truncate(
    row: Any,
    max_string: int = PREVIEW_MAX_STRING,
    max_items: int = PREVIEW_MAX_ITEMS,
    max_depth: int = 10,
) -> Any:
    """
    Build a capped COPY of one preview row.

    Every column of the row survives -- dropping columns would make the preview
    table disagree with its own header. Only the values inside are capped.
    Nothing is mutated: exports read the original rows.
    """
    if not isinstance(row, dict):
        return _truncate_preview_value(row, max_string, max_items, 0, max_depth)
    return {
        key: _truncate_preview_value(value, max_string, max_items, 1, max_depth)
        for key, value in row.items()
    }
