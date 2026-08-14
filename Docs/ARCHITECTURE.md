# TGACH & dvachbot — Architecture Specification

## 1. System Components
Connects the **[tgach.top](https://tgach.top)** web interface with **[@dvach_Chatbot](https://t.me/dvach_Chatbot)** via WebSocket and FastAPI pipelines.

```mermaid
graph LR
    Board[2ch.hk Board Ingest] --> Transcoder[Atkinson 1-Bit Dithering & WebP Transcoder]
    Transcoder --> SQLite[(Media Catalog)]
    Transcoder --> TG[@dvach_Chatbot Publisher]
    Transcoder --> Web[tgach.top WebSocket Client]
```

## 2. Atkinson Dithering Error Diffusion Matrix
Distributes $\frac{1}{8}$ of quantization error to 6 neighboring pixels:
- $(x+1, y)$, $(x+2, y)$
- $(x-1, y+1)$, $(x, y+1)$, $(x+1, y+1)$
- $(x, y+2)$
