/**
 * tests/test_challenger_repro_keyr_bug.js
 * Empirical reproduction of Uncaught TypeError in FormManager.focusMainForm() when KeyR is pressed
 * on pages without forms or before forms are initialized.
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const mainSrcPath = path.resolve(__dirname, '../site_tgach/static/js/main.src.js');
const code = fs.readFileSync(mainSrcPath, 'utf8');

class MockElement {
    constructor(tagName = 'DIV') {
        this.tagName = String(tagName).toUpperCase();
        this.classList = {
            contains: () => false,
            add: () => {},
            remove: () => {}
        };
        this.dataset = {};
        this.style = {};
        this.id = '';
        this.children = [];
        this.parentNode = null;
        this.listeners = {};
    }
    querySelector() { return null; }
    querySelectorAll() { return []; }
    getBoundingClientRect() { return { top: 0, height: 0 }; }
    scrollIntoView() {}
    getAttribute() { return null; }
    setAttribute() {}
    hasAttribute() { return false; }
    addEventListener(evt, fn) {
        if (!this.listeners[evt]) this.listeners[evt] = [];
        this.listeners[evt].push(fn);
    }
    dispatchEvent(evt) {
        const list = this.listeners[evt.type] || [];
        list.forEach(fn => fn(evt));
    }
}

const mockDocElement = new MockElement('HTML');
const mockBody = new MockElement('BODY');
mockDocElement.children.push(mockBody);

const documentListeners = {};
const mockDocument = {
    documentElement: mockDocElement,
    body: mockBody,
    activeElement: mockBody,
    createElement: (tag) => new MockElement(tag),
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: (evt, fn) => {
        if (!documentListeners[evt]) documentListeners[evt] = [];
        documentListeners[evt].push(fn);
    },
    dispatchEvent: (evt) => {
        if (!evt.preventDefault) evt.preventDefault = () => {};
        const list = documentListeners[evt.type] || [];
        list.forEach(fn => fn(evt));
    }
};

const mockWindow = {
    document: mockDocument,
    location: { href: 'http://localhost:8000/tags/', pathname: '/tags/' },
    innerWidth: 1920,
    innerHeight: 1080,
    scrollY: 0,
    localStorage: { getItem: () => null, setItem: () => {} },
    history: { pushState: () => {}, back: () => {} },
    matchMedia: () => ({ matches: false }),
    getSelection: () => ({ toString: () => '', anchorNode: null }),
    safeInit: (name, fn) => { try { fn(); } catch(e){} },
    setTimeout: (fn) => fn(),
    setInterval: () => {},
    requestAnimationFrame: (cb) => cb(),
    cancelAnimationFrame: () => {},
    addEventListener: () => {},
    removeEventListener: () => {}
};

const context = {
    window: mockWindow,
    document: mockDocument,
    location: mockWindow.location,
    localStorage: mockWindow.localStorage,
    history: mockWindow.history,
    safeInit: mockWindow.safeInit,
    closeModal: () => {},
    setTimeout: mockWindow.setTimeout,
    setInterval: mockWindow.setInterval,
    requestAnimationFrame: mockWindow.requestAnimationFrame,
    cancelAnimationFrame: mockWindow.cancelAnimationFrame,
    Audio: class { constructor() {} play() { return Promise.resolve(); } },
    Image: MockElement,
    MutationObserver: class { observe() {} disconnect() {} },
    IntersectionObserver: class { observe() {} disconnect() {} },
    navigator: { userAgent: 'Mozilla/5.0' },
    console: { log: () => {}, warn: () => {}, error: () => {} },
    module: { exports: {} }
};

const fn = new Function(
    ...Object.keys(context),
    code + `
    return {
        FormManager: typeof FormManager !== 'undefined' ? FormManager : null
    };`
);

const { FormManager } = fn(...Object.values(context));

console.log('--- VERIFICATION TEST: KeyR / focusMainForm on pages without post forms ---');

// Case 1: FormManager initialized on a page with zero forms (e.g. /tags, /catalog, /archive)
FormManager.init();
console.log('FormManager.forms count:', FormManager.forms ? FormManager.forms.length : 'undefined');

try {
    // Simulate user pressing KeyR
    mockDocument.dispatchEvent({
        type: 'keydown',
        key: 'r',
        code: 'KeyR',
        ctrlKey: false,
        altKey: false,
        metaKey: false,
        target: mockBody
    });
    console.log('  ✓ PASS: No exception thrown on KeyR when forms are absent (BUG-FE-01 fixed)');
} catch (err) {
    console.error('  ✗ FAIL: KeyR threw exception:', err);
    process.exit(1);
}
