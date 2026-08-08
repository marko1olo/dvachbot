const assert = require('assert');
const fs = require('fs');
const path = require('path');

// Mock a lightweight browser window environment
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
        // Ignore top-level DOM initialization errors if formatTextGlobal was defined
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
    console.log(`--- Testing ${name} ---`);
    
    // 1. Test formatTextGlobal
    const rawInput = ">>1234 https://domain.com/b/res/343717.html'>ТГАЧ";
    const formatted = env.formatTextGlobal(rawInput, 100, 'b', 100);
    console.log('Formatted output:', formatted);

    assert.ok(formatted.includes('href="https://domain.com/b/res/343717.html"'), 'href should be clean URL');
    assert.ok(!formatted.includes('href="https://domain.com/b/res/343717.html&#039;'), 'href must not contain &#039;');
    assert.ok(!formatted.includes('href="https://domain.com/b/res/343717.html\'>'), 'href must not contain \'>');
    assert.ok(formatted.includes('&gt;&gt;1234</a>'), 'Post link should be created cleanly');

    // 2. Test formatTextGlobal multi-parameter URLs
    const multiInput = "Check https://example.com/search?q=1&lang=en and YouTube https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s";
    const formattedMulti = env.formatTextGlobal(multiInput, 100, 'b', 100);
    console.log('Formatted multi-parameter output:', formattedMulti);

    assert.ok(formattedMulti.includes('q=1'), 'href must contain q=1');
    assert.ok(formattedMulti.includes('lang=en'), 'href must contain lang=en');
    assert.ok(formattedMulti.includes('v=dQw4w9WgXcQ'), 'href must contain YouTube v param');
    assert.ok(formattedMulti.includes('t=30s'), 'href must contain YouTube t param');

    // 3. Test formatTextGlobal multi-parameter with trailing quote
    const corruptedMulti = ">>1234 https://example.com/search?q=1&lang=en'>ТГАЧ";
    const formattedCorrMulti = env.formatTextGlobal(corruptedMulti, 100, 'b', 100);
    console.log('Formatted corrupted multi output:', formattedCorrMulti);

    assert.ok(formattedCorrMulti.includes('href="https://example.com/search?q=1&amp;lang=en"'), 'href should cleanly contain multi-params');
    assert.ok(!formattedCorrMulti.includes('href="https://example.com/search?q=1&amp;lang=en&#039;'), 'href should not include &#039;');

    // 4. Test parseTextEffects on container with pre-existing server-rendered <a>
    const mockContainer = {
        dataset: {},
        innerHTML: '<a href="https://domain.com/b/res/343717.html" target="_blank" rel="noopener noreferrer">https://domain.com/b/res/343717.html</a>&#039;&gt;ТГАЧ',
        querySelector: function() { return this; }
    };

    env.parseTextEffects(mockContainer);
    console.log('Parsed innerHTML:', mockContainer.innerHTML);

    assert.strictEqual(mockContainer.dataset.parsed, 'true', 'Dataset parsed should be set to true');
    const nestedCount = (mockContainer.innerHTML.match(/<a\b/g) || []).length;
    assert.strictEqual(nestedCount, 1, 'Should have exactly 1 <a> tag, no nested anchors');

    console.log(`✅ All tests passed for ${name}`);
});

console.log('🎉 Frontend HTML Anchor Verification Suite Succeeded!');

