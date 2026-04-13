# CortX AI/ML Architecture Pipeline

This document explains the technical implementation of the CortX AI pipeline for judges and technical reviewers.

## 1. Pipeline Overview: "Hear, Think, Remember"

The CortX system follows a hierarchical processing model:
1. **Edge (Hear)**: ESP32-S3 performs real-time audio capture and noise-gating.
2. **Inference (Think)**: Backend performs high-speed Speech-to-Text (ASR).
3. **Cognition (Remember)**: RAG (Retrieval-Augmented Generation) stores and retrieves memories.

---

## 2. Technical Stack & Logic

### A. The Edge Layer: Adaptive VAD
- **Implementation**: Written in optimized C++ for the ESP32-S3.
- **Logic**: Uses a **Dual-Threshold RMS Energy detector**. 
  - **High Threshold**: Triggers the start of a "Memory".
  - **Low Threshold**: Sustains the recording until the user finishes speaking.
- **Optimization**: The CPU dynamically scales from **80MHz** (idle listening) to **240MHz** (processing/uploading), maximizing battery life.

### B. The Transcription Layer: Faster-Whisper
- **Model**: `Faster-Whisper (Small)`
- **Framework**: CTranslate2 (C++ implementation of Transformer models).
- **Efficiency**: Achieves a **Real-Time Factor (RTF) of < 0.2**, meaning 10 seconds of speech is transcribed in less than 2 seconds.
- **Post-Processing**: We apply VAD-based segment filtering to remove "ghost hallucinations" (whisper tends to hallucinate text in absolute silence).

### C. The Intelligence Layer: Semantic RAG
- **Vector Database**: **Qdrant** (high-performance vector search engine).
- **Embedding Model**: `nomic-embed-text-v1.5`.
- **Logic**: Every transcript is converted into a **768-dimensional vector**. When you ask CortX a question, the system:
  1. Converts your question into a vector.
  2. Performs a **K-Nearest Neighbors (k-NN)** search in Qdrant.
  3. Pulls the relevant memory snippets.
  4. Feeds them into the LLM as "Context" to provide an accurate, fact-based answer.

---

## 3. Critical Innovations (The "Wow" Factor)

1. **PSRAM Multi-Buffering**: We use the 8MB of PSRAM on the XIAO board to create "Pre-Roll" buffers. The system captures the **~100ms of audio BEFORE** it actually detects voice, ensuring the beginning of your sentence is never cut off.
2. **TLS Session Persistence**: Unlike standard IoT devices that perform a slow 3-way handshake for every request, CortX reuses the encrypted TLS tunnel, reducing latency by **300ms per upload**.
3. **Entity Extraction**: Our AI pipeline doesn't just store text; it extracts **Entities** (People, Dates, Actions). It builds a "Knowledge Graph" of your life while you speak.

## 4. The Personal Knowledge Graph (Mind Mapping)

CortX goes beyond simple search by implementing a **Dynamic Mind Map** of the user's life:
1. **Node Discovery**: Using NER (Named Entity Recognition), we identify People, Projects, and Places from transcripts.
2. **Relational Edges**: Every conversation is linked to these entities. If two conversations mention the same person, they are automatically "connected" in the system.
3. **Idea Clustering**: Unsupervised machine learning clusters related memories into "Idea Threads," helping users see how their thoughts have evolved over months.

---

## 5. Why this matters
CortX represents a shift from **Reactive AI** to **Proactive AI**. By balancing local processing with efficient backend inference and semantic graph mapping, we provide a "Second Mind" that actually understands context and history.
