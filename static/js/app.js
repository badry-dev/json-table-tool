// CSRF token
const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

// DOM Elements
const form = document.getElementById('jsonForm');
const methodTabs = document.querySelectorAll('.method-tab');
const methodPanels = document.querySelectorAll('.method-panel');
const inputMethodField = document.getElementById('inputMethod');
const authMethodSelect = document.getElementById('authMethod');
const authOptions = document.querySelectorAll('.auth-options');
const fileUpload = document.getElementById('fileUpload');
const jsonFile = document.getElementById('jsonFile');
const fileName = document.getElementById('fileName');
const processBtn = document.getElementById('processBtn');
const loading = document.getElementById('loading');
const error = document.getElementById('error');
const errorText = document.getElementById('errorText');
const results = document.getElementById('results');
const tableHead = document.getElementById('tableHead');
const tableBody = document.getElementById('tableBody');
const rowCountText = document.getElementById('rowCountText');
const previewBadge = document.getElementById('previewBadge');
const exportBtn = document.getElementById('exportBtn');

// Store data for export and sorting
let csvData = null;
let csvColumns = null;
let currentColumns = null;
let currentRows = null;
let currentTotalRows = 0;
let sortColumn = null;
let sortDirection = 'asc';

// Format toggle
document.querySelectorAll('.format-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.format-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('dataFormat').value = btn.dataset.format;
    });
});

// Method tab switching
methodTabs.forEach(tab => {
    tab.addEventListener('click', () => {
        const method = tab.dataset.method;

        methodTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        methodPanels.forEach(p => {
            p.classList.remove('active');
            if (p.dataset.panel === method) {
                p.classList.add('active');
            }
        });

        inputMethodField.value = method;
        hideError();
    });
});

// Auth method switching
authMethodSelect.addEventListener('change', () => {
    const method = authMethodSelect.value;
    authOptions.forEach(opt => {
        opt.classList.remove('visible');
        if (opt.dataset.auth === method) {
            opt.classList.add('visible');
        }
    });
});

// File upload handling
fileUpload.addEventListener('dragover', (e) => {
    e.preventDefault();
    fileUpload.classList.add('drag-over');
});

fileUpload.addEventListener('dragleave', () => {
    fileUpload.classList.remove('drag-over');
});

fileUpload.addEventListener('drop', (e) => {
    e.preventDefault();
    fileUpload.classList.remove('drag-over');
    if (e.dataTransfer.files.length) {
        jsonFile.files = e.dataTransfer.files;
        updateFileName();
    }
});

jsonFile.addEventListener('change', updateFileName);

function updateFileName() {
    if (jsonFile.files.length) {
        fileName.textContent = jsonFile.files[0].name;
        fileName.classList.add('visible');
    } else {
        fileName.classList.remove('visible');
    }
}

// Form submission
form.addEventListener('submit', async (e) => {
    e.preventDefault();

    hideError();
    showLoading();
    hideResults();

    const formData = new FormData(form);
    formData.append('csrf_token', csrfToken);

    try {
        const response = await fetch('/process', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok || data.error) {
            throw new Error(data.error || 'An error occurred');
        }

        // Store for export
        csvData = data.csv_data;
        csvColumns = data.csv_columns;

        // Render table
        renderTable(data.columns, data.preview, data.total_rows);
        showResults();

    } catch (err) {
        showError(err.message);
    } finally {
        hideLoading();
    }
});

// Render table
function renderTable(columns, rows, totalRows) {
    currentColumns = columns;
    currentRows = rows;
    currentTotalRows = totalRows;
    renderTableDOM(columns, rows, totalRows);
}

function renderTableDOM(columns, rows, totalRows) {
    tableHead.innerHTML = '';
    tableBody.innerHTML = '';

    // Header with sortable columns
    const headerRow = document.createElement('tr');
    columns.forEach(col => {
        const th = document.createElement('th');
        th.textContent = col;
        th.classList.add('sortable');
        if (sortColumn === col) {
            th.classList.add(sortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
        }
        th.addEventListener('click', () => handleSort(col));
        headerRow.appendChild(th);
    });
    tableHead.appendChild(headerRow);

    // Body
    rows.forEach(row => {
        const tr = document.createElement('tr');
        columns.forEach(col => {
            const td = document.createElement('td');
            const value = row[col];
            td.innerHTML = formatValue(value);
            tr.appendChild(td);
        });
        tableBody.appendChild(tr);
    });

    // Update counts
    rowCountText.textContent = `${totalRows} total rows`;
    if (totalRows > 25) {
        previewBadge.textContent = 'Showing first 25';
        previewBadge.classList.remove('hidden');
    } else {
        previewBadge.textContent = `Showing all ${totalRows}`;
        previewBadge.classList.add('hidden');
    }
}

// Column sorting (client-side on preview rows)
function handleSort(col) {
    if (sortColumn === col) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortColumn = col;
        sortDirection = 'asc';
    }

    const sorted = [...currentRows].sort((a, b) => {
        let valA = a[col];
        let valB = b[col];

        if (valA === null || valA === undefined) valA = '';
        if (valB === null || valB === undefined) valB = '';

        if (typeof valA === 'object') valA = JSON.stringify(valA);
        if (typeof valB === 'object') valB = JSON.stringify(valB);

        if (typeof valA === 'number' && typeof valB === 'number') {
            return sortDirection === 'asc' ? valA - valB : valB - valA;
        }

        const strA = String(valA).toLowerCase();
        const strB = String(valB).toLowerCase();
        if (strA < strB) return sortDirection === 'asc' ? -1 : 1;
        if (strA > strB) return sortDirection === 'asc' ? 1 : -1;
        return 0;
    });

    renderTableDOM(currentColumns, sorted, currentTotalRows);
}

// Format cell value
function formatValue(value) {
    if (value === null || value === undefined) {
        return '<span class="text-null">null</span>';
    }

    if (typeof value === 'object') {
        if (Array.isArray(value)) {
            if (value.length === 0) return '[]';
            if (typeof value[0] === 'object') {
                return renderNestedTable(value);
            }
            return escapeHtml(JSON.stringify(value));
        }
        return renderNestedObject(value);
    }

    if (typeof value === 'boolean') {
        return value
            ? '<span class="text-true">true</span>'
            : '<span class="text-false">false</span>';
    }

    return escapeHtml(String(value));
}

// Render nested object as mini table
function renderNestedObject(obj) {
    const keys = Object.keys(obj);
    if (keys.length === 0) return '{}';

    let html = '<table class="nested-table"><tbody>';
    keys.forEach(key => {
        const val = obj[key];
        let displayVal = val;
        if (typeof val === 'object' && val !== null) {
            displayVal = JSON.stringify(val);
        }
        html += `<tr><td><strong>${escapeHtml(key)}</strong></td><td>${escapeHtml(String(displayVal))}</td></tr>`;
    });
    html += '</tbody></table>';
    return html;
}

// Render nested array of objects
function renderNestedTable(arr) {
    if (arr.length === 0) return '[]';

    const cols = [...new Set(arr.flatMap(item => typeof item === 'object' ? Object.keys(item) : []))];
    if (cols.length === 0) return escapeHtml(JSON.stringify(arr));

    let html = '<table class="nested-table"><thead><tr>';
    cols.forEach(col => {
        html += `<th>${escapeHtml(col)}</th>`;
    });
    html += '</tr></thead><tbody>';

    arr.slice(0, 5).forEach(item => {
        html += '<tr>';
        cols.forEach(col => {
            let val = item[col];
            if (typeof val === 'object' && val !== null) {
                val = JSON.stringify(val);
            }
            html += `<td>${escapeHtml(String(val ?? ''))}</td>`;
        });
        html += '</tr>';
    });

    if (arr.length > 5) {
        html += `<tr><td colspan="${cols.length}" class="text-center-muted">... and ${arr.length - 5} more rows</td></tr>`;
    }

    html += '</tbody></table>';
    return html;
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Export CSV
exportBtn.addEventListener('click', async () => {
    if (!csvData || !csvColumns) {
        showError('No data to export');
        return;
    }

    try {
        const response = await fetch('/export-csv', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                csv_data: csvData,
                csv_columns: csvColumns
            })
        });

        if (!response.ok) {
            throw new Error('Export failed');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'exported_data.csv';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();

    } catch (err) {
        showError(err.message);
    }
});

// About link
document.getElementById('aboutLink').addEventListener('click', (e) => {
    e.preventDefault();
    alert('JSON Table Converter v1.1.0\n\nBuilt with Flask + Python\nNo data is ever stored or logged.');
});

// UI helpers
function showLoading() {
    loading.classList.add('visible');
    processBtn.disabled = true;
}

function hideLoading() {
    loading.classList.remove('visible');
    processBtn.disabled = false;
}

function showError(message) {
    errorText.textContent = message;
    error.classList.add('visible');
}

function hideError() {
    error.classList.remove('visible');
}

function showResults() {
    results.classList.add('visible');
}

function hideResults() {
    results.classList.remove('visible');
}
