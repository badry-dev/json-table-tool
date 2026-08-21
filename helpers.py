"""Data processing helpers for JSON flattening and table extraction."""

import json


def flatten_for_csv(data, parent_key='', sep='.', _depth=0, max_depth=10):
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


def serialize_cell_value(value):
    """
    Reduce one cell value to the scalar an export writer can emit.

    Containers become their JSON text; everything else is passed through
    unchanged so numbers stay numbers in the workbook.
    """
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def is_formula_trigger(value):
    """True when a serialized value would be read as a formula by a spreadsheet."""
    return isinstance(value, str) and value.startswith(FORMULA_TRIGGERS)


def sanitize_cell(value):
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


def extract_table_data(json_data):
    """
    Extract tabular data from JSON.
    Handles arrays of objects, nested arrays, and single objects.
    Returns a list of row dicts.
    """
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
                result = extract_table_data(value)
                if result:
                    return result

        return [json_data]

    return []


def parse_jsonl(text):
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


def extract_by_path(json_data, path):
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


def get_all_columns(data):
    """Get all unique column names from the data, sorted alphabetically."""
    columns = set()
    for row in data:
        if isinstance(row, dict):
            columns.update(row.keys())
    return sorted(columns)
