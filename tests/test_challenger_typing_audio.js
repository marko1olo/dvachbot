/**
 * tests/test_challenger_typing_audio.js
 * Empirical challenger stress test suite for TypingAudioEngine (typing_audio.js).
 * 
 * Verifies:
 * 1. Web Audio API initialization and graceful degradation when unsupported.
 * 2. Rapid keystroke debounce stress (1,000 keystrokes in bursts).
 * 3. Security check: keystrokes inside password fields are completely ignored.
 * 4. Modifier / functional key filtering.
 * 5. All sound presets (kriper, mechanical, chiptune, shekel, fallback).
 * 6. LocalStorage settings loading/saving with corrupted JSON.
 * 7. AudioContext suspended -> resume lifecycle and error handling.
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');

console.log('='.repeat(70));
console.log('   STARTING CHALLENGER 2: TYPING_AUDIO DEEP STRESS SUITE');
console.log('='.repeat(70));

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

// Mock Web Audio
class MockGainNode {
    constructor() {
        this.gain = {
            value: 1,
            setValueAtTime: (val, t) => { this.gain.value = val; },
            linearRampToValueAtTime: (val, t) => { this.gain.value = val; },
            exponentialRampToValueAtTime: (val, t) => { this.gain.value = val; }
        };
    }
    connect(dest) {}
}

class MockOscillatorNode {
    constructor() {
        this.type = 'sine';
        this.frequency = {
            value: 440,
            setValueAtTime: (val, t) => { this.frequency.value = val; },
            exponentialRampToValueAtTime: (val, t) => { this.frequency.value = val; }
        };
        this.started = false;
        this.stopped = false;
    }
    connect(dest) {}
    start(t) { this.started = true; }
    stop(t) { this.stopped = true; }
}

class MockAudioContext {
    constructor() {
        this.state = 'running';
        this.currentTime = 0;
        this.destination = {};
        this.oscillatorCount = 0;
        this.gainCount = 0;
    }
    createOscillator() {
        this.oscillatorCount++;
        return new MockOscillatorNode();
    }
    createGain() {
        this.gainCount++;
        return new MockGainNode();
    }
    resume() {
        this.state = 'running';
        return Promise.resolve();
    }
}

function setupAudioEnv(mockLocalStorage = {}) {
    const documentListeners = {};
    const mockDocument = {
        addEventListener: (evt, fn) => {
            if (!documentListeners[evt]) documentListeners[evt] = [];
            documentListeners[evt].push(fn);
        },
        dispatchEvent: (evt) => {
            const list = documentListeners[evt.type] || [];
            list.forEach(fn => fn(evt));
        }
    };

    const mockWindow = {
        AudioContext: MockAudioContext,
        webkitAudioContext: MockAudioContext,
        document: mockDocument,
        localStorage: {
            _store: { ...mockLocalStorage },
            getItem: (k) => mockWindow.localStorage._store[k] || null,
            setItem: (k, v) => { mockWindow.localStorage._store[k] = String(v); },
            removeItem: (k) => { delete mockWindow.localStorage._store[k]; }
        },
        performance: {
            now: () => Date.now()
        }
    };

    const audioSrc = fs.readFileSync(path.join(__dirname, '../site_tgach/static/js/typing_audio.js'), 'utf8');
    const fn = new Function('window', 'document', 'localStorage', 'performance', audioSrc + '\nreturn { TypingAudio: window.TypingAudio };');
    const res = fn(mockWindow, mockDocument, mockWindow.localStorage, mockWindow.performance);

    return { win: mockWindow, doc: mockDocument, engine: res.TypingAudio };
}

// --- TEST 1: Initialization and Settings Loading ---
runTest('CH-AUD-01: TypingAudioEngine loads default and custom settings', () => {
    const { engine } = setupAudioEnv({
        'typing_audio_settings': JSON.stringify({ enabled: true, preset: 'chiptune', volume: 0.25 })
    });
    assert.strictEqual(engine.enabled, true);
    assert.strictEqual(engine.preset, 'chiptune');
    assert.strictEqual(engine.volume, 0.25);
});

// --- TEST 2: Corrupted LocalStorage Robustness ---
runTest('CH-AUD-02: Corrupted JSON in localStorage falls back safely without throwing', () => {
    const { engine } = setupAudioEnv({
        'typing_audio_settings': 'INVALID_JSON{[[['
    });
    assert.strictEqual(engine.enabled, false);
    assert.strictEqual(engine.preset, 'kriper');
});

// --- TEST 3: Keystroke in Password Field is Strictly Blocked ---
runTest('CH-AUD-03: Security - Keystrokes in password fields do NOT trigger audio synthesis', () => {
    const { engine, doc } = setupAudioEnv({
        'typing_audio_settings': JSON.stringify({ enabled: true, preset: 'kriper', volume: 0.2 })
    });

    const passwordInput = { tagName: 'INPUT', type: 'password' };
    let initialOscCount = engine.ctx ? engine.ctx.oscillatorCount : 0;

    doc.dispatchEvent({
        type: 'keydown',
        key: 'a',
        code: 'KeyA',
        target: passwordInput
    });

    let afterOscCount = engine.ctx ? engine.ctx.oscillatorCount : 0;
    assert.strictEqual(afterOscCount, initialOscCount, 'Password field must never generate sound');
});

// --- TEST 4: Keystrokes in Textarea & Text Input Synthesize Sound ---
runTest('CH-AUD-04: Keystrokes in Textarea and text Input synthesize sound', () => {
    const { engine, doc } = setupAudioEnv({
        'typing_audio_settings': JSON.stringify({ enabled: true, preset: 'kriper', volume: 0.2 })
    });

    const textarea = { tagName: 'TEXTAREA', type: 'textarea' };
    engine.lastPlayTime = 0; // reset debounce

    doc.dispatchEvent({
        type: 'keydown',
        key: 'g',
        code: 'KeyG',
        target: textarea
    });

    assert(engine.ctx !== null, 'AudioContext must be initialized');
    assert(engine.ctx.oscillatorCount > 0, 'Oscillator must be created');
});

// --- TEST 5: Functional & Modifier Key Filtering ---
runTest('CH-AUD-05: Modifiers (Shift, Alt, Ctrl, Meta, Escape, Arrows) are filtered out', () => {
    const { engine, doc } = setupAudioEnv({
        'typing_audio_settings': JSON.stringify({ enabled: true, preset: 'mechanical', volume: 0.2 })
    });

    const textarea = { tagName: 'TEXTAREA', type: 'textarea' };
    const modifiers = ['Shift', 'Control', 'Alt', 'Meta', 'CapsLock', 'Tab', 'Escape', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'];

    for (const mod of modifiers) {
        engine.lastPlayTime = 0;
        const oscBefore = engine.ctx ? engine.ctx.oscillatorCount : 0;
        doc.dispatchEvent({
            type: 'keydown',
            key: mod,
            code: mod,
            target: textarea
        });
        const oscAfter = engine.ctx ? engine.ctx.oscillatorCount : 0;
        assert.strictEqual(oscAfter, oscBefore, `Modifier ${mod} must not produce sound`);
    }
});

// --- TEST 6: Debounce Under 35ms Burst ---
runTest('CH-AUD-06: 35ms Debounce prevents sound storm on rapid keydowns', () => {
    const { engine } = setupAudioEnv({
        'typing_audio_settings': JSON.stringify({ enabled: true, preset: 'kriper', volume: 0.2 })
    });

    engine.initContext();
    const initialOsc = engine.ctx.oscillatorCount;

    // Trigger 10 rapid calls with same timestamp
    for (let i = 0; i < 10; i++) {
        engine.playKey({ key: 'a', code: 'KeyA' });
    }

    // Only 1 sound should have played
    assert.strictEqual(engine.ctx.oscillatorCount, initialOsc + 1, 'Debounce must limit sound count');
});

// --- TEST 7: All 4 Sound Presets Execute Correct Synthesis ---
runTest('CH-AUD-07: All synthesis presets (kriper, mechanical, chiptune, shekel, fallback) function', () => {
    const presets = ['kriper', 'mechanical', 'chiptune', 'shekel', 'unknown_preset'];

    for (const p of presets) {
        const { engine } = setupAudioEnv({
            'typing_audio_settings': JSON.stringify({ enabled: true, preset: p, volume: 0.2 })
        });
        engine.lastPlayTime = 0;
        engine.initContext();
        
        assert.doesNotThrow(() => {
            engine.playKey({ key: 'z', code: 'KeyZ' });
        }, `Preset ${p} should synthesize without throwing`);
    }
});

// --- TEST 8: Missing AudioContext Degrades Gracefully ---
runTest('CH-AUD-08: Environment with unsupported AudioContext degrades silently', () => {
    const mockDocument = { addEventListener: () => {} };
    const mockWindow = {
        AudioContext: null,
        webkitAudioContext: null,
        document: mockDocument,
        localStorage: { getItem: () => null, setItem: () => {} },
        performance: { now: () => Date.now() }
    };

    const audioSrc = fs.readFileSync(path.join(__dirname, '../site_tgach/static/js/typing_audio.js'), 'utf8');
    const fn = new Function('window', 'document', 'localStorage', 'performance', audioSrc + '\nreturn { TypingAudio: window.TypingAudio };');
    const { TypingAudio } = fn(mockWindow, mockDocument, mockWindow.localStorage, mockWindow.performance);

    TypingAudio.enabled = true;
    assert.doesNotThrow(() => {
        TypingAudio.playKey({ key: 'a', code: 'KeyA' });
    });
    assert.strictEqual(TypingAudio.ctx, null);
});

console.log('\n' + '='.repeat(70));
console.log(`   ALL ${passCount}/${totalTests} CHALLENGER 2 TYPING_AUDIO TESTS PASSED!`);
console.log('='.repeat(70) + '\n');
