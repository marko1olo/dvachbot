/**
 * Empirical Stress Test Harness for Frontend 404 Fallback & Retry Suppression (M2)
 * Agent: challenger_m2_1_b
 */

const assert = require('assert');
const path = require('path');

// --- MOCK DOM ENVIRONMENT ---
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

    play() {
        return Promise.resolve();
    }

    pause() {}
    load() {}

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
global.requestAnimationFrame = (cb) => setTimeout(cb, 16);
global.cancelAnimationFrame = (id) => clearTimeout(id);

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
    t: (key, fallback) => fallback || key,
    requestAnimationFrame: global.requestAnimationFrame,
    cancelAnimationFrame: global.cancelAnimationFrame
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
const frontendModule = require(path.join(__dirname, '../../site_tgach/static/js/main.js'));
const { FailedMediaCache, handleImageError, PostRenderer, SmartLoader, MediaStreamManager } = frontendModule;

let networkRequests = [];
MockElement.onRequestSent = (url) => {
    networkRequests.push(url);
};

const results = [];

function recordResult(testName, passed, details) {
    results.push({ testName, passed, details });
    const status = passed ? 'PASS' : 'FAIL';
    console.log(`[${status}] ${testName}: ${details}`);
}

function runStressTests() {
    console.log('\n=============================================================');
    console.log('  EMPIRICAL ADVERSARIAL STRESS TEST SUITE — challenger_m2_1_b ');
    console.log('=============================================================\n');

    // -------------------------------------------------------------
    // Scenario 1: Aggressive DOM Re-render Flooding (100 iterations)
    // -------------------------------------------------------------
    try {
        FailedMediaCache.clear();
        networkRequests = [];

        const badUrl = '/files/broken_media_flood.png';
        
        // Initial image load & 404 failure
        const img = new MockElement('IMG');
        img.src = badUrl;
        handleImageError(img);

        const initialRequestCount = networkRequests.length;
        assert.strictEqual(initialRequestCount, 1, 'Initial request count should be 1');

        // Simulate 100 WebSocket re-render events for the post containing this broken media
        for (let i = 0; i < 100; i++) {
            const post = PostRenderer.create({
                id: 1000 + i,
                board_id: 'b',
                content: {
                    text: `Update #${i}`,
                    files: [{ original_url: badUrl, type: 'image' }]
                }
            }, 'board');

            assert.ok(post.innerHTML.includes('⚠️ Media Unavailable'), `Re-render #${i} missing warning placeholder`);
            assert.strictEqual(post.innerHTML.includes('<img'), false, `Re-render #${i} created an img tag for failed media`);
        }

        assert.strictEqual(networkRequests.length, 1, `Expected total requests to remain 1, got ${networkRequests.length}`);
        recordResult('Scenario 1: 100x WebSocket Re-render Flooding', true, '0 additional network requests during 100 re-renders.');
    } catch (e) {
        recordResult('Scenario 1: 100x WebSocket Re-render Flooding', false, e.message);
    }

    // -------------------------------------------------------------
    // Scenario 2: Catalog Card Re-renders & Switch Views (with thread_type)
    // -------------------------------------------------------------
    try {
        FailedMediaCache.clear();
        networkRequests = [];

        const catalogUrl = '/files/catalog_404_thumb.jpg';
        const img = new MockElement('IMG');
        img.src = catalogUrl;
        handleImageError(img);

        assert.strictEqual(networkRequests.length, 1);

        for (let i = 0; i < 50; i++) {
            const card = PostRenderer.createCatalogCard({
                id: 2000 + i,
                thread_type: 'default',
                content: {
                    text: 'Catalog text',
                    files: [{ original_url: catalogUrl, type: 'image' }]
                }
            });
            assert.ok(card.innerHTML.includes('broken-media') || card.innerHTML.includes('⚠️'), `Catalog card #${i} missing broken-media styling`);
        }

        assert.strictEqual(networkRequests.length, 1, `Expected 1 network request, got ${networkRequests.length}`);
        recordResult('Scenario 2: Catalog Card Re-renders', true, 'Catalog card renders handle failed media without spawning GET requests.');
    } catch (e) {
        recordResult('Scenario 2: Catalog Card Re-renders', false, e.message);
    }

    // -------------------------------------------------------------
    // Scenario 3: URL Normalization Edge Cases (Query params, anchors, relative/absolute)
    // -------------------------------------------------------------
    try {
        FailedMediaCache.clear();
        
        const base = 'http://localhost:8000/files/image_edge_case.png';
        FailedMediaCache.markFailed(base + '?timestamp=12345&token=abc#view');

        assert.strictEqual(FailedMediaCache.isFailed(base), true, 'Fails to match base URL');
        assert.strictEqual(FailedMediaCache.isFailed('/files/image_edge_case.png'), true, 'Fails to match relative path');
        assert.strictEqual(FailedMediaCache.isFailed(base + '?different_param=999'), true, 'Fails to match with different query params');
        assert.strictEqual(FailedMediaCache.isFailed(base + '#different_anchor'), true, 'Fails to match with different anchor');

        recordResult('Scenario 3: FailedMediaCache URL Normalization', true, 'All URL variants match canonical cache key.');
    } catch (e) {
        recordResult('Scenario 3: FailedMediaCache URL Normalization', false, e.message);
    }

    // -------------------------------------------------------------
    // Scenario 4: SmartLoader Queue & Scan Stress Test
    // -------------------------------------------------------------
    try {
        FailedMediaCache.clear();
        networkRequests = [];

        const brokenUrl = '/files/smartloader_fail.png';
        FailedMediaCache.markFailed(brokenUrl);

        for (let i = 0; i < 20; i++) {
            const img = new MockElement('IMG');
            img.dataset.src = brokenUrl;
            const parent = new MockElement('DIV');
            parent.className = 'file-thumb';
            parent.appendChild(img);

            SmartLoader.enqueue(img);
            assert.ok(parent.innerHTML.includes('⚠️ Media Unavailable'), `SmartLoader item #${i} missing static placeholder`);
        }

        assert.strictEqual(networkRequests.length, 0, `SmartLoader issued ${networkRequests.length} requests for cached failed media`);
        recordResult('Scenario 4: SmartLoader Interception', true, 'SmartLoader suppressed all 20 enqueued items.');
    } catch (e) {
        recordResult('Scenario 4: SmartLoader Interception', false, e.message);
    }

    // -------------------------------------------------------------
    // Scenario 5: MediaStreamManager Video Retries & Cache Buster Elimination
    // -------------------------------------------------------------
    try {
        FailedMediaCache.clear();
        networkRequests = [];

        const videoItem = {
            file: {
                original_url: '/files/failed_video.mp4',
                type: 'video'
            }
        };

        const videoEl = new MockElement('VIDEO');
        MediaStreamManager.loadVideoWithRetry(videoEl, videoItem);

        assert.strictEqual(networkRequests.length, 1, 'Initial video request should be sent');
        assert.strictEqual(networkRequests[0], '/files/failed_video.mp4');

        // Simulate video failure
        videoEl.onerror();

        assert.strictEqual(FailedMediaCache.isFailed('/files/failed_video.mp4'), true, 'Video URL must be marked in FailedMediaCache');

        // Attempt to load video again
        const secondVideoEl = new MockElement('VIDEO');
        MediaStreamManager.loadVideoWithRetry(secondVideoEl, videoItem);

        // Network request count should STILL be 1 (second attempt aborted by FailedMediaCache)
        assert.strictEqual(networkRequests.length, 1, `Expected network request count 1, got ${networkRequests.length}`);

        recordResult('Scenario 5: MediaStreamManager Video Fallback & Cache Buster', true, 'Video retries blocked by FailedMediaCache, no timestamp parameters added.');
    } catch (e) {
        recordResult('Scenario 5: MediaStreamManager Video Fallback & Cache Buster', false, e.message);
    }

    // -------------------------------------------------------------
    // Scenario 6: Microtask & Error Handler Recursion Protection
    // -------------------------------------------------------------
    try {
        FailedMediaCache.clear();
        networkRequests = [];

        const img = new MockElement('IMG');
        img.src = '/files/recursion_test.png';
        let errorCallCount = 0;

        img.onerror = () => {
            errorCallCount++;
            handleImageError(img);
        };

        // Fire error event multiple times manually to simulate DOM bubbling / microtask loop
        img.onerror();
        assert.strictEqual(img.onerror, null, 'onerror MUST be set to null after first execution');

        recordResult('Scenario 6: Microtask & Error Handler Unbinding', true, 'onerror handler successfully unbound after 1 call.');
    } catch (e) {
        recordResult('Scenario 6: Microtask & Error Handler Unbinding', false, e.message);
    }

    // Summary
    console.log('\n-------------------------------------------------------------');
    const allPassed = results.every(r => r.passed);
    console.log(`FINAL STRESS TEST VERDICT: ${allPassed ? 'ALL STRESS TESTS PASSED (APPROVE)' : 'STRESS TEST FAILURES DETECTED (REJECT)'}`);
    console.log('-------------------------------------------------------------\n');
    return allPassed;
}

const pass = runStressTests();
process.exit(pass ? 0 : 1);
