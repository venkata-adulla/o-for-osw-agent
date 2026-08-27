/**
 * Traces -- the conversation -> trace -> span model, then the traces themselves.
 *
 * The page teaches the model before it shows the data: a conversation contains
 * request traces, and a request trace contains spans. Everything below reads as
 * an instance of that one sentence.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Async, DataTable, PageHead, Panel, SectionRule } from "../components/primitives";
import { fmtDuration, fmtInt, fmtTime, usePanel, type TraceListItem, shortId } from "../lib/api";

interface TraceModelCard {
  code?: string;
  step_no?: number;
  title: string;
  body?: string;
  relation?: string;
}

interface TraceModel {
  headline?: string;
  subtitle?: string;
  body?: string;
  coverage_pct?: number;
  items?: TraceModelCard[];
  cards?: TraceModelCard[];
}

interface TraceListResponse {
  items: TraceListItem[];
  coverage_pct?: number;
}

interface ConversationTrace {
  trace_id: string;
  label: string;
  duration_ms: number;
  workflow?: string | null;
  outcome?: string | null;
}

interface TelemetryConversation {
  conversation_id: string;
  guest_ref: string | null;
  channel: string | null;
  started_at: string | null;
  status: string;
  summary: string;
  trace_count: number;
  ticket_count: number;
  traces: ConversationTrace[];
}

/** Used only when `/api/traces/model` returns no rows of its own. */
const MODEL_FALLBACK: TraceModelCard[] = [
  { title: "Conversation", body: "The complete guest chat", relation: "CONTAINS" },
  { title: "Request trace", body: "One end-to-end outcome", relation: "CONTAINS" },
  { title: "Spans", body: "Individual system operations" },
];

const MODEL_BODY =
  "One conversation is the guest's chat session. Each request inside it creates a trace, " +
  "and each technical operation inside that trace is a span.";

const WORKFLOWS = [
  "all",
  "product_return",
  "billing_inquiry",
  "product_inquiry",
  "itinerary_document",
  "booking_change",
];

const OUTCOMES = ["all", "success", "error", "abandoned", "blocked"];

const pretty = (value: string) => value.replace(/_/g, " ");

export default function Traces() {
  const navigate = useNavigate();
  const [workflow, setWorkflow] = useState("all");
  const [outcome, setOutcome] = useState("all");

  const model = usePanel<TraceModel>("/api/traces/model");
  const list = usePanel<TraceListResponse>("/api/traces", {
    limit: 5,
    workflow: workflow === "all" ? undefined : workflow,
    outcome: outcome === "all" ? undefined : outcome,
  });

  const conversationId =
    list.data?.items.find((t) => t.conversation_id)?.conversation_id ?? "conv_8a2f";
  const conversation = usePanel<TelemetryConversation>(
    `/api/traces/conversations/${conversationId}`,
  );

  const coverage = model.data?.coverage_pct ?? list.data?.coverage_pct ?? null;

  return (
    <>
      <PageHead
        eyebrow="Technical view · Traces"
        title="Conversations → traces → spans"
        lede="Follow the guest, then inspect the work. Every request a guest makes becomes one trace, and every operation inside it becomes a span — so a business outcome and the technical work behind it share one context."
      />

      <Panel
        title={model.data?.headline ?? "Conversations → traces → spans"}
        question={model.data?.subtitle ?? "Follow the guest, then inspect the work"}
        readout={model.data?.body ?? MODEL_BODY}
      >
        <Async query={model} skeletonRows={3}>
          {(d) => {
            const cards = d.items ?? d.cards ?? MODEL_FALLBACK;
            return (
              <>
                <div className="callouts">
                  <div className="callout callout--good">
                    <div className="callout__label">Trace coverage</div>
                    <div className="callout__value">
                      {coverage === null ? "—" : `${coverage}%`}
                    </div>
                    <div className="callout__body">
                      Requests that produced a complete end-to-end trace.
                    </div>
                  </div>
                </div>

                <div className="grid grid--3">
                  {cards.map((card, i) => (
                    <div className="steps" key={card.code ?? `${card.title}-${i}`}>
                      <div className="step">
                        <span className="step__no">{card.step_no ?? i + 1}</span>
                        <div>
                          <div className="step__title">{card.title}</div>
                          <div className="step__body">{card.body}</div>
                          {i < cards.length - 1 ? (
                            <span className="tag">{card.relation ?? "CONTAINS"}</span>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            );
          }}
        </Async>
      </Panel>

      <SectionRule title="Selected conversation" note={conversationId} />

      <Panel
        title={`Guest session ${conversationId}`}
        question={conversation.data?.summary}
      >
        <Async query={conversation} skeletonRows={4}>
          {(d) => (
            <>
              <div className="callouts">
                <div className="callout callout--good">
                  <div className="callout__label">Status</div>
                  <div className="callout__body">{d.status}</div>
                </div>
                <div className="callout">
                  <div className="callout__label">Channel</div>
                  <div className="callout__body">{d.channel ?? "—"}</div>
                </div>
                <div className="callout">
                  <div className="callout__label">Started</div>
                  <div className="callout__body mono">
                    {d.started_at ? fmtTime(d.started_at) : "—"}
                  </div>
                </div>
                <div className="callout">
                  <div className="callout__label">Guest</div>
                  <div className="callout__body mono">{d.guest_ref ?? "—"}</div>
                </div>
                <div className="callout">
                  <div className="callout__label">Request traces</div>
                  <div className="callout__value">{fmtInt(d.trace_count)}</div>
                </div>
                <div className="callout">
                  <div className="callout__label">Tickets</div>
                  <div className="callout__value">{fmtInt(d.ticket_count)}</div>
                </div>
              </div>

              <div className="panel__basis">
                Contains — {fmtInt(d.traces.length)} request traces
              </div>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Trace</th>
                      <th>Request</th>
                      <th className="num">Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.traces.length === 0 ? (
                      <tr>
                        <td colSpan={3}>
                          <div className="empty">No request traces on this conversation.</div>
                        </td>
                      </tr>
                    ) : (
                      d.traces.map((t) => (
                        <tr key={t.trace_id}>
                          <td className="strong">
                            <Link className="trace-id" to={`/traces/${t.trace_id}`}>
                              {shortId(t.trace_id)}
                            </Link>
                          </td>
                          <td>{t.label}</td>
                          <td className="num">{fmtDuration(t.duration_ms)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Async>
      </Panel>

      <SectionRule title="Traces in this window" note="Select a row to open its waterfall" />

      <Panel
        title="Recent request traces"
        question="One row is one end-to-end request. Selecting it opens the span waterfall."
      >
        <div className="stack">
          <div className="row">
            <span className="control__label">Workflow</span>
            <div className="seg" role="group" aria-label="Filter by workflow">
              {WORKFLOWS.map((w) => (
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
            <span className="control__label">Outcome</span>
            <div className="seg" role="group" aria-label="Filter by outcome">
              {OUTCOMES.map((o) => (
                <button
                  key={o}
                  type="button"
                  className={outcome === o ? "is-active" : undefined}
                  aria-pressed={outcome === o}
                  onClick={() => setOutcome(o)}
                >
                  {pretty(o)}
                </button>
              ))}
            </div>
          </div>

          <Async query={list} skeletonRows={5}>
            {(d) => (
              <DataTable
                columns={["Trace", "Label", "Workflow", "Duration", "Conversation", "Outcome"]}
                numeric={[3]}
                rows={d.items.map((t) => [
                  <span className="trace-id">{shortId(t.trace_id)}</span>,
                  t.label,
                  t.workflow ? pretty(t.workflow) : "—",
                  fmtDuration(t.duration_ms),
                  <span className="mono">{t.conversation_id ?? "—"}</span>,
                  <span className="tag">{t.outcome}</span>,
                ])}
                onRowClick={(i) => {
                  const target = d.items[i];
                  if (target) navigate(`/traces/${target.trace_id}`);
                }}
              />
            )}
          </Async>
        </div>
      </Panel>
    </>
  );
}
