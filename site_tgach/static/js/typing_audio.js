/**
 * TypingAudioEngine - Interactive Web Audio Synthesizer for Dvachbot / Tgach
 * Synthesizes procedural musical notes, chimes, mechanical clicks, and coin sounds on keystroke.
 */
class TypingAudioEngine {
    constructor() {
        this.ctx = null;
        this.enabled = false;
        this.preset = 'kriper'; // 'kriper' | 'mechanical' | 'chiptune' | 'shekel'
        this.volume = 0.15;
        this.lastPlayTime = 0;
        
        // Pentatonic Scale Frequencies (Hz) mapped across keys for harmonious melody
        this.notes = [
            130.81, 146.83, 164.81, 196.00, 220.00, // C3-A3
            261.63, 293.66, 329.63, 392.00, 440.00, // C4-A4 (Middle)
            523.25, 587.33, 659.25, 783.99, 880.00, // C5-A5
            1046.50, 1174.66, 1318.51, 1567.98, 1760.00 // C6-A6
        ];
        
        this.initSettings();
        this.bindEvents();
    }

    initSettings() {
        try {
            const saved = JSON.parse(localStorage.getItem('typing_audio_settings') || '{}');
            this.enabled = !!saved.enabled;
            this.preset = saved.preset || 'kriper';
            this.volume = typeof saved.volume === 'number' ? saved.volume : 0.15;
        } catch (e) {
            this.enabled = false;
        }
    }

    saveSettings() {
        try {
            localStorage.setItem('typing_audio_settings', JSON.stringify({
                enabled: this.enabled,
                preset: this.preset,
                volume: this.volume
            }));
        } catch (e) {}
    }

    initContext() {
        if (!this.ctx) {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (AudioCtx) {
                this.ctx = new AudioCtx();
            }
        }
        if (this.ctx && this.ctx.state === 'suspended') {
            this.ctx.resume();
        }
    }

    getFrequencyForKey(key, code) {
        let hash = 0;
        const str = (key || code || 'a').toLowerCase();
        for (let i = 0; i < str.length; i++) {
            hash = (hash * 31 + str.charCodeAt(i)) % this.notes.length;
        }
        return this.notes[hash];
    }

    playKey(e) {
        if (!this.enabled) return;
        
        // Ignore modifiers, arrows, functional keys
        if (['Shift', 'Control', 'Alt', 'Meta', 'CapsLock', 'Tab', 'Escape', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
            return;
        }

        const now = performance.now();
        if (now - this.lastPlayTime < 35) return; // Debounce rapid keydown
        this.lastPlayTime = now;

        this.initContext();
        if (!this.ctx) return;

        const freq = this.getFrequencyForKey(e.key, e.code);
        const t = this.ctx.currentTime;

        try {
            switch (this.preset) {
                case 'kriper':
                    this.playKriperBell(freq, t);
                    break;
                case 'mechanical':
                    this.playMechanicalClick(freq, t);
                    break;
                case 'chiptune':
                    this.playChiptune(freq, t);
                    break;
                case 'shekel':
                    this.playShekelCoin(freq, t);
                    break;
                default:
                    this.playKriperBell(freq, t);
            }
        } catch (err) {
            console.warn('[TypingAudio] Error synthesizing sound:', err);
        }
    }

    // 1. Kriper Bell / Chime (FM bell synthesis with gentle reverb decay)
    playKriperBell(freq, t) {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq * 1.5, t);
        
        // Quick chime envelope
        gain.gain.setValueAtTime(0, t);
        gain.gain.linearRampToValueAtTime(this.volume * 0.8, t + 0.005);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);

        osc.connect(gain);
        gain.connect(this.ctx.destination);

        osc.start(t);
        osc.stop(t + 0.36);
    }

    // 2. Retro Mechanical Keyboard Click (Sharp click + low clack)
    playMechanicalClick(freq, t) {
        // High click
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(800 + (freq % 400), t);
        osc.frequency.exponentialRampToValueAtTime(100, t + 0.03);

        gain.gain.setValueAtTime(this.volume * 0.9, t);
        gain.gain.exponentialRampToValueAtTime(0.001, t + 0.04);

        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(t);
        osc.stop(t + 0.05);

        // Low thud
        const thud = this.ctx.createOscillator();
        const thudGain = this.ctx.createGain();
        thud.type = 'sine';
        thud.frequency.setValueAtTime(160, t);
        thud.frequency.exponentialRampToValueAtTime(50, t + 0.05);

        thudGain.gain.setValueAtTime(this.volume * 0.6, t);
        thudGain.gain.exponentialRampToValueAtTime(0.001, t + 0.06);

        thud.connect(thudGain);
        thudGain.connect(this.ctx.destination);
        thud.start(t);
        thud.stop(t + 0.07);
    }

    // 3. 8-Bit Chiptune / Arcade (Square wave with fast vibrato)
    playChiptune(freq, t) {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        
        osc.type = 'square';
        osc.frequency.setValueAtTime(freq, t);
        osc.frequency.setValueAtTime(freq * 1.05, t + 0.02);

        gain.gain.setValueAtTime(this.volume * 0.4, t);
        gain.gain.exponentialRampToValueAtTime(0.001, t + 0.12);

        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(t);
        osc.stop(t + 0.13);
    }

    // 4. Abu Shekel / Coin (High double ping)
    playShekelCoin(freq, t) {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        
        osc.type = 'sine';
        osc.frequency.setValueAtTime(987.77, t); // B5
        osc.frequency.setValueAtTime(1318.51, t + 0.06); // E6

        gain.gain.setValueAtTime(this.volume * 0.7, t);
        gain.gain.exponentialRampToValueAtTime(0.001, t + 0.28);

        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(t);
        osc.stop(t + 0.29);
    }

    bindEvents() {
        document.addEventListener('keydown', (e) => {
            const target = e.target;
            if (target && (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT')) {
                if (target.type !== 'password') {
                    this.playKey(e);
                }
            }
        }, { passive: true });
    }
}

// Global instance
window.TypingAudio = new TypingAudioEngine();
