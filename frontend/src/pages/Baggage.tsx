/**
 * Baggage -- request-level business context, governed.
 *
 * Two moves, in this order: find a request in the window, then follow that one
 * request's baggage hop by hop. The detailed view never combines values from
 * unrelated requests, which is the whole point of a request-scoped audit.
 */
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import HopChain, { type HopChainItem } from "../components/HopChain";
import {
  Async,
  DataTable,
  Empty,
  KpiTile,
  PageHead,
  Panel,
  SectionRule,
} from "../components/primitives";
import { fmtDuration, fmtInt, fmtTime, usePanel, type Kpi, shortId } from "../lib/api";

interface BaggageSummary {
  requests_inspected: number;
  complete_propagation: number;
  complete_pct: number;
  needs_attention: number;
  header_p95_bytes: number;
  spec: string;
}

interface BaggageRequest {
  trace_id: string;
  conversation_id: string | null;
  ticket_ref: string | null;
  request_label: string;
  workflow: string | null;
  propagation_status: string;
  fields_present: number;
  fields_expected: number;
  header_bytes: number;
  outcome: string;
  started_at: string;
  missing_count?: number;
  changed_count?: number;
}

interface BaggageRequestList {
  items: BaggageRequest[];
  workflows: string[];
  total: number;
}

interface BaggageHop {
  hop_no: number;
  service_name: string;
  display_name: string;
  operation: string;
  trace_offset_ms: number;
  fields_present: number;
  fields_expected: number;
  header_bytes: number;
  result: string;
  traceparent: string | null;
  baggage_value: string | null;
}

interface HopField {
  key: string;
  value: string | null;
  purpose: string;
  status: string;
}

interface BlockedField {
  field: string;
  observed_value: string;
  reason: string;
}

interface BaggageDetail {
  request: BaggageRequest;
  hops: BaggageHop[];
  hop_fields: Record<string, HopField[]>;
  blocked: BlockedField[];
}

const PROPAGATIONS = ["all", "complete", "attention"];
const WORKFLOW_FALLBACK = [
  "product_return",
  "billing_inquiry",
  "product_inquiry",
  "itinerary_document",
  "booking_change",
];

const pretty = (value: string) => value.replace(/_/g, " ");
const title = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

/** Hop 1 creates the header, so the chain calls it Origin; the audit says Created. */
const roleOf = (hop: BaggageHop) => (hop.result === "Created" ? "Origin" : hop.result);

function summaryTiles(d: BaggageSummary): Kpi[] {
  const blank = {
    delta_text: null,
    delta_direction: null,
    delta_is_good: null,
    panel_id: "",
    footnote: "",
  } as const;
  return [
    {
      ...blank,
      code: "inspected",
      label: "Requests inspected",
      value_text: fmtInt(d.requests_inspected),
      unit: "",
      sub_text: "with trace data",
      tone: "neutral",
    },
    {
      ...blank,
      code: "complete",
      label: "Complete propagation",
      value_text: fmtInt(d.complete_propagation),
      unit: "",
      sub_text: `${d.complete_pct}% of requests`,
      tone: "good",
    },
    {
      ...blank,
      code: "attention",
      label: "Needs attention",
      value_text: fmtInt(d.needs_attention),
      unit: "",
      sub_text: "missing or changed fields",
      tone: d.needs_attention > 0 ? "warning" : "good",
    },
    {
      ...blank,
      code: "p95",
      label: "Header size p95",
      value_text: fmtInt(d.header_p95_bytes),
      unit: "B",
      sub_text: "well below limits",
      tone: "neutral",
    },
  ];
}

export default function Baggage() {
  const [params, setParams] = useSearchParams();
  const traceParam = params.get("trace");

  const [workflow, setWorkflow] = useState("all");
  const [propagation, setPropagation] = useState("all");
  const [hopNo, setHopNo] = useState<number | null>(null);

  const summary = usePanel<BaggageSummary>("/api/baggage/summary");
  const list = usePanel<BaggageRequestList>("/api/baggage/requests", {
    workflow: workflow === "all" ? undefined : workflow,
    propagation: propagation === "all" ? undefined : propagation,
  });

  const selectedTrace = traceParam ?? list.data?.items[0]?.trace_id ?? null;
  const detail = usePanel<BaggageDetail>(
    `/api/baggage/requests/${selectedTrace ?? "none"}`,
    undefined,
    { enabled: selectedTrace !== null },
  );

  const workflowOptions = ["all", ...(list.data?.workflows ?? WORKFLOW_FALLBACK)];

  const selectTrace = (traceId: string) => {
    const next = new URLSearchParams(params);
    next.set("trace", traceId);
    setParams(next, { replace: true });
    setHopNo(null);
  };

  return (
    <>
      <PageHead
        eyebrow="Technical view · Baggage"
        title="Request-level context"
        lede="Find a request, then inspect its baggage. The time window finds candidate requests. The detailed view follows baggage on one selected trace without combining unrelated values."
      />

      <div className="row">
        <span className="pill pill--spec">W3C Baggage</span>
        {summary.data?.spec ? <span className="pill">{summary.data.spec}</span> : null}
      </div>

      <SectionRule title="Propagation health" note="Selected window" />

      <Async query={summary} skeletonRows={4}>
        {(d) => (
          <div className="grid grid--kpi">
            {summaryTiles(d).map((kpi) => (
              <KpiTile kpi={kpi} key={kpi.code} />
            ))}
          </div>
        )}
      </Async>

      <SectionRule title="Find a request" note="Select a row to audit it" />

      <Panel
        title="Request discovery"
        question="Candidate requests in the window. Baggage is shown as fields present out of fields expected, and the size of the header value."
        readout={
          list.data
            ? `Showing ${fmtInt(list.data.items.length)} representative requests from ${fmtInt(
                list.data.total,
              )} in the selected window · detailed baggage remains request-scoped.`
            : undefined
        }
      >
        <div className="stack">
          <div className="row">
            <span className="control__label">Workflow</span>
            <div className="seg" role="group" aria-label="Filter by workflow">
              {workflowOptions.map((w) => (
                <button
                  key={w}
                  type="button"
                  className={workflow === w ? "is-active" : undefined}
                  aria-pressed={workflow === w}
                  onClick={() => setWorkflow(w)}
                >
                  {pretty(w)}
                </button>
              ))}
            </div>
            <span className="control__label">Propagation</span>
            <div className="seg" role="group" aria-label="Filter by propagation status">
              {PROPAGATIONS.map((p) => (
                <button
                  key={p}
                  type="button"
                  className={propagation === p ? "is-active" : undefined}
                  aria-pressed={propagation === p}
                  onClick={() => setPropagation(p)}
                >
                  {title(p)}
                </button>
              ))}
            </div>
          </div>

          <Async query={list} skeletonRows={7}>
            {(d) => (
              <DataTable
                columns={[
                  "Started",
                  "Request",
                  "Ticket",
                  "Trace / conversation",
                  "Workflow",
                  "Baggage",
                  "Request outcome",
                ]}
                rows={d.items.map((r) => [
                  <span className="mono">{fmtTime(r.started_at)}</span>,
                  r.request_label,
                  r.ticket_ref ?? "No ticket created",
                  <>
                    <span className="trace-id">{shortId(r.trace_id)}</span>
                    <div className="span-row__op">{r.conversation_id ?? "—"}</div>
                  </>,
                  r.workflow ? <span className="tag">{r.workflow}</span> : "—",
                  <span className="mono">
                    {title(r.propagation_status)} {r.fields_present}/{r.fields_expected} ·{" "}
                    {r.header_bytes} B
                  </span>,
                  title(r.outcome),
                ])}
                onRowClick={(i) => {
                  const row = d.items[i];
                  if (row) selectTrace(row.trace_id);
                }}
                selectedIndex={d.items.findIndex((r) => r.trace_id === selectedTrace)}
              />
            )}
          </Async>
        </div>
      </Panel>

      <SectionRule
        title="Selected request"
        note={selectedTrace ? `Trace ${shortId(selectedTrace)}` : "No request selected"}
      />

      {selectedTrace === null ? (
        <Panel title="Selected request" question="Choose a row above to audit one request.">
          <Empty>No request selected.</Empty>
        </Panel>
      ) : (
        <Async query={detail} skeletonRows={8}>
          {(d) => {
            const hops = d.hops ?? [];
            const activeHop =
              hops.find((h) => h.hop_no === hopNo) ??
              hops.find((h) => h.result === "Extracted") ??
              hops[0];
            const hopItems: HopChainItem[] = hops.map((h) => ({
              hop_no: h.hop_no,
              title: h.display_name || h.service_name,
              subtitle: `${h.operation} · ${roleOf(h)}`,
              meta: `${h.fields_present}/${h.fields_expected} · ${h.header_bytes} B`,
              is_degraded: h.fields_present < h.fields_expected,
            }));
            const fields = activeHop ? (d.hop_fields?.[String(activeHop.hop_no)] ?? []) : [];
            const missing = d.request.missing_count;
            const changed = d.request.changed_count;

            return (
              <div className="stack">
                <Panel
                  title={`${d.request.request_label} · started ${fmtTime(d.request.started_at)}`}
                  question="One request, one audit. Every figure below belongs to this trace alone."
                  actions={
                    <Link className="btn" to={`/traces/${d.request.trace_id}`}>
                      ⑂ Open trace waterfall
                    </Link>
                  }
                >
                  <div className="callouts">
                    <div className="callout">
                      <div className="callout__label">Trace</div>
                      <div className="callout__body">
                        <span className="trace-id">{shortId(d.request.trace_id)}</span>
                      </div>
                    </div>
                    <div className="callout">
                      <div className="callout__label">Conversation</div>
                      <div className="callout__body mono">
                        {d.request.conversation_id ?? "—"}
                      </div>
                    </div>
                    <div className="callout">
                      <div className="callout__label">Ticket</div>
                      <div className="callout__body mono">
                        {d.request.ticket_ref ?? "No ticket created"}
                      </div>
                    </div>
                    <div className="callout">
                      <div className="callout__label">Workflow</div>
                      <div className="callout__body mono">
                        {d.request.workflow ?? "—"}
                      </div>
                    </div>
                    <div className="callout">
                      <div className="callout__label">Outcome</div>
                      <div className="callout__body">{title(d.request.outcome)}</div>
                    </div>
                    <div
                      className={`callout ${
                        d.request.fields_present < d.request.fields_expected
                          ? "callout--warning"
                          : "callout--good"
                      }`}
                    >
                      <div className="callout__label">Baggage fields</div>
                      <div className="callout__value">
                        {d.request.fields_present} / {d.request.fields_expected}
                      </div>
                    </div>
                    <div className="callout">
                      <div className="callout__label">Header value size</div>
                      <div className="callout__value">{d.request.header_bytes} B</div>
                    </div>
                  </div>
                </Panel>

                <Panel
                  title="Hops on this request"
                  question="Select a hop to see the header it received and the values it read."
                >
                  {hops.length === 0 ? (
                    <Empty>No hops recorded for this request.</Empty>
                  ) : (
                    <HopChain
                      hops={hopItems}
                      selectedHopNo={activeHop?.hop_no ?? null}
                      onSelect={setHopNo}
                      label="Baggage propagation hops"
                    />
                  )}
                </Panel>

                {activeHop ? (
                  <div className="grid grid--split">
                    <Panel
                      title={`HTTP request at hop ${activeHop.hop_no} · ${roleOf(activeHop)}`}
                      question={`${activeHop.display_name || activeHop.service_name} — ${
                        activeHop.operation
                      }`}
                    >
                      <pre className="code">
{`traceparent: ${activeHop.traceparent ?? "— not present —"}
baggage (${activeHop.header_bytes}-byte value): ${activeHop.baggage_value ?? "— not present —"}`}
                      </pre>
                    </Panel>

                    <Panel
                      title={`Hop ${activeHop.hop_no} snapshot`}
                      question="Values received by this service."
                      basis={`${activeHop.fields_present} / ${activeHop.fields_expected} present`}
                    >
                      <DataTable
                        columns={["Baggage key", "Value", "Purpose", "Status"]}
                        rows={fields.map((f) => [
                          <span className="mono">{f.key}</span>,
                          <span className="mono">{f.value ?? "—"}</span>,
                          f.purpose,
                          <span className="tag">{f.status}</span>,
                        ])}
                      />
                    </Panel>
                  </div>
                ) : null}

                <Panel
                  title="Origin filter evidence"
                  question="Fields blocked before propagation."
                  basis={`${fmtInt((d.blocked ?? []).length)} blocked`}
                  readout="These values never entered the outgoing baggage header."
                >
                  <DataTable
                    columns={["Blocked field", "Observed value", "Enforcement reason"]}
                    rows={(d.blocked ?? []).map((b) => [
                      <span className="mono">{b.field}</span>,
                      <span className="mono">{b.observed_value}</span>,
                      b.reason,
                    ])}
                  />
                </Panel>

                <Panel
                  title={`Propagation audit · trace ${shortId(d.request.trace_id)}`}
                  question="What every hop actually received. This audit belongs only to the selected request — choose another row above to replace it."
                  basis={
                    missing === undefined && changed === undefined
                      ? undefined
                      : `${fmtInt(missing ?? 0)} missing · ${fmtInt(changed ?? 0)} changed`
                  }
                >
                  <DataTable
                    columns={[
                      "Hop",
                      "Service",
                      "Operation",
                      "Trace offset",
                      "Fields",
                      "Header size",
                      "Result",
                    ]}
                    numeric={[0, 3, 4, 5]}
                    rows={hops.map((h) => [
                      h.hop_no,
                      h.display_name || h.service_name,
                      h.operation,
                      h.trace_offset_ms === 0 ? "0ms" : fmtDuration(h.trace_offset_ms),
                      `${h.fields_present} / ${h.fields_expected}`,
                      `${h.header_bytes} B`,
                      <span className="tag">{h.result}</span>,
                    ])}
                  />
                </Panel>
              </div>
            );
          }}
        </Async>
      )}
    </>
  );
}
