"""Tests for Flask routes."""

import csv
import io
import json
from unittest.mock import MagicMock, patch


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

    def test_returns_version(self, client, app):
        response = client.get('/health')
        data = json.loads(response.data)
        assert 'version' in data
        assert data['version'] == app.config['APP_VERSION']


class TestProcessRoute:
    def test_paste_valid_json(self, client):
        response = client.post(
            '/process',
            data={
                'input_method': 'paste',
                'pasted_json': '[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]',
                'json_path': '(root)',
            },
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total_rows'] == 2
        assert 'id' in data['columns']
        assert 'name' in data['columns']

    def test_paste_invalid_json(self, client):
        response = client.post(
            '/process', data={'input_method': 'paste', 'pasted_json': '{invalid json}'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_paste_empty(self, client):
        response = client.post('/process', data={'input_method': 'paste', 'pasted_json': ''})
        assert response.status_code == 400

    def test_invalid_input_method(self, client):
        response = client.post('/process', data={'input_method': 'unknown'})
        assert response.status_code == 400

    def test_nested_json_object(self, client):
        nested = json.dumps({'data': [{'x': 1}, {'x': 2}]})
        response = client.post(
            '/process', data={'input_method': 'paste', 'pasted_json': nested, 'json_path': 'data'}
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total_rows'] == 2

    def test_no_path_returns_tree_payload(self, client):
        response = client.post(
            '/process', data={'input_method': 'paste', 'pasted_json': '[{"id": 1}, {"id": 2}]'}
        )
        data = json.loads(response.data)
        assert data.get('needs_selection') is True
        assert data['raw_json'] == [{'id': 1}, {'id': 2}]

    def test_file_upload(self, client):
        import io

        json_content = json.dumps([{'a': 1}])
        data = {
            'input_method': 'file',
            'json_path': '(root)',
            'json_file': (io.BytesIO(json_content.encode()), 'test.json'),
        }
        response = client.post('/process', data=data, content_type='multipart/form-data')
        result = json.loads(response.data)
        assert result['success'] is True

    def test_jsonl_paste(self, client):
        jsonl_content = '{"id": 1, "name": "Alice"}\n{"id": 2, "name": "Bob"}'
        response = client.post(
            '/process',
            data={
                'input_method': 'paste',
                'pasted_json': jsonl_content,
                'data_format': 'jsonl',
                'json_path': '(root)',
            },
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total_rows'] == 2

    def test_jsonl_file_upload(self, client):
        import io

        jsonl_content = '{"a": 1}\n{"a": 2}\n{"a": 3}'
        data = {
            'input_method': 'file',
            'data_format': 'jsonl',
            'json_path': '(root)',
            'json_file': (io.BytesIO(jsonl_content.encode()), 'test.jsonl'),
        }
        response = client.post('/process', data=data, content_type='multipart/form-data')
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['total_rows'] == 3

    def test_preview_limit(self, client, app):
        app.config['PREVIEW_ROW_LIMIT'] = 5
        rows = json.dumps([{'id': i} for i in range(20)])
        response = client.post(
            '/process', data={'input_method': 'paste', 'pasted_json': rows, 'json_path': '(root)'}
        )
        data = json.loads(response.data)
        assert data['total_rows'] == 20
        assert len(data['preview']) == 5


class TestExportCsvRoute:
    def test_export_valid_data(self, client):
        response = client.post(
            '/export-csv',
            data=json.dumps(
                {'csv_data': [{'a': 1, 'b': 2}, {'a': 3, 'b': 4}], 'csv_columns': ['a', 'b']}
            ),
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.content_type.startswith('text/csv')
        csv_text = response.data.decode('utf-8')
        assert 'a,b' in csv_text

    def test_export_empty_data(self, client):
        response = client.post(
            '/export-csv',
            data=json.dumps({'csv_data': [], 'csv_columns': []}),
            content_type='application/json',
        )
        assert response.status_code == 400


class TestExportXlsxRoute:
    def test_export_xlsx(self, client):
        response = client.post(
            '/export-xlsx',
            data=json.dumps({'csv_data': [{'a': 1, 'b': 2}], 'csv_columns': ['a', 'b']}),
            content_type='application/json',
        )
        assert response.status_code == 200
        assert 'spreadsheetml' in response.content_type

    def test_export_xlsx_empty(self, client):
        response = client.post(
            '/export-xlsx',
            data=json.dumps({'csv_data': [], 'csv_columns': []}),
            content_type='application/json',
        )
        assert response.status_code == 400


class TestPathSelection:
    def test_no_path_returns_raw_json_for_tree(self, client):
        payload = {'users': [{'n': 'A'}], 'orders': [{'id': 1}]}
        response = client.post(
            '/process', data={'input_method': 'paste', 'pasted_json': json.dumps(payload)}
        )
        data = json.loads(response.data)
        assert data.get('needs_selection') is True
        assert data['raw_json'] == payload

    def test_path_selection(self, client):
        multi = json.dumps({'users': [{'n': 'A'}], 'orders': [{'id': 1}, {'id': 2}]})
        response = client.post(
            '/process', data={'input_method': 'paste', 'pasted_json': multi, 'json_path': 'orders'}
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total_rows'] == 2

    def test_path_to_array_index_object(self, client):
        payload = json.dumps({'data': [{'id': 1, 'orders': [{'x': 1}, {'x': 2}]}]})
        response = client.post(
            '/process',
            data={'input_method': 'paste', 'pasted_json': payload, 'json_path': 'data.0.orders'},
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total_rows'] == 2

    def test_path_to_single_object_becomes_one_row(self, client):
        payload = json.dumps({'meta': {'version': 3, 'name': 'x'}})
        response = client.post(
            '/process', data={'input_method': 'paste', 'pasted_json': payload, 'json_path': 'meta'}
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total_rows'] == 1
        assert 'version' in data['columns']

    def test_path_to_primitive_rejected(self, client):
        payload = json.dumps({'a': 1})
        response = client.post(
            '/process', data={'input_method': 'paste', 'pasted_json': payload, 'json_path': 'a'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'primitive' in data['error']

    def test_invalid_path_rejected(self, client):
        payload = json.dumps({'a': {'b': 1}})
        response = client.post(
            '/process', data={'input_method': 'paste', 'pasted_json': payload, 'json_path': 'a.c'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'not found' in data['error']


class TestApiFetch:
    def _mock_response(self, json_data, status_code=200):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        content = json.dumps(json_data).encode()
        mock_resp.iter_content.return_value = [content]
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    @patch('routes.requests.get')
    @patch('routes.validate_url')
    def test_api_fetch_success(self, mock_validate, mock_get, client):
        mock_validate.return_value = (True, None)
        mock_get.return_value = self._mock_response([{'id': 1}, {'id': 2}])

        response = client.post(
            '/process',
            data={
                'input_method': 'api',
                'api_url': 'https://api.example.com/data',
                'json_path': '(root)',
            },
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total_rows'] == 2
        # Verify allow_redirects=False is passed
        _, kwargs = mock_get.call_args
        assert kwargs['allow_redirects'] is False

    @patch('routes.requests.get')
    @patch('routes.validate_url')
    def test_api_fetch_timeout(self, mock_validate, mock_get, client):
        import requests as req

        mock_validate.return_value = (True, None)
        mock_get.side_effect = req.exceptions.Timeout('timed out')

        response = client.post(
            '/process', data={'input_method': 'api', 'api_url': 'https://api.example.com/data'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'timed out' in data['error'].lower()

    @patch('routes.requests.get')
    @patch('routes.validate_url')
    def test_api_fetch_non_json(self, mock_validate, mock_get, client):
        mock_validate.return_value = (True, None)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [b'<html>not json</html>']
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        response = client.post(
            '/process', data={'input_method': 'api', 'api_url': 'https://api.example.com/data'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'not valid JSON' in data['error']

    @patch('routes.requests.get')
    @patch('routes.validate_url')
    def test_api_fetch_max_size_exceeded(self, mock_validate, mock_get, client, app):
        mock_validate.return_value = (True, None)
        app.config['API_FETCH_MAX_RESPONSE'] = 100  # 100 bytes
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [b'x' * 200]
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        response = client.post(
            '/process', data={'input_method': 'api', 'api_url': 'https://api.example.com/data'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'exceeds maximum size' in data['error']

    @patch('routes.validate_url')
    def test_api_fetch_ssrf_blocked(self, mock_validate, client):
        mock_validate.return_value = (
            False,
            'URLs pointing to private or internal networks are not allowed',
        )

        response = client.post(
            '/process', data={'input_method': 'api', 'api_url': 'http://169.254.169.254/metadata'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'private' in data['error'].lower()

    @patch('routes.requests.get')
    @patch('routes.validate_url')
    def test_api_fetch_jsonl(self, mock_validate, mock_get, client):
        mock_validate.return_value = (True, None)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        content = b'{"id": 1, "name": "Alice"}\n{"id": 2, "name": "Bob"}'
        mock_resp.iter_content.return_value = [content]
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        response = client.post(
            '/process',
            data={
                'input_method': 'api',
                'api_url': 'https://api.example.com/data',
                'data_format': 'jsonl',
                'json_path': '(root)',
            },
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total_rows'] == 2

    @patch('routes.requests.get')
    @patch('routes.validate_url')
    def test_api_fetch_request_error_no_leak(self, mock_validate, mock_get, client):
        import requests as req

        mock_validate.return_value = (True, None)
        mock_get.side_effect = req.exceptions.ConnectionError(
            'Connection to secret-internal-host:8080 refused'
        )

        response = client.post(
            '/process', data={'input_method': 'api', 'api_url': 'https://api.example.com/data'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        # Should NOT leak the internal connection details
        assert 'secret-internal-host' not in data['error']
        assert data['error'] == 'API request failed'


class TestFileUploadEncoding:
    def test_non_utf8_file_returns_400(self, client):
        import io

        # Latin-1 encoded content with bytes invalid in UTF-8
        content = b'\xff\xfe This is not valid UTF-8'
        data = {'input_method': 'file', 'json_file': (io.BytesIO(content), 'test.json')}
        response = client.post('/process', data=data, content_type='multipart/form-data')
        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'UTF-8' in result['error']


class TestExportEdgeCases:
    def test_export_csv_no_json_body(self, client):
        response = client.post('/export-csv', data='not json', content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Invalid or missing' in data['error']

    def test_export_xlsx_no_json_body(self, client):
        response = client.post('/export-xlsx', data='not json', content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Invalid or missing' in data['error']

    def test_export_csv_no_content_type(self, client):
        response = client.post('/export-csv', data='hello')
        assert response.status_code == 400

    def test_export_xlsx_no_content_type(self, client):
        response = client.post('/export-xlsx', data='hello')
        assert response.status_code == 400


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


class TestFormulaInjection:
    """F1 - CSV/XLSX formula injection (CWE-1236)."""

    DANGEROUS = ['=SUM(A1)', '@cmd', '+1', '-1', '\tlead', '\rlead', '\nlead']

    def test_csv_prefixes_every_trigger(self, client):
        rows = [{'v': value} for value in self.DANGEROUS]
        response = client.post(
            '/export-csv',
            data=json.dumps({'csv_data': rows, 'csv_columns': ['v']}),
            content_type='application/json',
        )
        assert response.status_code == 200

        parsed = list(csv.reader(io.StringIO(response.data.decode('utf-8'))))
        emitted = [row[0] for row in parsed[1:]]
        assert emitted == ["'" + value for value in self.DANGEROUS]

    def test_csv_leaves_safe_values_alone(self, client):
        response = client.post(
            '/export-csv',
            data=json.dumps(
                {
                    'csv_data': [{'a': 'plain', 'b': 5, 'c': 'user@example.com'}],
                    'csv_columns': ['a', 'b', 'c'],
                }
            ),
            content_type='application/json',
        )
        parsed = list(csv.reader(io.StringIO(response.data.decode('utf-8'))))
        assert parsed[1] == ['plain', '5', 'user@example.com']

    def test_csv_sanitizes_column_headers(self, client):
        response = client.post(
            '/export-csv',
            data=json.dumps({'csv_data': [{'=EVIL()': 1}], 'csv_columns': ['=EVIL()']}),
            content_type='application/json',
        )
        parsed = list(csv.reader(io.StringIO(response.data.decode('utf-8'))))
        assert parsed[0] == ["'=EVIL()"]

    def test_csv_serializes_containers(self, client):
        response = client.post(
            '/export-csv',
            data=json.dumps({'csv_data': [{'a': {'k': 'v'}}], 'csv_columns': ['a']}),
            content_type='application/json',
        )
        parsed = list(csv.reader(io.StringIO(response.data.decode('utf-8'))))
        assert parsed[1] == ['{"k": "v"}']

    def test_xlsx_writes_triggers_as_string_cells(self, client):
        from openpyxl import load_workbook

        rows = [{'v': value} for value in self.DANGEROUS]
        response = client.post(
            '/export-xlsx',
            data=json.dumps({'csv_data': rows, 'csv_columns': ['v']}),
            content_type='application/json',
        )
        assert response.status_code == 200

        ws = load_workbook(io.BytesIO(response.data)).active
        for index, value in enumerate(self.DANGEROUS, start=2):
            cell = ws.cell(row=index, column=1)
            assert cell.data_type == 's', f'{value!r} was written as {cell.data_type}'
            # XLSX carries an explicit type, so the text itself stays intact.
            assert cell.value == value.replace('\r', '\n')

    def test_xlsx_sanitizes_column_headers(self, client):
        from openpyxl import load_workbook

        response = client.post(
            '/export-xlsx',
            data=json.dumps({'csv_data': [{'=EVIL()': 1}], 'csv_columns': ['=EVIL()']}),
            content_type='application/json',
        )
        ws = load_workbook(io.BytesIO(response.data)).active
        assert ws.cell(row=1, column=1).data_type == 's'

    def test_xlsx_keeps_numbers_numeric(self, client):
        from openpyxl import load_workbook

        response = client.post(
            '/export-xlsx',
            data=json.dumps({'csv_data': [{'a': -1, 'b': 2.5}], 'csv_columns': ['a', 'b']}),
            content_type='application/json',
        )
        ws = load_workbook(io.BytesIO(response.data)).active
        assert ws.cell(row=2, column=1).value == -1
        assert ws.cell(row=2, column=2).value == 2.5
