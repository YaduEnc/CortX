# Mind Map API + Implementation Guide

This is the active implementation guide for the CortX mind map feature.

It explains:
- where the graph data comes from
- which backend tables are involved
- which API endpoints the app should call
- how a frontend should render and drill into the graph

## What The Mind Map Actually Is

The mind map is not a separate storage system.

It is a derived view built from the existing memory pipeline:
1. audio capture is stored
2. transcript is created
3. AI extraction creates summary/tasks/reminders
4. entity extraction identifies people, projects, topics, places, and organizations
5. entities are persisted across sessions for the same user
6. graph edges are built dynamically from entity co-occurrence in the same memory/session

So the graph is a user-scoped semantic layer on top of captured memories.

## Data Model

### `entities`
One row per normalized entity for a user.

Important fields:
- `id`
- `user_id`
- `entity_type`
- `name`
- `normalized_name`
- `mention_count`
- `first_seen_at`
- `last_seen_at`

### `entity_mentions`
One row per entity mention in a specific capture session.

Important fields:
- `id`
- `entity_id`
- `user_id`
- `session_id`
- `extraction_id`
- `context_snippet`
- `confidence`
- `created_at`

## How Graph Data Is Produced

The graph is written by the worker after transcription and AI extraction succeed.

Backend flow:
1. `process_session_transcription(session_id)`
2. transcript row is saved
3. `process_session_ai_extraction(session_id)` runs
4. assistant payload is extracted and stored in:
   - `ai_extractions`
   - `ai_items`
5. entity extraction runs from the transcript text
6. backend upserts user-scoped entities into `entities`
7. backend inserts evidence rows into `entity_mentions`

Important implementation detail:
- entity dedup is by `user_id + normalized_name + entity_type`
- the same entity can appear across many sessions
- the same entity is only mentioned once per session in `entity_mentions`

## How Edges Are Built

Edges are not stored in a dedicated table right now.

They are computed on read in `GET /v1/app/idea-graph`:
- backend loads the selected user’s entities
- backend loads their `entity_mentions`
- backend groups mentions by `session_id`
- if two entities appear in the same `session_id`, they share an edge
- `shared_session_count` is the edge weight
- `shared_session_ids` are returned for traceability

This keeps the write path simple and makes the graph fully reconstructable from source evidence.

## Active API Endpoints

All of these are app-authenticated routes and require:

```http
Authorization: Bearer <app_jwt>
```

### 1) Graph Overview

### `GET /v1/app/idea-graph?entity_type=person&min_mentions=1&limit=100`

Query params:
- `entity_type` optional: `person | project | topic | place | organization`
- `min_mentions` optional, default `1`
- `limit` optional, capped by backend at `500`

Example:

```bash
curl "https://hamza.yaduraj.me/v1/app/idea-graph?entity_type=person&min_mentions=1&limit=100" \
  -H "Authorization: Bearer <app_jwt>"
```

Response shape:

```json
{
  "nodes": [
    {
      "entity_id": "<uuid>",
      "entity_type": "person",
      "name": "PM Modi",
      "mention_count": 3,
      "first_seen_at": "2026-04-07T06:10:00Z",
      "last_seen_at": "2026-04-07T08:20:00Z"
    }
  ],
  "edges": [
    {
      "source_entity_id": "<uuid>",
      "source_name": "PM Modi",
      "source_type": "person",
      "target_entity_id": "<uuid>",
      "target_name": "Iran",
      "target_type": "place",
      "shared_session_count": 2,
      "shared_session_ids": ["<session_uuid_1>", "<session_uuid_2>"]
    }
  ],
  "total_entities": 8,
  "total_connections": 13
}
```

### 2) Entity Detail

### `GET /v1/app/idea-graph/entities/{entity_id}`

Example:

```bash
curl "https://hamza.yaduraj.me/v1/app/idea-graph/entities/<entity_id>" \
  -H "Authorization: Bearer <app_jwt>"
```

Response:

```json
{
  "entity_id": "<uuid>",
  "entity_type": "person",
  "name": "PM Modi",
  "mention_count": 3,
  "first_seen_at": "2026-04-07T06:10:00Z",
  "last_seen_at": "2026-04-07T08:20:00Z"
}
```

### 3) Mention Timeline For One Entity

### `GET /v1/app/idea-graph/entities/{entity_id}/mentions?limit=50`

Example:

```bash
curl "https://hamza.yaduraj.me/v1/app/idea-graph/entities/<entity_id>/mentions?limit=20" \
  -H "Authorization: Bearer <app_jwt>"
```

Response:

```json
[
  {
    "mention_id": "<uuid>",
    "entity_id": "<uuid>",
    "entity_name": "PM Modi",
    "entity_type": "person",
    "session_id": "<session_uuid>",
    "context_snippet": "Meet with PM Modi tomorrow at 2:30 PM.",
    "confidence": 0.96,
    "created_at": "2026-04-07T08:22:00Z"
  }
]
```

## Frontend Implementation Contract

For any iOS/Flutter/web teammate, the correct rendering flow is:

1. load graph overview from `GET /v1/app/idea-graph`
2. render `nodes`
3. render `edges` using `source_entity_id` and `target_entity_id`
4. when user taps a node:
   - call `GET /v1/app/idea-graph/entities/{entity_id}` if you need the latest node detail
   - call `GET /v1/app/idea-graph/entities/{entity_id}/mentions`
5. use the mention list as the evidence timeline / inspector panel

Recommended UX:
- filter chips by `entity_type`
- size nodes using `mention_count`
- use `shared_session_count` as edge thickness or opacity
- show `context_snippet` as the proof of why a node exists
- when user taps a mention, deep-link to that memory/session in the memory detail screen

## Frontend Data Mapping

### Node mapping
- `entity_id` -> stable UI id
- `name` -> node label
- `entity_type` -> icon/color bucket
- `mention_count` -> node radius / prominence
- `first_seen_at`, `last_seen_at` -> metadata chips

### Edge mapping
- `source_entity_id`, `target_entity_id` -> connection endpoints
- `shared_session_count` -> line weight
- `shared_session_ids` -> drill-down or debug traceability

### Mention mapping
- `session_id` -> open memory detail
- `context_snippet` -> mention preview
- `confidence` -> optional quality indicator
- `created_at` -> timeline ordering

## Current Backend Constraints

- Graph is user-scoped only.
- Entity types are limited to:
  - `person`
  - `project`
  - `topic`
  - `place`
  - `organization`
- Edges are co-occurrence-based only for now.
- There is no separate graph database.
- There is no precomputed edge table yet.
- Entity extraction failure is non-fatal:
  - memory, transcript, and AI summary can still succeed
  - graph data may simply be missing for that session

## How To Extend It Later

Safe next extensions:
- add edge caching table if read-time graph building becomes expensive
- add entity merge/admin tooling for bad duplicates
- attach `session_count`, `last_session_id`, and transcript snippets directly to node payloads
- rank entities by recency and importance, not only mention count
- add relationship classification later:
  - `person -> place`
  - `person -> project`
  - `task -> person`

## Files To Read In Codebase

Backend:
- `/Users/sujeetkumarsingh/Desktop/CortX/app/api/v1/app.py`
- `/Users/sujeetkumarsingh/Desktop/CortX/app/services/entity_extraction.py`
- `/Users/sujeetkumarsingh/Desktop/CortX/app/workers/tasks.py`
- `/Users/sujeetkumarsingh/Desktop/CortX/app/models/entity.py`

Docs:
- `/Users/sujeetkumarsingh/Desktop/CortX/docs/api_contract_v1_freeze.md`
- `/Users/sujeetkumarsingh/Desktop/CortX/README.md`
