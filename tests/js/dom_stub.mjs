// Minimal DOM/browser stubs so static/js/app.js can be loaded in Node for
// assertions on its pure export helpers. No build step, no dependencies: the
// script under test is the exact file the browser gets.

function makeElement() {
    const el = {
        dataset: {},
        files: [],
        style: {},
        textContent: '',
        innerHTML: '',
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
    };
    context.globalThis = context;
    return context;
}
