const assert = require('assert');
const fs = require('fs');
const path = require('path');

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

    class MockAudio { constructor() {} play() {} }

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
        window, document, location: window.location, localStorage: window.localStorage,
        Audio: MockAudio, safeInit: () => {}, setInterval: () => {}, setTimeout: () => {},
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

const targets = [
    { name: 'main.src.js', env: createMockEnv(path.join(__dirname, '../site_tgach/static/js/main.src.js')) },
    { name: 'main.js', env: createMockEnv(path.join(__dirname, '../site_tgach/static/js/main.js')) }
];

let totalFailed = 0;

targets.forEach(({ name, env }) => {
    console.log(`\n================ Testing ${name} ================`);

    // Test 1: Multiple query parameters with &
    const urlWithParams = "https://example.com/search?q=cat&lang=ru&page=2";
    const res1 = env.formatTextGlobal(urlWithParams, 100, 'b', 100);
    console.log("Input 1 (Multi Query Params):", urlWithParams);
    console.log("Result 1:", res1);
    try {
        const hrefMatch = res1.match(/href="([^"]+)"/);
        assert.ok(hrefMatch, "No href found in output");
        assert.ok(hrefMatch[1].includes('lang=ru'), `href attribute '${hrefMatch[1]}' must contain 'lang=ru'`);
        assert.ok(hrefMatch[1].includes('page=2'), `href attribute '${hrefMatch[1]}' must contain 'page=2'`);
        console.log("PASS: Multi Query Params");
    } catch (err) {
        console.error("FAIL: Multi Query Params -", err.message);
        totalFailed++;
    }

    // Test 2: URL Fragment Anchors with #
    const urlWithAnchor = "https://example.com/docs.html#section-install";
    const res2 = env.formatTextGlobal(urlWithAnchor, 100, 'b', 100);
    console.log("Input 2 (Fragment Anchor #):", urlWithAnchor);
    console.log("Result 2:", res2);
    try {
        const hrefMatch = res2.match(/href="([^"]+)"/);
        assert.ok(hrefMatch, "No href found in output");
        assert.ok(hrefMatch[1].includes('#section-install'), `href attribute '${hrefMatch[1]}' must contain '#section-install'`);
        console.log("PASS: Fragment Anchor #");
    } catch (err) {
        console.error("FAIL: Fragment Anchor # -", err.message);
        totalFailed++;
    }

    // Test 3: Original Bug Case: single quote + Cyrillic
    const origBugInput = ">>1234 https://domain.com/b/res/343717.html'>ТГАЧ";
    const res3 = env.formatTextGlobal(origBugInput, 100, 'b', 100);
    console.log("Input 3 (Original Bug Input):", origBugInput);
    console.log("Result 3:", res3);
    try {
        const hrefMatch = res3.match(/href="(https:\/\/domain\.com\/b\/res\/343717\.html)"/);
        assert.ok(hrefMatch, "href should strictly match clean URL without leaks");
        console.log("PASS: Original Bug Case");
    } catch (err) {
        console.error("FAIL: Original Bug Case -", err.message);
        totalFailed++;
    }

    // Test 4: parseTextEffects pre-existing <a> tag protection
    const mockContainer = {
        dataset: {},
        innerHTML: '<a href="https://example.com/search?q=test&amp;lang=en" target="_blank" rel="noopener">https://example.com/search?q=test&amp;lang=en</a>&#039;&gt;Text',
        querySelector: function() { return this; }
    };
    env.parseTextEffects(mockContainer);
    console.log("Input 4 (parseTextEffects HTML):", mockContainer.innerHTML);
    try {
        const aCount = (mockContainer.innerHTML.match(/<a\b/g) || []).length;
        assert.strictEqual(aCount, 1, 'Should have exactly 1 <a> tag, no nested anchors');
        console.log("PASS: parseTextEffects Pre-existing <a> Tag");
    } catch (err) {
        console.error("FAIL: parseTextEffects Pre-existing <a> Tag -", err.message);
        totalFailed++;
    }
});

console.log(`\nFinal result: ${totalFailed} total failures.`);
if (totalFailed > 0) {
    process.exit(1);
}
