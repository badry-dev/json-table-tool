"""Tests for data processing helpers."""

import json

from helpers import (
    extract_by_path,
    extract_table_data,
    flatten_for_csv,
    get_all_columns,
    parse_jsonl,
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
