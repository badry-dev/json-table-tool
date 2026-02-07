"""Flask route handlers."""

import json
import csv
import io
import logging
import requests
from requests.auth import HTTPBasicAuth
from flask import Blueprint, render_template, request, jsonify, Response, current_app

from extensions import limiter
from security import validate_url
from helpers import (
    flatten_for_csv, extract_table_data, get_all_columns, parse_jsonl,
    find_candidate_arrays, extract_by_path
)

logger = logging.getLogger(__name__)

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')


@bp.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'version': current_app.config['APP_VERSION']
    })


@bp.route('/process', methods=['POST'])
@limiter.limit(lambda: current_app.config.get('RATE_LIMIT_PROCESS', '30/minute'))
def process_json():
    """Process JSON data from file upload, pasted text, or API fetch."""
    try:
        input_method = request.form.get('input_method')
        json_data = None

        data_format = request.form.get('data_format', 'json')

        if input_method == 'file':
            if 'json_file' not in request.files:
                return jsonify({'error': 'No file uploaded'}), 400
            file = request.files['json_file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            try:
                content = file.read().decode('utf-8')
                if data_format == 'jsonl':
                    json_data = parse_jsonl(content)
                else:
                    json_data = json.loads(content)
            except (json.JSONDecodeError, ValueError) as e:
                return jsonify({'error': f'Invalid data in file: {str(e)}'}), 400

        elif input_method == 'paste':
            pasted_json = request.form.get('pasted_json', '').strip()
            if not pasted_json:
                return jsonify({'error': 'No JSON provided'}), 400
            try:
                if data_format == 'jsonl':
                    json_data = parse_jsonl(pasted_json)
                else:
                    json_data = json.loads(pasted_json)
            except (json.JSONDecodeError, ValueError) as e:
                return jsonify({'error': f'Invalid data: {str(e)}'}), 400

        elif input_method == 'api':
            api_url = request.form.get('api_url', '').strip()
            if not api_url:
                return jsonify({'error': 'No API URL provided'}), 400

            is_valid, error_msg, resolved_ip = validate_url(api_url)
            if not is_valid:
                return jsonify({'error': error_msg}), 400

            auth_method = request.form.get('auth_method', 'none')
            headers = {}
            auth = None
            params = {}

            if auth_method == 'api_key':
                header_name = request.form.get('api_key_header', 'X-API-Key')
                api_key = request.form.get('api_key', '')
                if api_key:
                    headers[header_name] = api_key
            elif auth_method == 'basic':
                username = request.form.get('basic_username', '')
                password = request.form.get('basic_password', '')
                if username:
                    auth = HTTPBasicAuth(username, password)
            elif auth_method == 'bearer':
                bearer_token = request.form.get('bearer_token', '')
                if bearer_token:
                    headers['Authorization'] = f'Bearer {bearer_token}'
            elif auth_method == 'query_param':
                param_name = request.form.get('query_param_name', 'api_key')
                param_value = request.form.get('query_param_value', '')
                if param_value:
                    params[param_name] = param_value

            try:
                timeout = current_app.config['API_FETCH_TIMEOUT']
                max_size = current_app.config['API_FETCH_MAX_RESPONSE']

                # Pin to the resolved IP to prevent DNS rebinding,
                # and disable redirects to prevent SSRF bypass
                from urllib.parse import urlparse, urlunparse
                parsed_api = urlparse(api_url)
                headers['Host'] = parsed_api.hostname
                pinned_url = urlunparse(parsed_api._replace(
                    netloc=resolved_ip + (f':{parsed_api.port}' if parsed_api.port else '')
                ))

                resp = requests.get(
                    pinned_url,
                    headers=headers,
                    auth=auth,
                    params=params,
                    timeout=timeout,
                    stream=True,
                    allow_redirects=False,
                    verify=True
                )
                resp.raise_for_status()

                content = bytearray()
                for chunk in resp.iter_content(chunk_size=8192):
                    content.extend(chunk)
                    if len(content) > max_size:
                        return jsonify({
                            'error': f'API response exceeds maximum size '
                                     f'({max_size // (1024 * 1024)}MB)'
                        }), 400

                json_data = json.loads(bytes(content))

            except requests.exceptions.Timeout:
                return jsonify({'error': 'API request timed out'}), 400
            except requests.exceptions.RequestException as e:
                logger.warning('API request failed: %s', e)
                return jsonify({'error': 'API request failed'}), 400
            except json.JSONDecodeError:
                return jsonify({'error': 'API response is not valid JSON'}), 400
        else:
            return jsonify({'error': 'Invalid input method'}), 400

        # Check if user selected a specific JSON path
        json_path = request.form.get('json_path', '')

        if json_path:
            selected = extract_by_path(json_data, json_path)
            if selected is not None and isinstance(selected, list):
                table_data = extract_table_data(selected)
            else:
                return jsonify({'error': f'Path "{json_path}" not found or not an array'}), 400
        else:
            # Check for multiple candidate arrays
            candidates = find_candidate_arrays(json_data)
            if len(candidates) > 1:
                return jsonify({
                    'needs_selection': True,
                    'candidates': candidates
                })
            table_data = extract_table_data(json_data)

        if not table_data:
            return jsonify({'error': 'Could not extract tabular data from JSON'}), 400

        columns = get_all_columns(table_data)
        preview_limit = current_app.config['PREVIEW_ROW_LIMIT']
        preview_data = table_data[:preview_limit]

        max_depth = current_app.config['FLATTEN_MAX_DEPTH']
        csv_data = [flatten_for_csv(row, max_depth=max_depth) for row in table_data]
        csv_columns = get_all_columns(csv_data)

        return jsonify({
            'success': True,
            'columns': columns,
            'preview': preview_data,
            'total_rows': len(table_data),
            'csv_data': csv_data,
            'csv_columns': csv_columns
        })

    except Exception as e:
        logger.exception('Unexpected error in process_json')
        return jsonify({'error': 'An internal error occurred'}), 500


@bp.route('/export-csv', methods=['POST'])
@limiter.limit(lambda: current_app.config.get('RATE_LIMIT_EXPORT', '60/minute'))
def export_csv():
    """Export data as CSV file."""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'error': 'Invalid or missing JSON body'}), 400

        csv_data = data.get('csv_data', [])
        csv_columns = data.get('csv_columns', [])

        if not csv_data:
            return jsonify({'error': 'No data to export'}), 400

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=csv_columns, extrasaction='ignore')
        writer.writeheader()

        for row in csv_data:
            clean_row = {}
            for k, v in row.items():
                if isinstance(v, (dict, list)):
                    clean_row[k] = json.dumps(v)
                else:
                    clean_row[k] = v
            writer.writerow(clean_row)

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': 'attachment; filename=exported_data.csv',
                'Content-Type': 'text/csv; charset=utf-8'
            }
        )

    except Exception as e:
        logger.exception('Unexpected error in export_csv')
        return jsonify({'error': 'Export failed'}), 500


@bp.route('/export-xlsx', methods=['POST'])
@limiter.limit(lambda: current_app.config.get('RATE_LIMIT_EXPORT', '60/minute'))
def export_xlsx():
    """Export data as Excel file."""
    try:
        from openpyxl import Workbook

        data = request.get_json(silent=True)
        if not data:
            return jsonify({'error': 'Invalid or missing JSON body'}), 400

        xlsx_data = data.get('csv_data', [])
        xlsx_columns = data.get('csv_columns', [])

        if not xlsx_data:
            return jsonify({'error': 'No data to export'}), 400

        wb = Workbook()
        ws = wb.active
        ws.title = 'Data'

        # Header row
        ws.append(xlsx_columns)

        # Data rows
        for row in xlsx_data:
            row_values = []
            for col in xlsx_columns:
                v = row.get(col, '')
                if isinstance(v, (dict, list)):
                    v = json.dumps(v)
                row_values.append(v)
            ws.append(row_values)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return Response(
            output.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition': 'attachment; filename=exported_data.xlsx',
            }
        )

    except Exception as e:
        logger.exception('Unexpected error in export_xlsx')
        return jsonify({'error': 'Export failed'}), 500
