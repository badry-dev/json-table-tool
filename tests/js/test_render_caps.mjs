// P4/P5/P13 - client-side rendering and export caps.
//
// Loads the real static/js/app.js in a stubbed DOM and asserts the pure render
// helpers bound the work they do. Run with: node tests/js/test_render_caps.mjs

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { createContext } from './dom_stub.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const appJs = readFileSync(join(here, '..', '..', 'static', 'js', 'app.js'), 'utf8');

const context = vm.createContext(createContext());
vm.runInContext(appJs, context, { filename: 'app.js' });

const {
    formatValue,
    renderNestedObject,
    renderNestedTable,
    truncateForRender,
    buildDelimitedChunks,
    buildDelimited,
    childEntries,
    excelExportBlocked,
} = context;

let checks = 0;
const check = (fn) => { fn(); checks += 1; };

// --- P5: nested object key cap -------------------------------------------
check(() => {
    const wide = {};
    for (let i = 0; i < 50000; i += 1) wide[`k${i}`] = i;
    const html = renderNestedObject(wide);
    const rowCount = (html.match(/<tr>/g) || []).length;
    assert.equal(rowCount, 21, 'expected 20 keys plus one "more" row');
    assert.ok(html.includes('49980 more keys'));
});

check(() => {
    const small = { a: 1, b: 2 };
    const html = renderNestedObject(small);
    assert.equal((html.match(/<tr>/g) || []).length, 2);
    assert.ok(!html.includes('more keys'));
});

// --- P5: primitive array stringify cap ------------------------------------
check(() => {
    const big = Array.from({ length: 100000 }, (_, i) => i);
    const html = formatValue(big);
    assert.ok(html.length < 500, `rendered ${html.length} chars for a 100k array`);
    assert.ok(html.includes('and 99980 more'));
});

check(() => {
    assert.equal(formatValue([1, 2, 3]), '[1,2,3]');
    assert.equal(formatValue([]), '[]');
});

// --- P5: long string cap ---------------------------------------------------
check(() => {
    const html = formatValue('z'.repeat(5 * 1024 * 1024));
    assert.ok(html.length < 2000, `rendered ${html.length} chars for a 5 MB string`);
    assert.ok(html.includes('truncated'));
});

check(() => {
    assert.equal(formatValue('short'), 'short');
    assert.equal(truncateForRender('abc', 10).truncated, false);
    assert.equal(truncateForRender('abcdef', 3).text, 'abc');
});

// --- P5: nested table column cap ------------------------------------------
check(() => {
    const row = {};
    for (let i = 0; i < 200; i += 1) row[`c${i}`] = i;
    const html = renderNestedTable([row, row, row, row, row, row, row]);
    assert.equal((html.match(/<th>/g) || []).length, 21, '20 columns plus the overflow header');
    assert.ok(html.includes('... and 2 more rows'));
});

// --- P4: tree children are enumerable lazily ------------------------------
check(() => {
    const entries = childEntries({ a: 1, b: 2 }, '(root)');
    assert.deepEqual(Array.from(entries, e => e.path), ['a', 'b']);
    assert.deepEqual(Array.from(entries, e => e.label), ['a', 'b']);
});

check(() => {
    const entries = childEntries([10, 20], 'users');
    assert.deepEqual(Array.from(entries, e => e.path), ['users.0', 'users.1']);
    assert.deepEqual(Array.from(entries, e => e.label), ['[0]', '[1]']);
});

// --- P13: chunked blob parts ----------------------------------------------
check(() => {
    const rows = Array.from({ length: 5000 }, (_, i) => ({ a: i }));
    const chunks = buildDelimitedChunks(['a'], rows, ',');
    assert.ok(chunks.length > 1, 'expected the output to be split into parts');
    // Joined chunks are byte-identical to the single-string builder.
    assert.equal(chunks.join(''), buildDelimited(['a'], rows, ','));
    const lines = chunks.join('').trim().split('\n');
    assert.equal(lines.length, 5001);
    assert.equal(lines[1], '0');
    assert.equal(lines[5000], '4999');
});

check(() => {
    // A small dataset still produces exactly one part.
    assert.equal(buildDelimitedChunks(['a'], [{ a: 1 }], ',').length, 1);
});

// --- D6: the Excel entry is gated on the advertised budget ----------------
//
// The rule lives in the pure isExcelBlocked(cells, limit) so both directions can
// be asserted: the module-level totalCells/maxExportCells are `let` bindings,
// which vm.runInContext keeps in script scope rather than exposing on the
// context, so a test cannot drive them.
check(() => {
    const { isExcelBlocked } = context;
    assert.equal(typeof isExcelBlocked, 'function');

    // Over the limit -> blocked. This is the case the guard exists for.
    assert.equal(isExcelBlocked(250001, 250000), true);
    assert.equal(isExcelBlocked(1_000_000, 250000), true);

    // At or under the limit -> allowed.
    assert.equal(isExcelBlocked(250000, 250000), false);
    assert.equal(isExcelBlocked(1, 250000), false);

    // limit 0 disables the guard entirely, however large the dataset.
    assert.equal(isExcelBlocked(10_000_000, 0), false);

    // Nothing loaded yet.
    assert.equal(isExcelBlocked(0, 250000), false);
});

check(() => {
    assert.equal(typeof excelExportBlocked, 'function');
    assert.equal(excelExportBlocked(), false, 'no data loaded means nothing to block');
});

console.log(`ok - ${checks} client render/cap assertions passed`);
