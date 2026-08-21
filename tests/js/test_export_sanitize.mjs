// F1 - client-side export paths must not emit spreadsheet formulas.
//
// Exercises the real static/js/app.js in a stubbed DOM and asserts the CSV and
// TSV builders neutralize every OWASP formula trigger, in both cell values and
// column headers. Run with: node tests/js/test_export_sanitize.mjs

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

const { sanitizeCell, buildDelimited } = context;
assert.equal(typeof sanitizeCell, 'function', 'sanitizeCell must be reachable');
assert.equal(typeof buildDelimited, 'function', 'buildDelimited must be reachable');

const DANGEROUS = ['=SUM(A1)', '@cmd', '+1', '-1', '\tlead', '\rlead', '\nlead'];
const SAFE = ['plain', 'a=b', 'user@example.com', '', '0'];

let checks = 0;
const check = (label, fn) => {
    fn();
    checks += 1;
};

// --- sanitizeCell itself -------------------------------------------------
for (const value of DANGEROUS) {
    check(`sanitizeCell ${JSON.stringify(value)}`, () => {
        assert.equal(sanitizeCell(value), `'${value}`);
    });
}
for (const value of SAFE) {
    check(`sanitizeCell passthrough ${JSON.stringify(value)}`, () => {
        assert.equal(sanitizeCell(value), value);
    });
}
check('sanitizeCell serializes containers', () => {
    assert.equal(sanitizeCell({ a: 1 }), '{"a":1}');
    assert.equal(sanitizeCell([1, 2]), '[1,2]');
});
check('sanitizeCell maps null/undefined to empty', () => {
    assert.equal(sanitizeCell(null), '');
    assert.equal(sanitizeCell(undefined), '');
});
check('numbers are not prefixed', () => {
    assert.equal(sanitizeCell(-1), -1);
    assert.equal(sanitizeCell(1), 1);
});

// --- both delimiters, values and headers ---------------------------------
for (const delimiter of [',', '\t']) {
    const name = delimiter === ',' ? 'CSV' : 'TSV';

    for (const value of DANGEROUS) {
        check(`${name} value ${JSON.stringify(value)}`, () => {
            const out = buildDelimited(['col'], [{ col: value }], delimiter);
            const body = out.split('\n')[1];
            assert.ok(
                body.startsWith("'") || body.startsWith('"\''),
                `${name} cell ${JSON.stringify(value)} not neutralized: ${JSON.stringify(body)}`
            );
            assert.ok(
                !body.startsWith(value[0]),
                `${name} cell ${JSON.stringify(value)} still leads with a trigger`
            );
        });
    }

    check(`${name} header is sanitized too`, () => {
        const out = buildDelimited(['=EVIL()'], [{ '=EVIL()': 1 }], delimiter);
        const header = out.split('\n')[0];
        assert.ok(header.startsWith("'="), `${name} header not neutralized: ${header}`);
    });

    check(`${name} safe values are untouched`, () => {
        const out = buildDelimited(['a', 'b'], [{ a: 'plain', b: 5 }], delimiter);
        assert.equal(out, `a${delimiter}b\nplain${delimiter}5\n`);
    });

    check(`${name} quoting still applies after sanitization`, () => {
        const out = buildDelimited(['a'], [{ a: `x${delimiter}y` }], delimiter);
        assert.equal(out.split('\n')[1], `"x${delimiter}y"`);
    });

    check(`${name} objects are serialized`, () => {
        const out = buildDelimited(['a'], [{ a: { k: 'v' } }], delimiter);
        // Quotes inside the JSON force delimited quoting/doubling.
        assert.equal(out.split('\n')[1], '"{""k"":""v""}"');
    });
}

console.log(`ok - ${checks} client export assertions passed`);
