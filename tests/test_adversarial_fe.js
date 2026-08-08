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

const mainSrcEnv = createMockEnv(path.join(__dirname, '../site_tgach/static/js/main.src.js'));

console.log("--- Testing Frontend Query Params & Anchors ---");

const testUrl1 = "https://example.com/search?q=test&lang=en";
const formatted1 = mainSrcEnv.formatTextGlobal(testUrl1, 100, 'b', 100);
console.log("Input 1:", testUrl1);
console.log("Formatted 1:", formatted1);

const testUrl2 = "https://example.com/page.html#section2";
const formatted2 = mainSrcEnv.formatTextGlobal(testUrl2, 100, 'b', 100);
console.log("Input 2:", testUrl2);
console.log("Formatted 2:", formatted2);
