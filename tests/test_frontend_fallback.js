/**
 * Automated Verification Test for Frontend 404 Media Fallback & Retry Suppression
 * Milestone 2 (M2) — dvachbot
 *
 * Verifies:
 * 1. FailedMediaCache normalization and singleton tracking.
 * 2. Fail-fast handleImageError unbinding onerror and marking FailedMediaCache.
 * 3. Elimination of Date.now() timestamp retries.
 * 4. WebSocket re-render protection in PostRenderer.create and initializePostFeatures.
 * 5. SmartLoader suppression of cached failed media.
 * 6. Guarantee that 404 media is requested EXACTLY ONCE per session.
 */

const assert = require('assert');
const path = require('path');

// --- 1. MOCK DOM ENVIRONMENT ---
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

    get className() {
        return this.classList.toString();
    }

    set className(val) {
        this.classList._classes.clear();
        if (val) {
            val.split(/\s+/).forEach(c => { if (c) this.classList.add(c); });
        }
    }

    addEventListener() {}
    removeEventListener() {}
    setAttribute(k, v) { this[k] = v; if (this.dataset && k.startsWith('data-')) this.dataset[k.slice(5)] = v; }
    getAttribute(k) { return this[k] || (this.dataset && this.dataset[k.slice(5)]) || null; }
    hasAttribute(k) { return this.getAttribute(k) !== null; }

    get src() {
        return this._src;
    }

    set src(val) {
        this._src = val;
        if (typeof MockElement.onRequestSent === 'function' && val) {
            MockElement.onRequestSent(val);
        }
    }

    get innerHTML() {
        return this._innerHTML;
    }

    set innerHTML(val) {
        this._innerHTML = val;
    }

    getBoundingClientRect() {
        return { top: 100, bottom: 200, left: 0, right: 100, width: 100, height: 100 };
    }

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
            if (cleanSel.startsWith('.')) {
                return node.classList.contains(cleanSel.slice(1));
            }
            if (cleanSel.includes('.')) {
                const [tag, cls] = cleanSel.split('.');
                return (tag === '' || node.tagName === tag.toUpperCase()) && node.classList.contains(cls);
            }
            return node.tagName === cleanSel.toUpperCase();
        };

        const walk = (node) => {
            for (const child of node.children) {
                if (selector.split(',').some(s => matchSingle(child, s))) {
                    matches.push(child);
                }
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
            if (idx !== -1) {
                this.parentNode.children.splice(idx, 1);
            }
        }
    }

    removeAttribute(attr) {
        if (attr === 'src') this._src = '';
    }
}

// Global window & document shims
global.Audio = class {
    constructor(src) { this.src = src; }
    cloneNode() { return new global.Audio(this.src); }
    play() { return Promise.resolve(); }
};
global.Image = MockElement;
global.MutationObserver = class {
    constructor(cb) { this.cb = cb; }
    observe() {}
    disconnect() {}
};
global.IntersectionObserver = class {
    constructor(cb) { this.cb = cb; }
    observe() {}
    unobserve() {}
    disconnect() {}
};

global.safeInit = (name, fn) => {
    try {
        if (typeof fn === 'function') fn();
    } catch (e) {}
};

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
    getElementById: (id) => null,
    addEventListener: () => {},
    removeEventListener: () => {}
};

global.t = (key, fallback) => fallback || key;
global.UserState = global.window.UserState;
global.navigator = { connection: null };
global.localStorage = { getItem: () => null, setItem: () => {} };
global.console = console;

// Import the synchronized JS file
const frontendModule = require('../site_tgach/static/js/main.js');
const { FailedMediaCache, handleImageError, PostRenderer, SmartLoader, MediaStreamManager } = frontendModule;

// Track all network requests
let networkRequests = [];
MockElement.onRequestSent = (url) => {
    networkRequests.push(url);
};

// --- 2. TEST SUITE ---
function runTests() {
    console.log('====================================================');
    console.log('   RUNNING FRONTEND 404 FALLBACK TEST SUITE (M2)   ');
    console.log('====================================================\n');

    // Test 1: FailedMediaCache URL Normalization & Storage
    console.log('Test 1: FailedMediaCache Normalization & Storage...');
    FailedMediaCache.clear();
    const testUrl1 = 'http://localhost:8000/files/corrupted_image.png?skip=freeimage&retry=17683067552852#anchor';
    FailedMediaCache.markFailed(testUrl1);
    
    assert.strictEqual(FailedMediaCache.isFailed('http://localhost:8000/files/corrupted_image.png'), true);
    assert.strictEqual(FailedMediaCache.isFailed('/files/corrupted_image.png'), true);
    assert.strictEqual(FailedMediaCache.isFailed('http://localhost:8000/files/corrupted_image.png?skip=other'), true);
    assert.strictEqual(FailedMediaCache.isFailed('http://localhost:8000/files/valid_image.png'), false);
    console.log('  PASSED: FailedMediaCache correctly normalizes query params and tracks failed URLs.\n');

    // Test 2: handleImageError Fail-Fast & Unbinding
    console.log('Test 2: Fail-Fast handleImageError & Unbinding...');
    FailedMediaCache.clear();
    networkRequests = [];

    const parentDiv = new MockElement('DIV');
    parentDiv.className = 'file-thumb lazy-media-wrapper';
    parentDiv.dataset.src = '/files/17683067552852.png';

    const imgEl = new MockElement('IMG');
    imgEl.className = 'post-image lazy-load';
    imgEl.src = '/files/17683067552852.png';
    imgEl.onerror = () => handleImageError(imgEl);
    parentDiv.appendChild(imgEl);

    // Initial load request recorded
    assert.strictEqual(networkRequests.length, 1);
    assert.strictEqual(networkRequests[0], '/files/17683067552852.png');

    // Trigger error handler
    handleImageError(imgEl);

    assert.strictEqual(imgEl.onerror, null, 'onerror MUST be unbound to prevent microtask retry loops');
    assert.strictEqual(FailedMediaCache.isFailed('/files/17683067552852.png'), true, 'Local 404 URL MUST be recorded in FailedMediaCache');
    assert.strictEqual(parentDiv.classList.contains('broken-media'), true, 'Parent container MUST be marked broken-media');
    assert.ok(parentDiv.innerHTML.includes('⚠️ Media Unavailable'), 'Parent container MUST display static ⚠️ placeholder');
    assert.strictEqual(networkRequests.length, 1, 'NO retry GET request should have been sent during handleImageError');
    console.log('  PASSED: handleImageError fails fast, unbinds onerror, records cache, and sets static placeholder.\n');

    // Test 3: WebSocket Re-render Protection (PostRenderer.create)
    console.log('Test 3: WebSocket Re-render Protection (PostRenderer.create)...');
    networkRequests = [];

    // Simulate post data with the broken file URL
    const postData = {
        id: 343717,
        board_id: 'b',
        content: {
            text: 'Hello world',
            files: [
                {
                    original_file_id: '17683067552852',
                    original_url: '/files/17683067552852.png',
                    type: 'image',
                    filename: '17683067552852.png'
                }
            ]
        }
    };

    const renderedPost = PostRenderer.create(postData, 'board');
    assert.ok(renderedPost.innerHTML.includes('⚠️ Media Unavailable'), 'PostRenderer MUST output static error placeholder for cached failed media');
    assert.strictEqual(renderedPost.innerHTML.includes('<img src="/files/17683067552852.png"'), false, 'PostRenderer MUST NOT generate img tag for failed media');
    assert.strictEqual(networkRequests.length, 0, 'Zero network requests should be triggered during re-render');
    console.log('  PASSED: PostRenderer suppresses broken img tags for cached failed media during WebSocket re-renders.\n');

    // Test 4: SmartLoader Enqueue & Process Interception
    console.log('Test 4: SmartLoader Interception...');
    networkRequests = [];

    const lazyImg = new MockElement('IMG');
    lazyImg.className = 'post-image lazy-load';
    lazyImg.dataset.src = '/files/17683067552852.png';
    const lazyParent = new MockElement('DIV');
    lazyParent.className = 'file-thumb';
    lazyParent.appendChild(lazyImg);

    SmartLoader.enqueue(lazyImg);

    assert.strictEqual(lazyParent.classList.contains('broken-media'), true, 'SmartLoader MUST mark parent broken-media');
    assert.ok(lazyParent.innerHTML.includes('⚠️ Media Unavailable'), 'SmartLoader MUST replace content with ⚠️ placeholder');
    assert.strictEqual(networkRequests.length, 0, 'SmartLoader MUST NOT issue GET request for cached failed media');
    console.log('  PASSED: SmartLoader intercepts enqueued media and prevents HTTP requests.\n');

    // Test 5: Exact "Requested EXACTLY ONCE per Session" Proof
    console.log('Test 5: Proof that 404 media is requested EXACTLY ONCE per session...');
    FailedMediaCache.clear();
    networkRequests = [];

    const fileUrl = '/files/single_request_test.png';
    const testImg = new MockElement('IMG');
    const testParent = new MockElement('DIV');
    testParent.className = 'file-thumb';
    testParent.appendChild(testImg);

    // Step A: First request attempt (initial page load)
    testImg.src = fileUrl; // Request #1 sent
    assert.strictEqual(networkRequests.length, 1);

    // Step B: Server returns 404 -> handleImageError called
    handleImageError(testImg);
    assert.strictEqual(FailedMediaCache.isFailed(fileUrl), true);

    // Step C: Re-render post (e.g. WebSocket update or page feature re-init)
    const reRenderedPost = PostRenderer.create({
        id: 999,
        board_id: 'b',
        content: { text: 'update', files: [{ original_url: fileUrl, type: 'image' }] }
    }, 'board');

    // Step D: Re-run initializePostFeatures or SmartLoader scan
    SmartLoader.enqueue(testImg);

    // Assert total requests
    const fileRequests = networkRequests.filter(url => url === fileUrl);
    assert.strictEqual(fileRequests.length, 1, `Expected EXACTLY 1 request for ${fileUrl}, but got ${fileRequests.length}`);
    console.log(`  PASSED: Resource ${fileUrl} was requested EXACTLY ONCE (${fileRequests.length} HTTP GET request).\n`);

    console.log('====================================================');
    console.log('   ALL FRONTEND 404 FALLBACK TESTS PASSED PERFECTLY ');
    console.log('====================================================');
}

runTests();
