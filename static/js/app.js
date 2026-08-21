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
    await submitForm();
});

async function submitForm(jsonPath) {
    hideError();
    showLoading();
    hideResults();

    const formData = new FormData(form);
    formData.append('csrf_token', csrfToken);
    if (jsonPath) {
        formData.append('json_path', jsonPath);
    }

    try {
        const response = await fetch('/process', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.needs_selection) {
            hideLoading();
            showTreePicker(data.raw_json);
            return;
        }

        if (!response.ok || data.error) {
            throw new Error(data.error || 'An error occurred');
        }

        csvData = data.csv_data;
        csvColumns = data.csv_columns;

        renderTable(data.columns, data.preview, data.total_rows);
        showResults();

    } catch (err) {
        showError(err.message);
    } finally {
        hideLoading();
    }
}

// JSON tree picker
const pathModal = document.getElementById('pathModal');
const treeContainer = document.getElementById('treeContainer');
const treeSelectedLabel = document.getElementById('treeSelected');
const treeConfirmBtn = document.getElementById('treeConfirm');
const treeCancelBtn = document.getElementById('treeCancel');

let selectedTreePath = null;

function showTreePicker(rawJson) {
    selectedTreePath = null;
    treeSelectedLabel.textContent = 'No node selected';
    treeConfirmBtn.disabled = true;
    treeContainer.innerHTML = '';
    treeContainer.appendChild(buildTreeNode(rawJson, '(root)', 'root', true));
    pathModal.classList.add('visible');
}

function describeNode(value) {
    if (value === null) return { kind: 'null', label: 'null', selectable: false };
    if (Array.isArray(value)) {
        return { kind: 'array', label: `array (${value.length})`, selectable: true };
    }
    if (typeof value === 'object') {
        return { kind: 'object', label: `object (${Object.keys(value).length} keys)`, selectable: true };
    }
    if (typeof value === 'string') {
        const preview = value.length > 40 ? value.slice(0, 40) + '…' : value;
        return { kind: 'string', label: `"${preview}"`, selectable: false };
    }
    return { kind: typeof value, label: String(value), selectable: false };
}

function buildTreeNode(value, path, keyLabel, openByDefault) {
    const info = describeNode(value);
    const node = document.createElement('div');
    node.classList.add('tree-node', `tree-${info.kind}`);

    const row = document.createElement('div');
    row.classList.add('tree-row');

    const toggle = document.createElement('span');
    toggle.classList.add('tree-toggle');
    const hasChildren = info.kind === 'object' || info.kind === 'array';
    toggle.textContent = hasChildren ? (openByDefault ? '▾' : '▸') : '·';
    row.appendChild(toggle);

    const label = document.createElement('span');
    label.classList.add('tree-label');
    label.innerHTML = `<span class="tree-key">${escapeHtml(keyLabel)}</span> <span class="tree-type">${escapeHtml(info.label)}</span>`;
    row.appendChild(label);

    if (info.selectable) {
        row.classList.add('tree-selectable');
        row.addEventListener('click', (e) => {
            // Don't select when clicking only the toggle chevron
            if (e.target === toggle && hasChildren) return;
            selectNode(row, path);
        });
        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleNode(node, toggle);
        });
    } else {
        toggle.addEventListener('click', (e) => e.stopPropagation());
    }

    node.appendChild(row);

    if (hasChildren) {
        const children = document.createElement('div');
        children.classList.add('tree-children');
        if (!openByDefault) children.classList.add('hidden');

        if (Array.isArray(value)) {
            const max = Math.min(value.length, 50);
            for (let i = 0; i < max; i++) {
                const childPath = path === '(root)' ? String(i) : `${path}.${i}`;
                children.appendChild(buildTreeNode(value[i], childPath, `[${i}]`, false));
            }
            if (value.length > max) {
                const more = document.createElement('div');
                more.classList.add('tree-more');
                more.textContent = `… and ${value.length - max} more items`;
                children.appendChild(more);
            }
        } else {
            for (const k of Object.keys(value)) {
                const childPath = path === '(root)' ? k : `${path}.${k}`;
                children.appendChild(buildTreeNode(value[k], childPath, k, false));
            }
        }
        node.appendChild(children);
    }
    return node;
}

function toggleNode(node, toggle) {
    const children = node.querySelector(':scope > .tree-children');
    if (!children) return;
    const isHidden = children.classList.toggle('hidden');
    toggle.textContent = isHidden ? '▸' : '▾';
}

function selectNode(row, path) {
    treeContainer.querySelectorAll('.tree-row.selected').forEach(r => r.classList.remove('selected'));
    row.classList.add('selected');
    selectedTreePath = path;
    treeSelectedLabel.textContent = `Selected: ${path}`;
    treeConfirmBtn.disabled = false;
}

treeConfirmBtn.addEventListener('click', () => {
    if (!selectedTreePath) return;
    pathModal.classList.remove('visible');
    submitForm(selectedTreePath);
});

treeCancelBtn.addEventListener('click', () => {
    pathModal.classList.remove('visible');
});

// Close modal on overlay click
pathModal.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) {
        e.currentTarget.classList.remove('visible');
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

// Export dropdown toggle
const exportDropdown = document.getElementById('exportDropdown');
exportBtn.addEventListener('click', () => {
    exportDropdown.classList.toggle('visible');
});

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('.export-group')) {
        exportDropdown.classList.remove('visible');
    }
});

// Export handlers
document.querySelectorAll('.export-dropdown-item').forEach(item => {
    item.addEventListener('click', async () => {
        exportDropdown.classList.remove('visible');
        const format = item.dataset.format;

        if (!csvData || !csvColumns) {
            showError('No data to export');
            return;
        }

        if (format === 'csv') {
            downloadDelimited(csvColumns, csvData, ',', 'exported_data.csv');
        } else if (format === 'tsv') {
            downloadDelimited(csvColumns, csvData, '\t', 'exported_data.tsv');
        } else if (format === 'xlsx') {
            await exportXlsx();
        }
    });
});

// Spreadsheet formula triggers (OWASP). Must stay in sync with
// helpers.FORMULA_TRIGGERS on the server.
function formulaTriggers() {
    return ['=', '+', '-', '@', '\t', '\r', '\n'];
}

// Reduce a cell to the scalar a writer emits. Containers become their JSON text.
function serializeCellValue(value) {
    if (value === null || value === undefined) return '';
    if (typeof value === 'object') return JSON.stringify(value);
    return value;
}

// Defuse CSV/TSV formula injection (CWE-1236) by prefixing a dangerous value
// with a single quote. Delimited output carries no type channel, so this is the
// only place the value can be marked as text. JSONL and Markdown exports are
// deliberately NOT routed through here.
function sanitizeCell(value) {
    const serialized = serializeCellValue(value);
    if (typeof serialized === 'string' && formulaTriggers().some(t => serialized.startsWith(t))) {
        return "'" + serialized;
    }
    return serialized;
}

// Pure string builder, kept separate from the download so it can be asserted
// directly (tests/js/test_export_sanitize.mjs).
function buildDelimited(columns, data, delimiter) {
    const escape = (val) => {
        const str = String(val ?? '');
        if (str.includes(delimiter) || str.includes('"') || str.includes('\n')) {
            return '"' + str.replace(/"/g, '""') + '"';
        }
        return str;
    };

    let output = columns.map(col => escape(sanitizeCell(col))).join(delimiter) + '\n';
    data.forEach(row => {
        const line = columns
            .map(col => escape(sanitizeCell(row[col])))
            .join(delimiter);
        output += line + '\n';
    });
    return output;
}

// Client-side CSV/TSV generation
function downloadDelimited(columns, data, delimiter, filename) {
    const output = buildDelimited(columns, data, delimiter);

    const mimeType = delimiter === '\t'
        ? 'text/tab-separated-values; charset=utf-8'
        : 'text/csv; charset=utf-8';
    const blob = new Blob([output], { type: mimeType });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    a.remove();
}

// Server-side Excel export (needs openpyxl)
async function exportXlsx() {
    try {
        const response = await fetch('/export-xlsx', {
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

        if (!response.ok) throw new Error('Excel export failed');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'exported_data.xlsx';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
    } catch (err) {
        showError(err.message);
    }
}

// Theme toggle
const themeToggle = document.getElementById('themeToggle');
const sunPath = 'M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z';
const moonPath = 'M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z';

function applyTheme(theme) {
    if (theme === 'light') {
        document.documentElement.classList.add('light');
        document.getElementById('themeIcon').querySelector('path').setAttribute('d', moonPath);
    } else {
        document.documentElement.classList.remove('light');
        document.getElementById('themeIcon').querySelector('path').setAttribute('d', sunPath);
    }
}

function getPreferredTheme() {
    const saved = localStorage.getItem('theme');
    if (saved) return saved;
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

applyTheme(getPreferredTheme());

themeToggle.addEventListener('click', () => {
    const current = document.documentElement.classList.contains('light') ? 'light' : 'dark';
    const next = current === 'light' ? 'dark' : 'light';
    localStorage.setItem('theme', next);
    applyTheme(next);
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
