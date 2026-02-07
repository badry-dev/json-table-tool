"""Tests for data processing helpers."""

import json
from helpers import flatten_for_csv, extract_table_data, get_all_columns


class TestFlattenForCsv:
    def test_flat_dict(self):
        result = flatten_for_csv({"a": 1, "b": "hello"})
        assert result == {"a": 1, "b": "hello"}

    def test_nested_dict(self):
        result = flatten_for_csv({"a": {"b": 1, "c": 2}})
        assert result == {"a.b": 1, "a.c": 2}

    def test_deeply_nested(self):
        result = flatten_for_csv({"a": {"b": {"c": {"d": 42}}}})
        assert result == {"a.b.c.d": 42}

    def test_list_becomes_json_string(self):
        result = flatten_for_csv({"tags": [1, 2, 3]})
        assert result == {"tags": "[1, 2, 3]"}

    def test_empty_dict(self):
        result = flatten_for_csv({})
        assert result == {}

    def test_max_depth_stops_recursion(self):
        deep = {"a": {"b": {"c": {"d": "value"}}}}
        result = flatten_for_csv(deep, max_depth=2)
        # At depth 2, the remaining dict should be JSON-serialized
        assert "a.b" in result
        assert isinstance(result["a.b"], str)
        parsed = json.loads(result["a.b"])
        assert parsed == {"c": {"d": "value"}}

    def test_primitive_value(self):
        result = flatten_for_csv("hello", parent_key="key")
        assert result == {"key": "hello"}

    def test_mixed_types(self):
        data = {"name": "Alice", "meta": {"age": 30}, "scores": [90, 85]}
        result = flatten_for_csv(data)
        assert result["name"] == "Alice"
        assert result["meta.age"] == 30
        assert result["scores"] == "[90, 85]"


class TestExtractTableData:
    def test_array_of_objects(self):
        data = [{"id": 1}, {"id": 2}]
        assert extract_table_data(data) == data

    def test_array_of_primitives(self):
        result = extract_table_data([1, 2, 3])
        assert result == [{"value": 1}, {"value": 2}, {"value": 3}]

    def test_dict_with_array_property(self):
        data = {"results": [{"id": 1}, {"id": 2}]}
        assert extract_table_data(data) == [{"id": 1}, {"id": 2}]

    def test_dict_with_primitive_array(self):
        data = {"items": ["a", "b"]}
        assert extract_table_data(data) == [{"value": "a"}, {"value": "b"}]

    def test_nested_dict_with_array(self):
        data = {"data": {"users": [{"name": "Alice"}]}}
        assert extract_table_data(data) == [{"name": "Alice"}]

    def test_single_object(self):
        data = {"key": "value", "num": 42}
        assert extract_table_data(data) == [data]

    def test_empty_list(self):
        assert extract_table_data([]) == [{"value": item} for item in []]

    def test_non_dict_non_list(self):
        assert extract_table_data("hello") == []


class TestGetAllColumns:
    def test_basic(self):
        data = [{"a": 1, "b": 2}, {"b": 3, "c": 4}]
        assert get_all_columns(data) == ["a", "b", "c"]

    def test_empty(self):
        assert get_all_columns([]) == []

    def test_non_dict_rows_ignored(self):
        data = [{"a": 1}, "not a dict", {"b": 2}]
        assert get_all_columns(data) == ["a", "b"]
