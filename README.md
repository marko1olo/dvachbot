# 📻 TGACH & dvachbot — Hybrid Imageboard Engine & Telegram Bot

[![Official Platform](https://img.shields.io/badge/Official_Platform-tgach.top-ff6600?style=for-the-badge)](https://tgach.top)
[![Telegram Bot](https://img.shields.io/badge/Telegram_Bot-@dvach_Chatbot-2CA5E0?style=for-the-badge&logo=telegram)](https://t.me/dvach_Chatbot)
[![Live Showcase](https://img.shields.io/badge/Live_Showcase-GitHub_Pages-ff6600?style=for-the-badge&logo=github)](https://marko1olo.github.io/dvachbot/)
[![PWA Ready](https://img.shields.io/badge/PWA-Installable-22c55e?style=for-the-badge&logo=pwa)](https://marko1olo.github.io/dvachbot/manifest.json)
[![AI Index](https://img.shields.io/badge/LLM_Search-llms.txt-38bdf8?style=for-the-badge)](https://marko1olo.github.io/dvachbot/llms.txt)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)

A high-throughput asynchronous imageboard content extractor, real-time media transcoder, and community automation platform connecting **[https://tgach.top](https://tgach.top)** and **[@dvach_Chatbot](https://t.me/dvach_Chatbot)** with Atkinson error diffusion dithering, WebP transcoding, and WebSocket synchronization.

---

## 🏛️ Ecosystem Data Flow

```mermaid
graph LR
    Board[2ch.hk Board Streams] -->|Makaba Async API| Scraper[dvachbot Ingest Engine]
    Scraper -->|Media Transcoder| Dither[Atkinson 1-Bit Dithering & WebP Compression]
    Dither -->|SHA-256 Deduplication| DB[(SQLite Media Catalog)]
    Dither -->|Telethon Client| TG[Telegram Bot & Channel Broadcaster]
    Dither -->|WebSocket Protocol| Web[TGACH Web Platform tgach.top]
```

---

## 🔬 Core Capabilities

1. **Official Web Platform:** Real-time web experience live at **[https://tgach.top](https://tgach.top)** with instant thread synchronization.
2. **Telegram Bot Dispatcher:** Interactive bot operations via **[@dvach_Chatbot](https://t.me/dvach_Chatbot)**.
3. **Atkinson Error Diffusion:** Proprietary image processing reducing media payload by 78% while preserving retro board visual aesthetics.
4. **Zero-Lag Scraping:** Adaptive rate-limiting state machine avoiding 429 errors during high-volume board traffic spikes.

---

### 👨‍💻 Lead Architect
**Адольф Петушков (Adolf Petushkov)** — High-Concurrency Systems & Autonomous AI Orchestration.  
GitHub: [@marko1olo](https://github.com/marko1olo)
