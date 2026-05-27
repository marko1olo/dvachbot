/**
 * ENGINE: REVENGE ON MACAQUE (V5: NO LAG + PLASTIC BOTTLE)
 */

const canvas = document.getElementById('gameCanvas');
// alpha: false ускоряет отрисовку на некоторых браузерах
const ctx = canvas.getContext('2d', { alpha: false }); 

// --- GLOBAL AUDIO ---
const AudioContext = window.AudioContext || window.webkitAudioContext;
const audioCtx = new AudioContext();

// --- STATE ---
let GAME_WIDTH = window.innerWidth;
let GAME_HEIGHT = window.innerHeight;
let isRunning = false;
let frameCount = 0;

const State = {
    playerHP: 100,
    bossHP: 1000,
    projectiles: [],
    enemyProjectiles: [],
    particles: [],
    bossX: 0,
    bossY: 0,
    shake: 0,
    difficulty: { attackRate: 0.02, hammerSpeed: 10 }
};

// --- RESIZE ---
function resize() {
    GAME_WIDTH = window.innerWidth;
    GAME_HEIGHT = window.innerHeight;
    canvas.width = GAME_WIDTH;
    canvas.height = GAME_HEIGHT;
    State.bossX = GAME_WIDTH / 2;
    State.bossY = GAME_HEIGHT / 2; 
}
window.addEventListener('resize', resize);
resize();

// --- ASSETS (Optimized) ---
const Art = {
    // СТАТИЧНАЯ шерсть (без Math.random внутри цикла)
    // seed - смещение, чтобы шерсть выглядела по-разному на разных частях тела
    drawOrangutanFur(x, y, r, colorDark, seed = 0) {
        ctx.fillStyle = "#d35400"; 
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI*2);
        ctx.fill();
        
        ctx.strokeStyle = colorDark;
        ctx.lineWidth = 2;
        ctx.beginPath();
        
        // Рисуем 24 волоска по кругу с фиксированным искажением
        for(let i=0; i<24; i++) {
            const angle = (i / 24) * Math.PI * 2;
            const startX = x + Math.cos(angle)*(r-2);
            const startY = y + Math.sin(angle)*(r-2);
            
            // Используем синус для "кривизны" вместо рандома -> нет дрожания
            const curveX = Math.sin(i + seed) * 10; 
            const curveY = Math.cos(i * 2 + seed) * 15 + 10; // +10 чтобы висело вниз
            
            ctx.moveTo(startX, startY);
            ctx.quadraticCurveTo(
                startX + curveX, startY + 10,
                startX + curveX * 0.5, startY + curveY
            );
        }
        ctx.stroke();
    },

    drawBackground() {
        const grad = ctx.createLinearGradient(0, 0, 0, GAME_HEIGHT);
        grad.addColorStop(0, "#2c3e50"); 
        grad.addColorStop(1, "#4ca1af");
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT);

        // Клетка
        ctx.strokeStyle = "rgba(0,0,0,0.15)";
        ctx.lineWidth = 6;
        for(let i=0; i<GAME_WIDTH; i+=80) {
            ctx.beginPath(); ctx.moveTo(i,0); ctx.lineTo(i, GAME_HEIGHT); ctx.stroke();
        }
    },

    drawVerticalLog(x, y) {
        const width = 60;
        const height = GAME_HEIGHT;
        
        ctx.save();
        ctx.translate(x, y + 50); 
        const grad = ctx.createLinearGradient(-width/2, 0, width/2, 0);
        grad.addColorStop(0, "#2e1c11");
        grad.addColorStop(0.4, "#6d4c41");
        grad.addColorStop(1, "#2e1c11");
        ctx.fillStyle = grad;
        ctx.fillRect(-width/2, 0, width, height);
        
        // Верх
        ctx.fillStyle = "#261610";
        ctx.beginPath(); ctx.ellipse(0, 0, width/2, 10, 0, 0, Math.PI*2); ctx.fill();
        ctx.restore();
    },

    drawRealAbu(x, y, hitAnim) {
        ctx.save();
        ctx.translate(x, y);
        
        if (State.shake > 0) {
            // Тряска только при ударе
            ctx.translate((Math.random()-0.5)*5, (Math.random()-0.5)*5);
        }
        
        if (hitAnim > 0) {
            ctx.filter = 'brightness(1.5) sepia(1) hue-rotate(-50deg)';
        }

        // == ТЕЛО (ОРАНГУТАН) ==
        
        // Ноги
        ctx.save(); ctx.translate(-40, 60); ctx.rotate(-0.3);
        this.drawOrangutanFur(0, 0, 25, "#a04000", 1);
        ctx.restore();
        
        ctx.save(); ctx.translate(40, 60); ctx.rotate(0.3);
        this.drawOrangutanFur(0, 0, 25, "#a04000", 2);
        ctx.restore();

        // Туловище (Большое)
        this.drawOrangutanFur(0, 20, 65, "#8a3500", 3);

        // Руки (Свисают)
        ctx.lineWidth = 20;
        ctx.lineCap = "round";
        ctx.strokeStyle = "#d35400"; 
        
        ctx.beginPath(); ctx.moveTo(-50, -10); ctx.quadraticCurveTo(-100, 50, -70, 120); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(50, -10); ctx.quadraticCurveTo(100, 50, 70, 120); ctx.stroke();

        // == ГОЛОВА (ЧЕЛОВЕК) ==
        ctx.translate(0, -50);

        // Шея
        ctx.fillStyle = "#eecfa1";
        ctx.fillRect(-15, 0, 30, 25);

        // Лицо
        ctx.beginPath();
        ctx.moveTo(-22, -30);
        ctx.lineTo(-22, 0);
        ctx.quadraticCurveTo(0, 30, 22, 0);
        ctx.lineTo(22, -30);
        ctx.arc(0, -30, 22, Math.PI, 0);
        ctx.fill();

        // Волосы (Массив без рандома внутри)
        ctx.fillStyle = "#111";
        ctx.beginPath(); ctx.arc(0, -35, 25, Math.PI, 0); ctx.fill();
        
        // Борода
        ctx.fillStyle = "#0a0a0a";
        ctx.beginPath();
        ctx.moveTo(-22, -10); 
        ctx.quadraticCurveTo(0, 20, 22, -10);
        ctx.quadraticCurveTo(22, 5, 20, 10);
        ctx.quadraticCurveTo(0, 40, -20, 10);
        ctx.fill();
        
        // Лицо детали
        ctx.fillStyle = "#2d3436"; // Мешки
        ctx.beginPath(); ctx.arc(-9, -12, 4, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.arc(9, -12, 4, 0, Math.PI*2); ctx.fill();
        
        ctx.fillStyle = "#fff"; // Глаза
        ctx.beginPath(); ctx.ellipse(-9, -14, 4, 2.5, 0, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.ellipse(9, -14, 4, 2.5, 0, 0, Math.PI*2); ctx.fill();
        
        ctx.fillStyle = "#000"; // Зрачки
        ctx.beginPath(); ctx.arc(-9, -14, 1.5, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.arc(9, -14, 1.5, 0, Math.PI*2); ctx.fill();

        ctx.strokeStyle = "#cba885"; // Нос
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(0, -14); ctx.lineTo(-3, 0); ctx.lineTo(3, 0); ctx.stroke();

        ctx.restore();
    },

    // Пластиковая бутылка с мочой
    drawPlasticBottle(x, y, rot) {
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(rot);
        
        // Жидкость (Моча)
        ctx.fillStyle = "rgba(255, 235, 59, 0.9)"; 
        ctx.beginPath();
        ctx.moveTo(-8, -10);
        ctx.lineTo(-8, 20); // Дно
        ctx.quadraticCurveTo(0, 25, 8, 20);
        ctx.lineTo(8, -10); // Плечики
        ctx.quadraticCurveTo(5, -15, 3, -20); // Горлышко
        ctx.lineTo(-3, -20);
        ctx.quadraticCurveTo(-5, -15, -8, -10);
        ctx.fill();
        
        // Блики пластика
        ctx.strokeStyle = "rgba(255,255,255,0.4)";
        ctx.lineWidth = 1;
        ctx.stroke();
        
        // Этикетка
        ctx.fillStyle = "#f39c12";
        ctx.fillRect(-9, 0, 18, 12);
        
        // Крышка (Красная)
        ctx.fillStyle = "#c0392b";
        ctx.fillRect(-4, -23, 8, 4);

        ctx.restore();
    },
    
    drawPoop(x, y, rot) {
        ctx.save(); ctx.translate(x, y); ctx.rotate(rot);
        ctx.fillStyle = "#4e342e"; 
        ctx.beginPath();
        ctx.arc(0, 0, 9, 0, Math.PI*2);
        ctx.arc(-5, 5, 7, 0, Math.PI*2);
        ctx.arc(5, 5, 7, 0, Math.PI*2);
        ctx.fill();
        ctx.restore();
    },

    drawBanhammer(x, y, rot) {
        ctx.save(); ctx.translate(x, y); ctx.rotate(rot);
        ctx.shadowBlur = 0; // Убираем тень для производительности
        ctx.fillStyle = "#7f8c8d"; ctx.fillRect(-3, -15, 6, 35); // Ручка
        ctx.fillStyle = "#c0392b"; ctx.fillRect(-15, -25, 30, 18); // Голова
        ctx.fillStyle = "#fff"; ctx.font = "bold 9px Arial"; 
        ctx.textAlign="center"; ctx.fillText("BAN", 0, -13);
        ctx.restore();
    }
};

// --- LOGIC ---

class Projectile {
    constructor(targetX, targetY, type) {
        this.x = Math.random() * GAME_WIDTH;
        this.y = GAME_HEIGHT; 
        this.type = type; 
        
        const dx = targetX - this.x;
        const dy = targetY - this.y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        const speed = 22;
        
        this.vx = (dx / dist) * speed;
        this.vy = (dy / dist) * speed;
        this.rotation = Math.random();
        this.rotSpeed = 0.2;
        this.markedForDeletion = false;
    }

    update() {
        this.x += this.vx;
        this.y += this.vy;
        this.vy += 0.15;
        this.rotation += this.rotSpeed;

        // Хитбокс
        const dx = this.x - State.bossX;
        const dy = this.y - (State.bossY + 20);
        if (Math.sqrt(dx*dx + dy*dy) < 70) {
            this.markedForDeletion = true;
            hitBoss(15 + Math.random()*10);
            spawnParticles(this.x, this.y, this.type === 'bottle' ? 'urine' : 'brown');
        }

        if (this.y < -50 || this.x < -50 || this.x > GAME_WIDTH + 50) this.markedForDeletion = true;
    }

    draw() {
        if (this.type === 'poop') Art.drawPoop(this.x, this.y, this.rotation);
        else Art.drawPlasticBottle(this.x, this.y, this.rotation);
    }
}

class EnemyHammer {
    constructor() {
        this.x = State.bossX;
        this.y = State.bossY; 
        const targetX = Math.random() * GAME_WIDTH;
        const targetY = GAME_HEIGHT;
        const dx = targetX - this.x;
        const dy = targetY - this.y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        const speed = State.difficulty.hammerSpeed;

        this.vx = (dx / dist) * speed;
        this.vy = (dy / dist) * speed;
        this.rotation = 0;
        this.markedForDeletion = false;
    }
    update() {
        this.x += this.vx; this.y += this.vy; this.rotation += 0.2;
        if (this.y > GAME_HEIGHT) {
            this.markedForDeletion = true;
            hitPlayer(5 + Math.random()*5);
            State.shake = 5;
        }
    }
    draw() { Art.drawBanhammer(this.x, this.y, this.rotation); }
    checkTap(mx, my) {
        const dist = Math.sqrt((mx - this.x)**2 + (my - this.y)**2);
        if (dist < 60) {
            this.markedForDeletion = true;
            spawnParticles(this.x, this.y, 'spark');
            playSound(440, 'square');
            return true;
        }
        return false;
    }
}

class Particle {
    constructor(x, y, type) {
        this.x = x; this.y = y;
        this.vx = (Math.random()-0.5)*10;
        this.vy = (Math.random()-0.5)*10;
        this.life = 1.0;
        this.type = type;
    }
    update() {
        this.x += this.vx; this.y += this.vy;
        this.vy += 0.5;
        this.life -= 0.08;
    }
    draw() {
        ctx.globalAlpha = this.life;
        if (this.type === 'urine') ctx.fillStyle = '#ffff00';
        else if (this.type === 'brown') ctx.fillStyle = '#5d4037';
        else ctx.fillStyle = '#e74c3c';
        ctx.fillRect(this.x, this.y, 4, 4);
        ctx.globalAlpha = 1;
    }
}

// --- LOGIC ---
let bossHitTimer = 0;

function playSound(freq, type) {
    if (audioCtx.state === 'suspended') audioCtx.resume();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.type = type;
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
    gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.1);
    osc.start(); osc.stop(audioCtx.currentTime + 0.1);
}

function hitBoss(dmg) {
    State.bossHP -= dmg;
    bossHitTimer = 5;
    playSound(150, 'sawtooth');
    updateUI();
    if (State.bossHP <= 0) gameOver(true);
}

function hitPlayer(dmg) {
    State.playerHP -= dmg;
    playSound(80, 'square');
    updateUI();
    if (State.playerHP <= 0) gameOver(false);
}

function spawnParticles(x, y, type) {
    for(let i=0; i<4; i++) State.particles.push(new Particle(x, y, type));
}

// --- MAIN ---
window.addEventListener('pointerdown', (e) => {
    if (!isRunning) return;
    const mx = e.clientX;
    const my = e.clientY;
    let hit = false;
    State.enemyProjectiles.forEach(h => { if(h.checkTap(mx, my)) hit=true; });
    if (!hit) {
        const types = ['poop', 'bottle'];
        const type = types[Math.floor(Math.random() * types.length)];
        State.projectiles.push(new Projectile(mx, my, type));
        playSound(400, 'triangle');
    }
});

function update() {
    if (!isRunning) return;
    ctx.clearRect(0, 0, GAME_WIDTH, GAME_HEIGHT);
    
    if (State.shake > 0) {
        ctx.save();
        ctx.translate((Math.random()-0.5)*State.shake, (Math.random()-0.5)*State.shake);
        State.shake *= 0.9;
        if(State.shake < 1) State.shake = 0;
    }

    Art.drawBackground();
    Art.drawVerticalLog(State.bossX, State.bossY);

    State.projectiles.forEach(p => { p.update(); p.draw(); });
    State.projectiles = State.projectiles.filter(p => !p.markedForDeletion);

    if (bossHitTimer > 0) bossHitTimer--;
    if (Math.random() < State.difficulty.attackRate) State.enemyProjectiles.push(new EnemyHammer());
    
    State.bossX = (GAME_WIDTH / 2) + Math.sin(frameCount * 0.03) * 40;
    Art.drawRealAbu(State.bossX, State.bossY, bossHitTimer);

    State.enemyProjectiles.forEach(p => { p.update(); p.draw(); });
    State.enemyProjectiles = State.enemyProjectiles.filter(p => !p.markedForDeletion);

    State.particles.forEach(p => { p.update(); p.draw(); });
    State.particles = State.particles.filter(p => p.life > 0);

    if (State.shake > 0) ctx.restore();
    frameCount++;
    requestAnimationFrame(update);
}

function startGame() {
    document.getElementById('menu-screen').classList.add('hidden');
    document.getElementById('game-ui').classList.remove('hidden');
    const r = Math.random();
    State.playerHP = 100;
    State.bossHP = 800 + Math.floor(r * 1200);
    State.difficulty.attackRate = 0.015 + (r * 0.02);
    State.difficulty.hammerSpeed = 7 + (r * 5);
    State.projectiles = [];
    State.enemyProjectiles = [];
    State.particles = [];
    document.querySelector('#boss-hp-bar .hp-label').textContent = `АБУ (HP: ${State.bossHP})`;
    isRunning = true;
    updateUI();
    resize();
    update();
}

function gameOver(win) {
    isRunning = false;
    document.getElementById('game-ui').classList.add('hidden');
    const s = document.getElementById('game-over-screen');
    s.classList.remove('hidden');
    const t = document.getElementById('go-title');
    const m = document.getElementById('go-message');
    if (win) {
        t.textContent = "ПОБЕДА"; t.style.color="#4dff4d";
        m.innerHTML = "Абу повержен.";
    } else {
        t.textContent = "BANNED"; t.style.color="red";
        m.innerHTML = "Ты забанен.";
    }
}

function updateUI() {
    const b = document.querySelector('#boss-hp-bar .hp-fill');
    const p = document.querySelector('#player-hp-bar .hp-fill');
    b.style.width = Math.max(0, (State.bossHP / (State.bossHP + 200)) * 100) + '%'; 
    p.style.width = Math.max(0, State.playerHP) + '%';
}