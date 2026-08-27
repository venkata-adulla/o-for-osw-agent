/**
 * Structured logs.
 *
 * A log line here is not prose: it is an event with trace context. That is what
 * makes the CORRELATION link below possible -- one click from the message a human
 * can read to the waterfall that produced it.
 */
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Async, DataTable, PageHead, Panel, SectionRule } from "../components/primitives";
import { fmtInt, fmtTime, usePanel, type LogRecord, shortId } from "../lib/api";

interface LogListResponse {
  items: LogRecord[];
  total: number;
  limit: number;
  offset: number;
  window: string;
}

const PAGE_SIZE = 7;
const FILTERS = ["ALL", "ERROR", "WARN", "INFO"] as const;
type Filter = (typeof FILTERS)[number];

/** fmtTime to the second, plus the milliseconds a log record actually carries. */
function clock(iso: string): string {
  const ms = new Date(iso).getMilliseconds();
  return `${fmtTime(iso)}.${String(ms).padStart(3, "0")}`;
}

/** The record as the exported JSON payload, in OTel key order. */
function asJson(record: LogRecord): string {
  const base: Record<string, unknown> = {
    timestamp: record.observed_at,
    severity_text: record.severity_text,
    "service.name": record.service_name,
    "event.name": record.event_name,
    body: record.body,
    trace_id: record.trace_id,
    span_id: record.span_id,
    "error.type": record.error_type,
    ...(record.attributes ?? {}),
  };
  const present = Object.fromEntries(
    Object.entries(base).filter(([, value]) => value !== null && value !== undefined),
  );
  return JSON.stringify(present, null, 2);
}

export default function Logs() {
  const [params, setParams] = useSearchParams();
  const traceFilter = params.get("trace_id") ?? "";

  const [severity, setSeverity] = useState<Filter>("ALL");
  const [page, setPage] = useState(0);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const list = usePanel<LogListResponse>("/api/logs", {
    severity: severity === "ALL" ? undefined : severity,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    trace_id: traceFilter || undefined,
  });

  const detail = usePanel<LogRecord>(`/api/logs/${expandedId ?? 0}`, undefined, {
    enabled: expandedId !== null,
  });

  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const shown = list.data?.items.length ?? 0;

  const pick = (next: Filter) => {
    setSeverity(next);
    setPage(0);
    setExpandedId(null);
  };

  const clearTrace = () => {
    const next = new URLSearchParams(params);
    next.delete("trace_id");
    setParams(next, { replace: true });
    setPage(0);
    setExpandedId(null);
  };

  return (
    <>
      <PageHead
        eyebrow="Technical view · Logs"
        title="Structured logs"
        lede="Events with trace context. Every record is queryable and links back to the exact request that produced it."
      />

      <SectionRule
        title="Log records"
        note={list.data ? `${fmtInt(total)} / ${list.data.window}` : "—"}
      />

      <Panel
        title="Structured log records"
        question="Filter by severity, then open a row for the full record."
        basis={`Showing ${fmtInt(shown)} of ${fmtInt(total)} log records · page ${page + 1} of ${pages}`}
        readout="This demo loads 7 representative records per page. A production query retrieves only the requested page — not every record at once."
      >
        <div className="stack">
          <div className="row">
            <span className="control__label">Severity</span>
            <div className="seg" role="group" aria-label="Filter by severity">
              {FILTERS.map((f) => (
                <button
                  key={f}
                  type="button"
                  className={severity === f ? "is-active" : undefined}
                  aria-pressed={severity === f}
                  onClick={() => pick(f)}
                >
                  {f}
                </button>
              ))}
            </div>
            {traceFilter ? (
              <>
                <span className="pill pill--spec">
                  trace <b className="mono">{shortId(traceFilter)}</b>
                </span>
                <button type="button" className="btn" onClick={clearTrace}>
                  Clear trace filter
                </button>
                <Link className="btn" to={`/traces/${traceFilter}`}>
                  ⑂ Open trace waterfall
                </Link>
              </>
            ) : null}
          </div>

          <Async query={list} skeletonRows={7}>
            {(d) => (
              <DataTable
                columns={["Time", "Level", "Service / event", "Message", "Trace"]}
                rows={d.items.map((r) => [
                  <span className="mono">{clock(r.observed_at)}</span>,
                  <span className={`sev sev--${r.severity_text}`}>{r.severity_text}</span>,
                  <>
                    <div className="span-row__service">{r.service_name}</div>
                    <div className="span-row__op">{r.event_name}</div>
                  </>,
                  r.body,
                  r.trace_id ? (
                    <span className="trace-id">{shortId(r.trace_id)}</span>
                  ) : (
                    "—"
                  ),
                ])}
                onRowClick={(i) => {
                  const row = d.items[i];
                  if (!row) return;
                  setExpandedId((current) => (current === row.id ? null : row.id));
                }}
                selectedIndex={d.items.findIndex((r) => r.id === expandedId)}
              />
            )}
          </Async>

          <div className="row">
            <button
              type="button"
              className="btn"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              aria-label="Previous page of log records"
            >
              ← Previous
            </button>
            <span className="control__label">
              Page {page + 1} of {pages}
            </span>
            <button
              type="button"
              className="btn"
              onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}
              disabled={page >= pages - 1}
              aria-label="Next page of log records"
            >
              Next →
            </button>
          </div>
        </div>
      </Panel>

      {expandedId !== null ? (
        <>
          <SectionRule title="Expanded record" note="The exported payload, verbatim" />
          <Panel
            title="Log record"
            question="This is the structured payload as it leaves the service — nothing is added for the screen."
            actions={
              <button type="button" className="btn" onClick={() => setExpandedId(null)}>
                Close
              </button>
            }
          >
            <Async query={detail} skeletonRows={6}>
              {(d) => (
                <>
                  <pre className="code">{asJson(d)}</pre>

                  <div className="callouts">
                    <div className="callout callout--good">
                      <div className="callout__label">Correlation</div>
                      <div className="callout__body">
                        {d.trace_id ? (
                          <Link to={`/traces/${d.trace_id}`}>Open trace waterfall →</Link>
                        ) : (
                          "This record carries no trace context — it is an infrastructure event, not a guest request."
                        )}
                      </div>
                    </div>
                    <div className="callout">
                      <div className="callout__label">Trace id</div>
                      <div className="callout__body">
                        <span className="trace-id">{d.trace_id ?? "—"}</span>
                      </div>
                    </div>
                    <div className="callout">
                      <div className="callout__label">Span id</div>
                      <div className="callout__body">
                        <span className="trace-id">{d.span_id ?? "—"}</span>
                      </div>
                    </div>
                  </div>

                  <div className="note note--info">
                    <span className="note__glyph" aria-hidden="true">
                      i
                    </span>
                    <span>IDs belong in logs and traces — not metric labels.</span>
                  </div>
                </>
              )}
            </Async>
          </Panel>
        </>
      ) : null}
    </>
  );
}
