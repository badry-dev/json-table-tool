"""
JSON Table Converter - A Flask web application for converting JSON to tables
Supports file upload, paste, and external API fetching with various auth methods
"""

from flask import Flask, render_template, request, jsonify, Response
import json
import csv
import io
import requests
from requests.auth import HTTPBasicAuth
#from urllib.parse import urljoin

app = Flask(__name__)

# Maximum content length for uploads (10MB)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024


def flatten_for_csv(data, parent_key='', sep='.'):
    """
    Flatten nested dictionaries for CSV export.
    Arrays are converted to JSON strings.
    """
    items = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(flatten_for_csv(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                # Convert lists to JSON string for CSV
                items.append((new_key, json.dumps(v)))
            else:
                items.append((new_key, v))
    else:
        items.append((parent_key, data))
    return dict(items)


def extract_table_data(json_data):
    """
    Extract tabular data from JSON.
    Handles nested objects and arrays.
    Returns a list of rows (dicts) and column headers.
    """
    # If it's a list of objects, use directly
    if isinstance(json_data, list):
        if len(json_data) > 0 and isinstance(json_data[0], dict):
            return json_data
        else:
            # List of primitives
            return [{"value": item} for item in json_data]
    
    # If it's a dict, look for array values
    if isinstance(json_data, dict):
        # Check if any value is a list of objects
        for key, value in json_data.items():
            if isinstance(value, list) and len(value) > 0:
                if isinstance(value[0], dict):
                    return value
                else:
                    return [{"value": item} for item in value]
        
        # If no arrays found, treat the dict itself as a single row
        # or if it has nested dicts, try to find data there
        for key, value in json_data.items():
            if isinstance(value, dict):
                result = extract_table_data(value)
                if result:
                    return result
        
        # Return the dict as a single row
        return [json_data]
    
    return []


def get_all_columns(data):
    """Get all unique column names from the data."""
    columns = set()
    for row in data:
        if isinstance(row, dict):
            columns.update(row.keys())
    return sorted(list(columns))


@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')


@app.route('/process', methods=['POST'])
def process_json():
    """
    Process JSON data from various sources:
    - File upload
    - Pasted JSON
    - External API fetch
    """
    try:
        input_method = request.form.get('input_method')
        json_data = None
        
        if input_method == 'file':
            # Handle file upload
            if 'json_file' not in request.files:
                return jsonify({'error': 'No file uploaded'}), 400
            
            file = request.files['json_file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            try:
                json_data = json.load(file)
            except json.JSONDecodeError as e:
                return jsonify({'error': f'Invalid JSON in file: {str(e)}'}), 400
        
        elif input_method == 'paste':
            # Handle pasted JSON
            pasted_json = request.form.get('pasted_json', '').strip()
            if not pasted_json:
                return jsonify({'error': 'No JSON provided'}), 400
            
            try:
                json_data = json.loads(pasted_json)
            except json.JSONDecodeError as e:
                return jsonify({'error': f'Invalid JSON: {str(e)}'}), 400
        
        elif input_method == 'api':
            # Handle external API fetch
            api_url = request.form.get('api_url', '').strip()
            if not api_url:
                return jsonify({'error': 'No API URL provided'}), 400
            
            auth_method = request.form.get('auth_method', 'none')
            
            headers = {}
            auth = None
            params = {}
            
            # Configure authentication
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
                response = requests.get(
                    api_url,
                    headers=headers,
                    auth=auth,
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                json_data = response.json()
            except requests.exceptions.Timeout:
                return jsonify({'error': 'API request timed out'}), 400
            except requests.exceptions.RequestException as e:
                return jsonify({'error': f'API request failed: {str(e)}'}), 400
            except json.JSONDecodeError:
                return jsonify({'error': 'API response is not valid JSON'}), 400
        
        else:
            return jsonify({'error': 'Invalid input method'}), 400
        
        # Extract table data
        table_data = extract_table_data(json_data)
        
        if not table_data:
            return jsonify({'error': 'Could not extract tabular data from JSON'}), 400
        
        # Get columns
        columns = get_all_columns(table_data)
        
        # Prepare preview (first 25 rows)
        preview_data = table_data[:25]
        
        # Prepare full data for CSV export (flattened)
        csv_data = [flatten_for_csv(row) for row in table_data]
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
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500


@app.route('/export-csv', methods=['POST'])
def export_csv():
    """Export data as CSV file."""
    try:
        data = request.json
        csv_data = data.get('csv_data', [])
        csv_columns = data.get('csv_columns', [])
        
        if not csv_data:
            return jsonify({'error': 'No data to export'}), 400
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=csv_columns, extrasaction='ignore')
        writer.writeheader()
        
        for row in csv_data:
            # Convert any remaining complex types to strings
            clean_row = {}
            for k, v in row.items():
                if isinstance(v, (dict, list)):
                    clean_row[k] = json.dumps(v)
                else:
                    clean_row[k] = v
            writer.writerow(clean_row)
        
        # Create response
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
        return jsonify({'error': f'Export failed: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
