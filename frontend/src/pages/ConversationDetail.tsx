/**
 * One conversation — the session detail plus the transcript.
 *
 * PII arrives already tokenised as `#*#SENSITIVE-xxx#*#`. Those tokens are
 * rendered as a neutral [redacted] chip and are never resolved, joined or
 * reversed: the redaction happens upstream and this screen keeps it that way.
 */
import { Fragment } from "react";
import { Link, useParams } from "react-router-dom";
import { fmtDuration, fmtInt, fmtTime, usePanel, type Callout } from "../lib/api";
import { Async, Callouts, Empty, PageHead, Panel } from "../components/primitives";

interface ConversationCore {
  session_id: string;
  bot_id: string | null;
  channel: string | null;
  language: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  message_count: number | null;
  task_count: number | null;
  containment_type: string | null;
  session_status: string | null;
  ticket_id: number | null;
  inquiry_type: string | null;
  event_name: string | null;
}

interface MessageRow {
  turn_no: number | null;
  direction: "incoming" | "outgoing";
  body: string | null;
  task_name: string | null;
  created_at: string | null;
  is_template: boolean;
}

type DetailResponse = Partial<ConversationCore> & {
  conversation?: ConversationCore;
  messages?: MessageRow[];
  trace_ids?: string[];
};

/**
 * Split on the token but keep it, so the chip can replace it in place.
 *
 * The bot echoes a token back wrapped as `#*#SENSITIVE-xxx#*#` (with markdown
 * emphasis around it), but the guest's own turn is just the bare token --
 * `SENSITIVE-xxx`, no delimiters -- because Kore.ai substitutes the tokenised
 * placeholder for whatever the guest typed. Both forms are the same three
 * families (name, email, phone) and neither carries real PII, but only
 * catching the wrapped form left every guest-authored turn showing the raw
 * token next to the bot's redacted echo of that exact value.
 */
const SENSITIVE_SPLIT = /(#\*#(?:SENSITIVE|EMAIL|PHONE)-[^#]*#\*#|\b(?:SENSITIVE|EMAIL|PHONE)-[A-Za-z0-9]+\b)/g;
const isSensitiveToken = (part: string): boolean =>
  /^#\*#(?:SENSITIVE|EMAIL|PHONE)-[^#]*#\*#$/.test(part) ||
  /^(?:SENSITIVE|EMAIL|PHONE)-[A-Za-z0-9]+$/.test(part);

/** Renders a message body with tokenised PII replaced by a neutral chip. */
function Redacted({ body }: { body: string }) {
  const parts = body.split(SENSITIVE_SPLIT);
  return (
    <>
      {parts.map((part, i) =>
        isSensitiveToken(part) ? (
          <span className="tag" key={i} title="Redacted before this screen ever saw it">
            [redacted]
          </span>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

const callout = (
  code: string,
  label: string,
  value: string | number | null | undefined,
): Callout | null =>
  value === null || value === undefined || value === ""
    ? null
    : { code, label, value_text: String(value), body: "", tone: "neutral" };

export default function ConversationDetail() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const query = usePanel<DetailResponse>(`/api/conversations/${sessionId ?? ""}`, undefined, {
    enabled: Boolean(sessionId),
  });

  return (
    <>
      <PageHead
        eyebrow="Business view · population A"
        title={`Session ${sessionId ?? ""}`}
        lede="One guest chat, turn by turn — and the traces that carried it across the services."
      />

      <div className="row">
        <Link to="/conversations">← All conversations</Link>
      </div>

      <Panel title="Session detail" meta={query.data?.meta}>
        <Async query={query} skeletonRows={4}>
          {(data) => {
            const c: Partial<ConversationCore> = data.conversation ?? data;
            const items = [
              callout("channel", "Channel", c.channel),
              callout("started", "Started", c.started_at ? fmtTime(c.started_at) : null),
              callout("ended", "Ended", c.ended_at ? fmtTime(c.ended_at) : null),
              callout(
                "length",
                "Length",
                c.duration_seconds === null || c.duration_seconds === undefined
                  ? null
                  : fmtDuration(c.duration_seconds * 1000),
              ),
              callout(
                "messages",
                "Messages",
                c.message_count === null || c.message_count === undefined
                  ? null
                  : fmtInt(c.message_count),
              ),
              callout(
                "tasks",
                "Tasks",
                c.task_count === null || c.task_count === undefined ? null : fmtInt(c.task_count),
              ),
              callout("outcome", "Outcome", c.containment_type ?? c.session_status),
              callout("flow", "Flow", c.inquiry_type),
              callout("ticket", "Ticket", c.ticket_id),
              callout("event", "Event", c.event_name),
            ].filter((item): item is Callout => item !== null);

            const traces = data.trace_ids ?? [];

            return (
              <div className="stack">
                <Callouts items={items} />
                <div className="row">
                  <span className="panel__basis">Correlated traces</span>
                  {traces.length === 0 ? (
                    <span className="tag">no trace correlated to this session</span>
                  ) : (
                    traces.map((traceId) => (
                      <Link className="trace-id" to={`/traces/${traceId}`} key={traceId}>
                        {traceId} →
                      </Link>
                    ))
                  )}
                </div>
              </div>
            );
          }}
        </Async>
      </Panel>

      <Panel
        title="Transcript"
        question="What did the guest and the bot actually say?"
        basis="Guest messages are incoming · bot messages are outgoing · sensitive values are redacted upstream"
      >
        <Async query={query} skeletonRows={6}>
          {(data) => {
            const messages = data.messages ?? [];
            if (messages.length === 0) return <Empty>No transcript held for this session.</Empty>;
            return (
              <div className="stack">
                {messages.map((message, i) => {
                  const incoming = message.direction === "incoming";
                  return (
                    <div
                      className={`note ${incoming ? "note--thin" : "note--info"}`}
                      key={`${message.turn_no ?? i}-${i}`}
                    >
                      <span className="note__glyph" aria-hidden="true">
                        {incoming ? "◀" : "▶"}
                      </span>
                      <div>
                        <div className="row">
                          <span className="funnel__name">{incoming ? "Guest" : "Bot"}</span>
                          {message.turn_no !== null && message.turn_no !== undefined ? (
                            <span className="mono">turn {fmtInt(message.turn_no)}</span>
                          ) : null}
                          {message.created_at ? (
                            <span className="mono">{fmtTime(message.created_at)}</span>
                          ) : null}
                          {message.task_name ? <span className="tag">{message.task_name}</span> : null}
                          {message.is_template ? <span className="tag">template</span> : null}
                        </div>
                        <div>
                          {message.body ? <Redacted body={message.body} /> : <span>—</span>}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          }}
        </Async>
      </Panel>
    </>
  );
}
