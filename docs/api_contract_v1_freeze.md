# CortX API Contract (v1, Current)

Version: `v1`  
Updated: `2026-04-07`  
Base URL: `https://<domain>/v1` (local: `http://localhost:8000/v1`)

Auth:
- App routes: `Authorization: Bearer <app_jwt>`
- Device routes: `Authorization: Bearer <device_jwt>`
- Device bootstrap route: `X-Admin-Key: <admin_bootstrap_key>`

## Health

### `GET /v1/health`
```json
{"status": "ok"}
```

### `GET /v1/health/ai-metrics`
```json
{
  "status_counts": {"queued": 0, "processing": 0, "done": 0, "failed": 0},
  "avg_done_latency_ms": null,
  "last_error": null,
  "updated_at": "2026-04-03T15:10:22Z"
}
```

## App Auth + Account

### `POST /v1/app/register`
Request:
```json
{"email":"user@example.com","password":"StrongPass123","full_name":"Demo User"}
```
Response `201`:
```json
{"access_token":"<app_jwt>","token_type":"bearer","expires_in_minutes":1440}
```

### `POST /v1/app/auth`
Request:
```json
{"email":"user@example.com","password":"StrongPass123"}
```
Response `200` same token payload.

### `GET /v1/app/me`
```json
{"user_id":"<uuid>","email":"user@example.com","full_name":"Demo User","created_at":"2026-04-03T08:00:00Z"}
```

### `PATCH /v1/app/me`
Request:
```json
{"full_name":"Updated Name"}
```
Response `200` same shape as `GET /app/me`.

### `GET /v1/app/me/preferences`
```json
{
  "timezone":"Asia/Kolkata",
  "daily_summary_enabled":true,
  "reminder_notifications_enabled":true,
  "calendar_export_default_enabled":false,
  "updated_at":"2026-04-03T15:10:22Z"
}
```

### `PATCH /v1/app/me/preferences`
Request (partial allowed):
```json
{
  "timezone":"Asia/Kolkata",
  "daily_summary_enabled":true,
  "reminder_notifications_enabled":true,
  "calendar_export_default_enabled":false
}
```
Response `200` same as `GET /app/me/preferences`.

### `POST /v1/app/password/forgot/request`
Request:
```json
{"email":"user@example.com"}
```
Response `200`:
```json
{
  "status":"accepted",
  "message":"If the account exists, a reset token has been issued.",
  "expires_in_seconds":900,
  "reset_token":"<non-production-only>"
}
```

### `POST /v1/app/password/forgot/confirm`
Request:
```json
{"email":"user@example.com","reset_token":"<token>","new_password":"NewStrongPass123"}
```
Response `200`:
```json
{"status":"password_reset","message":"Password reset successful"}
```

### `POST /v1/app/me/delete`
Request:
```json
{"password":"CurrentPassword123"}
```
Response `200`:
```json
{"status":"deleted","message":"Account deleted"}
```

## Pairing

### `POST /v1/pairing/start`
Request:
```json
{"device_code":"manu","pair_nonce":"<ble_nonce>"}
```
Response `200`:
```json
{"pairing_session_id":"<uuid>","pair_token":"<short_lived_token>","expires_at":"2026-04-03T10:00:00Z"}
```

### `POST /v1/device/pairing/complete`
Request:
```json
{"pair_token":"<short_lived_token>"}
```
Response `200`:
```json
{"status":"completed","pairing_session_id":"<uuid>","user_id":"<uuid>"}
```

## Devices (App-side)

### `GET /v1/app/devices`
```json
[
  {
    "device_id":"<uuid>",
    "device_code":"manu",
    "alias":null,
    "paired_at":"2026-04-03T10:05:00Z",
    "last_seen_at":"2026-04-03T15:00:00Z",
    "status":"online",
    "firmware_version":"v1.3.0",
    "last_capture_at":"2026-04-03T14:42:00Z"
  }
]
```

### `PATCH /v1/app/devices/{device_id}`
Request:
```json
{"alias":"Office Recorder"}
```
Response `200`: same object shape as one row in `GET /app/devices`.

### `DELETE /v1/app/devices/{device_id}`
Response `200`:
```json
{"status":"unpaired","message":"Device unpaired"}
```

### `POST /v1/app/devices/{device_id}/network-profile`
Request:
```json
{"ssid":"MyWifi","password":"pass123","source":"app_manual"}
```
Response `200`:
```json
{"status":"queued","expires_in_seconds":300}
```

## Device Auth + Capture

### `POST /v1/device/register` (admin bootstrap)
Request:
```json
{"device_code":"shashwat","secret":"1234567890"}
```
Exact operator `curl` for the current device:
```bash
curl -X POST "https://hamza.yaduraj.me/v1/device/register" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: hamza2026" \
  -d '{"device_code":"shashwat","secret":"1234567890"}'
```
Firmware constants to keep in sync with registration:
```cpp
const char* DEVICE_CODE = "shashwat";
const char* DEVICE_SECRET = "1234567890";
const char* DEVICE_BLE_NAME = "Yaduraj";
```
Note:
- `DEVICE_BLE_NAME` is firmware-only and is not sent to `/v1/device/register`.
- When adding a new device, usually only `DEVICE_CODE` and `DEVICE_SECRET` need matching backend registration.
Response `201`:
```json
{"id":"<uuid>","device_code":"shashwat","is_active":true}
```

### `POST /v1/device/auth`
Request:
```json
{"device_code":"shashwat","secret":"1234567890"}
```
Exact operator `curl` for the current device:
```bash
curl -X POST "https://hamza.yaduraj.me/v1/device/auth" \
  -H "Content-Type: application/json" \
  -d '{"device_code":"shashwat","secret":"1234567890"}'
```
Response `200`:
```json
{"access_token":"<device_jwt>","token_type":"bearer","expires_in_minutes":1440}
```

## Operator Commands

### Full database wipe
This removes all users, devices, pairings, captures, transcripts, AI items, and derived graph data from PostgreSQL.

```bash
docker compose exec -T postgres psql -U secondmind -d secondmind <<'SQL'
TRUNCATE TABLE
  entity_mentions,
  entities,
  ai_items,
  ai_extractions,
  transcript_segments,
  transcripts,
  audio_chunks,
  capture_sessions,
  pairing_sessions,
  device_user_bindings,
  app_password_reset_tokens,
  app_user_preferences,
  app_users,
  devices
RESTART IDENTITY CASCADE;
SQL
```

### Capture-only wipe
This keeps users and devices, but deletes audio, transcripts, AI extraction rows, and idea graph rows created from captures.

```bash
docker compose exec -T postgres psql -U secondmind -d secondmind <<'SQL'
TRUNCATE TABLE
  entity_mentions,
  entities,
  ai_items,
  ai_extractions,
  transcript_segments,
  transcripts,
  audio_chunks,
  capture_sessions
RESTART IDENTITY CASCADE;
SQL
```

### `POST /v1/device/heartbeat`
Request:
```json
{"firmware_version":"v1.3.0"}
```
Response `200`:
```json
{
  "status":"ok",
  "device_id":"<uuid>",
  "last_seen_at":"2026-04-03T15:12:10Z",
  "firmware_version":"v1.3.0"
}
```

### `POST /v1/device/network-profile/pull`
Response when profile queued:
```json
{"status":"ready","ssid":"MyWifi","password":"pass123","source":"app_manual"}
```
Response when none:
```json
{"status":"none"}
```

### `POST /v1/device/capture/sessions`
Request:
```json
{"sample_rate":16000,"channels":1,"codec":"pcm16le"}
```
Response `201`:
```json
{"session_id":"<uuid>","status":"receiving","sample_rate":16000,"channels":1,"codec":"pcm16le"}
```

### `POST /v1/device/capture/chunks`
Headers:
- `Content-Type: application/octet-stream`
- `X-Session-Id: <session_uuid>`
- `X-Chunk-Index: 0` (strict ordered sequence)
- `X-Start-Ms: 0`
- `X-End-Ms: 8000`
- `X-Sample-Rate: 16000`
- `X-Channels: 1`
- `X-Codec: pcm16le`

Response `201` stored:
```json
{"session_id":"<uuid>","chunk_index":0,"status":"stored","ack_seq":0,"next_seq":1,"total_chunks":1,"byte_size":256000}
```
Response `201` duplicate:
```json
{"session_id":"<uuid>","chunk_index":0,"status":"duplicate","ack_seq":0,"next_seq":1,"total_chunks":1,"byte_size":256000}
```

### `POST /v1/device/capture/sessions/{session_id}/finalize`
Request:
```json
{"reason":"device_stop"}
```
Response `200`:
```json
{"session_id":"<uuid>","status":"queued","total_chunks":5,"queued_for_transcription":true}
```

### `POST /v1/device/captures/upload-wav` (compatibility route)
Headers:
- `Content-Type: audio/wav`
- `X-Sample-Rate: 16000`
- `X-Channels: 1`
- `X-Codec: pcm16le`

Response `201`:
```json
{
  "session_id":"<uuid>",
  "status":"queued",
  "queued_for_transcription":true,
  "audio_size_bytes":160044,
  "sample_rate":16000,
  "channels":1,
  "codec":"pcm16le"
}
```

## Dashboard Daily Summary

### `GET /v1/app/dashboard/daily-summary?date=YYYY-MM-DD&tz=Asia/Kolkata&device_id=<optional>`
Notes:
- `date` optional, defaults to today in requested timezone.
- `tz` optional, defaults to stored user preference timezone.
- `device_id` optional; if omitted, summary aggregates all paired devices.

Response `200`:
```json
{
  "date":"2026-04-03",
  "timezone":"Asia/Kolkata",
  "headline":"Today you captured 5 memories across 2 devices. Top intent: update_api. You have 3 due actions/reminders and 2 upcoming events.",
  "generated_at":"2026-04-03T15:20:00Z",
  "metrics":{
    "memories_count":5,
    "transcript_ready_count":5,
    "open_actions_due_count":3,
    "upcoming_events_count":2,
    "top_intent":"update_api",
    "device_count":2
  },
  "focus_items":[
    {
      "item_id":"<uuid>",
      "item_type":"task",
      "title":"Update API docs",
      "due_at":"2026-04-04T09:00:00Z",
      "status":"open",
      "session_id":"<uuid>",
      "device_code":"manu"
    }
  ],
  "device_breakdown":[
    {
      "device_id":"<uuid>",
      "device_code":"manu",
      "memories_count":3,
      "transcript_ready_count":3,
      "open_action_count":2,
      "upcoming_event_count":1
    }
  ]
}
```

## App Memory + AI

### `POST /v1/app/captures/upload-wav`
Headers:
- `Content-Type: audio/wav`
- `Authorization: Bearer <app_jwt>`
- `X-Sample-Rate: 16000`
- `X-Channels: 1`
- `X-Codec: pcm16le`

Response `201`:
```json
{
  "session_id":"<uuid>",
  "status":"queued",
  "queued_for_transcription":true,
  "audio_size_bytes":160044,
  "sample_rate":16000,
  "channels":1,
  "codec":"pcm16le"
}
```

### `GET /v1/app/captures?limit=30`
```json
[
  {
    "session_id":"<uuid>",
    "device_id":"<uuid>",
    "device_code":"manu",
    "status":"done",
    "total_chunks":4,
    "started_at":"2026-04-03T13:32:00Z",
    "finalized_at":"2026-04-03T13:32:35Z",
    "duration_seconds":31.8,
    "has_audio":true
  }
]
```

### `GET /v1/app/captures/{session_id}/audio`
Response `200`: binary WAV (`audio/wav`).

### `GET /v1/app/captures/{session_id}/transcript`
```json
{"session_id":"<uuid>","model_name":"small","language":"en","full_text":"...","duration_seconds":31.8}
```

### `GET /v1/app/captures/{session_id}/ai`
Returns extraction status + intent/summary/plan + assistant items.

### `POST /v1/app/captures/{session_id}/ai/reprocess`
```json
{"session_id":"<uuid>","extraction_id":"<uuid>","status":"queued","queued":true}
```

### `GET /v1/app/assistant/items?item_type=task|reminder|plan_step&item_status=open|done|dismissed|snoozed&limit=60`
Returns list of assistant items scoped to current user.

### `PATCH /v1/app/assistant/items/{item_id}`
Request examples:
```json
{"status":"done"}
```
```json
{"snooze_minutes":60,"timezone":"Asia/Kolkata"}
```
```json
{"due_at":"2026-04-04T10:30:00Z","timezone":"Asia/Kolkata"}
```

## App Mind Map / Idea Graph

Notes:
- graph is user-scoped
- nodes come from `entities`
- mention evidence comes from `entity_mentions`
- edges are built dynamically from entity co-occurrence in the same capture session
- supported entity types: `person`, `project`, `topic`, `place`, `organization`

### `GET /v1/app/idea-graph?entity_type=person|project|topic|place|organization&min_mentions=1&limit=100`
Response `200`:
```json
{
  "nodes":[
    {
      "entity_id":"<uuid>",
      "entity_type":"person",
      "name":"PM Modi",
      "mention_count":3,
      "first_seen_at":"2026-04-07T06:10:00Z",
      "last_seen_at":"2026-04-07T08:20:00Z"
    }
  ],
  "edges":[
    {
      "source_entity_id":"<uuid>",
      "source_name":"PM Modi",
      "source_type":"person",
      "target_entity_id":"<uuid>",
      "target_name":"Iran",
      "target_type":"place",
      "shared_session_count":2,
      "shared_session_ids":["<session_uuid_1>","<session_uuid_2>"]
    }
  ],
  "total_entities":8,
  "total_connections":13
}
```

Exact example `curl`:
```bash
curl "https://hamza.yaduraj.me/v1/app/idea-graph?entity_type=person&min_mentions=1&limit=100" \
  -H "Authorization: Bearer <app_jwt>"
```

### `GET /v1/app/idea-graph/entities/{entity_id}`
Response `200`:
```json
{
  "entity_id":"<uuid>",
  "entity_type":"person",
  "name":"PM Modi",
  "mention_count":3,
  "first_seen_at":"2026-04-07T06:10:00Z",
  "last_seen_at":"2026-04-07T08:20:00Z"
}
```

Exact example `curl`:
```bash
curl "https://hamza.yaduraj.me/v1/app/idea-graph/entities/<entity_id>" \
  -H "Authorization: Bearer <app_jwt>"
```

### `GET /v1/app/idea-graph/entities/{entity_id}/mentions?limit=50`
Response `200`:
```json
[
  {
    "mention_id":"<uuid>",
    "entity_id":"<uuid>",
    "entity_name":"PM Modi",
    "entity_type":"person",
    "session_id":"<session_uuid>",
    "context_snippet":"Meet with PM Modi tomorrow at 2:30 PM.",
    "confidence":0.96,
    "created_at":"2026-04-07T08:22:00Z"
  }
]
```

Exact example `curl`:
```bash
curl "https://hamza.yaduraj.me/v1/app/idea-graph/entities/<entity_id>/mentions?limit=20" \
  -H "Authorization: Bearer <app_jwt>"
```

Implementation notes:
- `mention_count` is the node importance signal
- `shared_session_count` is the edge strength
- `shared_session_ids` provide traceability back to memories
- mention rows should be used by the app to render the entity timeline / inspector panel

## Founder Memory Engine

Notes:
- this is user-scoped founder/startup intelligence built from transcripts over time
- ideas are persisted across sessions as `founder_idea_clusters`
- each linked memory is tracked in `founder_idea_memories`
- signals are separate evidence rows in `founder_signals`
- weekly summaries are stored in `weekly_founder_memos`

### `GET /v1/app/founder/ideas?status=emerging|active|validating|paused|dropped&limit=50`
Response `200`:
```json
{
  "ideas": [
    {
      "idea_id":"<uuid>",
      "title":"Founder memory OS for startup teams",
      "summary":"A persistent memory layer that turns founder conversations into action.",
      "problem_statement":"Founders repeat product insights but lose them across days.",
      "proposed_solution":"Capture voice, extract memory, cluster ideas, and suggest next moves.",
      "target_user":"early-stage startup founders",
      "status":"active",
      "confidence":0.91,
      "novelty_score":0.74,
      "conviction_score":0.88,
      "mention_count":6,
      "first_seen_at":"2026-04-07T08:00:00Z",
      "last_seen_at":"2026-04-07T10:00:00Z",
      "created_at":"2026-04-07T08:00:00Z",
      "updated_at":"2026-04-07T10:00:00Z"
    }
  ],
  "total":1
}
```

### `GET /v1/app/founder/ideas/{idea_id}`
Response `200`:
```json
{
  "idea_id":"<uuid>",
  "title":"Founder memory OS for startup teams",
  "summary":"A persistent memory layer that turns founder conversations into action.",
  "problem_statement":"Founders repeat product insights but lose them across days.",
  "proposed_solution":"Capture voice, extract memory, cluster ideas, and suggest next moves.",
  "target_user":"early-stage startup founders",
  "status":"active",
  "confidence":0.91,
  "novelty_score":0.74,
  "conviction_score":0.88,
  "mention_count":6,
  "first_seen_at":"2026-04-07T08:00:00Z",
  "last_seen_at":"2026-04-07T10:00:00Z",
  "created_at":"2026-04-07T08:00:00Z",
  "updated_at":"2026-04-07T10:00:00Z",
  "memories":[
    {
      "memory_id":"<uuid>",
      "session_id":"<session_uuid>",
      "transcript_id":"<transcript_uuid>",
      "relevance_score":0.94,
      "role":"origin",
      "created_at":"2026-04-07T08:00:00Z"
    }
  ],
  "actions":[
    {
      "action_id":"<uuid>",
      "idea_cluster_id":"<uuid>",
      "title":"Interview 5 founders about memory loss",
      "details":"Validate whether repeated lost context is painful enough to pay for.",
      "status":"open",
      "priority":1,
      "due_at":null,
      "source":"founder_ai",
      "created_at":"2026-04-07T08:01:00Z",
      "updated_at":"2026-04-07T08:01:00Z",
      "completed_at":null
    }
  ],
  "linked_signal_count":2
}
```

### `GET /v1/app/founder/signals?signal_type=opportunity|pain_point|obsession|contradiction|market_signal&limit=60`
Response `200`:
```json
{
  "signals":[
    {
      "signal_id":"<uuid>",
      "signal_type":"opportunity",
      "title":"Repeated founder pain around lost context",
      "summary":"The user keeps returning to startup memory loss as a product opportunity.",
      "strength":0.89,
      "session_id":"<session_uuid>",
      "transcript_id":"<transcript_uuid>",
      "idea_cluster_id":"<idea_uuid>",
      "created_at":"2026-04-07T10:00:00Z"
    }
  ],
  "total":1
}
```

### `GET /v1/app/founder/weekly-memo?week_start=YYYY-MM-DD&tz=Asia/Kolkata`
Response `200`:
```json
{
  "memo_id":"<uuid>",
  "week_start":"2026-04-06",
  "headline":"Founder memory OS is becoming the dominant product thread this week.",
  "memo_text":"You repeatedly returned to founder memory capture, startup execution drift, and actionability.",
  "top_ideas":[
    {
      "idea_id":"<uuid>",
      "title":"Founder memory OS for startup teams",
      "status":"active",
      "confidence":0.91,
      "conviction_score":0.88
    }
  ],
  "top_risks":["Execution is broad; the wedge still needs sharper validation."],
  "top_actions":["Interview 5 founders about repeated context loss."],
  "created_at":"2026-04-07T10:00:00Z",
  "updated_at":"2026-04-07T10:00:00Z"
}
```

### `PATCH /v1/app/founder/actions/{action_id}`
Request:
```json
{"status":"done","priority":1}
```
Response `200`:
```json
{
  "action_id":"<uuid>",
  "idea_cluster_id":"<uuid>",
  "title":"Interview 5 founders about memory loss",
  "details":"Validate whether repeated lost context is painful enough to pay for.",
  "status":"done",
  "priority":1,
  "due_at":null,
  "source":"founder_ai",
  "created_at":"2026-04-07T08:01:00Z",
  "updated_at":"2026-04-07T10:10:00Z",
  "completed_at":"2026-04-07T10:10:00Z"
}
```

## Deprecated / Legacy

### `POST /v1/app/live/start`
Returns `410 Gone`.

### `WS /v1/stream/ws`
Legacy websocket stream route; HTTP chunk-session APIs are the active capture path.

## Error Envelope

Errors are returned as:
```json
{"detail":"Error message"}
```

Common statuses: `400`, `401`, `403`, `404`, `409`, `410`, `413`, `503`.
