/**
 * Unified E2E Acceptance Test Suite — Frontend JavaScript (M4)
 * dvachbot — 404 HTTP Flood & Corrupted HTML Anchor Patch
 *
 * Verifies Acceptance Criteria 1 & 2:
 * 1. R1 HTML Anchor Parsing: URL pattern stopping at entity boundaries, quote protection, multi-param integrity, nested anchor suppression.
 * 2. R2 Frontend Fallback: FailedMediaCache singleton, fail-fast handleImageError, zero timestamp retries, WebSocket re-render protection, exactly 1 HTTP GET request per session.
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');

console.log('================================================================');
console.log('   STARTING UNIFIED E2E FRONTEND INTEGRATION TEST SUITE (M4)    ');
console.log('================================================================\n');

// --- SECTION 1: M1 HTML ANCHOR PARSING & REGEX TEST SUITE ---
function createMockEnv(jsFilePath) {
    const code = fs.readFileSync(jsFilePath, 'utf8');
    const storage = {};
    const mockElement = {
        classList: { add: () => {}, remove: () => {}, contains: () => false },
        dataset: {},
        setAttribute: () => {},
        getAttribute: () => null,
        style: {},
        appendChild: () => {}
    };

    class MockAudio {
        constructor() {}
        play() {}
    }

    const window = {
        location: { pathname: '/b/res/100.html' },
        addEventListener: () => {},
        removeEventListener: () => {},
        Audio: MockAudio,
        localStorage: {
            getItem: (k) => storage[k] || null,
            setItem: (k, v) => { storage[k] = String(v); },
            removeItem: (k) => { delete storage[k]; }
        },
        safeInit: () => {},
        setInterval: () => {},
        setTimeout: () => {}
    };
    const document = {
        cookie: '',
        documentElement: mockElement,
        body: mockElement,
        addEventListener: () => {},
        querySelector: () => mockElement,
        querySelectorAll: () => [],
        getElementById: () => mockElement,
        createElement: () => mockElement
    };

    const globalSandbox = {
        window,
        document,
        location: window.location,
        localStorage: window.localStorage,
        Audio: MockAudio,
        safeInit: () => {},
        setInterval: () => {},
        setTimeout: () => {},
        navigator: { userAgent: 'test' }
    };
    
    const keys = Object.keys(globalSandbox);
    const values = Object.values(globalSandbox);
    
    try {
        const fn = new Function(...keys, code);
        fn(...values);
    } catch (e) {
        if (!window.formatTextGlobal) throw e;
    }
    return window;
}

const mainSrcEnv = createMockEnv(path.join(__dirname, '../site_tgach/static/js/main.src.js'));
const mainJsEnv = createMockEnv(path.join(__dirname, '../site_tgach/static/js/main.js'));

[
    { name: 'main.src.js', env: mainSrcEnv },
    { name: 'main.js', env: mainJsEnv }
].forEach(({ name, env }) => {
    console.log(`[M1 E2E] Testing HTML Anchor rendering for ${name}...`);
    
    // 1. Corrupted link parsing check
    const rawInput = ">>1234 https://domain.com/b/res/343717.html'>ТГАЧ";
    const formatted = env.formatTextGlobal(rawInput, 100, 'b', 100);

    assert.ok(formatted.includes('href="https://domain.com/b/res/343717.html"'), `${name}: href should be clean URL`);
    assert.ok(!formatted.includes('href="https://domain.com/b/res/343717.html&#039;'), `${name}: href must not contain &#039;`);
    assert.ok(!formatted.includes('href="https://domain.com/b/res/343717.html\'>'), `${name}: href must not contain '>`);
    assert.ok(formatted.includes('&gt;&gt;1234</a>'), `${name}: Post link should be created cleanly`);

    // 2. Multi-parameter query string preservation
    const multiInput = "Check https://example.com/search?q=1&lang=en and YouTube https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s";
    const formattedMulti = env.formatTextGlobal(multiInput, 100, 'b', 100);

    assert.ok(formattedMulti.includes('q=1'), `${name}: href must contain q=1`);
    assert.ok(formattedMulti.includes('lang=en'), `${name}: href must contain lang=en`);
    assert.ok(formattedMulti.includes('v=dQw4w9WgXcQ'), `${name}: href must contain YouTube v param`);
    assert.ok(formattedMulti.includes('t=30s'), `${name}: href must contain YouTube t param`);

    // 3. Multi-parameter URL with trailing corrupted quote
    const corruptedMulti = ">>1234 https://example.com/search?q=1&lang=en'>ТГАЧ";
    const formattedCorrMulti = env.formatTextGlobal(corruptedMulti, 100, 'b', 100);

    assert.ok(formattedCorrMulti.includes('href="https://example.com/search?q=1&amp;lang=en"'), `${name}: href should cleanly contain multi-params`);
    assert.ok(!formattedCorrMulti.includes('href="https://example.com/search?q=1&amp;lang=en&#039;'), `${name}: href should not include &#039;`);

    // 4. Nested anchor prevention in parseTextEffects
    const mockContainer = {
        dataset: {},
        innerHTML: '<a href="https://domain.com/b/res/343717.html" target="_blank" rel="noopener noreferrer">https://domain.com/b/res/343717.html</a>&#039;&gt;ТГАЧ',
        querySelector: function() { return this; }
    };

    env.parseTextEffects(mockContainer);
    assert.strictEqual(mockContainer.dataset.parsed, 'true', `${name}: Dataset parsed should be set to true`);
    const nestedCount = (mockContainer.innerHTML.match(/<a\b/g) || []).length;
    assert.strictEqual(nestedCount, 1, `${name}: Should have exactly 1 <a> tag, no nested anchors`);

    console.log(`  PASSED: ${name} HTML anchor parsing verified.\n`);
});


// --- SECTION 2: M2 FRONTEND 404 FALLBACK & RETRY SUPPRESSION SUITE ---
console.log('[M2 E2E] Initializing DOM Mock & Frontend Fallback Suite...');

class MockClassList {
    constructor(owner) {
        this.owner = owner;
        this._classes = new Set();
    }
    add(...args) { args.forEach(c => { if (c) this._classes.add(c); }); }
    remove(...args) { args.forEach(c => this._classes.delete(c)); }
    contains(c) { return this._classes.has(c); }
    toString() { return Array.from(this._classes).join(' '); }
}

class MockElement {
    constructor(tagName) {
        this.tagName = (tagName || 'DIV').toUpperCase();
        this.classList = new MockClassList(this);
        this.dataset = {};
        this.style = {};
        this.children = [];
        this.parentNode = null;
        this._innerHTML = '';
        this._src = '';
        this.onerror = null;
        this.onload = null;
        this.id = '';
        this.href = '';
        this.isConnected = true;
    }

    get className() { return this.classList.toString(); }
    set className(val) {
        this.classList._classes.clear();
        if (val) val.split(/\s+/).forEach(c => { if (c) this.classList.add(c); });
    }

    addEventListener() {}
    removeEventListener() {}
    setAttribute(k, v) { this[k] = v; if (this.dataset && k.startsWith('data-')) this.dataset[k.slice(5)] = v; }
    getAttribute(k) { return this[k] || (this.dataset && this.dataset[k.slice(5)]) || null; }
    hasAttribute(k) { return this.getAttribute(k) !== null; }

    get src() { return this._src; }
    set src(val) {
        this._src = val;
        if (typeof MockElement.onRequestSent === 'function' && val) {
            MockElement.onRequestSent(val);
        }
    }

    get innerHTML() { return this._innerHTML; }
    set innerHTML(val) { this._innerHTML = val; }

    getBoundingClientRect() { return { top: 100, bottom: 200, left: 0, right: 100, width: 100, height: 100 }; }

    closest(selector) {
        let cur = this;
        while (cur) {
            if (selector.split(',').some(s => s.trim().startsWith('.') ? cur.classList.contains(s.trim().slice(1)) : cur.tagName === s.trim().toUpperCase())) {
                return cur;
            }
            cur = cur.parentNode;
        }
        return null;
    }

    querySelector(selector) {
        const results = this.querySelectorAll(selector);
        return results.length > 0 ? results[0] : null;
    }

    querySelectorAll(selector) {
        const matches = [];
        const matchSingle = (node, sel) => {
            const cleanSel = sel.trim();
            if (cleanSel.startsWith('.')) return node.classList.contains(cleanSel.slice(1));
            if (cleanSel.includes('.')) {
                const [tag, cls] = cleanSel.split('.');
                return (tag === '' || node.tagName === tag.toUpperCase()) && node.classList.contains(cls);
            }
            return node.tagName === cleanSel.toUpperCase();
        };

        const walk = (node) => {
            for (const child of node.children) {
                if (selector.split(',').some(s => matchSingle(child, s))) matches.push(child);
                walk(child);
            }
        };
        walk(this);
        return matches;
    }

    appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        return child;
    }

    replaceWith(newEl) {
        if (this.parentNode) {
            const idx = this.parentNode.children.indexOf(this);
            if (idx !== -1) {
                this.parentNode.children[idx] = newEl;
                newEl.parentNode = this.parentNode;
            }
        }
    }

    remove() {
        if (this.parentNode) {
            const idx = this.parentNode.children.indexOf(this);
            if (idx !== -1) this.parentNode.children.splice(idx, 1);
        }
    }

    removeAttribute(attr) {
        if (attr === 'src') this._src = '';
    }
}

global.Audio = class {
    constructor(src) { this.src = src; }
    cloneNode() { return new global.Audio(this.src); }
    play() { return Promise.resolve(); }
};
global.Image = MockElement;
global.MutationObserver = class { constructor() {} observe() {} disconnect() {} };
global.IntersectionObserver = class { constructor() {} observe() {} unobserve() {} disconnect() {} };
global.safeInit = (name, fn) => { try { if (typeof fn === 'function') fn(); } catch (e) {} };

global.window = {
    location: { href: 'http://localhost:8000/b/res/123.html', pathname: '/b/res/123.html' },
    innerHeight: 1000,
    addEventListener: () => {},
    matchMedia: () => ({ matches: false }),
    initializePostFeatures: null,
    UserState: { postIds: new Set(), userId: '1' },
    t: (key, fallback) => fallback || key
};

global.location = global.window.location;
global.document = {
    body: new MockElement('BODY'),
    documentElement: new MockElement('HTML'),
    createElement: (tag) => new MockElement(tag),
    querySelector: (s) => global.document.body.querySelector(s),
    querySelectorAll: (s) => global.document.body.querySelectorAll(s),
    getElementById: () => null,
    addEventListener: () => {},
    removeEventListener: () => {}
};

global.t = (key, fallback) => fallback || key;
global.UserState = global.window.UserState;
global.navigator = { connection: null };
global.localStorage = { getItem: () => null, setItem: () => {} };

const frontendModule = require('../site_tgach/static/js/main.js');
const { FailedMediaCache, handleImageError, PostRenderer, SmartLoader } = frontendModule;

let networkRequests = [];
MockElement.onRequestSent = (url) => { networkRequests.push(url); };

// 1. FailedMediaCache
console.log('[M2 E2E] Test 1: FailedMediaCache URL Normalization...');
FailedMediaCache.clear();
const testUrl = 'http://localhost:8000/files/broken_media.png?retry=17683067552852#hash';
FailedMediaCache.markFailed(testUrl);
assert.strictEqual(FailedMediaCache.isFailed('http://localhost:8000/files/broken_media.png'), true);
assert.strictEqual(FailedMediaCache.isFailed('/files/broken_media.png'), true);
assert.strictEqual(FailedMediaCache.isFailed('/files/valid_media.png'), false);
console.log('  PASSED: FailedMediaCache correctly tracks canonical failed URLs.\n');

// 2. handleImageError
console.log('[M2 E2E] Test 2: Fail-Fast handleImageError...');
FailedMediaCache.clear();
networkRequests = [];

const parentDiv = new MockElement('DIV');
parentDiv.className = 'file-thumb lazy-media-wrapper';
const imgEl = new MockElement('IMG');
imgEl.src = '/files/17683067552852.png';
imgEl.onerror = () => handleImageError(imgEl);
parentDiv.appendChild(imgEl);

assert.strictEqual(networkRequests.length, 1);
handleImageError(imgEl);

assert.strictEqual(imgEl.onerror, null, 'onerror MUST be unbound');
assert.strictEqual(FailedMediaCache.isFailed('/files/17683067552852.png'), true, 'Must record in cache');
assert.strictEqual(parentDiv.classList.contains('broken-media'), true, 'Must mark broken-media class');
assert.ok(parentDiv.innerHTML.includes('⚠️ Media Unavailable'), 'Must display static ⚠️ placeholder');
assert.strictEqual(networkRequests.length, 1, 'Zero extra GET requests');
console.log('  PASSED: handleImageError fails fast without retry loops.\n');

// 3. WebSocket Re-render Protection
console.log('[M2 E2E] Test 3: WebSocket Re-render Protection...');
networkRequests = [];
const renderedPost = PostRenderer.create({
    id: 343717,
    board_id: 'b',
    content: {
        text: 'E2E post',
        files: [{ original_file_id: '17683067552852', original_url: '/files/17683067552852.png', type: 'image' }]
    }
}, 'board');

assert.ok(renderedPost.innerHTML.includes('⚠️ Media Unavailable'), 'Must render error placeholder directly');
assert.strictEqual(renderedPost.innerHTML.includes('<img src="/files/17683067552852.png"'), false, 'Must NOT generate broken img tag');
assert.strictEqual(networkRequests.length, 0, 'Zero network requests on WebSocket re-render');
console.log('  PASSED: WebSocket re-render protection verified.\n');

// 4. Exact 1 Request Per Session Assertion
console.log('[M2 E2E] Test 4: Guarantee EXACTLY 1 Request Per Session...');
FailedMediaCache.clear();
networkRequests = [];

const e2eUrl = '/files/e2e_single_request_media.png';
const e2eImg = new MockElement('IMG');
const e2eParent = new MockElement('DIV');
e2eParent.className = 'file-thumb';
e2eParent.appendChild(e2eImg);

// Initial GET request
e2eImg.src = e2eUrl;
assert.strictEqual(networkRequests.length, 1);

// 404 response trigger
handleImageError(e2eImg);

// Re-renders & SmartLoader scans
PostRenderer.create({ id: 888, board_id: 'b', content: { text: 'test', files: [{ original_url: e2eUrl, type: 'image' }] } }, 'board');
SmartLoader.enqueue(e2eImg);

const totalRequests = networkRequests.filter(url => url === e2eUrl).length;
assert.strictEqual(totalRequests, 1, `Expected EXACTLY 1 request, got ${totalRequests}`);
console.log(`  PASSED: ${e2eUrl} was requested EXACTLY ONCE (${totalRequests} HTTP GET request).\n`);

console.log('================================================================');
console.log('   🎉 ALL UNIFIED E2E FRONTEND TESTS PASSED WITH EXIT CODE 0    ');
console.log('================================================================');
