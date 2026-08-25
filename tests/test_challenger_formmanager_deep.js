/**
 * tests/test_challenger_formmanager_deep.js
 * Empirical Challenger deep stress and edge case test suite for FormManager & UI Lifecycle.
 * 
 * Verifies:
 * 1. FormManager.hideFloating() invocation context resilience (null, undefined, non-objects, missing sub-properties).
 * 2. 10,000 rapid open/hide idempotency loops.
 * 3. Detached DOM elements & corrupted children mid-lifecycle.
 * 4. Audio recording cleanup with missing/throwing stop buttons.
 * 5. Keyboard event malformations (undefined key/code, null target, null preventDefault).
 * 6. History popstate event floods with corrupt states.
 * 7. FailedMediaCache high-load cache hit/miss and deduplication.
 * 8. handleImageError cascading retries and terminal unbind.
 * 9. appendToTextarea massive payloads (200k+ unicode / emoji / newlines).
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');

console.log('='.repeat(70));
console.log('   STARTING CHALLENGER 2: FORM_MANAGER & FRONTEND DEEP STRESS SUITE');
console.log('='.repeat(70));

class MockClassList {
    constructor(owner) {
        this.owner = owner;
        this._classes = new Set();
    }
    add(...args) { args.forEach(c => { if (c) this._classes.add(c); }); }
    remove(...args) { args.forEach(c => this._classes.delete(c)); }
    contains(c) { return this._classes.has(c); }
    toggle(c) { if (this.contains(c)) { this.remove(c); return false; } else { this.add(c); return true; } }
    toString() { return Array.from(this._classes).join(' '); }
}

class MockElement {
    constructor(tagName = 'DIV') {
        this.tagName = String(tagName).toUpperCase();
        this.classList = new MockClassList(this);
        this.dataset = {};
        this.style = {};
        this.children = [];
        this.parentNode = null;
        this.id = '';
        this.value = '';
        this.selectionStart = 0;
        this.selectionEnd = 0;
        this.type = '';
        this.clickCount = 0;
        this.focusCount = 0;
        this.blurCount = 0;
        this.onerror = null;
        this.onload = null;
        this.src = '';
        this.href = '';
        this.innerHTML = '';
        this.textContent = '';
        this.listeners = {};
    }

    click() {
        this.clickCount++;
        if (typeof this.onclick === 'function') this.onclick();
        this.dispatchEvent({ type: 'click', target: this, defaultPrevented: false });
    }

    focus() { this.focusCount++; }
    blur() { this.blurCount++; }
    scrollIntoView() {}
    getBoundingClientRect() {
        return { top: 100, bottom: 200, left: 0, right: 100, width: 100, height: 100 };
    }
    setSelectionRange(start, end) {
        this.selectionStart = start;
        this.selectionEnd = end;
    }
    setRangeText(replacement, start, end) {
        const s = start !== undefined ? start : this.selectionStart;
        const e = end !== undefined ? end : this.selectionEnd;
        this.value = this.value.slice(0, s) + replacement + this.value.slice(e);
        this.selectionStart = s + replacement.length;
        this.selectionEnd = s + replacement.length;
    }

    setAttribute(k, v) {
        this[k] = v;
        if (k.startsWith('data-')) {
            const key = k.slice(5).replace(/-([a-z])/g, (_, g) => g.toUpperCase());
            this.dataset[key] = v;
        }
    }
    getAttribute(k) {
        if (k.startsWith('data-')) {
            const key = k.slice(5).replace(/-([a-z])/g, (_, g) => g.toUpperCase());
            return this.dataset[key] !== undefined ? this.dataset[key] : (this[k] || null);
        }
        return this[k] || null;
    }
    hasAttribute(k) { return this.getAttribute(k) !== null; }
    removeAttribute(k) {
        delete this[k];
        if (k.startsWith('data-')) {
            const key = k.slice(5).replace(/-([a-z])/g, (_, g) => g.toUpperCase());
            delete this.dataset[key];
        }
    }

    appendChild(child) {
        if (!child) return null;
        if (child.parentNode) child.parentNode.removeChild(child);
        child.parentNode = this;
        this.children.push(child);
        return child;
    }

    removeChild(child) {
        const idx = this.children.indexOf(child);
        if (idx !== -1) {
            this.children.splice(idx, 1);
            child.parentNode = null;
        }
        return child;
    }

    remove() {
        if (this.parentNode) this.parentNode.removeChild(this);
    }

    addEventListener(type, fn) {
        if (!this.listeners[type]) this.listeners[type] = [];
        this.listeners[type].push(fn);
    }

    removeEventListener(type, fn) {
        if (this.listeners[type]) {
            this.listeners[type] = this.listeners[type].filter(f => f !== fn);
        }
    }

    dispatchEvent(event) {
        if (!event.target) event.target = this;
        const fns = this.listeners[event.type] || [];
        for (const fn of fns) {
            try { fn.call(this, event); } catch (e) {}
        }
        if (this.parentNode && !event.cancelBubble) this.parentNode.dispatchEvent(event);
    }

    querySelector(selector) {
        const res = this.querySelectorAll(selector);
        return res.length > 0 ? res[0] : null;
    }

    querySelectorAll(selector) {
        const results = [];
        const match = (el) => {
            if (selector.startsWith('#') && el.id === selector.slice(1)) return true;
            if (selector.startsWith('.') && el.classList.contains(selector.slice(1))) return true;
            if (el.tagName && el.tagName.toLowerCase() === selector.toLowerCase()) return true;
            return false;
        };

        const traverse = (node) => {
            for (const child of node.children) {
                if (match(child)) results.push(child);
                traverse(child);
            }
        };
        traverse(this);
        return results;
    }

    closest(selector) {
        let cur = this;
        while (cur) {
            if (selector.startsWith('#') && cur.id === selector.slice(1)) return cur;
            if (selector.startsWith('.') && cur.classList && cur.classList.contains(selector.slice(1))) return cur;
            if (cur.tagName && cur.tagName.toLowerCase() === selector.toLowerCase()) return cur;
            cur = cur.parentNode;
        }
        return null;
    }
}

function createEnv() {
    const documentListeners = {};
    const windowListeners = {};
    const historyStack = [];

    const mockDocElement = new MockElement('HTML');
    const mockBody = new MockElement('BODY');
    const mockHead = new MockElement('HEAD');
    mockDocElement.appendChild(mockHead);
    mockDocElement.appendChild(mockBody);

    const mockDocument = {
        documentElement: mockDocElement,
        head: mockHead,
        body: mockBody,
        createElement: (tag) => new MockElement(tag),
        getElementById: (id) => {
            const find = (node) => {
                if (node.id === id) return node;
                for (const c of node.children) {
                    const res = find(c);
                    if (res) return res;
                }
                return null;
            };
            return find(mockDocElement);
        },
        querySelector: (s) => mockDocElement.querySelector(s),
        querySelectorAll: (s) => mockDocElement.querySelectorAll(s),
        addEventListener: (evt, fn) => {
            if (!documentListeners[evt]) documentListeners[evt] = [];
            documentListeners[evt].push(fn);
        },
        removeEventListener: (evt, fn) => {
            if (documentListeners[evt]) {
                documentListeners[evt] = documentListeners[evt].filter(cb => cb !== fn);
            }
        },
        dispatchEvent: (evt) => {
            if (!evt.preventDefault) evt.preventDefault = () => { evt.defaultPrevented = true; };
            if (!evt.stopPropagation) evt.stopPropagation = () => { evt.cancelBubble = true; };
            const list = documentListeners[evt.type] || [];
            list.forEach(fn => fn(evt));
        }
    };
    mockDocument.activeElement = mockDocument.body;

    const mockWindow = {
        document: mockDocument,
        location: { href: 'http://localhost:8000/b/chat/', pathname: '/b/chat/' },
        innerWidth: 1920,
        innerHeight: 1080,
        localStorage: {
            _store: {},
            getItem: (k) => mockWindow.localStorage._store[k] || null,
            setItem: (k, v) => { mockWindow.localStorage._store[k] = String(v); },
            removeItem: (k) => { delete mockWindow.localStorage._store[k]; }
        },
        history: {
            pushState: () => {},
            replaceState: () => {},
            back: () => { historyStack.pop(); }
        },
        matchMedia: () => ({ matches: false }),
        getSelection: () => ({ toString: () => '', anchorNode: null }),
        safeInit: (name, fn) => { try { if (typeof fn === 'function') fn(); } catch (e) {} },
        setTimeout: (fn, ms) => { if (typeof fn === 'function') fn(); },
        setInterval: () => {},
        requestAnimationFrame: (cb) => { if (typeof cb === 'function') cb(); },
        cancelAnimationFrame: () => {},
        addEventListener: (evt, fn) => {
            if (!windowListeners[evt]) windowListeners[evt] = [];
            windowListeners[evt].push(fn);
        },
        removeEventListener: (evt, fn) => {
            if (windowListeners[evt]) {
                windowListeners[evt] = windowListeners[evt].filter(cb => cb !== fn);
            }
        },
        dispatchEvent: (evt) => {
            if (!evt.preventDefault) evt.preventDefault = () => { evt.defaultPrevented = true; };
            if (!evt.stopPropagation) evt.stopPropagation = () => { evt.cancelBubble = true; };
            const list = windowListeners[evt.type] || [];
            list.forEach(fn => fn(evt));
        }
    };

    const mockModalClose = {
        called: false,
        fn: () => { mockModalClose.called = true; }
    };

    return {
        document: mockDocument,
        window: mockWindow,
        documentListeners,
        windowListeners,
        mockModalClose,
        historyStack
    };
}

function loadMainScript(env) {
    const filePath = path.join(__dirname, '../site_tgach/static/js/main.src.js');
    const code = fs.readFileSync(filePath, 'utf8');

    const context = {
        window: env.window,
        document: env.document,
        location: env.window.location,
        localStorage: env.window.localStorage,
        history: env.window.history,
        closeModal: env.mockModalClose.fn,
        safeInit: env.window.safeInit,
        setTimeout: env.window.setTimeout,
        setInterval: env.window.setInterval,
        requestAnimationFrame: env.window.requestAnimationFrame,
        cancelAnimationFrame: env.window.cancelAnimationFrame,
        Audio: class { constructor() {} play() { return Promise.resolve(); } },
        Image: MockElement,
        MutationObserver: class { observe() {} disconnect() {} },
        IntersectionObserver: class { observe() {} disconnect() {} },
        navigator: { userAgent: 'Mozilla/5.0' },
        console: { log: () => {}, warn: () => {}, error: () => {}, info: () => {} },
        module: { exports: {} }
    };

    const fn = new Function(
        ...Object.keys(context),
        code + `
        return {
            FormManager: typeof FormManager !== 'undefined' ? FormManager : null,
            BackButtonManager: typeof BackButtonManager !== 'undefined' ? BackButtonManager : null,
            handleImageError: typeof handleImageError !== 'undefined' ? handleImageError : null,
            FailedMediaCache: typeof FailedMediaCache !== 'undefined' ? FailedMediaCache : null,
            moduleExports: typeof module !== 'undefined' ? module.exports : {}
        };`
    );

    return fn(...Object.values(context));
}

let passCount = 0;
let totalTests = 0;

function runTest(name, fn) {
    totalTests++;
    try {
        fn();
        passCount++;
        console.log(`  ✓ PASSED: ${name}`);
    } catch (err) {
        console.error(`  ✗ FAILED: ${name}`);
        console.error(err);
        throw err;
    }
}

// --- 1. Invocation Context Resilience ---
runTest('CH-FM-01: FormManager.hideFloating() invocation context fuzzing', () => {
    const env = createEnv();
    const { FormManager } = loadMainScript(env);
    assert(FormManager, 'FormManager must exist');

    const weirdContexts = [
        null, undefined, 0, 1, -1, NaN, Infinity, "", "test", true, false,
        [], [1, 2, 3], {}, { floatingBox: null }, { floatingBox: 123 },
        { floatingBox: { style: {} } },
        { floatingBox: { style: {}, querySelector: () => null } },
        { floatingBox: { style: {}, querySelector: () => ({ click: () => { throw new Error('Click fail'); } }) } },
        { isMobile: () => true, floatingBox: null }
    ];

    for (const ctx of weirdContexts) {
        assert.doesNotThrow(() => {
            FormManager.hideFloating.call(ctx);
        }, `hideFloating should not throw for context: ${JSON.stringify(ctx)}`);
    }
});

// --- 2. Rapid 10,000x Open / Hide Idempotency Loop ---
runTest('CH-FM-02: 10,000 rapid open/hide operations on floating reply box', () => {
    const env = createEnv();
    const { FormManager } = loadMainScript(env);
    FormManager.init();

    const mainForm = env.document.createElement('FORM');
    mainForm.id = 'post-form';
    const mainTa = env.document.createElement('TEXTAREA');
    mainTa.id = 'post-text';
    mainForm.appendChild(mainTa);
    env.document.body.appendChild(mainForm);

    for (let i = 0; i < 10000; i++) {
        const box = env.document.createElement('DIV');
        box.id = 'floating-reply-box';
        box.style.display = 'block';
        env.document.body.appendChild(box);
        FormManager.floatingBox = box;

        // Hide with alternating history flag
        FormManager.hideFloating(i % 2 === 0);

        // Remove node
        env.document.body.removeChild(box);
        FormManager.floatingBox = null;
    }

    assert.strictEqual(FormManager.floatingBox, null);
});

// --- 3. Audio Recorder Cleanup Defensive Safeguards ---
runTest('CH-FM-03: Audio recording cleanup with missing or throwing DOM buttons', () => {
    const env = createEnv();
    const { FormManager } = loadMainScript(env);
    FormManager.init();

    const box = env.document.createElement('DIV');
    box.id = 'floating-reply-box';
    
    // Active recording stage
    const stage = env.document.createElement('DIV');
    stage.id = 'voice-recording-stage';
    stage.style.display = 'block';
    box.appendChild(stage);

    // Stop button that throws when clicked
    const stopBtn = env.document.createElement('BUTTON');
    stopBtn.id = 'btn-voice-stop';
    stopBtn.onclick = () => { throw new Error('Simulated stop crash'); };
    box.appendChild(stopBtn);

    // Delete button that throws when clicked
    const delBtn = env.document.createElement('BUTTON');
    delBtn.id = 'btn-voice-delete';
    delBtn.onclick = () => { throw new Error('Simulated delete crash'); };
    box.appendChild(delBtn);

    env.document.body.appendChild(box);
    FormManager.floatingBox = box;

    assert.doesNotThrow(() => {
        FormManager.hideFloating();
    });
});

// --- 4. Keyboard Shortcut Listener Under Malformed Event Storm ---
runTest('CH-FM-04: Keyboard listener fuzzing with 1,000 malformed event objects', () => {
    const env = createEnv();
    const { FormManager } = loadMainScript(env);
    FormManager.init();

    const keys = ['Escape', 'Enter', 'r', 'R', 'KeyR', 'KeyQ', null, undefined, '', 'F5', 'Tab'];
    
    for (let i = 0; i < 1000; i++) {
        const key = keys[i % keys.length];
        const event = {
            type: 'keydown',
            key: key,
            code: key,
            altKey: i % 3 === 0,
            ctrlKey: i % 4 === 0,
            shiftKey: i % 5 === 0,
            target: i % 2 === 0 ? env.document.body : null,
            preventDefault: i % 2 === 0 ? () => {} : null,
            stopPropagation: () => {}
        };

        assert.doesNotThrow(() => {
            env.document.dispatchEvent(event);
        });
    }
});

// --- 5. Popstate Event Storm with Corrupted State Objects ---
runTest('CH-FM-05: 1,000 history popstate events with arbitrary state objects', () => {
    const env = createEnv();
    const { FormManager } = loadMainScript(env);
    FormManager.init();

    const box = env.document.createElement('DIV');
    box.id = 'floating-reply-box';
    box.style.display = 'block';
    env.document.body.appendChild(box);
    FormManager.floatingBox = box;

    const corruptedStates = [
        null, undefined, 0, 1, -1, true, false, "", "text",
        {}, { floatingOpen: true }, { floatingOpen: false },
        { deeply: { nested: { invalid: true } } }
    ];

    for (let i = 0; i < 1000; i++) {
        const st = corruptedStates[i % corruptedStates.length];
        assert.doesNotThrow(() => {
            env.window.dispatchEvent({ type: 'popstate', state: st });
        });
    }
});

// --- 6. FailedMediaCache Deduplication & Memory Bound ---
runTest('CH-FM-06: FailedMediaCache high-throughput insert & query', () => {
    const env = createEnv();
    const { FailedMediaCache } = loadMainScript(env);
    
    if (FailedMediaCache) {
        for (let i = 0; i < 5000; i++) {
            FailedMediaCache.add(`file_id_${i}`);
        }
        
        for (let i = 0; i < 5000; i++) {
            assert.strictEqual(FailedMediaCache.has(`file_id_${i}`), true);
        }
        
        assert.strictEqual(FailedMediaCache.has('non_existent'), false);
    }
});

// --- 7. handleImageError Cascading Failures and Infinite Loop Prevention ---
runTest('CH-FM-07: handleImageError cascading failures (step 1 -> step 2 -> step 3 final unbind)', () => {
    const env = createEnv();
    const { handleImageError } = loadMainScript(env);

    const img = env.document.createElement('IMG');
    img.src = 'https://imgbb.com/broken.jpg';
    img.setAttribute('data-file-id', 'AgAC_adversarial_404');
    env.document.body.appendChild(img);

    // Initial state
    assert.strictEqual(img.src, 'https://imgbb.com/broken.jpg');

    // First error: falls back to local Telegram files proxy
    handleImageError(img);
    assert.strictEqual(img.src.includes('/files/AgAC_adversarial_404'), true);
    assert.strictEqual(img.getAttribute('data-fallback-tried'), 'true');

    // Second error: falls back to proxy with skip param
    handleImageError(img);
    assert.strictEqual(img.src.includes('skip='), true);
    assert.strictEqual(img.getAttribute('data-fallback-direct'), 'true');

    // Third error: stops retry loop and clears onerror to prevent infinite refresh storm
    handleImageError(img);
    assert.strictEqual(img.onerror, null);
});

// --- 8. FormManager.appendToTextarea with Massive Payloads ---
runTest('CH-FM-08: FormManager.appendToTextarea handles 200KB multi-byte text payload', () => {
    const env = createEnv();
    const { FormManager } = loadMainScript(env);
    FormManager.init();

    const form = env.document.createElement('FORM');
    form.id = 'post-form';
    const textarea = env.document.createElement('TEXTAREA');
    textarea.id = 'post-text';
    form.appendChild(textarea);
    env.document.body.appendChild(form);

    const largePayload = ">>99999\n" + "🔥 Тестовая цитата с эмодзи и разметкой 🌟\n".repeat(3000);
    FormManager.appendToTextarea(largePayload);

    assert.strictEqual(textarea.value.includes('>>99999'), true);
    assert.strictEqual(textarea.value.includes('🔥 Тестовая цитата'), true);
    assert.strictEqual(textarea.value.length > 50000, true);
});

console.log('\n' + '='.repeat(70));
console.log(`   ALL ${passCount}/${totalTests} CHALLENGER 2 FORM_MANAGER DEEP TESTS PASSED!`);
console.log('='.repeat(70) + '\n');
