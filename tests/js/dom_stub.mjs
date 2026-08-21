// Minimal DOM/browser stubs so static/js/app.js can be loaded in Node for
// assertions on its pure export helpers. No build step, no dependencies: the
// script under test is the exact file the browser gets.

const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;' };

function makeElement() {
    // textContent/innerHTML are real accessors so app.js's escapeHtml() -- which
    // escapes by round-tripping through a detached div -- behaves as in a browser.
    let text = '';
    let html = '';

    const el = {
        dataset: {},
        files: [],
        style: {},
        get textContent() { return text; },
        set textContent(value) {
            text = String(value);
            html = text.replace(/[&<>]/g, (ch) => HTML_ESCAPES[ch]);
        },
        get innerHTML() { return html; },
        set innerHTML(value) { html = String(value); },
        value: '',
        disabled: false,
        classList: {
            add() {},
            remove() {},
            toggle() { return false; },
            contains() { return false; },
        },
        addEventListener() {},
        removeEventListener() {},
        appendChild() {},
        remove() {},
        setAttribute() {},
        getAttribute() { return 'test-csrf-token'; },
        click() {},
        closest() { return null; },
        querySelector() { return makeElement(); },
        querySelectorAll() { return []; },
    };
    return el;
}

export function createContext() {
    const document = {
        body: makeElement(),
        documentElement: makeElement(),
        createElement: () => makeElement(),
        getElementById: () => makeElement(),
        querySelector: () => makeElement(),
        querySelectorAll: () => [],
        addEventListener() {},
    };

    const window = {
        matchMedia: () => ({ matches: false, addEventListener() {} }),
        URL: { createObjectURL: () => 'blob:stub', revokeObjectURL() {} },
        location: { hash: '' },
    };

    const context = {
        document,
        window,
        localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
        location: window.location,
        Blob: class Blob {
            constructor(parts, options) {
                this.parts = parts;
                this.type = options && options.type;
            }
        },
        FormData: class FormData {
            append() {}
        },
        fetch: async () => ({ ok: true, json: async () => ({}) }),
        alert() {},
        console,
        setTimeout,
        clearTimeout,
        // Web platform globals app.js uses that Node also provides.
        URLSearchParams,
        JSON,
    };
    context.globalThis = context;
    return context;
}
