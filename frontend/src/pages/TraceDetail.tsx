/**
 * One request trace, hop by hop.
 *
 * The waterfall is the evidence; the two attribute tables are the contract.
 * Semantic conventions on the left prove the instrumentation is standard, and the
 * PII-safe business correlation on the right proves the same trace can answer a
 * business question without carrying a guest's details.
 */
import { Link, useParams } from "react-router-dom";
import Waterfall from "../components/Waterfall";
import { Async, DataTable, PageHead, Panel, SectionRule } from "../components/primitives";
import { fmtDuration, fmtInt, usePanel, type SpanRow, shortId } from "../lib/api";

interface AttributeRow {
  key: string;
  value: string;
}

interface TraceDetailResponse {
  trace_id: string;
  label: string;
  status: string;
  duration_ms: number;
  span_count: number;
  axis_ticks_ms: number[];
  spans: SpanRow[];
  attributes: { semconv: AttributeRow[]; business: AttributeRow[] };
  conversation_id?: string | null;
  ticket_ref?: string | null;
  workflow?: string | null;
  outcome?: string | null;
}

const CORRELATION_KEYS = [
  "osw.conversation.id",
  "osw.ticket.id",
  "osw.inquiry.type",
  "osw.cruise.line",
  "osw.request.outcome",
  "trace_id",
];

/** Business attributes in the reference order, with anything extra appended. */
function orderCorrelation(rows: AttributeRow[]): AttributeRow[] {
  const known = CORRELATION_KEYS.map((key) => rows.find((r) => r.key === key)).filter(
    (r): r is AttributeRow => r !== undefined,
  );
  const rest = rows.filter((r) => !CORRELATION_KEYS.includes(r.key));
  return [...known, ...rest];
}

export default function TraceDetail() {
  const { traceId = "" } = useParams();
  const trace = usePanel<TraceDetailResponse>(`/api/traces/${traceId}`);

  const business = trace.data?.attributes?.business ?? [];
  const conversationId =
    trace.data?.conversation_id ??
    business.find((r) => r.key === "osw.conversation.id")?.value ??
    null;

  return (
    <>
      <PageHead
        eyebrow="Technical view · Traces"
        title={`Request trace ${shortId(traceId).toUpperCase()}`}
        lede={
          conversationId
            ? `Inside ${conversationId} — the guest's chat session. One trace is one end-to-end request; every span below is one operation inside it.`
            : "One trace is one end-to-end request; every span below is one operation inside it."
        }
      />

      <div className="row">
        <Link className="btn" to="/traces">
          ← All traces
        </Link>
        <Link className="btn" to={`/logs?trace_id=${traceId}`}>
          ≡ Logs for this trace
        </Link>
        <Link className="btn" to={`/baggage?trace=${traceId}`}>
          ◇ Baggage audit for this trace
        </Link>
        {conversationId ? (
          <span className="pill">
            Conversation <b>{conversationId}</b>
          </span>
        ) : null}
      </div>

      <SectionRule title="Span waterfall" note={`Trace ${shortId(traceId)}`} />

      <Panel
        title={
          trace.data
            ? `${trace.data.label} · ${fmtDuration(trace.data.duration_ms)}`
            : "Request trace"
        }
        question="Each bar is a span, positioned and sized against the root span's own duration."
        actions={
          trace.data ? (
            <span className={`pill ${trace.data.status === "OK" ? "pill--live" : ""}`}>
              {trace.data.status}
            </span>
          ) : undefined
        }
      >
        <Async query={trace} skeletonRows={8}>
          {(d) => (
            <>
              <Waterfall
                spans={d.spans}
                axisTicks={d.axis_ticks_ms}
                rootDurationMs={d.duration_ms}
              />
              <div className="legend">
                <span className="legend__key">
                  <span
                    className="legend__swatch"
                    style={{ background: "var(--accent-ink)" }}
                  />
                  Trace — entire {fmtDuration(d.duration_ms)} request
                </span>
                <span className="legend__key">
                  <span className="legend__swatch" style={{ background: "var(--accent)" }} />
                  Spans — {fmtInt(d.span_count)} operations with trace-specific timings
                </span>
                <span className="legend__key">
                  <span className="legend__swatch" style={{ background: "var(--serious)" }} />
                  Slow span
                </span>
                <span className="legend__key">
                  <span className="legend__swatch" style={{ background: "var(--critical)" }} />
                  Error span
                </span>
              </div>
            </>
          )}
        </Async>
      </Panel>

      <SectionRule
        title="What the trace carries"
        note="Standard attributes · PII-safe business context"
      />

      <div className="grid grid--split">
        <Panel
          title="Root span attributes · semantic conventions"
          question="Standard HTTP, service and deployment attributes — nothing OSW-specific."
        >
          <Async query={trace} skeletonRows={5}>
            {(d) => (
              <DataTable
                columns={["Attribute", "Value"]}
                rows={(d.attributes?.semconv ?? []).map((row) => [
                  <span className="mono">{row.key}</span>,
                  <span className="mono">{row.value}</span>,
                ])}
              />
            )}
          </Async>
        </Panel>

        <Panel
          title="Trace-to-business correlation · PII-safe"
          question="Identifiers and categories only. No guest name, email, booking number or transcript."
          readout={
            <>
              These are the keys that let a business question reach a technical answer.
              Identifiers belong in traces and logs — <b>never</b> as metric labels.
            </>
          }
        >
          <Async query={trace} skeletonRows={6}>
            {(d) => (
              <DataTable
                columns={["Attribute", "Value"]}
                rows={orderCorrelation(d.attributes?.business ?? []).map((row) => [
                  <span className="mono">{row.key}</span>,
                  row.key === "trace_id" || row.key === "osw.conversation.id" ? (
                    <span className="trace-id">{row.value}</span>
                  ) : (
                    <span className="mono">{row.value}</span>
                  ),
                ])}
              />
            )}
          </Async>
        </Panel>
      </div>
    </>
  );
}
