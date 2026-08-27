-- ============================================================================
-- O for OSW  --  unified observability schema
--
-- Two halves, one context:
--   BUSINESS  (what leadership sees)   -- ports every panel of the kore-dashboard
--   TELEMETRY (OpenTelemetry-shaped)   -- ports every page of the OTel lab
--
-- Provenance is first-class: no figure is shown without the population it came
-- from, so the UI can never imply a period total it does not have.
-- ============================================================================

DROP SCHEMA IF EXISTS osw CASCADE;
CREATE SCHEMA osw;
SET search_path TO osw, public;

-- ---------------------------------------------------------------------------
-- 0 · Provenance: every number on the screen points back to one of these
-- ---------------------------------------------------------------------------
CREATE TABLE populations (
    code            text PRIMARY KEY,            -- 'A_KORE_SESSIONS' | 'B_ZENDESK_BOT' | 'C_HAND_REVIEW' | 'T_TELEMETRY'
    letter          text NOT NULL,               -- 'A' | 'B' | 'C' | 'T'
    label           text NOT NULL,
    source_system   text NOT NULL,               -- 'kore.ai' | 'zendesk' | 'hand review' | 'otel collector'
    window_from     date,
    window_to       date,
    row_count       integer,
    is_capped       boolean NOT NULL DEFAULT false,
    cap_rows        integer,
    more_available  boolean NOT NULL DEFAULT false,
    caveat          text NOT NULL DEFAULT ''
);

-- Headline figures per population, rendered on the provenance page
CREATE TABLE population_figures (
    id              serial PRIMARY KEY,
    population_code text NOT NULL REFERENCES populations(code) ON DELETE CASCADE,
    sort_order      integer NOT NULL DEFAULT 0,
    value_text      text NOT NULL,
    label           text NOT NULL
);

-- The ! / !! / ~ annotations that sit under panels. Ported verbatim so the
-- rebuilt UI carries the same honesty as the original.
CREATE TABLE panel_notes (
    id          serial PRIMARY KEY,
    panel_id    text NOT NULL,                   -- 'P-09', 'P-44', 'OTEL-METRICS' ...
    severity    text NOT NULL CHECK (severity IN ('caveat','critical','thin','info')),
    body        text NOT NULL,
    sort_order  integer NOT NULL DEFAULT 0
);
CREATE INDEX ON panel_notes (panel_id);

-- Data-coverage strip (what fraction of records actually carry each field)
CREATE TABLE coverage_metrics (
    code        text PRIMARY KEY,
    label       text NOT NULL,
    numerator   integer NOT NULL,
    denominator integer NOT NULL,
    pct         numeric(5,1) NOT NULL,
    basis       text NOT NULL DEFAULT '',
    sort_order  integer NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 1 · Bots and conversations  (population A)
-- ---------------------------------------------------------------------------
CREATE TABLE bots (
    bot_id          text PRIMARY KEY,
    bot_name        text NOT NULL,
    environment     text NOT NULL DEFAULT 'QA',
    instrumented    boolean NOT NULL DEFAULT false,   -- OTel: Marina first
    data_held       boolean NOT NULL DEFAULT false,   -- Serena = false today
    note            text NOT NULL DEFAULT ''
);

CREATE TABLE conversations (
    session_id          text PRIMARY KEY,
    bot_id              text NOT NULL REFERENCES bots(bot_id),
    channel             text,
    channel_user_id     text,
    language            text,
    started_at          timestamptz,
    ended_at            timestamptz,
    duration_seconds    integer,
    message_count       integer,
    task_count          integer,
    containment_type    text CHECK (containment_type IN ('self_service','drop_off','agent_transfer')),
    session_status      text,
    is_developer        boolean NOT NULL DEFAULT false,
    ticket_id           bigint,                      -- from the TicketID session tag
    inquiry_type        text,                        -- from the inquiryType session tag
    event_name          text,                        -- e.g. zendesk_ticket_successful
    alt_text            text[],                      -- survey/category labels captured pre-drop-off
    source_file         text,
    raw                 jsonb,
    CONSTRAINT conversations_duration_nonneg CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
);
CREATE INDEX ON conversations (bot_id, started_at);
CREATE INDEX ON conversations (ticket_id);
CREATE INDEX ON conversations (containment_type);

CREATE TABLE messages (
    message_id      text PRIMARY KEY,
    session_id      text REFERENCES conversations(session_id) ON DELETE CASCADE,
    bot_id          text NOT NULL REFERENCES bots(bot_id),
    turn_no         integer,
    direction       text NOT NULL CHECK (direction IN ('incoming','outgoing')),
    body            text,
    component_type  text,
    task_name       text,
    intent          text,
    created_at      timestamptz,
    is_template     boolean NOT NULL DEFAULT false,
    tags            jsonb
);
CREATE INDEX ON messages (session_id, created_at);
CREATE INDEX ON messages (bot_id, created_at);

-- NLU outcomes (successintent / failintent / unhandledutterance)
CREATE TABLE nlu_events (
    id              serial PRIMARY KEY,
    bot_id          text NOT NULL REFERENCES bots(bot_id),
    session_id      text,
    message_id      text,
    result          text NOT NULL CHECK (result IN ('successintent','failintent','unhandledUtterance')),
    utterance       text,
    intent          text,
    task_name       text,
    node_name       text,
    identified_intents text[],
    is_ambiguous    boolean NOT NULL DEFAULT false,
    occurred_at     timestamptz
);
CREATE INDEX ON nlu_events (bot_id, result, occurred_at);

-- ---------------------------------------------------------------------------
-- 2 · Tickets  (population B -- bot-raised subset is the analysed cohort)
-- ---------------------------------------------------------------------------
CREATE TABLE tickets (
    ticket_id           bigint PRIMARY KEY,
    subject             text,
    description         text,
    status              text,
    priority            text,
    ticket_type         text,
    created_at          timestamptz,
    updated_at          timestamptz,
    via_channel         text,
    via_source_rel      text,                       -- 'follow_up' => chasing an older ticket
    requester_id        bigint,
    submitter_id        bigint,
    assignee_id         bigint,
    group_id            bigint,
    brand_id            bigint,
    is_bot_raised       boolean NOT NULL DEFAULT false,
    -- parsed out of the markdown description
    cruise_line         text,
    ship_name           text,
    sail_start          date,
    sail_end            date,
    service_date        date,
    cabin_number        text,
    charge_amount       numeric(12,2),
    spa_guest_name      text,
    -- taxonomy from tags
    inquiry_type        text,                       -- Return inquiry, Spa product, Pricing issue, HD order ...
    order_route         text,                       -- Onboard purchase | Home delivery order
    return_reason       text,                       -- Reaction or health concern | Did not meet expectation ...
    sentiment           text,                       -- neutral | negative | very negative | positive
    sentiment_conf      text,
    intent_tag          text,
    intent_conf         text,
    language_tag        text,
    satisfaction_score  text,
    tags                text[],
    custom_fields       jsonb,
    raw                 jsonb,
    correlated_session_id text
);
CREATE INDEX ON tickets (created_at);
CREATE INDEX ON tickets (is_bot_raised);
CREATE INDEX ON tickets (cruise_line);
CREATE INDEX ON tickets (inquiry_type);
CREATE INDEX ON tickets (requester_id);

CREATE TABLE ticket_tags (
    ticket_id   bigint NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    tag         text NOT NULL,
    family      text,                               -- 'osw' | 'intent' | 'sentiment' | 'backend' | 'system' | 'other'
    PRIMARY KEY (ticket_id, tag)
);
CREATE INDEX ON ticket_tags (tag);
CREATE INDEX ON ticket_tags (family);

-- Backend/automation failure signals carried on tickets
CREATE TABLE backend_failures (
    id          serial PRIMARY KEY,
    tag         text NOT NULL,
    label       text NOT NULL,
    ticket_count integer NOT NULL,
    stage       text,                               -- reservations | transactions | returns | eform | notification
    sort_order  integer NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 3 · Hand review  (population C -- the only source that traces chat->document)
-- ---------------------------------------------------------------------------
CREATE TABLE hand_review_days (
    review_date     date PRIMARY KEY,
    was_read        boolean NOT NULL DEFAULT false,
    reviewed        integer,
    ticket_created  integer,
    no_ticket       integer,
    note            text NOT NULL DEFAULT ''
);

CREATE TABLE hand_review_sessions (
    id                  serial PRIMARY KEY,
    review_date         date NOT NULL REFERENCES hand_review_days(review_date),
    session_ref         text,
    guest_spoke         boolean NOT NULL DEFAULT true,
    ticket_created      boolean NOT NULL DEFAULT false,
    ticket_id           bigint,
    enrichment_status   text CHECK (enrichment_status IN ('created','transaction_initiated_only','failed','not_recorded')),
    quit_reason_code    text,
    duplicate_group     text,
    notes               text NOT NULL DEFAULT ''
);
CREATE INDEX ON hand_review_sessions (review_date);

-- The chat -> document chain (P-54). Stored as rows so the funnel is data, not layout.
CREATE TABLE journey_stages (
    stage_no        integer PRIMARY KEY,
    code            text NOT NULL UNIQUE,
    label           text NOT NULL,
    reached         integer NOT NULL,
    pct_of_sample   numeric(5,1),
    lost_here       integer,
    why             text NOT NULL DEFAULT '',
    basis           text NOT NULL DEFAULT '',       -- 'api_page' | 'sample'
    basis_change    boolean NOT NULL DEFAULT false  -- true on stage 2 (the double-bar)
);

CREATE TABLE quit_reasons (
    code        text PRIMARY KEY,
    label       text NOT NULL,
    count       integer NOT NULL,
    category    text NOT NULL DEFAULT 'other',      -- 'never_spoke' | 'paperwork' | 'bot_fault' | 'routing' | 'other'
    sort_order  integer NOT NULL DEFAULT 0
);

CREATE TABLE enrichment_outcomes (
    code        text PRIMARY KEY,
    label       text NOT NULL,
    count       integer NOT NULL,
    meaning     text NOT NULL DEFAULT '',
    sort_order  integer NOT NULL DEFAULT 0
);

CREATE TABLE enrichment_failures (
    code        text PRIMARY KEY,
    label       text NOT NULL,
    count       integer NOT NULL,
    is_intake   boolean NOT NULL DEFAULT true,      -- intake data vs pipeline fault
    sort_order  integer NOT NULL DEFAULT 0
);

CREATE TABLE duplicate_pairs (
    id              serial PRIMARY KEY,
    ticket_a        bigint NOT NULL,
    ticket_b        bigint NOT NULL,
    is_exact_repeat boolean NOT NULL DEFAULT false,
    evidence        text NOT NULL DEFAULT '',
    cause           text NOT NULL DEFAULT ''
);

-- Fixes that would make a manual panel automatic
CREATE TABLE automation_gaps (
    id          serial PRIMARY KEY,
    panel_id    text NOT NULL,
    change      text NOT NULL,
    effect      text NOT NULL,
    sort_order  integer NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 4 · Daily activity (one row per calendar day, per source -- NULL means the
--     day is absent from that extract, which is not the same as zero)
-- ---------------------------------------------------------------------------
CREATE TABLE daily_activity (
    day                 date PRIMARY KEY,
    conversations       integer,
    bot_tickets         integer,
    reviewed            integer,
    review_ticket_created integer,
    review_no_ticket    integer,
    in_kore_extract     boolean NOT NULL DEFAULT false,
    in_zendesk_extract  boolean NOT NULL DEFAULT false,
    was_reviewed        boolean NOT NULL DEFAULT false
);

-- ---------------------------------------------------------------------------
-- 5 · Headline KPI snapshots. Two states per KPI (healthy / incident) so the
--     "Simulate incident" control has real rows behind it rather than JS math.
-- ---------------------------------------------------------------------------
CREATE TABLE kpi_snapshots (
    id              serial PRIMARY KEY,
    code            text NOT NULL,
    view            text NOT NULL CHECK (view IN ('business','technical')),
    state           text NOT NULL CHECK (state IN ('healthy','incident')),
    label           text NOT NULL,
    value_text      text NOT NULL,
    unit            text NOT NULL DEFAULT '',
    sub_text        text NOT NULL DEFAULT '',
    delta_text      text,
    delta_direction text CHECK (delta_direction IN ('up','down','flat')),
    delta_is_good   boolean,
    tone            text NOT NULL DEFAULT 'neutral' CHECK (tone IN ('neutral','good','warning','serious','critical')),
    panel_id        text NOT NULL DEFAULT '',
    footnote        text NOT NULL DEFAULT '',
    sort_order      integer NOT NULL DEFAULT 0,
    -- (view, code, state), not (code, state): business and technical each
    -- have their own "conversations" tile, and they are different numbers.
    UNIQUE (view, code, state)
);

-- ---------------------------------------------------------------------------
-- 6 · TELEMETRY -- services, traces, spans
-- ---------------------------------------------------------------------------
CREATE TABLE services (
    service_name    text PRIMARY KEY,
    display_name    text NOT NULL,
    service_version text,
    deployment_env  text NOT NULL DEFAULT 'production',
    role            text NOT NULL DEFAULT '',
    sdk_language    text,
    is_reporting    boolean NOT NULL DEFAULT true,
    is_collector    boolean NOT NULL DEFAULT false
);

CREATE TABLE traces (
    trace_id        text PRIMARY KEY,
    conversation_id text,
    ticket_ref      text,                           -- 'ZD-348211'
    root_service    text REFERENCES services(service_name),
    root_operation  text NOT NULL,
    workflow        text,                           -- product_return | billing_inquiry | ...
    outcome         text NOT NULL DEFAULT 'success' CHECK (outcome IN ('success','error','abandoned','blocked')),
    status          text NOT NULL DEFAULT 'OK',
    label           text NOT NULL DEFAULT '',
    started_at      timestamptz NOT NULL,
    duration_ms     integer NOT NULL,
    span_count      integer NOT NULL DEFAULT 0
);
CREATE INDEX ON traces (started_at DESC);
CREATE INDEX ON traces (conversation_id);
CREATE INDEX ON traces (workflow);
CREATE INDEX ON traces (outcome);

-- A conversation groups 1..n request traces
CREATE TABLE telemetry_conversations (
    conversation_id text PRIMARY KEY,
    guest_ref       text,
    channel         text,
    started_at      timestamptz,
    status          text NOT NULL DEFAULT 'COMPLETED',
    summary         text NOT NULL DEFAULT '',
    trace_count     integer NOT NULL DEFAULT 0,
    ticket_count    integer NOT NULL DEFAULT 0
);

CREATE TABLE spans (
    span_id         text PRIMARY KEY,
    trace_id        text NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
    parent_span_id  text,
    service_name    text NOT NULL REFERENCES services(service_name),
    operation       text NOT NULL,
    kind            text NOT NULL DEFAULT 'SERVER',
    hop_no          integer,
    depth           integer NOT NULL DEFAULT 0,
    start_offset_ms integer NOT NULL DEFAULT 0,
    duration_ms     integer NOT NULL,
    status          text NOT NULL DEFAULT 'OK' CHECK (status IN ('OK','ERROR','UNSET')),
    is_root         boolean NOT NULL DEFAULT false,
    attributes      jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ON spans (trace_id, start_offset_ms);

-- Attribute rows for the "semantic conventions" / "business correlation" tables
CREATE TABLE span_attributes (
    id          serial PRIMARY KEY,
    span_id     text NOT NULL REFERENCES spans(span_id) ON DELETE CASCADE,
    key         text NOT NULL,
    value       text NOT NULL,
    grouping    text NOT NULL DEFAULT 'semconv' CHECK (grouping IN ('semconv','business')),
    sort_order  integer NOT NULL DEFAULT 0
);
CREATE INDEX ON span_attributes (span_id, grouping);

-- ---------------------------------------------------------------------------
-- 7 · TELEMETRY -- logs
-- ---------------------------------------------------------------------------
CREATE TABLE log_records (
    id              bigserial PRIMARY KEY,
    observed_at     timestamptz NOT NULL,
    severity_text   text NOT NULL CHECK (severity_text IN ('TRACE','DEBUG','INFO','WARN','ERROR','FATAL')),
    severity_number integer NOT NULL DEFAULT 9,
    service_name    text NOT NULL,
    event_name      text NOT NULL,
    body            text NOT NULL,
    trace_id        text,
    span_id         text,
    error_type      text,
    attributes      jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ON log_records (observed_at DESC);
CREATE INDEX ON log_records (severity_text);
CREATE INDEX ON log_records (trace_id);

-- ---------------------------------------------------------------------------
-- 8 · TELEMETRY -- metrics
-- ---------------------------------------------------------------------------
CREATE TABLE metric_instruments (
    name        text PRIMARY KEY,
    kind        text NOT NULL CHECK (kind IN ('Counter','Histogram','Gauge','UpDownCounter')),
    unit        text NOT NULL,
    description text NOT NULL DEFAULT '',
    dimensions  text[] NOT NULL DEFAULT '{}',
    sort_order  integer NOT NULL DEFAULT 0
);

-- Tile-level readings
CREATE TABLE metric_summaries (
    code        text PRIMARY KEY,
    instrument  text REFERENCES metric_instruments(name),
    label       text NOT NULL,
    value_text  text NOT NULL,
    unit        text NOT NULL DEFAULT '',
    -- "window" is reserved in Postgres, hence the suffix. The API still exposes
    -- this as `window` -- see the alias in services/telemetry.py.
    window_label text NOT NULL DEFAULT '24h',
    description text NOT NULL DEFAULT '',
    sort_order  integer NOT NULL DEFAULT 0
);

CREATE TABLE metric_histogram_buckets (
    id          serial PRIMARY KEY,
    instrument  text NOT NULL REFERENCES metric_instruments(name),
    bucket_label text NOT NULL,
    count       integer NOT NULL,
    sort_order  integer NOT NULL DEFAULT 0
);

CREATE TABLE metric_outcomes (
    id          serial PRIMARY KEY,
    instrument  text NOT NULL REFERENCES metric_instruments(name),
    result      text NOT NULL,
    count       integer NOT NULL,
    is_error    boolean NOT NULL DEFAULT false,
    note        text NOT NULL DEFAULT '',
    sort_order  integer NOT NULL DEFAULT 0
);

CREATE TABLE metric_series (
    id          bigserial PRIMARY KEY,
    instrument  text NOT NULL REFERENCES metric_instruments(name),
    bucket_at   timestamptz NOT NULL,
    value       numeric NOT NULL,
    dimensions  jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ON metric_series (instrument, bucket_at);

-- ---------------------------------------------------------------------------
-- 9 · TELEMETRY -- baggage (governed business context)
-- ---------------------------------------------------------------------------
CREATE TABLE baggage_fields (
    key         text PRIMARY KEY,
    purpose     text NOT NULL,
    is_allowed  boolean NOT NULL DEFAULT true,
    sort_order  integer NOT NULL DEFAULT 0
);

CREATE TABLE baggage_blocked_fields (
    field           text PRIMARY KEY,
    observed_value  text NOT NULL,
    reason          text NOT NULL,
    sort_order      integer NOT NULL DEFAULT 0
);

CREATE TABLE baggage_requests (
    trace_id            text PRIMARY KEY REFERENCES traces(trace_id) ON DELETE CASCADE,
    request_label       text NOT NULL,
    ticket_ref          text,
    conversation_id     text,
    workflow            text,
    propagation_status  text NOT NULL CHECK (propagation_status IN ('complete','attention')),
    fields_present      integer NOT NULL,
    fields_expected     integer NOT NULL,
    header_bytes        integer NOT NULL,
    outcome             text NOT NULL,
    started_at          timestamptz NOT NULL,
    missing_count       integer NOT NULL DEFAULT 0,
    changed_count       integer NOT NULL DEFAULT 0
);

CREATE TABLE baggage_hops (
    id              serial PRIMARY KEY,
    trace_id        text NOT NULL REFERENCES baggage_requests(trace_id) ON DELETE CASCADE,
    hop_no          integer NOT NULL,
    service_name    text NOT NULL,
    operation       text NOT NULL,
    trace_offset_ms integer NOT NULL,
    fields_present  integer NOT NULL,
    fields_expected integer NOT NULL,
    header_bytes    integer NOT NULL,
    result          text NOT NULL,                  -- Created | Injected | Extracted | Forwarded | Read
    traceparent     text,
    baggage_value   text,
    UNIQUE (trace_id, hop_no)
);

CREATE TABLE baggage_hop_fields (
    id          serial PRIMARY KEY,
    trace_id    text NOT NULL,
    hop_no      integer NOT NULL,
    key         text NOT NULL,
    value       text,
    status      text NOT NULL DEFAULT 'Present',
    sort_order  integer NOT NULL DEFAULT 0
);
CREATE INDEX ON baggage_hop_fields (trace_id, hop_no);

-- ---------------------------------------------------------------------------
-- 10 · TELEMETRY -- profiles
-- ---------------------------------------------------------------------------
CREATE TABLE profiles (
    id              serial PRIMARY KEY,
    service_name    text NOT NULL REFERENCES services(service_name),
    profile_type    text NOT NULL CHECK (profile_type IN ('cpu','allocations')),
    window_label    text NOT NULL DEFAULT 'last 30 min',
    sample_hz       integer NOT NULL DEFAULT 60,
    finding         text NOT NULL DEFAULT '',
    UNIQUE (service_name, profile_type)
);

CREATE TABLE profile_frames (
    id          serial PRIMARY KEY,
    profile_id  integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    parent_id   integer REFERENCES profile_frames(id) ON DELETE CASCADE,
    function_name text NOT NULL,
    pct         numeric(5,1) NOT NULL,
    self_ms     integer,
    depth       integer NOT NULL DEFAULT 0,
    sort_order  integer NOT NULL DEFAULT 0
);
CREATE INDEX ON profile_frames (profile_id, depth);

CREATE TABLE profile_hot_functions (
    id          serial PRIMARY KEY,
    profile_id  integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    function_name text NOT NULL,
    pct         numeric(5,1) NOT NULL,
    total_ms    integer NOT NULL,
    sort_order  integer NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 11 · Topology, signal coverage, incidents, standards, diagnose workflow
-- ---------------------------------------------------------------------------
CREATE TABLE topology_hops (
    hop_no          integer PRIMARY KEY,
    service_name    text NOT NULL,
    display_name    text NOT NULL,
    operation       text NOT NULL,
    is_origin       boolean NOT NULL DEFAULT false,
    healthy_ms      integer,
    incident_ms     integer,
    is_telemetry_path boolean NOT NULL DEFAULT false
);

CREATE TABLE signal_coverage (
    signal      text PRIMARY KEY,                   -- traces | metrics | logs | baggage | profiles
    glyph       text NOT NULL,
    volume_text text NOT NULL,
    coverage_text text NOT NULL,
    description text NOT NULL DEFAULT '',
    route       text NOT NULL DEFAULT '',
    sort_order  integer NOT NULL DEFAULT 0
);

CREATE TABLE incidents (
    id          serial PRIMARY KEY,
    code        text NOT NULL UNIQUE,
    title       text NOT NULL,
    detail      text NOT NULL,
    severity    text NOT NULL DEFAULT 'SEV-2',
    started_at  timestamptz,
    resolved_at timestamptz,
    is_simulated boolean NOT NULL DEFAULT true
);

CREATE TABLE otel_requirements (
    code        text PRIMARY KEY,                   -- '01' .. '06'
    badge       text NOT NULL,                      -- 'API + SDK', 'traceparent', 'OTLP' ...
    title       text NOT NULL,
    body        text NOT NULL,
    is_required boolean NOT NULL DEFAULT true,
    is_met      boolean NOT NULL DEFAULT true,
    sort_order  integer NOT NULL DEFAULT 0
);

CREATE TABLE otel_checklist (
    code        text PRIMARY KEY,                   -- 'OTEL-01' .. 'OTEL-08'
    statement   text NOT NULL,
    is_passing  boolean NOT NULL DEFAULT true,
    sort_order  integer NOT NULL DEFAULT 0
);

CREATE TABLE collector_path_steps (
    step_no     integer PRIMARY KEY,
    code        text NOT NULL,
    title       text NOT NULL,
    detail      text NOT NULL
);

CREATE TABLE diagnose_steps (
    id          serial PRIMARY KEY,
    phase       text NOT NULL CHECK (phase IN ('symptom','diagnosis')),
    step_no     integer NOT NULL,
    title       text NOT NULL,
    body        text NOT NULL,
    route       text NOT NULL DEFAULT '',
    UNIQUE (phase, step_no)
);

-- The four pillars + five signals from the operating-model slide
CREATE TABLE operating_model (
    id          serial PRIMARY KEY,
    kind        text NOT NULL CHECK (kind IN ('pillar','signal','journey_stage','privacy','scale')),
    code        text NOT NULL,
    title       text NOT NULL,
    body        text NOT NULL DEFAULT '',
    sort_order  integer NOT NULL DEFAULT 0,
    UNIQUE (kind, code)
);

-- ---------------------------------------------------------------------------
-- 12 · Operational: ETL runs and OTLP ingest audit
-- ---------------------------------------------------------------------------
CREATE TABLE etl_runs (
    id              serial PRIMARY KEY,
    source          text NOT NULL,
    detail          text NOT NULL DEFAULT '',
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    rows_loaded     integer,
    status          text NOT NULL DEFAULT 'running' CHECK (status IN ('running','success','failed')),
    error_message   text
);
CREATE INDEX ON etl_runs (started_at DESC);

-- Everything the OTLP receiver accepts lands here first, so live instrumentation
-- can arrive without a schema change and be promoted into spans/logs/metrics.
CREATE TABLE otlp_ingest (
    id          bigserial PRIMARY KEY,
    received_at timestamptz NOT NULL DEFAULT now(),
    signal      text NOT NULL CHECK (signal IN ('traces','metrics','logs')),
    payload     jsonb NOT NULL,
    promoted    boolean NOT NULL DEFAULT false
);
CREATE INDEX ON otlp_ingest (signal, received_at DESC);

-- ---------------------------------------------------------------------------
-- Views used by more than one panel
-- ---------------------------------------------------------------------------
CREATE VIEW bot_tickets AS
    SELECT * FROM tickets WHERE is_bot_raised;

CREATE VIEW journey_funnel AS
    SELECT stage_no, code, label, reached, pct_of_sample, lost_here, why, basis, basis_change
    FROM journey_stages ORDER BY stage_no;
