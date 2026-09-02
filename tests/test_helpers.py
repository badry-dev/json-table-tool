"""Tests for data processing helpers."""

import json

from helpers import (
    PREVIEW_MAX_ITEMS,
    PREVIEW_MAX_STRING,
    PREVIEW_TRUNCATION_SUFFIX,
    extract_by_path,
    extract_table_data,
    flatten_for_csv,
    flatten_rows,
    get_all_columns,
    parse_jsonl,
    preview_truncate,
)


class TestFlattenForCsv:
    def test_flat_dict(self):
        result = flatten_for_csv({'a': 1, 'b': 'hello'})
        assert result == {'a': 1, 'b': 'hello'}

    def test_nested_dict(self):
        result = flatten_for_csv({'a': {'b': 1, 'c': 2}})
        assert result == {'a.b': 1, 'a.c': 2}

    def test_deeply_nested(self):
        result = flatten_for_csv({'a': {'b': {'c': {'d': 42}}}})
        assert result == {'a.b.c.d': 42}

    def test_list_becomes_json_string(self):
        result = flatten_for_csv({'tags': [1, 2, 3]})
        assert result == {'tags': '[1, 2, 3]'}

    def test_empty_dict(self):
        result = flatten_for_csv({})
        assert result == {}

    def test_max_depth_stops_recursion(self):
        deep = {'a': {'b': {'c': {'d': 'value'}}}}
        result = flatten_for_csv(deep, max_depth=2)
        # At depth 2, the remaining dict should be JSON-serialized
        assert 'a.b' in result
        assert isinstance(result['a.b'], str)
        parsed = json.loads(result['a.b'])
        assert parsed == {'c': {'d': 'value'}}

    def test_primitive_value(self):
        result = flatten_for_csv('hello', parent_key='key')
        assert result == {'key': 'hello'}

    def test_mixed_types(self):
        data = {'name': 'Alice', 'meta': {'age': 30}, 'scores': [90, 85]}
        result = flatten_for_csv(data)
        assert result['name'] == 'Alice'
        assert result['meta.age'] == 30
        assert result['scores'] == '[90, 85]'


class TestExtractTableData:
    def test_array_of_objects(self):
        data = [{'id': 1}, {'id': 2}]
        assert extract_table_data(data) == data

    def test_array_of_primitives(self):
        result = extract_table_data([1, 2, 3])
        assert result == [{'value': 1}, {'value': 2}, {'value': 3}]

    def test_dict_with_array_property(self):
        data = {'results': [{'id': 1}, {'id': 2}]}
        assert extract_table_data(data) == [{'id': 1}, {'id': 2}]

    def test_dict_with_primitive_array(self):
        data = {'items': ['a', 'b']}
        assert extract_table_data(data) == [{'value': 'a'}, {'value': 'b'}]

    def test_nested_dict_with_array(self):
        data = {'data': {'users': [{'name': 'Alice'}]}}
        assert extract_table_data(data) == [{'name': 'Alice'}]

    def test_single_object(self):
        data = {'key': 'value', 'num': 42}
        assert extract_table_data(data) == [data]

    def test_empty_list(self):
        assert extract_table_data([]) == [{'value': item} for item in []]

    def test_non_dict_non_list(self):
        assert extract_table_data('hello') == []


class TestParseJsonl:
    def test_basic_jsonl(self):
        text = '{"id": 1}\n{"id": 2}\n{"id": 3}'
        result = parse_jsonl(text)
        assert len(result) == 3
        assert result[0] == {'id': 1}

    def test_empty_lines_skipped(self):
        text = '{"a": 1}\n\n{"a": 2}\n'
        result = parse_jsonl(text)
        assert len(result) == 2

    def test_empty_input(self):
        assert parse_jsonl('') == []

    def test_invalid_line_raises(self):
        import pytest

        with pytest.raises(ValueError, match='line 2'):
            parse_jsonl('{"a": 1}\n{bad json}\n{"a": 3}')

    def test_mixed_objects(self):
        text = '{"name": "Alice", "age": 30}\n{"name": "Bob", "age": 25}'
        result = parse_jsonl(text)
        assert result[1]['name'] == 'Bob'


class TestExtractByPath:
    def test_root_path(self):
        data = [{'a': 1}]
        assert extract_by_path(data, '(root)') == data

    def test_nested_path(self):
        data = {'data': {'items': [1, 2, 3]}}
        assert extract_by_path(data, 'data.items') == [1, 2, 3]

    def test_invalid_path(self):
        data = {'a': 1}
        assert extract_by_path(data, 'b.c') is None

    def test_array_index_in_path(self):
        data = {'data': [{'orders': [{'x': 1}, {'x': 2}]}, {'orders': []}]}
        assert extract_by_path(data, 'data.0.orders') == [{'x': 1}, {'x': 2}]

    def test_array_index_out_of_range(self):
        assert extract_by_path({'a': [1, 2]}, 'a.5') is None

    def test_non_numeric_index_on_array(self):
        assert extract_by_path({'a': [1, 2]}, 'a.foo') is None


class TestGetAllColumns:
    def test_basic(self):
        data = [{'a': 1, 'b': 2}, {'b': 3, 'c': 4}]
        assert get_all_columns(data) == ['a', 'b', 'c']

    def test_empty(self):
        assert get_all_columns([]) == []

    def test_non_dict_rows_ignored(self):
        data = [{'a': 1}, 'not a dict', {'b': 2}]
        assert get_all_columns(data) == ['a', 'b']


class TestExtractTableDataDepthGuard:
    """F8 - extract_table_data must not recurse without a bound."""

    @staticmethod
    def _nest(depth):
        """Build a depth-N chain of dicts iteratively (no recursion in the test)."""
        node = {'leaf': 'value'}
        for _ in range(depth):
            node = {'a': node}
        return node

    def test_deep_nesting_does_not_raise(self):
        result = extract_table_data(self._nest(1500))
        assert isinstance(result, list)
        assert len(result) == 1

    def test_stops_at_max_depth(self):
        # With max_depth=3 the descent stops before reaching the array.
        data = {'a': {'b': {'c': {'d': [{'x': 1}]}}}}
        assert extract_table_data(data, max_depth=3) == [{'d': [{'x': 1}]}]

    def test_shallow_data_is_unaffected_by_the_guard(self):
        data = {'data': {'users': [{'name': 'Alice'}]}}
        assert extract_table_data(data) == [{'name': 'Alice'}]

    def test_non_dict_at_the_cap_yields_no_rows(self):
        assert extract_table_data('scalar', _depth=99, max_depth=10) == []


class TestPreviewTruncate:
    """P2.2 / P5 - a capped COPY; the original is never touched."""

    def test_long_string_is_capped(self):
        row = {'a': 'x' * 1000}
        result = preview_truncate(row)
        assert len(result['a']) == PREVIEW_MAX_STRING + len(PREVIEW_TRUNCATION_SUFFIX)
        assert result['a'].endswith(PREVIEW_TRUNCATION_SUFFIX)

    def test_short_string_is_untouched(self):
        assert preview_truncate({'a': 'short'}) == {'a': 'short'}

    def test_every_column_survives(self):
        # Capping row keys would leave the preview table disagreeing with its
        # own header, so only the values inside a row are capped.
        row = {f'col{i}': i for i in range(60)}
        assert list(preview_truncate(row).keys()) == list(row.keys())

    def test_nested_object_keys_are_capped(self):
        row = {'meta': {f'k{i}': i for i in range(100)}}
        meta = preview_truncate(row)['meta']
        assert len(meta) == PREVIEW_MAX_ITEMS + 1
        assert '80 more keys' in meta[PREVIEW_TRUNCATION_SUFFIX]

    def test_nested_array_items_are_capped(self):
        row = {'tags': list(range(100))}
        tags = preview_truncate(row)['tags']
        assert len(tags) == PREVIEW_MAX_ITEMS + 1
        assert tags[:PREVIEW_MAX_ITEMS] == list(range(PREVIEW_MAX_ITEMS))
        assert '80 more items' in tags[-1]

    def test_input_is_not_mutated(self):
        nested = {'k': 'y' * 1000, 'items': list(range(100))}
        row = {'meta': nested, 'plain': 'z' * 1000}
        snapshot = json.dumps(row, sort_keys=True)

        preview_truncate(row)

        assert json.dumps(row, sort_keys=True) == snapshot
        assert len(row['meta']['k']) == 1000
        assert row['meta'] is nested

    def test_depth_is_bounded(self):
        node = {'leaf': 'v'}
        for _ in range(1500):
            node = {'a': node}
        result = preview_truncate(node)
        assert isinstance(result, dict)

    def test_numbers_and_booleans_pass_through(self):
        row = {'n': 1, 'f': 2.5, 'b': True, 'null': None}
        assert preview_truncate(row) == row


class TestFlattenRows:
    """P8 - one pass must produce exactly what two passes produced."""

    CASES = [
        [{'a': 1, 'b': 2}, {'b': 3, 'c': 4}],
        [{'z': 1}, {'a': 2}, {'m': 3}],
        [{'meta': {'age': 30}, 'name': 'Alice', 'scores': [1, 2]}],
        [{'a': {'b': {'c': 1}}}, {'a': {'b': {'d': 2}}}],
        [],
        [{}],
    ]

    def test_matches_the_previous_two_pass_result(self):
        for rows in self.CASES:
            expected_rows = [flatten_for_csv(row) for row in rows]
            expected_columns = get_all_columns(expected_rows)

            actual_rows, actual_columns = flatten_rows(rows)

            assert actual_rows == expected_rows
            # Column order must be byte-identical, not merely equivalent.
            assert actual_columns == expected_columns

    def test_respects_max_depth(self):
        rows = [{'a': {'b': {'c': {'d': 1}}}}]
        flattened, columns = flatten_rows(rows, max_depth=2)
        assert columns == ['a.b']
        assert isinstance(flattened[0]['a.b'], str)

    def test_non_dict_row_keeps_its_existing_empty_key_behavior(self):
        # flatten_for_csv maps a bare scalar to {'': value}, so '' has always been
        # a column here. Preserved deliberately: P8 is a refactor, not a fix.
        flattened, columns = flatten_rows([{'a': 1}, 'not a dict'])
        assert flattened == [{'a': 1}, {'': 'not a dict'}]
        assert columns == ['', 'a']
