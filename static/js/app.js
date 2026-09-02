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
let totalCells = 0;
let maxExportCells = 0;
let previewLimit = 25;
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
        totalCells = data.total_cells || 0;
        maxExportCells = data.max_export_cells || 0;
        // P11: the badge used to hardcode 25, so changing PREVIEW_ROW_LIMIT gave
        // an operator a wrong badge.
        previewLimit = data.preview_limit || previewLimit;
        updateExcelAvailability();

        setTableData(data);
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

// P4: the picker used to build a DOM node for every key of every object up
// front, so a 10 MB payload meant tens of thousands of nodes in one synchronous
// pass -- a multi-second freeze before the modal appeared. Children are now
// built on first toggle, and both the per-level fan-out and the total node count
// are capped.
const TREE_MAX_CHILDREN = 200;
const TREE_MAX_NODES = 5000;

// Values are held off-DOM: a node's children cannot be built from markup alone.
const treeNodeValues = new WeakMap();
let treeNodesBuilt = 0;

function showTreePicker(rawJson) {
    selectedTreePath = null;
    treeNodesBuilt = 0;
    treeSelectedLabel.textContent = 'No node selected';
    treeConfirmBtn.disabled = true;
    treeContainer.innerHTML = '';
    treeContainer.appendChild(buildTreeNode(rawJson, '(root)', 'root', true));
    pathModal.classList.add('visible');
    preselectPathFromHash();
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
    treeNodesBuilt += 1;

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
        row.dataset.path = path;
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
        children.classList.add('tree-children', 'hidden');
        treeNodeValues.set(children, { value, path });
        node.appendChild(children);
        if (openByDefault) {
            populateChildren(children);
            children.classList.remove('hidden');
        }
    }
    return node;
}

function childEntries(value, path) {
    if (Array.isArray(value)) {
        return value.map((item, index) => ({
            value: item,
            path: path === '(root)' ? String(index) : `${path}.${index}`,
            label: `[${index}]`,
        }));
    }
    return Object.keys(value).map(key => ({
        value: value[key],
        path: path === '(root)' ? key : `${path}.${key}`,
        label: key,
    }));
}

function appendTreeNotice(container, text) {
    const notice = document.createElement('div');
    notice.classList.add('tree-more');
    notice.textContent = text;
    container.appendChild(notice);
}

// The per-level cap keeps the first paint cheap, but it must never make a node
// unreachable: without this control, a key past the 200th could be selected
// neither by clicking nor by a #path= deep link.
function appendTreeMoreButton(container, remaining) {
    const button = document.createElement('button');
    button.type = 'button';
    button.classList.add('tree-more', 'tree-more-button');
    button.textContent = `Show ${Math.min(remaining, TREE_MAX_CHILDREN)} more of ${remaining}`;
    button.addEventListener('click', (e) => {
        e.stopPropagation();
        populateNextBatch(container);
    });
    container.appendChild(button);
}

function clearTreeOverflowControl(container) {
    const existing = container.querySelector(':scope > .tree-more');
    if (existing) existing.remove();
}

// Append the next batch of children. Returns the number now materialized.
function populateNextBatch(children) {
    const held = treeNodeValues.get(children);
    if (!held) return 0;

    const entries = childEntries(held.value, held.path);
    let built = Number(children.dataset.built || 0);
    if (built >= entries.length) return built;

    clearTreeOverflowControl(children);

    const target = Math.min(entries.length, built + TREE_MAX_CHILDREN);
    while (built < target && treeNodesBuilt < TREE_MAX_NODES) {
        const entry = entries[built];
        children.appendChild(buildTreeNode(entry.value, entry.path, entry.label, false));
        built += 1;
    }
    children.dataset.built = String(built);

    if (built < entries.length) {
        if (treeNodesBuilt >= TREE_MAX_NODES) {
            appendTreeNotice(children, 'Tree size limit reached — narrow the selection above.');
        } else {
            appendTreeMoreButton(children, entries.length - built);
        }
    }
    return built;
}

// First batch only; safe to call every time a node is toggled open.
function populateChildren(children) {
    if (children.dataset.built === undefined) populateNextBatch(children);
}

function toggleNode(node, toggle) {
    const children = node.querySelector(':scope > .tree-children');
    if (!children) return;
    populateChildren(children);
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

// --- 4.5 deep-linkable path selection -------------------------------------
//
// #path=users.0.orders pre-selects that node when the picker opens, and
// confirming a selection writes the hash back, so the link can be shared for a
// conversion someone repeats.

function readPathFromHash() {
    const hash = (window.location.hash || '').replace(/^#/, '');
    if (!hash) return null;
    const match = new URLSearchParams(hash).get('path');
    return match ? match.trim() : null;
}

function writePathToHash(path) {
    const params = new URLSearchParams();
    params.set('path', path);
    window.location.hash = params.toString();
}

// Attribute selectors would need escaping for arbitrary JSON keys; scanning the
// rows avoids the question entirely.
function findTreeRowByPath(path) {
    return (
        Array.from(treeContainer.querySelectorAll('.tree-row[data-path]')).find(
            row => row.dataset.path === path
        ) || null
    );
}

function expandTreeToPath(path) {
    if (path === '(root)') {
        const rootRow = findTreeRowByPath('(root)');
        if (rootRow) selectNode(rootRow, '(root)');
        return Boolean(rootRow);
    }

    let current = '';
    let target = null;
    let container = treeContainer.querySelector(':scope > .tree-node > .tree-children');

    for (const segment of path.split('.')) {
        current = current ? `${current}.${segment}` : segment;

        // The target may sit past the per-level cap, so keep materializing
        // batches at this level until it appears or the level is exhausted.
        let row = findTreeRowByPath(current);
        while (!row && container) {
            const before = Number(container.dataset.built || 0);
            if (populateNextBatch(container) === before) break;
            row = findTreeRowByPath(current);
        }
        // Still missing means the path genuinely does not exist. This is a hint,
        // not a command -- leave the picker open rather than erroring.
        if (!row) return false;

        const children = row.parentElement.querySelector(':scope > .tree-children');
        container = children;
        if (children) {
            populateChildren(children);
            children.classList.remove('hidden');
            const toggle = row.querySelector('.tree-toggle');
            if (toggle) toggle.textContent = '▾';
        }
        target = row;
    }

    if (target) {
        selectNode(target, current);
        target.scrollIntoView({ block: 'nearest' });
        return true;
    }
    return false;
}

function preselectPathFromHash() {
    const path = readPathFromHash();
    if (!path) return;
    expandTreeToPath(path);
}

treeConfirmBtn.addEventListener('click', () => {
    if (!selectedTreePath) return;
    writePathToHash(selectedTreePath);
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

// --- Table view model (4.1/4.2/4.4) ---------------------------------------
//
// Two datasets arrive from /process: `preview` (nested, capped server-side) with
// its own `columns`, and `csv_data` (flattened, full fidelity) with
// `csv_columns`. The table starts on the preview. "Load more" switches to the
// flattened dataset -- that is the only one the browser holds for every row --
// and the badge says so, because the column set genuinely differs (a nested
// `meta` object becomes `meta.age`).

// Above this many DOM rows the browser starts to struggle; "Load all" asks first.
const MAX_DOM_ROWS = 50000;
const LOAD_MORE_STEP = 500;

let previewRows = null;
let previewColumns = null;
let viewMode = 'preview';
let loadedRowCount = 0;
let hiddenColumns = new Set();
let filterText = '';

const rowFilterInput = document.getElementById('rowFilter');
const filterCount = document.getElementById('filterCount');
const loadMoreBtn = document.getElementById('loadMoreBtn');
const loadAllBtn = document.getElementById('loadAllBtn');
const rowWarning = document.getElementById('rowWarning');
const columnsBtn = document.getElementById('columnsBtn');
const columnsDropdown = document.getElementById('columnsDropdown');

function setTableData(data) {
    previewColumns = data.columns || [];
    previewRows = data.preview || [];
    currentTotalRows = data.total_rows || 0;
    viewMode = 'preview';
    loadedRowCount = previewRows.length;
    hiddenColumns = new Set();
    renderedColumnSignature = null;
    filterText = '';
    sortColumn = null;
    sortDirection = 'asc';
    if (rowFilterInput) rowFilterInput.value = '';
    // Otherwise the "rendering stops at N rows" banner from a previous, larger
    // dataset stays up and describes data that is no longer on screen.
    showRowWarning('');
    renderTable();
}

function baseColumns() {
    return (viewMode === 'preview' ? previewColumns : csvColumns) || [];
}

function baseRows() {
    if (viewMode === 'preview') return previewRows || [];
    return (csvData || []).slice(0, loadedRowCount);
}

function visibleColumns() {
    return baseColumns().filter(col => !hiddenColumns.has(col));
}

function rowMatchesFilter(row, needle) {
    return Object.values(row).some(value => {
        if (value === null || value === undefined) return false;
        const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
        return text.toLowerCase().includes(needle);
    });
}

function applyFilter(rows) {
    const needle = filterText.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter(row => rowMatchesFilter(row, needle));
}

function compareValues(a, b, col) {
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
}

function applySort(rows) {
    if (!sortColumn) return rows;
    return [...rows].sort((a, b) => compareValues(a, b, sortColumn));
}

// Render table
function renderTable() {
    const columns = visibleColumns();
    const loaded = baseRows();
    const filtered = applyFilter(loaded);
    const rows = applySort(filtered);

    renderTableDOM(columns, rows);
    renderColumnToggles();
    updateCounts(loaded.length, filtered.length);
    updateLoadControls();
}

function renderTableDOM(columns, rows) {
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

    // Body. One fragment, so a large "load all" is a single reflow.
    const fragment = document.createDocumentFragment();
    rows.forEach(row => {
        const tr = document.createElement('tr');
        columns.forEach(col => {
            const td = document.createElement('td');
            td.innerHTML = formatValue(row[col]);
            tr.appendChild(td);
        });
        fragment.appendChild(tr);
    });
    tableBody.appendChild(fragment);
}

function updateCounts(loadedCount, shownCount) {
    rowCountText.textContent = `${currentTotalRows} total rows`;

    if (filterCount) {
        filterCount.textContent = filterText.trim()
            ? `${shownCount} of ${loadedCount} loaded rows match`
            : '';
    }

    if (loadedCount < currentTotalRows) {
        previewBadge.textContent = `Showing first ${loadedCount}`;
        // Sorting and filtering act on the rows currently loaded, while exports
        // always contain every row -- say so rather than leaving the discrepancy
        // invisible (P11).
        previewBadge.title =
            `Preview limit is ${previewLimit}. Sorting and filtering apply to the ` +
            'rows loaded here; exports always contain all rows.';
        previewBadge.classList.remove('hidden');
    } else {
        previewBadge.textContent =
            viewMode === 'full'
                ? `Showing all ${currentTotalRows} (flattened columns)`
                : `Showing all ${currentTotalRows}`;
        previewBadge.title =
            viewMode === 'full'
                ? 'Rows past the preview come from the flattened dataset, so nested '
                  + 'objects appear as dotted columns.'
                : '';
        if (viewMode === 'full') {
            previewBadge.classList.remove('hidden');
        } else {
            previewBadge.classList.add('hidden');
        }
    }
}

function updateLoadControls() {
    const total = currentTotalRows;
    // Past MAX_DOM_ROWS loadRows() clamps, so further clicks would re-render the
    // same rows and the buttons would look broken.
    const moreAvailable = loadedRowCount < total && loadedRowCount < MAX_DOM_ROWS;
    if (loadMoreBtn) {
        loadMoreBtn.disabled = !moreAvailable;
        loadMoreBtn.textContent = moreAvailable
            ? `Load next ${Math.min(LOAD_MORE_STEP, total - loadedRowCount)}`
            : (loadedRowCount >= MAX_DOM_ROWS ? 'Render limit reached' : 'All rows loaded');
    }
    if (loadAllBtn) loadAllBtn.disabled = !moreAvailable;
}

function showRowWarning(message) {
    if (!rowWarning) return;
    if (!message) {
        rowWarning.classList.add('hidden');
        rowWarning.textContent = '';
        return;
    }
    rowWarning.textContent = message;
    rowWarning.classList.remove('hidden');
}

function loadRows(count) {
    if (!csvData) return;
    // Rows past the preview only exist in the flattened dataset.
    viewMode = 'full';
    const target = Math.min(loadedRowCount + count, csvData.length);

    if (target > MAX_DOM_ROWS) {
        loadedRowCount = Math.min(target, MAX_DOM_ROWS);
        showRowWarning(
            `Rendering stops at ${MAX_DOM_ROWS} rows to keep the page responsive. ` +
            `All ${currentTotalRows} rows are still included in every export.`
        );
    } else {
        loadedRowCount = target;
        showRowWarning('');
    }
    renderTable();
}

if (loadMoreBtn) loadMoreBtn.addEventListener('click', () => loadRows(LOAD_MORE_STEP));
if (loadAllBtn) {
    loadAllBtn.addEventListener('click', () => loadRows(Number.MAX_SAFE_INTEGER));
}

const FILTER_DEBOUNCE_MS = 150;
let filterDebounce = null;

if (rowFilterInput) {
    rowFilterInput.addEventListener('input', () => {
        // renderTable() re-filters, re-sorts and rebuilds every cell, so running
        // it per keystroke blocks the main thread on a fully loaded dataset.
        clearTimeout(filterDebounce);
        filterDebounce = setTimeout(() => {
            filterText = rowFilterInput.value;
            renderTable();
        }, FILTER_DEBOUNCE_MS);
    });
}

// --- Column visibility (4.4) ----------------------------------------------
let renderedColumnSignature = null;

function renderColumnToggles() {
    if (!columnsDropdown) return;

    const columns = baseColumns();
    const signature = JSON.stringify(columns);
    if (signature === renderedColumnSignature) {
        // Same columns: only the checked state can have changed. Rebuilding here
        // would destroy the checkbox a keyboard user just activated and drop
        // focus to document.body.
        columnsDropdown.querySelectorAll('input[type=checkbox]').forEach(box => {
            box.checked = !hiddenColumns.has(box.dataset.column);
        });
        return;
    }
    renderedColumnSignature = signature;

    columnsDropdown.innerHTML = '';
    columns.forEach(col => {
        const label = document.createElement('label');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.dataset.column = col;
        checkbox.checked = !hiddenColumns.has(col);
        checkbox.addEventListener('change', () => {
            if (checkbox.checked) {
                hiddenColumns.delete(col);
            } else {
                hiddenColumns.add(col);
            }
            renderTable();
        });
        const text = document.createElement('span');
        text.textContent = col;
        label.appendChild(checkbox);
        label.appendChild(text);
        columnsDropdown.appendChild(label);
    });
}

if (columnsBtn) {
    columnsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const open = columnsDropdown.classList.toggle('visible');
        columnsBtn.setAttribute('aria-expanded', String(open));
    });
}

document.addEventListener('click', (e) => {
    if (columnsDropdown && !e.target.closest('.column-group')) {
        columnsDropdown.classList.remove('visible');
        if (columnsBtn) columnsBtn.setAttribute('aria-expanded', 'false');
    }
});

// Column sorting (client-side, over the rows currently loaded)
function handleSort(col) {
    if (sortColumn === col) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortColumn = col;
        sortDirection = 'asc';
    }
    renderTable();
}

// P5: a nested object with 50k keys, a 100k-item array stringified whole, or a
// single 5 MB string cell each freeze the tab. The server caps the preview
// projection too (2.4); these caps also protect rows loaded client-side (4.1).
const RENDER_MAX_KEYS = 20;
const RENDER_MAX_ARRAY_ITEMS = 20;
const RENDER_MAX_STRING = 500;

function truncateForRender(text, max) {
    const str = String(text);
    if (str.length <= max) return { text: str, truncated: false };
    return { text: str.slice(0, max), truncated: true };
}

function renderTruncatable(value, max) {
    const { text, truncated } = truncateForRender(value, max);
    return escapeHtml(text) + (truncated ? '<span class="text-muted"> … (truncated)</span>' : '');
}

// Format cell value
function formatValue(value) {
    if (value === null || value === undefined) {
        return '<span class="text-null">null</span>';
    }

    if (typeof value === 'object') {
        if (Array.isArray(value)) {
            if (value.length === 0) return '[]';
            if (typeof value[0] === 'object' && value[0] !== null) {
                return renderNestedTable(value);
            }
            // Stringify only the head of a primitive array: JSON.stringify over a
            // 100k-item array produces one huge string in a single <td>.
            const head = value.slice(0, RENDER_MAX_ARRAY_ITEMS);
            const rendered = escapeHtml(JSON.stringify(head));
            if (value.length > RENDER_MAX_ARRAY_ITEMS) {
                return `${rendered}<span class="text-muted"> … and ${value.length - RENDER_MAX_ARRAY_ITEMS} more</span>`;
            }
            return rendered;
        }
        return renderNestedObject(value);
    }

    if (typeof value === 'boolean') {
        return value
            ? '<span class="text-true">true</span>'
            : '<span class="text-false">false</span>';
    }

    return renderTruncatable(value, RENDER_MAX_STRING);
}

// Render nested object as mini table
function renderNestedObject(obj) {
    const keys = Object.keys(obj);
    if (keys.length === 0) return '{}';

    const shown = keys.slice(0, RENDER_MAX_KEYS);
    let html = '<table class="nested-table"><tbody>';
    shown.forEach(key => {
        const val = obj[key];
        let displayVal = val;
        if (typeof val === 'object' && val !== null) {
            displayVal = JSON.stringify(val);
        }
        html += `<tr><td><strong>${escapeHtml(key)}</strong></td><td>${renderTruncatable(displayVal, RENDER_MAX_STRING)}</td></tr>`;
    });
    if (keys.length > shown.length) {
        html += `<tr><td colspan="2" class="text-center-muted">… and ${keys.length - shown.length} more keys</td></tr>`;
    }
    html += '</tbody></table>';
    return html;
}

// Render nested array of objects
function renderNestedTable(arr) {
    if (arr.length === 0) return '[]';

    const allCols = [...new Set(arr.flatMap(item => (typeof item === 'object' && item !== null) ? Object.keys(item) : []))];
    if (allCols.length === 0) return escapeHtml(JSON.stringify(arr.slice(0, RENDER_MAX_ARRAY_ITEMS)));
    const cols = allCols.slice(0, RENDER_MAX_KEYS);

    let html = '<table class="nested-table"><thead><tr>';
    cols.forEach(col => {
        html += `<th>${escapeHtml(col)}</th>`;
    });
    if (allCols.length > cols.length) {
        html += `<th>… +${allCols.length - cols.length}</th>`;
    }
    html += '</tr></thead><tbody>';

    arr.slice(0, 5).forEach(item => {
        html += '<tr>';
        cols.forEach(col => {
            let val = item ? item[col] : undefined;
            if (typeof val === 'object' && val !== null) {
                val = JSON.stringify(val);
            }
            html += `<td>${renderTruncatable(val ?? '', RENDER_MAX_STRING)}</td>`;
        });
        if (allCols.length > cols.length) {
            html += '<td></td>';
        }
        html += '</tr>';
    });

    if (arr.length > 5) {
        const span = cols.length + (allCols.length > cols.length ? 1 : 0);
        html += `<tr><td colspan="${span}" class="text-center-muted">... and ${arr.length - 5} more rows</td></tr>`;
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

// P3/D6: tell the user Excel is out of range before they click, rather than
// after a 400. CSV/TSV are streamed and uncapped, so there is always a way out.
function isExcelBlocked(cells, limit) {
    return limit > 0 && cells > limit;
}

function excelExportBlocked() {
    return isExcelBlocked(totalCells, maxExportCells);
}

function updateExcelAvailability() {
    const item = document.querySelector('.export-dropdown-item[data-format="xlsx"]');
    if (!item) return;
    if (excelExportBlocked()) {
        item.disabled = true;
        item.classList.add('disabled');
        item.textContent = 'Excel — too large, use CSV/TSV';
        item.title = `${totalCells} cells exceeds the Excel export limit of ${maxExportCells}`;
    } else {
        item.disabled = false;
        item.classList.remove('disabled');
        item.textContent = 'Export Excel';
        item.title = '';
    }
}

// Export dropdown toggle
const exportDropdown = document.getElementById('exportDropdown');

function setExportDropdownOpen(open) {
    exportDropdown.classList.toggle('visible', open);
    exportBtn.setAttribute('aria-expanded', String(open));
}

exportBtn.addEventListener('click', () => {
    setExportDropdownOpen(!exportDropdown.classList.contains('visible'));
});

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('.export-group')) {
        setExportDropdownOpen(false);
    }
});

// Keyboard: Escape closes and returns focus to the trigger; arrows walk the menu.
document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (exportDropdown.classList.contains('visible')) {
        setExportDropdownOpen(false);
        exportBtn.focus();
    }
    if (columnsDropdown && columnsDropdown.classList.contains('visible')) {
        columnsDropdown.classList.remove('visible');
        if (columnsBtn) {
            columnsBtn.setAttribute('aria-expanded', 'false');
            columnsBtn.focus();
        }
    }
    if (aboutModal && aboutModal.classList.contains('visible')) {
        aboutModal.classList.remove('visible');
    }
    if (pathModal.classList.contains('visible')) {
        pathModal.classList.remove('visible');
    }
});

exportDropdown.addEventListener('keydown', (e) => {
    const items = Array.from(exportDropdown.querySelectorAll('.export-dropdown-item'));
    const index = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') {
        e.preventDefault();
        items[(index + 1) % items.length].focus();
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        items[(index - 1 + items.length) % items.length].focus();
    }
});

exportBtn.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowDown') return;
    e.preventDefault();
    setExportDropdownOpen(true);
    const first = exportDropdown.querySelector('.export-dropdown-item');
    if (first) first.focus();
});

// Export handlers
document.querySelectorAll('.export-dropdown-item').forEach(item => {
    item.addEventListener('click', async () => {
        setExportDropdownOpen(false);
        const format = item.dataset.format;

        if (!csvData || !csvColumns) {
            showError('No data to export');
            return;
        }

        if (format === 'csv') {
            downloadDelimited(csvColumns, csvData, ',', 'exported_data.csv');
        } else if (format === 'tsv') {
            downloadDelimited(csvColumns, csvData, '\t', 'exported_data.tsv');
        } else if (format === 'jsonl') {
            downloadChunks(
                buildJsonlChunks(csvColumns, csvData),
                'application/x-ndjson; charset=utf-8',
                'exported_data.jsonl'
            );
        } else if (format === 'markdown') {
            downloadChunks(
                buildMarkdownChunks(csvColumns, csvData),
                'text/markdown; charset=utf-8',
                'exported_data.md'
            );
        } else if (format === 'xlsx') {
            if (excelExportBlocked()) {
                showError(
                    `Dataset is ${totalCells} cells, above the Excel export limit of ` +
                    `${maxExportCells}. Export CSV or TSV instead.`
                );
                return;
            }
            await exportXlsx();
        }
    });
});

// Spreadsheet formula triggers (OWASP). Must stay in sync with
// helpers.FORMULA_TRIGGERS on the server.
const FORMULA_TRIGGERS = ['=', '+', '-', '@', '\t', '\r', '\n'];

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
    if (typeof serialized === 'string' && FORMULA_TRIGGERS.some(t => serialized.startsWith(t))) {
        return "'" + serialized;
    }
    return serialized;
}

// P13: build the file as a list of chunks instead of one giant string. A 10 MB
// dataset otherwise means a ~10-30 MB string plus a Blob copy of it, which
// blocks the main thread and doubles peak memory for no reason -- Blob already
// accepts several parts.
const BLOB_CHUNK_ROWS = 2000;

// Pure builders, kept separate from the download so they can be asserted
// directly (tests/js/test_export_sanitize.mjs).
function buildDelimitedChunks(columns, data, delimiter) {
    const escape = (val) => {
        const str = String(val ?? '');
        if (str.includes(delimiter) || str.includes('"') || str.includes('\n')) {
            return '"' + str.replace(/"/g, '""') + '"';
        }
        return str;
    };

    const chunks = [];
    let pending = columns.map(col => escape(sanitizeCell(col))).join(delimiter) + '\n';

    data.forEach((row, index) => {
        pending += columns.map(col => escape(sanitizeCell(row[col]))).join(delimiter) + '\n';
        if ((index + 1) % BLOB_CHUNK_ROWS === 0) {
            chunks.push(pending);
            pending = '';
        }
    });

    if (pending) chunks.push(pending);
    return chunks;
}

function buildDelimited(columns, data, delimiter) {
    return buildDelimitedChunks(columns, data, delimiter).join('');
}

// --- 4.3 JSONL export -----------------------------------------------------
//
// Values go out UNESCAPED -- no formula sanitization. F1's sanitizer exists
// because CSV/TSV/XLSX have no type channel and a spreadsheet re-interprets a
// leading '=' as a formula; JSON has types, nothing evaluates it, and prefixing
// values here would corrupt the data instead of protecting anything.
//
// NOT a faithful copy of the input document: rows come from csv_data, which the
// server already flattened, so nested objects appear as dotted keys and nested
// arrays as JSON strings. The unflattened rows are never sent to the browser --
// `preview` is both truncated and capped at preview_limit rows -- so a
// round-tripping JSONL export would require shipping the original rows too,
// which is exactly the payload/memory cost P2 and P12 set out to avoid.
function buildJsonlChunks(columns, data) {
    const chunks = [];
    let pending = '';
    data.forEach((row, index) => {
        const projected = {};
        columns.forEach(col => {
            if (row[col] !== undefined) projected[col] = row[col];
        });
        pending += JSON.stringify(projected) + '\n';
        if ((index + 1) % BLOB_CHUNK_ROWS === 0) {
            chunks.push(pending);
            pending = '';
        }
    });
    if (pending) chunks.push(pending);
    return chunks;
}

// --- 4.3 Markdown export --------------------------------------------------
//
// Markdown-specific escaping only, again NOT the spreadsheet sanitizer: a
// leading '=' is inert in Markdown. What does break a Markdown table is an
// unescaped pipe or a newline inside a cell.
function escapeMarkdownCell(value) {
    if (value === null || value === undefined) return '';
    const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
    return text
        .replace(/\\/g, '\\\\')
        // Markdown permits raw HTML, so an unescaped '<' carries a live tag --
        // `<img src=x onerror=...>` -- into the .md file and executes wherever
        // it is rendered. Escaped before the newline rule below so the '<' of
        // the <br> that rule injects is not itself escaped.
        .replace(/</g, '&lt;')
        .replace(/\|/g, '\\|')
        .replace(/\r\n|\r|\n/g, '<br>');
}

function buildMarkdownChunks(columns, data) {
    const chunks = [];
    let pending =
        '| ' + columns.map(escapeMarkdownCell).join(' | ') + ' |\n' +
        '| ' + columns.map(() => '---').join(' | ') + ' |\n';

    data.forEach((row, index) => {
        pending += '| ' + columns.map(col => escapeMarkdownCell(row[col])).join(' | ') + ' |\n';
        if ((index + 1) % BLOB_CHUNK_ROWS === 0) {
            chunks.push(pending);
            pending = '';
        }
    });
    if (pending) chunks.push(pending);
    return chunks;
}

function downloadChunks(chunks, mimeType, filename) {
    const blob = new Blob(chunks, { type: mimeType });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    a.remove();
}

// Client-side CSV/TSV generation. The blob/anchor dance lives in
// downloadChunks alone -- duplicating it here meant a fix to one copy (an
// unrevoked object URL, say) silently missed CSV and TSV.
function downloadDelimited(columns, data, delimiter, filename) {
    const mimeType = delimiter === '\t'
        ? 'text/tab-separated-values; charset=utf-8'
        : 'text/csv; charset=utf-8';
    downloadChunks(buildDelimitedChunks(columns, data, delimiter), mimeType, filename);
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

        if (!response.ok) {
            const detail = await response.json().catch(() => null);
            throw new Error((detail && detail.error) || 'Excel export failed');
        }

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

// About dialog. Replaces alert(), which also hardcoded a version string that
// went stale the moment APP_VERSION changed -- the modal reads it from config.
const aboutModal = document.getElementById('aboutModal');

document.getElementById('aboutLink').addEventListener('click', (e) => {
    e.preventDefault();
    aboutModal.classList.add('visible');
});

document.getElementById('aboutClose').addEventListener('click', () => {
    aboutModal.classList.remove('visible');
});

aboutModal.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) {
        e.currentTarget.classList.remove('visible');
    }
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
