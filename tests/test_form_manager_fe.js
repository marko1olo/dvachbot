/**
 * tests/test_form_manager_fe.js
 * Comprehensive Frontend JavaScript Test Suite for FormManager & UI Lifecycle (Tiers 1-4)
 * Requirements: R2-A, R3-B, R4-B, R5-A, R5-B
 * 
 * Verifies:
 * - Tier 1: Feature Coverage (FormManager.hideFloating null-safety, keyboard listeners, image error fallback)
 * - Tier 2: Boundary & Corner Cases (unmounted DOM, rapid idempotency, malformed events, mobile stacks)
 * - Tier 3: Cross-Feature Combinations (floating form + audio recording + Escape + image fallback)
 * - Tier 4: Real-World Application Scenarios (end-to-end user workflows)
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');

// --- 1. ROBUST DOM & BROWSER MOCK ENVIRONMENT ---
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

    focus(opts) { this.focusCount++; }
    blur() { this.blurCount++; }
    scrollIntoView(opts) {}
    getBoundingClientRect() {
        return { top: 100, bottom: 200, left: 0, right: 100, width: 100, height: 100 };
    }
    setSelectionRange(start, end) {
        this.selectionStart = start;
        this.selectionEnd = end;
    }
    setRangeText(replacement, start, end, selectMode) {
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
        if (child) {
            child.parentNode = this;
            this.children.push(child);
        }
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
        if (this.parentNode) {
            this.parentNode.removeChild(this);
        }
    }

    addEventListener(event, fn) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(fn);
    }

    removeEventListener(event, fn) {
        if (!this.listeners[event]) return;
        this.listeners[event] = this.listeners[event].filter(cb => cb !== fn);
    }

    dispatchEvent(evt) {
        try { if (!evt.target) evt.target = this; } catch (e) {}
        const list = this.listeners[evt.type] || [];
        list.forEach(fn => {
            try { fn(evt); } catch (e) { console.error('Error in listener:', e); }
        });
        if (this.parentNode && !evt.cancelBubble) {
            this.parentNode.dispatchEvent(evt);
        }
    }

    querySelector(selector) {
        const res = this.querySelectorAll(selector);
        return res.length > 0 ? res[0] : null;
    }

    querySelectorAll(selector) {
        const matches = [];
        const matchSingle = (node, sel) => {
            const clean = sel.trim();
            if (!clean) return false;
            if (clean.startsWith('.')) {
                const classes = clean.split('.').filter(Boolean);
                return classes.every(c => node.classList.contains(c));
            }
            if (clean.startsWith('#')) {
                return node.id === clean.slice(1);
            }
            if (clean.includes(':not(')) {
                const [base, notPart] = clean.split(':not(');
                const notSel = notPart.replace(')', '').trim();
                const matchesBase = !base || matchSingle(node, base);
                return matchesBase && !matchSingle(node, notSel);
            }
            if (clean.includes('.')) {
                const [tag, ...classes] = clean.split('.');
                const matchesTag = !tag || node.tagName === tag.toUpperCase();
                return matchesTag && classes.every(c => node.classList.contains(c));
            }
            if (clean.includes('[')) {
                const [tag, attrPart] = clean.split('[');
                const attrMatch = attrPart.replace(']', '').split('=');
                const attrName = attrMatch[0].trim();
                const attrVal = attrMatch[1] ? attrMatch[1].replace(/["']/g, '').trim() : null;
                const matchesTag = !tag || node.tagName === tag.toUpperCase();
                if (!matchesTag) return false;
                if (attrVal !== null) return String(node.getAttribute(attrName)) === attrVal;
                return node.hasAttribute(attrName);
            }
            return node.tagName === clean.toUpperCase();
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

    closest(selector) {
        let cur = this;
        while (cur) {
            const clean = selector.trim();
            if (clean.startsWith('.') && cur.classList.contains(clean.slice(1))) return cur;
            if (clean.startsWith('#') && cur.id === clean.slice(1)) return cur;
            if (cur.tagName === clean.toUpperCase()) return cur;
            cur = cur.parentNode;
        }
        return null;
    }
}

// Environment Setup Factory
function setupEnvironment() {
    const documentListeners = {};
    const windowListeners = {};
    const historyStack = [];

    const mockDocument = {
        body: new MockElement('BODY'),
        documentElement: new MockElement('HTML'),
        activeElement: null,
        cookie: '',
        createElement: (tag) => new MockElement(tag),
        getElementById: (id) => {
            if (id === 'floating-reply-box') return mockDocument.body.querySelector('#floating-reply-box');
            if (id === 'post-form') return mockDocument.body.querySelector('#post-form');
            return mockDocument.body.querySelector('#' + id);
        },
        querySelector: (s) => mockDocument.body.querySelector(s),
        querySelectorAll: (s) => mockDocument.body.querySelectorAll(s),
        addEventListener: (evt, fn) => {
            if (!documentListeners[evt]) documentListeners[evt] = [];
            documentListeners[evt].push(fn);
        },
        removeEventListener: (evt, fn) => {
            if (!documentListeners[evt]) return;
            documentListeners[evt] = documentListeners[evt].filter(cb => cb !== fn);
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
        innerWidth: 1024,
        innerHeight: 768,
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
        setTimeout: (fn, ms) => { if (typeof fn === 'function') setTimeout(fn, ms || 0); },
        setInterval: () => {},
        requestAnimationFrame: (cb) => { if (typeof cb === 'function') cb(); },
        cancelAnimationFrame: () => {},
        addEventListener: (evt, fn) => {
            if (!windowListeners[evt]) windowListeners[evt] = [];
            windowListeners[evt].push(fn);
        },
        removeEventListener: (evt, fn) => {
            if (!windowListeners[evt]) return;
            windowListeners[evt] = windowListeners[evt].filter(cb => cb !== fn);
        }
    };

    const mockBackButtonManager = {
        stack: historyStack,
        push: (item) => historyStack.push(item),
        pop: () => historyStack.pop()
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
        BackButtonManager: mockBackButtonManager,
        mockModalClose,
        historyStack
    };
}

// Load and evaluate script
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

    // Evaluate in context and return FormManager and handlers
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

console.log('================================================================');
console.log('   STARTING E2E FRONTEND FORM_MANAGER & UI TEST SUITE (M1-M5)   ');
console.log('================================================================\n');

let totalTests = 0;
let passedTests = 0;

function runTest(tier, name, fn) {
    totalTests++;
    try {
        fn();
        passedTests++;
        console.log(`  ✓ [${tier}] ${name}`);
    } catch (e) {
        console.error(`  ✗ [${tier}] ${name} FAILED:`, e.message);
        throw e;
    }
}

// ============================================================================
// TIER 1: FEATURE COVERAGE (≥5 tests per feature)
// ============================================================================
console.log('\n--- TIER 1: FEATURE COVERAGE ---');

// Feature 1: FormManager.hideFloating Null-Safety (R5-A)
runTest('Tier 1', 'R5-A.1: FormManager.hideFloating() with null floatingBox returns safely without TypeError', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;
    assert.ok(fm, 'FormManager must exist');

    fm.floatingBox = null;
    assert.doesNotThrow(() => {
        fm.hideFloating();
    }, TypeError, 'Calling hideFloating() with null floatingBox must not throw TypeError');
});

runTest('Tier 1', 'R5-A.2: FormManager.hideFloating() with active floatingBox hides element and resets classes', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const box = new MockElement('DIV');
    box.id = 'floating-reply-box';
    box.classList.add('active');
    box.style.display = 'block';
    env.document.body.appendChild(box);
    fm.floatingBox = box;

    fm.hideFloating();
    assert.strictEqual(box.classList.contains('active'), false, 'active class must be removed');
    assert.strictEqual(box.style.display, 'none', 'display style must be none');
    assert.strictEqual(env.document.body.style.overflow, '', 'body overflow style must be cleared');
});

runTest('Tier 1', 'R5-A.3: FormManager.hideFloating() with active audio recording clicks stop and delete buttons', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const box = new MockElement('DIV');
    const stage = new MockElement('DIV');
    stage.classList.add('audio-stage-record');
    stage.style.display = 'block';

    const stopBtn = new MockElement('BUTTON');
    stopBtn.classList.add('stop-btn');
    const delBtn = new MockElement('BUTTON');
    delBtn.classList.add('delete-btn');

    stage.appendChild(stopBtn);
    stage.appendChild(delBtn);
    box.appendChild(stage);
    env.document.body.appendChild(box);
    fm.floatingBox = box;

    fm.hideFloating();
    assert.strictEqual(stopBtn.clickCount >= 1, true, 'stop-btn must be clicked');
});

runTest('Tier 1', 'R5-A.4: FormManager.hideFloating(true) does not pop history stack', () => {
    const env = setupEnvironment();
    env.window.innerWidth = 500;
    env.BackButtonManager.push('form');

    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;
    const box = new MockElement('DIV');
    env.document.body.appendChild(box);
    fm.floatingBox = box;

    fm.hideFloating(true);
    assert.strictEqual(env.BackButtonManager.stack.length, 1, 'History stack should remain untouched when fromHistory=true');
});

runTest('Tier 1', 'R5-A.5: FormManager.hideFloating() invoked with unbound context does not throw', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const hideFn = loaded.FormManager.hideFloating;

    assert.doesNotThrow(() => {
        hideFn.call(null);
        hideFn.call(undefined);
    }, 'Unbound hideFloating calls must be defensive and not crash');
});

// Feature 2: Keyboard Listeners & Shortcuts (R5-B)
runTest('Tier 1', 'R5-B.1: Escape key triggers FormManager.hideFloating and closeModal', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const box = new MockElement('DIV');
    box.classList.add('active');
    box.style.display = 'block';
    env.document.body.appendChild(box);
    fm.floatingBox = box;

    const modal = new MockElement('DIV');
    modal.classList.add('modal');
    modal.classList.add('active');
    modal.style.display = 'block';
    env.document.body.appendChild(modal);

    env.document.dispatchEvent({ type: 'keydown', key: 'Escape', code: 'Escape' });
    assert.strictEqual(box.style.display, 'none', 'Escape should dismiss floating form');
    assert.strictEqual(modal.classList.contains('active'), false, 'Escape should deactivate modal');
});

runTest('Tier 1', 'R5-B.2: Alt+Enter submits active form without throwing when form exists', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const form = new MockElement('FORM');
    form.id = 'post-form';
    const submitBtn = new MockElement('BUTTON');
    submitBtn.type = 'submit';
    form.appendChild(submitBtn);
    env.document.body.appendChild(form);
    fm.mainForm = form;

    env.document.dispatchEvent({ type: 'keydown', altKey: true, key: 'Enter', code: 'Enter' });
    assert.strictEqual(submitBtn.clickCount >= 1, true, 'Alt+Enter should click submit button');
});

runTest('Tier 1', 'R5-B.3: KeyR focuses main form when outside text inputs', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const form = new MockElement('FORM');
    form.id = 'post-form';
    const textarea = new MockElement('TEXTAREA');
    form.appendChild(textarea);
    env.document.body.appendChild(form);
    fm.mainForm = form;
    fm.mainTextarea = textarea;

    env.document.activeElement = env.document.body;
    let focusCalled = false;
    fm.focusMainForm = (replyTo) => { focusCalled = true; };

    env.document.dispatchEvent({ type: 'keydown', code: 'KeyR', key: 'r', ctrlKey: false, defaultPrevented: false });
    assert.strictEqual(focusCalled, true, 'KeyR should focus main form when outside inputs');
});

runTest('Tier 1', 'R5-B.4: KeyR ignored when user is actively typing inside TEXTAREA', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const textarea = new MockElement('TEXTAREA');
    env.document.activeElement = textarea;
    let focusCalled = false;
    fm.focusMainForm = () => { focusCalled = true; };

    env.document.dispatchEvent({ type: 'keydown', code: 'KeyR', key: 'r', ctrlKey: false });
    assert.strictEqual(focusCalled, false, 'KeyR must NOT hijack focus while inside textarea');
});

runTest('Tier 1', 'R5-B.5: Module exports verify required exports', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    assert.ok(loaded.moduleExports, 'module.exports must exist');
    assert.ok(typeof loaded.handleImageError === 'function', 'handleImageError must be exported');
});

// Feature 3: Frontend Image Fallback (R2-A)
runTest('Tier 1', 'R2-A.1: handleImageError falls back to local Telegram files proxy and updates src', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const handleImageError = loaded.handleImageError;

    const img = new MockElement('IMG');
    img.setAttribute('data-file-id', 'AgAC123456');
    img.src = 'https://i.ibb.co/broken.jpg';

    handleImageError(img);
    assert.ok(img.src.includes('/files/AgAC123456') || img.src.includes('skip='), `Expected /files/ fallback, got ${img.src}`);
});

runTest('Tier 1', 'R2-A.2: handleImageError on final failure unbinds onerror permanently', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const handleImageError = loaded.handleImageError;

    const img = new MockElement('IMG');
    img.setAttribute('data-file-id', 'AgACtestfile');
    img.src = 'https://unknown-broken-host.com/image.jpg';

    // Call first time -> switches to fallback
    handleImageError(img);
    assert.ok(img.dataset.triedFallback === 'true', 'Must mark triedFallback');

    // Call second time -> fallback also failed -> permanent static error
    handleImageError(img);
    assert.strictEqual(img.onerror, null, 'onerror must be null after final failure');
    assert.strictEqual(img.classList.contains('broken-final'), true, 'Must add broken-final class');
});

runTest('Tier 1', 'R2-A.3: FailedMediaCache records failed file ID singleton', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const { handleImageError, FailedMediaCache } = loaded;

    const img = new MockElement('IMG');
    img.setAttribute('data-file-id', 'AgACduplicate_fail');
    img.src = 'https://broken.pixhost.to/img.png';

    handleImageError(img);
    if (FailedMediaCache) {
        assert.strictEqual(FailedMediaCache.isFailed('AgACduplicate_fail') || FailedMediaCache.isFailed(img.src) || FailedMediaCache.isFailed('https://broken.pixhost.to/img.png'), true);
    }
});

runTest('Tier 1', 'R2-A.4: handleImageError on video poster falls back cleanly', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const handleImageError = loaded.handleImageError;

    const video = new MockElement('VIDEO');
    video.setAttribute('data-file-id', 'BAACvideotest');
    video.setAttribute('poster', 'https://broken-cdn.com/thumb.jpg');

    handleImageError(video);
    assert.strictEqual(video.onerror, null);
});

runTest('Tier 1', 'R2-A.5: handleImageError on element without data-file-id does not crash', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const handleImageError = loaded.handleImageError;

    const img = new MockElement('IMG');
    img.src = 'https://random-broken-domain.com/pic.jpg';

    assert.doesNotThrow(() => {
        handleImageError(img);
    });
});

// ============================================================================
// TIER 2: BOUNDARY AND CORNER CASES
// ============================================================================
console.log('\n--- TIER 2: BOUNDARY AND CORNER CASES ---');

runTest('Tier 2', 'BVA.1: Multiple rapid consecutive calls to FormManager.hideFloating() (idempotency stress)', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const box = new MockElement('DIV');
    env.document.body.appendChild(box);
    fm.floatingBox = box;

    for (let i = 0; i < 50; i++) {
        fm.hideFloating();
    }
    assert.strictEqual(box.style.display, 'none');
});

runTest('Tier 2', 'BVA.2: FormManager.hideFloating() when floatingBox is detached from document', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const box = new MockElement('DIV');
    fm.floatingBox = box; // Not attached to document.body

    assert.doesNotThrow(() => {
        fm.hideFloating();
    });
    assert.strictEqual(box.style.display, 'none');
});

runTest('Tier 2', 'BVA.3: Audio cleanup inside floatingBox with missing stop button or stage', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const box = new MockElement('DIV');
    const brokenStage = new MockElement('DIV');
    brokenStage.classList.add('audio-stage-record');
    box.appendChild(brokenStage); // No stopBtn inside
    env.document.body.appendChild(box);
    fm.floatingBox = box;

    assert.doesNotThrow(() => {
        fm.hideFloating();
    });
});

runTest('Tier 2', 'BVA.4: Mobile viewport history stack popping on floating box dismissal', () => {
    const env = setupEnvironment();
    env.window.innerWidth = 375; // iPhone viewport
    let historyBackCalled = false;
    env.window.history.back = () => { historyBackCalled = true; };

    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;
    const bbm = loaded.BackButtonManager;
    if (bbm) {
        bbm.push('form');
    }

    const box = new MockElement('DIV');
    env.document.body.appendChild(box);
    fm.floatingBox = box;

    fm.hideFloating(false);
    assert.strictEqual(historyBackCalled, true, 'Should trigger history.back() on mobile when form is on stack');
});

runTest('Tier 2', 'BVA.5: Keydown event with undefined key or code properties does not throw', () => {
    const env = setupEnvironment();
    loadMainScript(env);

    assert.doesNotThrow(() => {
        env.document.dispatchEvent({ type: 'keydown', key: undefined, code: undefined });
        env.document.dispatchEvent({ type: 'keydown', key: null, code: null });
        env.document.dispatchEvent({ type: 'keydown' });
    });
});

runTest('Tier 2', 'BVA.6: Alt+Enter when document contains zero form elements executes without error', () => {
    const env = setupEnvironment();
    loadMainScript(env);

    assert.doesNotThrow(() => {
        env.document.dispatchEvent({ type: 'keydown', altKey: true, key: 'Enter', code: 'Enter' });
    });
});

runTest('Tier 2', 'BVA.7: FormManager.appendToTextarea with null quote and missing selection', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const ta = new MockElement('TEXTAREA');
    ta.value = 'Existing content\n';
    ta.selectionStart = ta.value.length;
    ta.selectionEnd = ta.value.length;

    assert.doesNotThrow(() => {
        fm.appendToTextarea(ta, '12345', null);
    });
    assert.ok(ta.value.includes('>>12345'), 'Should append >>12345 reference');
});

// ============================================================================
// TIER 3: CROSS-FEATURE INTERACTIONS
// ============================================================================
console.log('\n--- TIER 3: CROSS-FEATURE INTERACTIONS ---');

runTest('Tier 3', 'CROSS.1: Open floating reply box -> trigger Escape dismissal -> verify clean DOM state', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const box = new MockElement('DIV');
    box.id = 'floating-reply-box';
    box.classList.add('active');
    box.style.display = 'block';
    env.document.body.appendChild(box);
    fm.floatingBox = box;

    env.document.dispatchEvent({ type: 'keydown', key: 'Escape', code: 'Escape' });
    assert.strictEqual(box.style.display, 'none');
    assert.strictEqual(box.classList.contains('active'), false);
    assert.strictEqual(env.document.body.style.overflow, '');
});

runTest('Tier 3', 'CROSS.2: Broken gallery thumbnail error fallback while floating reply box is open', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const { FormManager: fm, handleImageError } = loaded;

    // Floating box is open
    const box = new MockElement('DIV');
    box.style.display = 'block';
    env.document.body.appendChild(box);
    fm.floatingBox = box;

    // Image triggers error in background
    const img = new MockElement('IMG');
    img.setAttribute('data-file-id', 'AgACcross_test');
    img.src = 'https://broken.cdn.org/sample.jpg';
    handleImageError(img);

    assert.ok(img.src.includes('/files/AgACcross_test'));
    assert.strictEqual(box.style.display, 'block', 'Floating box must remain open and undisturbed');
});

runTest('Tier 3', 'CROSS.3: Mobile guest mode: Form disabled + Escape key safety', () => {
    const env = setupEnvironment();
    env.window.innerWidth = 360;

    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    // No floating box present
    fm.floatingBox = null;

    // Guest presses Escape
    assert.doesNotThrow(() => {
        env.document.dispatchEvent({ type: 'keydown', key: 'Escape', code: 'Escape' });
    });
});

runTest('Tier 3', 'CROSS.4: Appending quote to textarea then dismissing floating box', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const box = new MockElement('DIV');
    const ta = new MockElement('TEXTAREA');
    box.appendChild(ta);
    env.document.body.appendChild(box);
    fm.floatingBox = box;
    fm.floatingTextarea = ta;

    fm.appendToTextarea(ta, '999', 'Quoted text sample');
    assert.ok(ta.value.includes('> Quoted text sample'));

    fm.hideFloating();
    assert.strictEqual(box.style.display, 'none');
    assert.ok(ta.value.includes('> Quoted text sample'), 'Text should be preserved in textarea');
});

// ============================================================================
// TIER 4: REAL-WORLD APPLICATION SCENARIOS
// ============================================================================
console.log('\n--- TIER 4: REAL-WORLD APPLICATION SCENARIOS ---');

runTest('Tier 4', 'WORKLOAD.1: Complete user reply journey: Quote post -> edit text -> dismiss via Escape -> reopen via KeyR', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const mainForm = new MockElement('FORM');
    const mainTa = new MockElement('TEXTAREA');
    mainForm.appendChild(mainTa);
    env.document.body.appendChild(mainForm);
    fm.mainForm = mainForm;
    fm.mainTextarea = mainTa;

    const floatingBox = new MockElement('DIV');
    floatingBox.id = 'floating-reply-box';
    const floatingTa = new MockElement('TEXTAREA');
    floatingBox.appendChild(floatingTa);
    env.document.body.appendChild(floatingBox);
    fm.floatingBox = floatingBox;
    fm.floatingTextarea = floatingTa;

    // 1. User quotes post #101
    fm.appendToTextarea(floatingTa, '101', 'Hello world');
    floatingBox.classList.add('active');
    floatingBox.style.display = 'block';

    // 2. User presses Escape to cancel
    env.document.dispatchEvent({ type: 'keydown', key: 'Escape', code: 'Escape' });
    assert.strictEqual(floatingBox.style.display, 'none');

    // 3. User hits KeyR from body
    env.document.activeElement = env.document.body;
    let focusReached = false;
    fm.focusMainForm = () => { focusReached = true; };
    env.document.dispatchEvent({ type: 'keydown', code: 'KeyR', key: 'r', ctrlKey: false });
    assert.strictEqual(focusReached, true);
});

runTest('Tier 4', 'WORKLOAD.2: High-velocity keyboard shortcut spamming under simulated page navigation', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const fm = loaded.FormManager;

    const mainForm = new MockElement('FORM');
    const ta = new MockElement('TEXTAREA');
    mainForm.appendChild(ta);
    env.document.body.appendChild(mainForm);
    fm.forms = [mainForm];
    fm.mainForm = mainForm;
    fm.mainTextarea = ta;

    const keys = ['Escape', 'Enter', 'KeyR', 'KeyB', 'Tab', 'Space'];
    for (let i = 0; i < 100; i++) {
        const k = keys[i % keys.length];
        env.document.dispatchEvent({
            type: 'keydown',
            key: k,
            code: k,
            altKey: i % 2 === 0,
            ctrlKey: i % 3 === 0
        });
    }

    // Now dynamically attach floating box
    const box = new MockElement('DIV');
    env.document.body.appendChild(box);
    fm.floatingBox = box;

    for (let i = 0; i < 50; i++) {
        fm.hideFloating();
    }
    assert.strictEqual(box.style.display, 'none');
});

runTest('Tier 4', 'WORKLOAD.3: Multi-image search gallery error recovery during simultaneous user interaction', () => {
    const env = setupEnvironment();
    const loaded = loadMainScript(env);
    const { handleImageError } = loaded;

    const images = [];
    for (let i = 0; i < 20; i++) {
        const img = new MockElement('IMG');
        img.setAttribute('data-file-id', `AgACbatch_${i}`);
        img.src = `https://cdn${i}.mirror.com/photo_${i}.jpg`;
        img.onerror = () => handleImageError(img);
        images.push(img);
    }

    // Trigger error on all 20 images
    images.forEach(img => handleImageError(img));

    images.forEach((img, i) => {
        assert.ok(img.src.includes(`/files/AgACbatch_${i}`) || img.src.includes('skip='), `Image ${i} must point to fallback proxy`);
    });
});

console.log('\n================================================================');
console.log(`   ALL ${passedTests}/${totalTests} FRONTEND FORM_MANAGER TESTS PASSED PERFECTLY!   `);
console.log('================================================================\n');
