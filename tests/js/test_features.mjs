// Phase 4 client features: JSONL/Markdown exports (4.3), filtering (4.2),
// column visibility (4.4) and deep-link path parsing (4.5).
//
// Run with: node tests/js/test_features.mjs

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
    buildJsonlChunks,
    buildMarkdownChunks,
    escapeMarkdownCell,
    rowMatchesFilter,
    readPathFromHash,
    sanitizeCell,
} = context;

let checks = 0;
const check = (fn) => { fn(); checks += 1; };

// --- 4.3 JSONL: values unescaped, NOT formula-sanitized -------------------
check(() => {
    const rows = [{ a: '=SUM(A1)', b: 1 }, { a: '@cmd', b: null }];
    const lines = buildJsonlChunks(['a', 'b'], rows).join('').trim().split('\n');
    assert.equal(lines.length, 2);

    const first = JSON.parse(lines[0]);
    // The spreadsheet sanitizer must NOT have touched this: JSON has types,
    // nothing evaluates it, and a quote prefix would corrupt the value.
    // (Values are verbatim; the COLUMN SHAPE is the server's flattened one.)
    assert.equal(first.a, '=SUM(A1)');
    assert.notEqual(first.a, sanitizeCell('=SUM(A1)'));
    assert.equal(first.b, 1);

    assert.deepEqual(JSON.parse(lines[1]), { a: '@cmd', b: null });
});

check(() => {
    // Types survive the round trip.
    const rows = [{ n: 1.5, b: true, s: 'x', o: { k: 'v' }, arr: [1, 2] }];
    const parsed = JSON.parse(buildJsonlChunks(['n', 'b', 's', 'o', 'arr'], rows).join('').trim());
    assert.equal(parsed.n, 1.5);
    assert.equal(parsed.b, true);
    assert.deepEqual(Object.keys(parsed).sort(), ['arr', 'b', 'n', 'o', 's']);
});

check(() => {
    // Only the selected columns are projected, and absent keys stay absent.
    const parsed = JSON.parse(buildJsonlChunks(['a'], [{ a: 1, b: 2 }]).join('').trim());
    assert.deepEqual(parsed, { a: 1 });
    const sparse = JSON.parse(buildJsonlChunks(['a', 'z'], [{ a: 1 }]).join('').trim());
    assert.deepEqual(sparse, { a: 1 });
});

check(() => {
    const rows = Array.from({ length: 5000 }, (_, i) => ({ a: i }));
    assert.ok(buildJsonlChunks(['a'], rows).length > 1, 'JSONL should be chunked too');
});

// --- 4.3 Markdown: Markdown escaping only ---------------------------------
check(() => {
    // A pipe breaks the table; a leading '=' does not mean anything here.
    assert.equal(escapeMarkdownCell('a|b'), 'a\\|b');
    assert.equal(escapeMarkdownCell('=SUM(A1)'), '=SUM(A1)');
    assert.equal(escapeMarkdownCell('a\nb'), 'a<br>b');
    assert.equal(escapeMarkdownCell('a\r\nb'), 'a<br>b');
    assert.equal(escapeMarkdownCell('back\\slash'), 'back\\\\slash');
    assert.equal(escapeMarkdownCell(null), '');
    assert.equal(escapeMarkdownCell(undefined), '');
    assert.equal(escapeMarkdownCell({ k: 'v' }), '{"k":"v"}');
});

check(() => {
    const md = buildMarkdownChunks(['a', 'b'], [{ a: 1, b: 'x|y' }]).join('');
    const lines = md.trim().split('\n');
    assert.equal(lines[0], '| a | b |');
    assert.equal(lines[1], '| --- | --- |');
    assert.equal(lines[2], '| 1 | x\\|y |');
});

check(() => {
    // Markdown must not carry the spreadsheet quote prefix either.
    const md = buildMarkdownChunks(['a'], [{ a: '=EVIL()' }]).join('');
    assert.ok(md.includes('| =EVIL() |'));
    assert.ok(!md.includes("'=EVIL()"));
});

// --- 4.2 filtering --------------------------------------------------------
check(() => {
    const row = { name: 'Alice', city: 'Berlin', meta: { role: 'admin' }, n: 42 };
    assert.equal(rowMatchesFilter(row, 'ali'), true, 'case-insensitive substring');
    assert.equal(rowMatchesFilter(row, 'BERLIN'.toLowerCase()), true);
    assert.equal(rowMatchesFilter(row, 'admin'), true, 'searches nested values');
    assert.equal(rowMatchesFilter(row, '42'), true, 'searches numbers');
    assert.equal(rowMatchesFilter(row, 'zzz'), false);
});

check(() => {
    assert.equal(rowMatchesFilter({ a: null, b: undefined }, 'null'), false);
});

// --- 4.5 deep-link parsing ------------------------------------------------
check(() => {
    context.window.location.hash = '#path=users.0.orders';
    assert.equal(readPathFromHash(), 'users.0.orders');

    context.window.location.hash = '';
    assert.equal(readPathFromHash(), null);

    context.window.location.hash = '#other=1';
    assert.equal(readPathFromHash(), null);

    context.window.location.hash = '#path=(root)';
    assert.equal(readPathFromHash(), '(root)');

    context.window.location.hash = '#path=a.b%20c';
    assert.equal(readPathFromHash(), 'a.b c', 'percent-encoding is decoded');
});

// --- Codex review follow-ups ---------------------------------------------

// Finding 4: nodes past the per-level cap must stay reachable.
check(() => {
    // The batching entry points exist, so the overflow notice can become a
    // control rather than a dead end.
    assert.equal(typeof context.populateNextBatch, 'function');
    assert.equal(typeof context.populateChildren, 'function');

    // childEntries must enumerate EVERY child (500 > the 200 per-level render
    // cap); the cap belongs to the renderer, not to the enumeration, or a deep
    // link could never resolve past it.
    const wide = {};
    for (let i = 0; i < 500; i += 1) wide[`k${i}`] = i;
    const entries = context.childEntries(wide, '(root)');
    assert.equal(entries.length, 500);
    assert.equal(entries[499].path, 'k499');
});

// The deep-link feature has two halves; writePathToHash is the one that runs
// when a user confirms a selection. It encodes through URLSearchParams, so a
// round trip is what proves the halves agree.
check(() => {
    const { writePathToHash } = context;
    assert.equal(typeof writePathToHash, 'function');

    for (const path of [
        'users.0.orders',
        '(root)',
        'a.b c',
        'weird&key=value',
        'key#with+chars',
        'plain',
    ]) {
        writePathToHash(path);
        assert.equal(readPathFromHash(), path, `round trip failed for ${path}`);
    }
});

console.log(`ok - ${checks} client feature assertions passed`);
