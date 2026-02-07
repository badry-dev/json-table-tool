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
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(
                    flatten_for_csv(v, new_key, sep=sep, _depth=_depth + 1, max_depth=max_depth).items()
                )
            elif isinstance(v, list):
                items.append((new_key, json.dumps(v)))
            else:
                items.append((new_key, v))
    else:
        items.append((parent_key, data))
    return dict(items)


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
            return [{"value": item} for item in json_data]

    if isinstance(json_data, dict):
        for key, value in json_data.items():
            if isinstance(value, list) and len(value) > 0:
                if isinstance(value[0], dict):
                    return value
                else:
                    return [{"value": item} for item in value]

        for key, value in json_data.items():
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
            raise ValueError(f'Invalid JSON on line {i}: {str(e)}')
    return rows


def get_all_columns(data):
    """Get all unique column names from the data, sorted alphabetically."""
    columns = set()
    for row in data:
        if isinstance(row, dict):
            columns.update(row.keys())
    return sorted(list(columns))
