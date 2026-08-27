# O for OSW

**One operating picture for every OSW automation** — the business view and the
technical view of the same guest journey, over one context, on open standards.

This is the merge of two earlier prototypes into a single product:

| Source | What it contributed |
|---|---|
| `kore-dashboard.nitcoinc.in` | The business view — conversation-to-document funnel, ticket and cruise-line analytics, repeat guests, and its unusually honest provenance discipline |
| `osw-opentelemetry-lab…` | The technical view — traces, metrics, logs, baggage, profiles, and the OpenTelemetry contract |

Every panel from both is reproduced here. `docs/REFERENCE_PARITY.md` is the
line-by-line acceptance checklist.

---

## Why one pane rather than two

A business symptom and its technical cause are the same event seen from two
distances. Splitting them across two tools is what turns a five-minute diagnosis
into an afternoon of log archaeology. So the guest journey funnel on the command
centre is the *front door* to the trace, the log, and the flame graph underneath
it — that path is the product, and `/diagnose` walks it end to end.

## Architecture

```
Kore.ai APIs ─┐
Zendesk API  ─┼─► ETL (Python) ─► Postgres 17 ─► FastAPI ─► React dashboard
transcripts  ─┘                        ▲            │
                                       │            └─ Claude (OpenRouter) /api/ask
OSW services ─► OTLP ─► OTel Collector ┘
```

Two ingestion paths land in one store:

- **ETL** pulls the business record (Kore.ai sessions/messages/analytics, Zendesk
  tickets, the hand-review sheets, the transcript CSVs) and *derives* spans from
  Kore.ai's real per-node timings — so the telemetry pages are grounded in real
  measurements, not only in seeded reference data.
- **The Collector** is live. The moment an OSW service is instrumented, its
  signals arrive at `/v1/traces|metrics|logs` and land in `otlp_ingest` with no
  schema change. That is the forward path off the prototype.

The API is itself instrumented to the contract it audits (`backend/app/core/otel.py`):
W3C trace context and baggage propagation, OTLP export through the Collector,
semantic-convention resource attributes, `osw.*` for business context, trace ids
in every log line, and no guest identifier in any attribute.

## Layout

| Path | What it is |
|---|---|
| `backend/` | FastAPI + psycopg 3. `routers/` are thin; all SQL lives in `services/`, so the REST endpoints and the LLM tools call the same functions and can never disagree. |
| `backend/app/etl/` | Loaders for the real extracts, the reference seed, and span derivation. |
| `frontend/` | React 19 + Vite + TypeScript. `pages/` per screen, `components/` shared, one design system in `styles/theme.css`. |
| `db/schema.sql` | The whole data model. Business tables, OpenTelemetry-shaped telemetry tables, and provenance tables. |
| `otel/collector-config.yaml` | The single export contract, including the privacy processors. |
| `docs/` | `API_CONTRACT.md`, `REFERENCE_PARITY.md`. |

## Quickstart

```bash
docker compose up -d --build
```

Then load the data:

```bash
docker compose exec backend python -m app.etl.run
```

| Surface | URL |
|---|---|
| Dashboard | http://localhost:3010 |
| API docs | http://localhost:8010/docs |
| Health | http://localhost:8010/health |
| OTLP (gRPC / HTTP) | localhost:4317 / localhost:4318 |
| Collector health | http://localhost:13133 |
| Postgres | localhost:5433 |

Ports are offset from the existing `osw-agent` stack (5432/8000/3000) so both run
side by side. Credentials come from the shared `.env`.

## The provenance rule

No figure is rendered without the population it came from. Every business panel
response carries a `meta` block with its panel id, population, basis line and
caveats, and the UI renders those caveats next to the number — `!` a limitation,
`!!` something that changes the reading, `~` data too thin to act on.

This is deliberate and worth preserving. The three populations do not line up:

| | Source | Window | Holds |
|---|---|---|---|
| **A** | Kore.ai sessions | 13–18 Aug | 100 of more available (page 1, capped) |
| **B** | Zendesk, bot-raised only | 17–19 Aug | 28 of a page of 100, from 345 reported |
| **C** | Hand review | 14–19 Aug | 74 sessions across 5 of 19 days |

No count here is a period total, and no percentage is computed across two
populations. The two `100`s in A and B are a coincidence of both APIs capping at
100 rows, not a match — which is exactly the kind of thing a dashboard without
provenance would quietly present as agreement.

## Known gaps

- **Serena and AiVA hold no conversation data** — Marina is instrumented first, by
  design; both plug into the same Collector pipeline when their data lands.
- **Document attachment cannot be read from the Zendesk API.** Five of the six
  lifecycle events tag the ticket, but `DocumentCreated` attaches a file instead of
  tagging, and the ticket API returns no `attachments` field. That panel is
  hand-reviewed until a `DocumentCreated` tag is emitted — see the
  "how to make this automatic" note on the Guest journey page.
- **No authentication.** The dashboard and API are open, and CORS is `*`. Fine for
  the lab; must be closed before this faces anyone outside the team.
- **Chat history is process-local**, so it is lost on restart and will not survive
  more than one replica.
- Reference figures on the telemetry pages are seeded from the agreed reference
  design where real instrumentation does not exist yet. Derived-from-real rows are
  marked distinctly so the two are never confused.
