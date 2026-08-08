/**
 * Empirical Challenger Stress-Test Suite — Milestone 2 (M2)
 * Agent: challenger_m2_1
 *
 * Verifies:
 * 1. 404 response on /files/... produces EXACTLY 1 network request per session.
 * 2. 100 rapid WebSocket DOM re-renders calling initializePostFeatures produce 0 network requests.
 * 3. Date.now() timestamp parameters are NEVER appended to media URLs on failure.
 * 4. SmartLoader and MediaStreamManager suppress cached failed media completely.
 * 5. Handle varied URL forms (query params, relative vs absolute, hash anchors).
 */

const assert = require('assert');
const path = require('path');

// --- MOCK DOM ENVIRONMENT ---
class MockClassList {
    constructor() {
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
        this.classList = new MockClassList();
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
    removeAttribute(k) { if (k === 'src') this._src = ''; }

    get src() { return this._src; }
    set src(val) {
        this._src = val;
        if (typeof MockElement.onRequestSent === 'function' && val) {
            MockElement.onRequestSent(val);
        }
    }

    get innerHTML() { return this._innerHTML; }
    set innerHTML(val) { this._innerHTML = val; }

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
}

// Global environment shims
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
global.console = console;

// Load module
const frontendModule = require('../site_tgach/static/js/main.js');
const { FailedMediaCache, handleImageError, PostRenderer, SmartLoader, MediaStreamManager } = frontendModule;

let networkRequests = [];
MockElement.onRequestSent = (url) => {
    networkRequests.push(url);
};

// --- STRESS TESTS ---
function runStressTests() {
    console.log('================================================================');
    console.log('   EMPIRICAL CHALLENGER STRESS TEST SUITE (challenger_m2_1)   ');
    console.log('================================================================\n');

    let passedCount = 0;
    let totalCount = 0;

    function runTest(name, fn) {
        totalCount++;
        console.log(`[TEST ${totalCount}] ${name}...`);
        try {
            fn();
            passedCount++;
            console.log(`  => RESULT: PASSED\n`);
        } catch (e) {
            console.error(`  => RESULT: FAILED — ${e.message}\n${e.stack}\n`);
            throw e;
        }
    }

    // 1. EXACT 1 NETWORK REQUEST FOR 404 MEDIA
    runTest('Verify exactly 1 network request for local 404 media per session', () => {
        FailedMediaCache.clear();
        networkRequests = [];

        const url = '/files/broken_test_image.png';
        const img = new MockElement('IMG');
        const wrapper = new MockElement('DIV');
        wrapper.className = 'file-thumb';
        wrapper.appendChild(img);

        // Step 1: Initial network request sent when src set
        img.src = url;
        assert.strictEqual(networkRequests.length, 1, `Expected 1 request after setting img.src, got ${networkRequests.length}`);

        // Step 2: 404 error event fires
        img.onerror = () => handleImageError(img);
        handleImageError(img);

        assert.strictEqual(img.onerror, null, 'onerror must be unbound immediately');
        assert.strictEqual(FailedMediaCache.isFailed(url), true, 'URL must be recorded in FailedMediaCache');
        assert.strictEqual(networkRequests.length, 1, 'No extra network request during handleImageError');

        // Step 3: Trigger error again manually to simulate edge cases
        handleImageError(img);
        assert.strictEqual(networkRequests.length, 1, 'Subsequent handleImageError calls must not fire network requests');
    });

    // 2. 100 RAPID WEBSOCKET DOM RE-RENDERS
    runTest('Simulate 100 rapid WebSocket post re-renders calling initializePostFeatures', () => {
        FailedMediaCache.clear();
        networkRequests = [];

        const brokenUrl = '/files/ws_broken_media.png';
        FailedMediaCache.markFailed(brokenUrl);

        const postData = {
            id: 777123,
            board_id: 'b',
            content: {
                text: 'WebSocket Post Update Test',
                files: [
                    {
                        original_file_id: 'ws_broken_media',
                        original_url: brokenUrl,
                        type: 'image',
                        filename: 'ws_broken_media.png'
                    }
                ]
            }
        };

        const initialReqCount = networkRequests.length;

        // Perform 100 rapid DOM re-renders via PostRenderer + initializePostFeatures
        for (let i = 0; i < 100; i++) {
            const postEl = PostRenderer.create(postData, 'board');
            postEl.id = `post-${postData.id}`;
            // Delete data-initialized to simulate new DOM insertion per re-render
            delete postEl.dataset.initialized;

            // Call initializePostFeatures
            if (typeof window.initializePostFeatures === 'function') {
                window.initializePostFeatures(postEl);
            }

            assert.ok(postEl.innerHTML.includes('⚠️ Media Unavailable'), `Re-render ${i+1}: expected static fallback placeholder`);
            assert.strictEqual(postEl.querySelectorAll('img').length, 0, `Re-render ${i+1}: expected 0 img tags created`);
        }

        const newRequests = networkRequests.length - initialReqCount;
        assert.strictEqual(newRequests, 0, `EXACTLY 0 network requests expected during 100 re-renders, got ${newRequests}`);
    });

    // 3. ZERO DATE.NOW() TIMESTAMP PARAMETERS
    runTest('Verify NO Date.now() or timestamp cache-buster query parameters are appended', () => {
        FailedMediaCache.clear();
        networkRequests = [];

        const targetUrl = '/files/no_timestamp_test.png';
        const img = new MockElement('IMG');
        img.src = targetUrl;
        handleImageError(img);

        // Check all recorded network requests
        networkRequests.forEach(reqUrl => {
            assert.strictEqual(reqUrl.includes('Date.now'), false, `URL ${reqUrl} contains literal Date.now string`);
            assert.strictEqual(reqUrl.includes('retry='), false, `URL ${reqUrl} contains retry= parameter`);
            assert.strictEqual(/\?.*[0-9]{13}/.test(reqUrl), false, `URL ${reqUrl} contains 13-digit millisecond timestamp query param`);
        });
    });

    // 4. SMARTLOADER STRESS TEST (100 ENQUEUES & OBSERVE)
    runTest('SmartLoader 100 enqueues of broken media items', () => {
        FailedMediaCache.clear();
        networkRequests = [];

        const brokenUrl = '/files/smartloader_fail.png';
        FailedMediaCache.markFailed(brokenUrl);

        for (let i = 0; i < 100; i++) {
            const img = new MockElement('IMG');
            img.dataset.src = brokenUrl;
            const parent = new MockElement('DIV');
            parent.className = 'file-thumb';
            parent.appendChild(img);

            SmartLoader.enqueue(img);

            assert.strictEqual(parent.classList.contains('broken-media'), true);
            assert.ok(parent.innerHTML.includes('⚠️ Media Unavailable'));
        }

        assert.strictEqual(networkRequests.length, 0, `Expected 0 network requests from SmartLoader enqueues of failed media, got ${networkRequests.length}`);
    });

    // 5. MEDIA STREAM MANAGER STRESS TEST
    runTest('MediaStreamManager.loadVideoWithRetry with failed source', () => {
        FailedMediaCache.clear();
        networkRequests = [];

        const videoUrl = '/files/stream_failed.mp4';
        FailedMediaCache.markFailed(videoUrl);

        const videoEl = new MockElement('VIDEO');
        const item = { file: { sources: [videoUrl], original_url: videoUrl } };

        MediaStreamManager.loadVideoWithRetry(videoEl, item, 0);

        assert.strictEqual(networkRequests.length, 0, `MediaStreamManager must NOT send request for cached failed video, got ${networkRequests.length}`);
    });

    // 6. URL NORMALIZATION & QUERY PARAMS STRESS TEST
    runTest('URL Normalization across query params, hashes, absolute and relative paths', () => {
        FailedMediaCache.clear();

        const base = 'http://localhost:8000/files/norm_test.png';
        FailedMediaCache.markFailed(`${base}?param=1#hash`);

        assert.strictEqual(FailedMediaCache.isFailed('/files/norm_test.png'), true, 'Relative path matching failed');
        assert.strictEqual(FailedMediaCache.isFailed(base), true, 'Full absolute URL matching failed');
        assert.strictEqual(FailedMediaCache.isFailed(`${base}?another=2`), true, 'Different query param matching failed');
    });

    // 7. MULTIPLE POSTS CONTAINING SAME BROKEN MEDIA
    runTest('Multiple distinct posts sharing identical broken media URL', () => {
        FailedMediaCache.clear();
        networkRequests = [];

        const sharedUrl = '/files/shared_broken.png';
        const img1 = new MockElement('IMG');
        img1.src = sharedUrl; // Request #1
        assert.strictEqual(networkRequests.length, 1);

        handleImageError(img1);
        assert.strictEqual(FailedMediaCache.isFailed(sharedUrl), true);

        // Render 5 distinct posts with sharedUrl
        for (let id = 1001; id <= 1005; id++) {
            const postEl = PostRenderer.create({
                id,
                board_id: 'b',
                content: { text: `Post ${id}`, files: [{ original_url: sharedUrl, type: 'image' }] }
            }, 'board');

            window.initializePostFeatures(postEl);
            assert.ok(postEl.innerHTML.includes('⚠️ Media Unavailable'));
        }

        assert.strictEqual(networkRequests.length, 1, `Expected EXACTLY 1 total request for shared broken media across 5 posts, got ${networkRequests.length}`);
    });

    console.log('================================================================');
    console.log(`   ALL ${passedCount}/${totalCount} EMPIRICAL STRESS TESTS PASSED PERFECTLY!   `);
    console.log('================================================================');
}

runStressTests();
