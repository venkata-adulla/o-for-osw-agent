# Reference parity — everything the two source dashboards show

This is both the **seed data specification** and the **acceptance checklist**.
Nothing in this file may be dropped from O for OSW. Panel IDs (`P-xx`) are kept so
a reviewer can point at the old screen and find the same thing here.

Two sources:

- **Business** — `kore-dashboard.nitcoinc.in` (already titled "O for OSW")
- **Telemetry** — `osw-opentelemetry-lab.ashishkashyap.chatgpt.site`

Plus three NITCO slides (operating model / diagnose / trust & scale) reproduced at
the end.

---

# PART 1 — Business view

Header controls: **Bot** switcher (Marina), **Period** (13–19 Aug 2026), **Compare**
(disabled — "No prior period exists in this extract"), freshness ("Updated 14:05 ·
next 15:00"), **Export view**.

Section anchors: Overview · Cruise Lines & Ships · Products & Services · Customers ·
Tickets & System Health · Conversations.

Severity glyphs, used verbatim: `!` caveat · `!!` critical · `~` thin data ·
`HAND-REVIEWED` badge · `new` badge.

## Overview — "is the bot working?"

Sub-header: *every figure here is a page, not a period total*.

| Panel | Figure | Sub | Footnote |
|---|---|---|---|
| P-01 Conversations | **100** | 13–18 Aug · one API page | "Not a period total. The API caps at 100 rows and reports more available, so the real figure is higher." |
| P-04 Guests served | **26** | 26 distinct · sessions only | "Distinct people in the session page. Repeat contact is measured on tickets, not sessions — see Customers, where 15 guests came back. Kore.ai also reports 0 users on 14 Aug while returning 28 sessions that day, so treat 26 as a floor." |
| P-43 Requests raised | **7** | 7% of conversations | "Conversations that produced a Zendesk ticket, matched by ticket number." |
| P-45 Still waiting | **28 of 28** | Untouched · 0 open, 0 solved | "Every bot-raised ticket is still new. Not one has been picked up. The 8 tickets at open elsewhere in the queue arrived by web, phone and email — none of them from the bot." |

## P-54 End to end — chat to document  · HAND-REVIEWED · 5 OF 19 DAYS

Question: *A guest opens the chat. How often does paperwork actually land on a ticket?*

Basis note: "Stage 1 is the API page, shown for scale. The ‖ marks a change of
basis, not a drop — the 74 reviewed sessions cover 14–19 Aug and are not a subset
of it. Stages 2 to 6 are percentages of the sample."

| Stage | Label | Reached | % of sample | Lost | Why |
|---|---|---|---|---|---|
| 1 | Conversations (API page) | 100 | — | — | context only · 13–18 Aug, capped at 100 |
| 2 | Reviewed sessions | 74 | 100% | — | sample, 14–19 Aug · **not a subset of the row above** (basis change) |
| 3 | Guest spoke | 71 | 96% | 3 | greeted, never typed |
| 4 | Ticket created | 46 | 62% | 25 | paperwork the guest lacked, bot loops, misroutes, one crash |
| 5 | Enrichment ran | 40 | 54% | 6 | no enrichment recorded against the ticket |
| 6 | Document attached | 31 | 42% | 9 | 4 transactions stalled · 5 validation failures |

Callouts:
- **COMPLETES THE CHAIN** — 31 of 74 — "42% — the only guests whose request is fully actionable"
- **BIGGEST SINGLE LOSS** — 25 — "quit before a ticket existed — stage 3 to 4"
- **LOST AFTER THE TICKET** — 15 — "ticket raised but no document: 6 + 4 stalled + 5 failed"
- **NEVER A BOT PROBLEM** — 3 — "greeted and left without typing"

Readout: "Fewer than half of conversations finish the job. The chain loses most at
stage 4 — 25 guests abandoned or were failed before a ticket existed — and then
loses 15 more **after** a ticket was raised, where the guest has been told their
request is in hand."

`!!` note: "The 15 lost after stage 4 are the expensive ones. The guest believes
they are done. The service team receives a ticket with no paperwork behind it.
Causes: missing cabin number ×2, ship not in our system, missing purchase date,
one transaction call failed, and 4 transactions that started and never finished."

Table toggle: **SHOW THE CHAIN AS A TABLE** (columns: Stage, Reached, Of sample, Lost here, Why).

## P-07 Activity over time — "Is use growing, flat or falling?"

Two series: Conversations · Bot-raised tickets.

| Day | Conversations | Bot-raised tickets |
|---|---|---|
| 13 Aug 2026 | 28 | — |
| 14 Aug 2026 | 28 | — |
| 15 Aug 2026 | — | — |
| 16 Aug 2026 | — | — |
| 17 Aug 2026 | 18 | 3 |
| 18 Aug 2026 | 26 | 21 |
| 19 Aug 2026 | — | 4 |
| **In extract** | **100** | **28** |

Axis note: "Kore page covers 13–18 Aug · Zendesk export covers 17–19 Aug · tickets
are bot-raised only". In-chart labels: "no data in either extract", "21 tickets",
"26 chats".

Readout: "Both lines are the bot now. On 18 Aug, 26 conversations produced 21
tickets — the one day the two systems can be compared, and they broadly agree. The
tickets line runs one day later than the chats, which is the enrichment and intake lag."

Table note: "— means the day is absent from that extract, not that nothing
happened. The review sheets record traffic on 15, 16 and 19 Aug."

## Cruise lines & ships

Section note: *cruise line named on 23 of 28 bot-raised tickets*.

### P-09 Contacts by cruise line — "Which partners generate the most guest contact?"

| Cruise line | Tickets | Share of 23 named |
|---|---|---|
| Princess | 9 | 39% |
| Royal Caribbean | 5 | 22% |
| Norwegian | 5 | 22% |
| Holland America | 2 | 9% |
| Carnival | 1 | 4% |
| Virgin Voyages | 1 | 4% |

`!` note: "Raw counts. No sailing or passenger divisor yet, so the biggest partner
always ranks worst. P-10 needs it before this faces a partner."

### P-13 Guest mood — "How happy are guests when they reach us?"

Neutral 19 · Negative 8 · Very negative 1.
Readout: "9 of 28 arrive unhappy — 32%. Every bot-raised ticket is scored, so
unlike the other channels there is no gap here. Not one is positive."
`~` note: "Not split by cruise line yet. 23 of 28 name one, but that leaves 2 to 9
tickets per partner — too thin to show a partner."

## Products & services

Section note: *one flow per ticket · 25 of 100 carry none*.

### P-16 What guests come to us about — "Which flow does the guest need?"

Basis: "Bot-raised tickets only — 28. One flow per ticket. Flows are the Inquiry
Type values from the One Spa World form."

| Flow | Tickets |
|---|---|
| Return inquiry | 22 |
| Spa product | 2 |
| Pricing issue | 1 |
| HD order | 1 |
| Asked for a person | 1 |
| No flow recorded | 1 |

Readout: "The bot is a returns machine. 22 of 28 tickets are returns. Everything
else the form offers — Medi-Spa, Acupuncture, Fitness, Wellness, Thermal Suite,
Pre-booking — produced nothing at all this period."

`!` note: "That is a scope finding, not a demand finding. The bot only runs the
returns and billing flows, so it can only report on them. Guests asking about
anything else reach OSW by email or phone, and none of that is on this screen."

### P-44 Inside the returns flow — "22 returns — ordered how, and sent back why?"

Basis: "Every return ticket carries exactly three tags: the return itself, one
order route, one reason. So both breakdowns below sum to 22 with nothing missing —
the cleanest taxonomy on the whole screen."

**HOW IT WAS ORDERED** — Onboard purchase 14 · Home delivery order 8
**WHY IT IS BEING RETURNED** — Reaction or health concern 8 · Did not meet expectation 6 · Order, delivery or billing 2 · Other 6

`!!` note: "Reactions are the single biggest reason a guest returns something — 8
of 22, ahead of disappointment at 6. A safety matter is the leading driver of the
bot's main flow."
`~` note: "'Other' is 6 of 22. More than a quarter of returns land in a bucket that
names nothing — as large as the whole did-not-meet-expectation category. Worth
splitting before anyone reads a trend off this."

## Customers

Section note: *4 of 23 guests came back · bot-raised only*.

### P-30 · P-48 Guests who came back — "How often does one guest have to ask the bot twice?"

REPEAT GUESTS **4** of 23 who used it (**17%**) · THEIR TICKETS **9** ·
Raised 2+ bot tickets **3** · Chasing an older ticket **1**.

Basis: "Bot-raised only — 28 tickets from 23 guests. Nearly one guest in five had
to come back. Identified from requester_id and Zendesk's own via.source.rel =
follow_up link, so no name matching."

`!` note: "A floor, not a ceiling. Repeat contact that arrives by email or phone is
not counted here, and the ticket a follow-up points back to is usually older than
this page. Across all channels the figure was materially higher."

## HAND-REVIEWED block

Banner: "Figures on these cards come from your team's daily transcript-review
sheets, not from an API. Read: 14, 15, 16, 18, 19 Aug. Not read: the other 14 days
— 1–13 Aug, plus 17 Aug which uses a different schema. These figures will move once
those are loaded."

### P-32 What the conversation produced — "Where do guests actually end up?"

74 reviewed → 71 made a request (−3 never spoke) → 46 got a ticket (−25 did not) →
49 tickets (+3 duplicates).

Readout: "One session in three ends with nothing. 25 of 71 guests who started a
request never got a ticket. And 46 requests produced 49 tickets, so the queue is
slightly larger than the demand behind it."

**SHOW BY DAY** table:

| Day | Reviewed | Ticket | None |
|---|---|---|---|
| Fri 14 Aug | 15 | 10 | 4 |
| Sat 15 Aug | 5 | 5 | 0 |
| Sun 16 Aug | 5 | 4 | 1 |
| Mon 17 Aug | — | — | — |
| Tue 18 Aug | 29 | 15 | 13 |
| Wed 19 Aug | 20 | 12 | 7 |
| **Total** | **74** | **46** | **25** |

### Where guests quit  · `new` — "Which question ends the conversation?"

| Reason | Count | Category |
|---|---|---|
| Never spoke at all | 5 | never_spoke |
| End of flow, no confirm | 3 | other |
| Attachment upload | 2 | paperwork |
| Cabin number | 2 | paperwork |
| Full name | 2 | other |
| Ship name correction | 2 | other |
| Booking number | 1 | paperwork |
| Card last 4 digits | 1 | paperwork |
| Spa record name | 1 | paperwork |
| Bot loop or halt | 2 | bot_fault |
| Sent to the wrong flow | 2 | routing |
| System crash | 1 | bot_fault |
| Not classified | 1 | other |

Readout: "Five never typed a word — those are not a bot problem. Of the 20 who did
quit mid-flow, 7 stopped at a piece of paperwork the guest simply did not have to
hand: cabin number, booking number, card digits, spa record name."

### P-36 Length and duration — "How long does the bot hold a guest?"

FASTEST **0.9 sec** · TYPICAL **1.9 min** · LONGEST **23.6 min**
Basis: "Across the 100 sessions in the API page. Under a second = opened and
closed; 23.6 minutes = one guest completing a return."
`!` note: "All 100 report closed. The API cannot separate an idle timeout from a
satisfied guest — only the hand review can, which is why the cards above exist."

### P-55 Document enrichment — "Did the guest's paperwork actually reach the ticket?"

ATTACHED **31** · STALLED **4** · FAILED **5**

| Status | Count | What it means |
|---|---|---|
| Created | 31 | document attached to the ticket |
| Transaction initiated only | 4 | returns file made, transaction never finished |
| Failed | 5 | no document reached the ticket |
| Not recorded | 34 | mostly sessions that never produced a ticket |

Readout: "This is the status the Zendesk API cannot give you. Five of the six
lifecycle events tag the ticket; DocumentCreated attaches the file instead of
tagging, and the ticket API returns no attachments field. Everything above is read
from the daily review sheet by hand."

**HOW TO MAKE THIS AUTOMATIC** table:

| Change | Effect |
|---|---|
| Emit a DocumentCreated tag | one line in the CallBackAgent tool; success becomes visible with no extra call |
| `GET /tickets/{id}/comments` | returns `attachments[]` — proof a file landed |
| Terminal event on transactions | so the 4 stalled cases stop reading as in-flight |

### Why enrichment failed  · `new` — "Is it the pipeline, or the intake?"

Missing cabin number 2 · Ship not in our system 1 · Missing purchase date 1 ·
Transaction call failed 1 · Transaction never finished 4.

`!!` note: "Not one failure is a pipeline fault. Four of five are missing intake
data — a cabin number, a purchase date, a ship the system does not recognise. Fix
the intake and the enrichment fixes itself."

Extra line: "'Holland America Westerdam' was rejected until the guest simplified it
to 'Holland America'. That is the same naming gap that blocks the ship panel — here
it costs a guest their paperwork."

### Duplicate tickets  · `new` — "Is the service team being asked to do the same job twice?"

SESSIONS **4** · EXTRA TICKETS **4** · EXACT REPEATS **1**
Pairs: 343000 + 343003 (2) · 343456 + 343467 (2) · 343498 + 343499 (2) · 342833 + 342836 (2)

Readout: "343000 and 343003 are the same refund twice — identical 6 bottles,
$769.32 on both. The bot's 'anything else?' prompt restarted the whole intake and
the guest, following instructions, completed it again. Both were rated 5 out of 5."

`~` note: "The cause is one prompt. A closing 'anything else?' re-enters the routing
menu instead of ending the conversation. It also re-triggered after guests said
goodbye in three further sessions."

### P-43 Conversation to ticket journey — "Does the link between the two systems hold?"

Conversations **100** → Carry a ticket number **7** → Back-end step done **7**.
Readout: "The link is proven. 7 Kore.ai sessions carry a real Zendesk number via
TicketID, and all 7 succeeded. Every one is Billing — no return has run the full
path. The tag is only written on 7 of 100 sessions, so this is a proof of concept,
not a measurement."

### P-07 extended — Reviewed sessions by day — "Is review keeping up with traffic?"

Series: Reviewed · Ticket created · Not read. Values: Fri 14 = 15, Sat 15 = 5,
Sun 16 = 5, Mon 17 = not read, Tue 18 = 29, Wed 19 = 20.
Readout: "Review volume is not traffic volume. The weekend pair of 5 sessions each
is what was reviewed, not what arrived — so this chart measures the review effort,
and the Tuesday spike of 29 is the day someone had time."

## Where every figure comes from — 3 populations

Intro: "Three separate extracts. Both APIs cap at 100, so the two 100s below are a
coincidence, not a match."

**A · KORE.AI SESSIONS** — 13–18 Aug · page 1, capped at 100, more available
→ 100 CONVERSATIONS · 26 GUESTS · 7 CARRY A TICKET NO. · 1.9min MEDIAN LENGTH · 23.6min LONGEST

**B · ZENDESK — BOT-RAISED ONLY** — 17–19 Aug · 28 tickets, filtered from a page of 100 · every panel on this screen uses these 28
→ 28 BOT-RAISED TICKETS · 22 ARE RETURNS · 0 SOLVED · 9/28 ARRIVE UNHAPPY · 4 REPEAT GUESTS · 23/28 NAME A CRUISE LINE

**C · HAND REVIEW** — 14–19 Aug · 5 of 19 daily sheets · the only source that traces a conversation to a document
→ 74 SESSIONS REVIEWED · 46 MADE A TICKET · 25 PRODUCED NOTHING · 31 DOCUMENT ATTACHED · 4 DUPLICATE TICKETS

`!!` note: "No figure on this screen is a period total. Zendesk reports 345 tickets
and we hold 100 of them. Kore.ai reports more sessions available beyond its 100.
The review covers 5 days of 19. Every count here is a floor, and every percentage
is computed inside its own page — never across the three."

## Data coverage — "within page 1"

Basis: "Of the 28 bot-raised tickets, except where a row says otherwise."

| Metric | Pct | Detail |
|---|---|---|
| MOOD SCORED | 100% | 28 of 28 bot-raised |
| FLOW RECORDED | 96% | 27 of 28 bot-raised |
| CRUISE LINE NAMED | 82% | 23 of 28 · from free text, not a field |
| CONVERSATION → TICKET | 7% | 7 of 100 conversations |
| DAYS READ | 26% | 5 of 19 day-folders · 1–19 Aug |
| ENRICHMENT KNOWN | 54% | 40 of 74 reviewed sessions |
| SERENA DATA HELD | 0% | no conversations anywhere |

---

# PART 2 — Technical view (OpenTelemetry)

Chrome: left rail with 7 items and glyphs — ◎ Overview · ⑂ Traces · ⌁ Metrics ·
≡ Logs · ◇ Baggage · ▥ Profiles · ✓ Standards. Badges: "DEMO ENVIRONMENT
production-sim", "OpenTelemetry Spec 1.60". Breadcrumb "OSW / <page>". Window
selector 1 hour / 6 hours / 24 hours / 7 days. "⚡ Simulate incident" toggle. LIVE pill.
Footer: "Dummy data · built for OSW engineering discussion".

## Overview

Health banner (healthy): "All OSW services are operational — 6 services reporting ·
OTLP export healthy · last signal 8 seconds ago" — state HEALTHY.

KPI tiles (vs previous 24 hours):

| KPI | Healthy | Delta | Incident | Delta |
|---|---|---|---|---|
| Conversations | 1,284 | +12.4% | 1,284 | +12.4% |
| End-to-end success | 83.4% | +4.8% | 71.2% | −12.2% |
| p95 latency | 2.81s | −8.1% | 8.12s | +189% |
| Error rate | 2.1% | −0.6 pp | 8.7% | +6.6 pp |

**LIVE TOPOLOGY · SELECTED RETURN REQUEST** — "Business request path", subtitle
"The same ordered hops shown on the Baggage page", "6 / 6 reporting":

| Hop | Service | Operation | Healthy | Incident |
|---|---|---|---|---|
| 1 | Web chat | Guest request | origin | origin |
| 2 | Kore.ai | Process dialog | 711ms | 711ms |
| 3 | OSW Orchestrator | Route request | 244ms | 244ms |
| 4 | Zendesk Adapter | Create ticket | 451ms | 451ms |
| 5 | Enrichment | Add context | 852ms | **4.7s** |
| 6 | Document Service | Generate PDF | 341ms | 341ms |
| 7 | Zendesk Adapter | Upload document | 398ms | 398ms |

**TELEMETRY PATH · SEPARATE FROM THE REQUEST** — "Every service exports traces,
metrics and logs" → **OTel Collector** "Receives and routes signals" 12ms.

**SIGNAL COVERAGE — "Five signals, one context"**:
Traces `T` 1.28k / 99.8% · Metrics `M` 84 series / 100% · Logs `L` 4.7k / 98.6% ·
Baggage `B` 4 fields / 100% · Profiles `P` 60 Hz / 24h.

**BUSINESS + TECHNICAL TELEMETRY — Guest journey · last 24 hours** (link "Explore traces →"):
1,284 Conversation started 100% → −65 → 1,219 Guest spoke 94.9% → −148 → 1,071
Ticket created 83.4% → −68 → 1,003 Enrichment completed 78.1% → −41 → 962 Document
attached 74.9%.

Incident banner: "! Enrichment degradation detected — Error rate crossed the 5%
threshold · started 6 minutes ago" — SEV-2. Button flips to "✓ Restore healthy".

## Traces

Model explainer — "CONVERSATIONS → TRACES → SPANS", *Follow the guest, then inspect
the work*: "One conversation is the guest's chat session. Each request inside it
creates a trace, and each technical operation inside that trace is a span."
Trace coverage **99.8%**. Three cards: 1 Conversation "The complete guest chat"
CONTAINS 2 Request trace "One end-to-end outcome" CONTAINS 3 Spans "Individual
system operations".

**SELECTED CONVERSATION · GUEST SESSION `conv_8a2f`** — "Guest asked to return a
product, then raised a billing question in the same chat." COMPLETED · CHANNEL Web
chat · STARTED 14:30:31 · GUEST guest_8a2f · REQUEST TRACES 2 · TICKETS 1.
Contains: Trace `7fd3a91c` Return request 2.84s · Trace `0be42f76` Billing inquiry 1.18s.

**Recent request traces** (5 shown):

| Trace | Label | Duration | Conversation |
|---|---|---|---|
| 7fd3a91c | Return request · document attached | 2.84s | conv_8a2f |
| 0be42f76 | Billing inquiry · resolved | 1.18s | conv_8a2f |
| a9c0772d | Return request · enrichment failed | 8.12s | conv_71b0 |
| 27ecf108 | Product inquiry · abandoned | 42.6s | conv_a440 |
| b1e55d40 | Return request · duplicate blocked | 1.76s | conv_4cc2 |

**Waterfall — REQUEST TRACE 7FD3A91C · INSIDE CONV_8A2F** — "Return request ·
document attached", status OK, axis ticks 0ms / 710ms / 1.42s / 2.13s / 2.84s:

| Service | Operation | Duration |
|---|---|---|
| Kore.ai | `osw.return_request` | 2.84s (root) |
| Kore.ai | `dialog.process` | 711ms |
| OSW Orchestrator | `POST /requests` | 244ms |
| Zendesk Adapter | `zendesk.ticket.create` | 451ms |
| Enrichment | `document.enrich` | 852ms |
| Document Service | `document.generate` | 341ms |
| Zendesk Adapter | `zendesk.attachment.upload` | 398ms |

Legend: "Trace — Entire 2.84s request · Spans — 7 operations with trace-specific timings".

**Root span attributes · semantic conventions**: `service.name` osw-orchestrator ·
`service.version` 2.4.1 · `deployment.environment.name` production ·
`http.request.method` POST · `http.response.status_code` 200 · `osw.workflow.name` return_request.

**Trace-to-business correlation · PII-safe**: `osw.conversation.id` conv_8a2f ·
`osw.ticket.id` ZD-348211 · `osw.inquiry.type` return · `osw.cruise.line` princess ·
`osw.request.outcome` success · `trace_id` 7fd3a91c6a1e3d88…

## Metrics

Header: "Rates, distributions and outcomes — Low-cardinality dimensions keep
dashboards fast and costs predictable." **84 active series**.

Tiles:
- Conversation rate **53.5** / hour — "New guest chat sessions started per hour." — `osw.conversation.started` 24h
- Conversation duration (p95) **8m 42s** — "95% finish within this time; the slowest 5% take longer." — `osw.conversation.duration` 24h
- Ticket success **83.4** percent — "Eligible requests that successfully created a ticket." — `osw.ticket.created` 24h
- Enrichment system errors **1.3** percent — "Unexpected service failures only; rejected guest input is separate." — `osw.enrichment.operation` 24h

**HISTOGRAM · 1,284 GUEST SESSIONS — Conversation duration** (unit: minutes),
"Time from the guest's first message until the chat is completed or abandoned":
≤ 30s **78** · 30–60s **156** · 1–2m **342** · 2–5m **493** · 5–10m **171** · > 10m **44**.
Explainer: "What is p95? Sort all conversation durations from shortest to longest.
The p95 value is the point below which 95% fall; only the slowest 5% take longer."

**OUTCOME DIMENSIONS · Enrichment operations** — "Attempts to validate or add
business context—such as cruise line, ship alias, booking details or document
metadata—before the request continues." **1,003 operations**:
Success **962** · Input rejected **28** · System error **13**.
Note: "Enrichment error rate: 13 system errors ÷ 1,003 attempts = 1.3%. Input
rejections are tracked separately because the service itself did not fail."

**METRIC CATALOG — OSW business metric instruments** (custom namespace `osw.*`):

| Instrument | Type | Unit | Allowed dimensions |
|---|---|---|---|
| osw.conversation.started | Counter | {conversation} | channel, bot.id |
| osw.conversation.duration | Histogram | s | workflow, outcome |
| osw.conversation.abandoned | Counter | {conversation} | step, reason |
| osw.ticket.created | Counter | {ticket} | inquiry.type |
| osw.enrichment.operation | Counter | {operation} | result |
| osw.enrichment.duration | Histogram | s | result |
| osw.document.attached | Counter | {document} | result |

Glossary: "Counter adds up events, such as conversations started. Histogram groups
measurements, such as conversation duration, so percentiles like p95 can be
calculated. Dimensions are approved categories used to filter or group the metric."

## Logs

Header: "STRUCTURED LOGS — Events with trace context. Every record is queryable and
links back to the exact request that produced it." **4,728 / 24 hours**.
Filters: ALL / ERROR / WARN / INFO. "Showing 7 of 4,728 log records", 7 per page, 4 pages.
Note: "This demo loads 7 representative records per page. A production query
retrieves only the requested page—not every record at once."

Columns: TIME · LEVEL · SERVICE / EVENT · MESSAGE · TRACE

| Time | Level | Service | Event | Message | Trace |
|---|---|---|---|---|---|
| 14:31:10.842 | INFO | zendesk-adapter | osw.document.attached | Return document attached to ticket ZD-348211 | 7fd3a91c |
| 14:31:10.444 | INFO | document-service | osw.document.generated | Document created in 341 ms | 7fd3a91c |
| 14:29:59.911 | ERROR | enrichment-service | osw.enrichment.failed | Ship alias could not be resolved | a9c0772d |
| 14:29:58.306 | WARN | osw-orchestrator | osw.input.validation | Purchase date absent; recovery prompt issued | a9c0772d |
| 14:28:31.017 | INFO | kore-dialog | osw.conversation.started | New conversation accepted from web channel | 27ecf108 |
| 14:27:20.774 | WARN | osw-orchestrator | osw.ticket.duplicate_blocked | Idempotency key matched existing request | b1e55d40 |
| 14:26:12.401 | INFO | otel-collector | otel.export.completed | Batch exported: 512 spans, 84 metrics, 226 logs | — |
| 14:12:36.791 | INFO | osw-orchestrator | osw.request.completed | Product inquiry completed without ticket creation | 3ed901ac |
| 14:11:18.340 | INFO | kore-dialog | osw.conversation.started | New conversation accepted from mobile web | 3ed901ac |
| 14:10:05.612 | WARN | enrichment-service | osw.input.rejected | Booking reference format was not accepted | 98f22d70 |

Expanded record (the ERROR row) renders as JSON:
```json
{
  "timestamp": "2026-08-25T14:29:59.911Z",
  "severity_text": "ERROR",
  "service.name": "enrichment-service",
  "event.name": "osw.enrichment.failed",
  "body": "Ship alias could not be resolved",
  "trace_id": "a9c0772d6a1e3d8857f1c2f0742a9b00",
  "span_id": "21a77ee63a8a1bf2",
  "error.type": "SHIP_NOT_FOUND"
}
```
With a **CORRELATION** affordance "Open trace waterfall" and the rule
"IDs belong in logs and traces—not metric labels."

## Baggage

Header: "REQUEST-LEVEL CONTEXT — Find a request, then inspect its baggage. The time
window finds candidate requests. The detailed view follows baggage on one selected
trace without combining unrelated values." Badge **W3C Baggage**.

Summary: REQUESTS INSPECTED **1,284** (with trace data) · COMPLETE PROPAGATION
**1,274** (99.2% of requests) · NEEDS ATTENTION **10** (missing or changed fields) ·
HEADER SIZE P95 **94 B** (well below limits).

Filters: WORKFLOW (All, product_return, billing_inquiry, product_inquiry,
itinerary_document, booking_change) · PROPAGATION (All, Complete, Attention).

Discovery table — SELECT · STARTED · REQUEST · TRACE / CONVERSATION · WORKFLOW ·
BAGGAGE · REQUEST OUTCOME:

| Started | Request | Ticket | Trace / Conv | Workflow | Baggage | Outcome |
|---|---|---|---|---|---|---|
| 14:31:08 | Return request · document attached | ZD-348211 | 7fd3a91c / conv_8a2f | product_return | Complete 4/4 · 92 B | Success |
| 14:30:44 | Billing inquiry · resolved in chat | No ticket created | 0be42f76 / conv_8a2f | billing_inquiry | Complete 4/4 · 91 B | Success |
| 14:29:57 | Return request · enrichment failed | ZD-348208 | a9c0772d / conv_71b0 | product_return | Complete 4/4 · 92 B | Error |
| 14:28:31 | Product inquiry · guest abandoned | No ticket created | 27ecf108 / conv_a440 | product_inquiry | Attention 3/4 · 64 B | Abandoned |
| 14:27:19 | Return request · duplicate blocked | ZD-348205 | b1e55d40 / conv_4cc2 | product_return | Complete 4/4 · 92 B | Blocked |
| 14:24:02 | Itinerary request · PDF generated | ZD-348201 | d2a60f94 / conv_b902 | itinerary_document | Complete 4/4 · 94 B | Success |
| 14:22:14 | Booking change · routed to agent | ZD-348197 | e81bd550 / conv_c117 | booking_change | Attention 3/4 · 73 B | Success |

Footers: "Showing 7 representative requests from 1,284 in the selected window" ·
"Detailed baggage remains request-scoped".

Selected request detail (started 14:31:08): trace / conversation / ticket /
workflow / outcome / BAGGAGE FIELDS 4 / 4 / HEADER VALUE SIZE 92 B.
Hop selector with roles: 1 Web chat *Guest request · Origin* → 2 Kore.ai *Process
dialog · Injected* → 3 OSW Orchestrator *Route request · Extracted* → 4 Zendesk
Adapter *Create ticket · Forwarded* → 5 Enrichment *Add context · Forwarded* →
6 Document Service *Generate PDF · Forwarded* → 7 Zendesk Adapter *Upload document · Read*.

**HTTP REQUEST AT HOP 3 · EXTRACTED — OSW Orchestrator**
```
traceparent: 00-7fd3a91c6a1e3d8857f1c2f0742a9b00-21a77ee63a8a1bf2-01
baggage (92-byte value): osw.tenant.id=osw-prod, osw.bot.id=marina,
                         osw.channel=web, osw.workflow.name=product_return
```

**HOP 3 SNAPSHOT — Values received by this service** (4 / 4 present):

| Baggage key | Value | Purpose | Status |
|---|---|---|---|
| osw.tenant.id | osw-prod | Routing | Present |
| osw.bot.id | marina | Bot configuration | Present |
| osw.channel | web | Channel behavior | Present |
| osw.workflow.name | product_return | Workflow selection | Present |

**ORIGIN FILTER EVIDENCE — Fields blocked before propagation** (4 blocked):

| Blocked field | Observed value | Enforcement reason |
|---|---|---|
| guest.email | [redacted] | PII blocked |
| booking.number | [redacted] | Record key blocked |
| card.last_four | not present | Payment data denied |
| conversation.text | [dropped] | Sensitive + unbounded |

"These values never entered the outgoing baggage header."

**PROPAGATION AUDIT · TRACE 7FD3A91C — What every hop actually received**
("This audit belongs only to the selected request. Choose another row above to
replace it." · 0 missing · 0 changed):

| Hop | Service | Operation | Trace offset | Fields | Header size | Result |
|---|---|---|---|---|---|---|
| 1 | Web chat | Guest request | 0ms | 4 / 4 | 92 B | Created |
| 2 | Kore.ai | Process dialog | 57ms | 4 / 4 | 92 B | Injected |
| 3 | OSW Orchestrator | Route request | 768ms | 4 / 4 | 92 B | Extracted |
| 4 | Zendesk Adapter | Create ticket | 1.01s | 4 / 4 | 92 B | Forwarded |
| 5 | Enrichment | Add context | 1.46s | 4 / 4 | 92 B | Forwarded |
| 6 | Document Service | Generate PDF | 2.31s | 4 / 4 | 92 B | Forwarded |
| 7 | Zendesk Adapter | Upload document | 2.65s | 4 / 4 | 92 B | Read |

## Profiles

Header: "CONTINUOUS PROFILES — Find the code behind the latency. Sampled stack
traces explain where CPU time and memory are being consumed." Toggle CPU / ALLOCATIONS.

**FLAME GRAPH · ENRICHMENT-SERVICE** — CPU samples · last 30 min · 60 Hz:
```
main 100%
└─ handleEnrichment 96%
   ├─ resolveShipAlias 56%
   │  ├─ normalizeName 35%
   │  │  ├─ fuzzyMatch 21%
   │  │  └─ tokenize 11%
   │  └─ lookupCache 18%
   └─ buildDocument 37%
      ├─ renderTemplate 20%
      │  └─ layoutText 12%
      └─ serializePdf 14%
```
FINDING: "resolveShipAlias() accounts for 56% of CPU samples. This supports the
trace evidence around failed ship-name resolution."

Hot functions (optimization candidates): `resolveShipAlias()` 56.2% 1.46s ·
`normalizeName()` 34.8% 906ms · `renderTemplate()` 19.7% 512ms · `serializePdf()` 14.1% 367ms.

**TRACE-TO-PROFILE CORRELATION — From symptom to code**:
1 Metric alert "p95 latency exceeded 5 seconds" → 2 Slow trace "Enrichment span took
4.7 seconds" → 3 Linked profile "Ship alias matching is the hot path".

## Standards

Header: "IMPLEMENTATION BLUEPRINT — What 'OpenTelemetry compliant' means for OSW. A
practical contract your development team can implement and test." Badge "reference design".

| # | Badge | Title | Body |
|---|---|---|---|
| 01 | API + SDK | Instrument every service | Use the supported OpenTelemetry SDK for Kore.ai integrations, orchestration, enrichment, document generation and Zendesk adapters. |
| 02 | traceparent | Propagate one context | Use W3C Trace Context across every HTTP call and asynchronous handoff. Preserve the same trace across the guest journey. |
| 03 | OTLP | Export through OTLP | Send traces, metrics and logs to an OpenTelemetry Collector—not directly from every service to a vendor. |
| 04 | SemConv | Use semantic conventions | Prefer standard HTTP, service, deployment and error attributes. Place OSW-specific fields under the osw.* namespace. |
| 05 | Correlation | Correlate every signal | Write trace_id and span_id into structured logs. Link profiles to services and traces. Never use unique IDs as metric labels. |
| 06 | Privacy | Protect customer data | Keep transcripts, names, emails, booking numbers and payment data out of baggage and default telemetry exports. |

All marked REQUIRED ✓.

**COLLECTOR PATH — Vendor-neutral signal pipeline** ("one export contract"):
01 OSW services *SDK instrumentation* → 02 OTLP *gRPC or HTTP* → 03 OTel Collector
*process + route* → 04 Backend *query + visualize*.

Env block (comment "# Every service identifies itself with Resource attributes"):
```
OTEL_SERVICE_NAME=osw-enrichment
OTEL_RESOURCE_ATTRIBUTES=service.version=2.4.1,deployment.environment.name=production
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_PROPAGATORS=tracecontext,baggage
```

**DEFINITION OF DONE — Acceptance checklist 8 / 8**:

| Code | Statement |
|---|---|
| OTEL-01 | Every conversation has one root trace |
| OTEL-02 | Every cross-service call preserves traceparent |
| OTEL-03 | Spans use standard HTTP and error attributes |
| OTEL-04 | Business metrics exclude unique customer identifiers |
| OTEL-05 | Logs are structured and include trace_id + span_id |
| OTEL-06 | Baggage allowlist is documented and enforced |
| OTEL-07 | OTLP export succeeds through the Collector |
| OTEL-08 | Sensitive fields are redacted before export |

---

# PART 3 — The three slides

## Step 1 · SEE — one operating picture
"A unified observability model for every OSW automation — One place for the business
view and the technical view of every AI agent and automation — built on open standards."

Four pillars:
- **Business view** — How conversations are going — outcomes, journey health and guest experience
- **Technical view** — What happens behind each one — latency, errors and service health
- **Open standards** — OpenTelemetry end to end — vendor-neutral, portable, no lock-in
- **One place** — Every current and future automation lands in the same pane of glass

**FIVE SIGNALS, ONE CONTEXT — OPEN TELEMETRY**: Traces *Every request, end to end* ·
Metrics *Rates, durations and outcomes* · Logs *Events that carry trace context* ·
Baggage *Governed business context* · Profiles *Code-level insight*.

**THE GUEST JOURNEY — SEE EVERY STAGE, LIVE**: Conversation started → Guest spoke →
Ticket created → Enrichment run → Document attached.
"Follow guest journeys stage by stage — with a path to live production monitoring;
when a stage stalls, diagnosis starts with one click."

## Step 2 · DIAGNOSE — from symptom to code
"When something breaks, know why in minutes — not hours or days. The target
architecture ties each conversation to its traces and spans — so a business symptom
leads straight to the technical root cause."

**THE SYMPTOM — WHAT THE BUSINESS SEES**
1. **A journey stalls** — The live guest journey shows requests piling up at one stage of the flow
2. **The business feels it** — Drop-offs rise, tickets arrive without paperwork, guest mood starts to dip
3. **Today: hours of hunting** — Extracts from separate systems, log archaeology and war rooms to find a culprit
4. **With one view: minutes** — The screen that shows the symptom is the front door to the evidence behind it

**THE DIAGNOSIS — FIVE CLICKS, ONE TOOL**
1. **Alerts trigger** — Business and technical thresholds can flag problems automatically
2. **Open the trace** — The guest's exact request, timed hop by hop across every service
3. **Read the log** — The error event carries its trace context — one click between log and waterfall
4. **Profile the code** — Flame graphs point to the exact function consuming the time
5. **Fix and verify** — Ship the fix, then watch the same journey turn healthy again — live

"One investigation workflow — from business symptom to technical evidence."

## Step 3 · TRUST & SCALE — one open standard
"One standard OSW can adopt across every automation — current and future. A practical
OpenTelemetry contract OSW's teams can implement, test and audit — proven end to end in the lab."

Six contract items (as the Standards page).

**PRIVACY BY PRODUCTION DESIGN** — "Allowlists, redaction and collector controls keep
guest emails, booking numbers, card digits and chat transcripts out of the telemetry
stream — by design."
- Only an approved allowlist of business context travels with each request
- Auditable hop by hop — see exactly what every service received

**EVERY AUTOMATION JOINS THE SAME PICTURE** — "Marina is instrumented first. Serena,
AiVA and every future automation or channel plug into the same collector pipeline."
- Reusable instrumentation and dashboard templates accelerate onboarding
- One OSW command center — business and technical, in one place

Next step: "instrument Marina's production return journey first — live visibility for
all current automations ahead of peak season."

Slide footer, on every slide: "Illustrative product views — representative data for discussion".
