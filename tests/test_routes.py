"""Tests for Flask routes."""

import json


class TestIndexRoute:
    def test_returns_200(self, client):
        response = client.get('/')
        assert response.status_code == 200

    def test_contains_html(self, client):
        response = client.get('/')
        assert b'JSON' in response.data


class TestHealthRoute:
    def test_returns_ok(self, client):
        response = client.get('/health')
        data = json.loads(response.data)
        assert data['status'] == 'ok'

    def test_returns_version(self, client):
        response = client.get('/health')
        data = json.loads(response.data)
        assert 'version' in data
        assert data['version'] == '1.1.0'


class TestProcessRoute:
    def test_paste_valid_json(self, client):
        response = client.post('/process', data={
            'input_method': 'paste',
            'pasted_json': '[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]'
        })
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total_rows'] == 2
        assert 'id' in data['columns']
        assert 'name' in data['columns']

    def test_paste_invalid_json(self, client):
        response = client.post('/process', data={
            'input_method': 'paste',
            'pasted_json': '{invalid json}'
        })
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_paste_empty(self, client):
        response = client.post('/process', data={
            'input_method': 'paste',
            'pasted_json': ''
        })
        assert response.status_code == 400

    def test_invalid_input_method(self, client):
        response = client.post('/process', data={
            'input_method': 'unknown'
        })
        assert response.status_code == 400

    def test_nested_json_object(self, client):
        nested = json.dumps({"data": [{"x": 1}, {"x": 2}]})
        response = client.post('/process', data={
            'input_method': 'paste',
            'pasted_json': nested
        })
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total_rows'] == 2

    def test_file_upload(self, client):
        import io
        json_content = json.dumps([{"a": 1}])
        data = {
            'input_method': 'file',
            'json_file': (io.BytesIO(json_content.encode()), 'test.json')
        }
        response = client.post('/process', data=data, content_type='multipart/form-data')
        result = json.loads(response.data)
        assert result['success'] is True

    def test_jsonl_paste(self, client):
        jsonl_content = '{"id": 1, "name": "Alice"}\n{"id": 2, "name": "Bob"}'
        response = client.post('/process', data={
            'input_method': 'paste',
            'pasted_json': jsonl_content,
            'data_format': 'jsonl'
        })
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total_rows'] == 2

    def test_jsonl_file_upload(self, client):
        import io
        jsonl_content = '{"a": 1}\n{"a": 2}\n{"a": 3}'
        data = {
            'input_method': 'file',
            'data_format': 'jsonl',
            'json_file': (io.BytesIO(jsonl_content.encode()), 'test.jsonl')
        }
        response = client.post('/process', data=data, content_type='multipart/form-data')
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['total_rows'] == 3

    def test_preview_limit(self, client, app):
        app.config['PREVIEW_ROW_LIMIT'] = 5
        rows = json.dumps([{"id": i} for i in range(20)])
        response = client.post('/process', data={
            'input_method': 'paste',
            'pasted_json': rows
        })
        data = json.loads(response.data)
        assert data['total_rows'] == 20
        assert len(data['preview']) == 5


class TestExportCsvRoute:
    def test_export_valid_data(self, client):
        response = client.post('/export-csv',
            data=json.dumps({
                'csv_data': [{'a': 1, 'b': 2}, {'a': 3, 'b': 4}],
                'csv_columns': ['a', 'b']
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        assert response.content_type.startswith('text/csv')
        csv_text = response.data.decode('utf-8')
        assert 'a,b' in csv_text

    def test_export_empty_data(self, client):
        response = client.post('/export-csv',
            data=json.dumps({
                'csv_data': [],
                'csv_columns': []
            }),
            content_type='application/json'
        )
        assert response.status_code == 400


class TestExportXlsxRoute:
    def test_export_xlsx(self, client):
        response = client.post('/export-xlsx',
            data=json.dumps({
                'csv_data': [{'a': 1, 'b': 2}],
                'csv_columns': ['a', 'b']
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        assert 'spreadsheetml' in response.content_type

    def test_export_xlsx_empty(self, client):
        response = client.post('/export-xlsx',
            data=json.dumps({'csv_data': [], 'csv_columns': []}),
            content_type='application/json'
        )
        assert response.status_code == 400


class TestPathSelection:
    def test_multiple_arrays_returns_candidates(self, client):
        multi = json.dumps({"users": [{"n": "A"}], "orders": [{"id": 1}]})
        response = client.post('/process', data={
            'input_method': 'paste',
            'pasted_json': multi
        })
        data = json.loads(response.data)
        assert data.get('needs_selection') is True
        assert len(data['candidates']) == 2

    def test_path_selection(self, client):
        multi = json.dumps({"users": [{"n": "A"}], "orders": [{"id": 1}, {"id": 2}]})
        response = client.post('/process', data={
            'input_method': 'paste',
            'pasted_json': multi,
            'json_path': 'orders'
        })
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total_rows'] == 2


class TestSecurityHeaders:
    def test_csp_header(self, client):
        response = client.get('/')
        assert 'Content-Security-Policy' in response.headers

    def test_xframe_header(self, client):
        response = client.get('/')
        assert response.headers['X-Frame-Options'] == 'DENY'

    def test_xcontent_type_header(self, client):
        response = client.get('/')
        assert response.headers['X-Content-Type-Options'] == 'nosniff'

    def test_referrer_policy(self, client):
        response = client.get('/')
        assert 'strict-origin' in response.headers['Referrer-Policy']
