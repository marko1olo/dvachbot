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
    console.log(`\n================ Deep Stress Testing ${name} ================`);

    // Test 1: Complex multi query params with & and #
    const complexUrl = "https://example.com/search?q=cat&lang=ru&page=2#section-3";
    const res1 = env.formatTextGlobal(complexUrl, 100, 'b', 100);
    console.log("Input 1:", complexUrl);
    console.log("Result 1:", res1);
    try {
        const hrefMatch = res1.match(/href="([^"]+)"/);
        assert.ok(hrefMatch, "No href found");
        assert.strictEqual(hrefMatch[1], "https://example.com/search?q=cat&amp;lang=ru&amp;page=2#section-3");
        console.log("PASS: Multi Query Params & Fragment Anchor");
    } catch (err) {
        console.error("FAIL: Multi Query Params & Fragment Anchor -", err.message);
        totalFailed++;
    }

    // Test 2: Original bug input
    const origInput = ">>1234 https://domain.com/b/res/343717.html'>ТГАЧ";
    const res2 = env.formatTextGlobal(origInput, 100, 'b', 100);
    console.log("Input 2:", origInput);
    console.log("Result 2:", res2);
    try {
        const hrefMatch = res2.match(/href="(https:\/\/[^"]+)"/);
        assert.ok(hrefMatch, "No http href found");
        assert.strictEqual(hrefMatch[1], "https://domain.com/b/res/343717.html");
        assert.ok(res2.endsWith("&gt;ТГАЧ") || res2.endsWith("&#039;&gt;ТГАЧ") || res2.endsWith("&#x27;&gt;ТГАЧ"), "Suffix must follow </a>");
        console.log("PASS: Original Bug Input");
    } catch (err) {
        console.error("FAIL: Original Bug Input -", err.message);
        totalFailed++;
    }

    // Test 3: Double quote + Cyrillic
    const doubleQuoteInput = '>>1234 https://domain.com/path">Текст';
    const res3 = env.formatTextGlobal(doubleQuoteInput, 100, 'b', 100);
    console.log("Input 3:", doubleQuoteInput);
    console.log("Result 3:", res3);
    try {
        const hrefMatch = res3.match(/href="(https:\/\/[^"]+)"/);
        assert.ok(hrefMatch, "No http href found");
        assert.strictEqual(hrefMatch[1], "https://domain.com/path");
        console.log("PASS: Double Quote + Cyrillic");
    } catch (err) {
        console.error("FAIL: Double Quote + Cyrillic -", err.message);
        totalFailed++;
    }

    // Test 4: Single quote in query param URL
    const querySingleQuoteInput = "https://example.com/search?q=1&lang=en'>ТГАЧ";
    const res4 = env.formatTextGlobal(querySingleQuoteInput, 100, 'b', 100);
    console.log("Input 4:", querySingleQuoteInput);
    console.log("Result 4:", res4);
    try {
        const hrefMatch = res4.match(/href="(https:\/\/[^"]+)"/);
        assert.ok(hrefMatch, "No http href found");
        assert.strictEqual(hrefMatch[1], "https://example.com/search?q=1&amp;lang=en");
        console.log("PASS: Single Quote in Query Param URL");
    } catch (err) {
        console.error("FAIL: Single Quote in Query Param URL -", err.message);
        totalFailed++;
    }

    // Test 5: Wikipedia balanced parens
    const wikiInput = "https://en.wikipedia.org/wiki/Python_(programming_language)";
    const res5 = env.formatTextGlobal(wikiInput, 100, 'b', 100);
    console.log("Input 5:", wikiInput);
    console.log("Result 5:", res5);
    try {
        const hrefMatch = res5.match(/href="([^"]+)"/);
        assert.ok(hrefMatch, "No href found");
        assert.strictEqual(hrefMatch[1], wikiInput);
        console.log("PASS: Wikipedia Balanced Parens");
    } catch (err) {
        console.error("FAIL: Wikipedia Balanced Parens -", err.message);
        totalFailed++;
    }

    // Test 6: Trailing parens in sentence
    const sentenceInput = "(Check https://example.com/test)";
    const res6 = env.formatTextGlobal(sentenceInput, 100, 'b', 100);
    console.log("Input 6:", sentenceInput);
    console.log("Result 6:", res6);
    try {
        const hrefMatch = res6.match(/href="([^"]+)"/);
        assert.ok(hrefMatch, "No href found");
        assert.strictEqual(hrefMatch[1], "https://example.com/test");
        assert.ok(res6.endsWith("</a>)"));
        console.log("PASS: Trailing Parens in Sentence");
    } catch (err) {
        console.error("FAIL: Trailing Parens in Sentence -", err.message);
        totalFailed++;
    }
});

console.log(`\nFinal result: ${totalFailed} total failures.`);
if (totalFailed > 0) {
    process.exit(1);
}
