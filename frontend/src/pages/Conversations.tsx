/**
 * Conversations — the session page itself, filterable and paginated.
 *
 * This is population A: one capped API page. The count at the bottom is the
 * number of rows we hold, never a period total.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fmtDuration, fmtInt, usePanel } from "../lib/api";
import { Async, DataTable, PageHead, Panel } from "../components/primitives";

interface ConversationRow {
  session_id: string;
  channel: string | null;
  started_at: string | null;
  duration_seconds: number | null;
  message_count: number | null;
  containment_type: string | null;
  session_status: string | null;
  ticket_id: number | null;
  inquiry_type: string | null;
}

interface ConversationsResponse {
  items: ConversationRow[];
  total: number;
  limit: number;
  offset: number;
}

const CONTAINMENT: { value: string; label: string }[] = [
  { value: "", label: "All outcomes" },
  { value: "self_service", label: "Self service" },
  { value: "drop_off", label: "Drop off" },
  { value: "agent_transfer", label: "Agent transfer" },
];

const LIMITS = [25, 50, 100];

const stamp = (iso: string | null): string | null => {
  if (!iso) return null;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
};

export default function Conversations() {
  const [channel, setChannel] = useState("");
  const [containment, setContainment] = useState("");
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);

  const query = usePanel<ConversationsResponse>("/api/conversations", {
    limit,
    offset,
    channel: channel || undefined,
    containment_type: containment || undefined,
    q: search || undefined,
  });

  // Unfiltered page, used only to offer the channel values this extract holds.
  const facets = usePanel<ConversationsResponse>("/api/conversations", { limit: 100, offset: 0 });
  const channels = useMemo(() => {
    const seen = new Set<string>();
    for (const item of facets.data?.items ?? []) {
      if (item.channel) seen.add(item.channel);
    }
    if (channel) seen.add(channel);
    return Array.from(seen).sort();
  }, [facets.data, channel]);

  const total = query.data?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);

  const reset = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setOffset(0);
  };

  return (
    <>
      <PageHead
        eyebrow="Business view · population A"
        title="Conversations"
        lede="Every session in the extract. Open one to read the transcript and follow it into the trace behind it."
      />

      <Panel
        title="Sessions"
        question="Which conversation do you want to read?"
        meta={query.data?.meta}
        actions={
          <div className="row">
            <label className="control">
              <span className="control__label">Channel</span>
              <select
                className="control__value"
                value={channel}
                onChange={(e) => reset(setChannel)(e.target.value)}
                aria-label="Filter by channel"
              >
                <option value="">All channels</option>
                {channels.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>

            <label className="control">
              <span className="control__label">Containment</span>
              <select
                className="control__value"
                value={containment}
                onChange={(e) => reset(setContainment)(e.target.value)}
                aria-label="Filter by containment type"
              >
                {CONTAINMENT.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>

            <form
              className="row"
              onSubmit={(e) => {
                e.preventDefault();
                setSearch(draft.trim());
                setOffset(0);
              }}
            >
              <label className="control">
                <span className="control__label">Search</span>
                <input
                  className="control__value"
                  type="search"
                  value={draft}
                  placeholder="session, flow or channel"
                  onChange={(e) => setDraft(e.target.value)}
                  aria-label="Search conversations"
                />
              </label>
              <button type="submit" className="btn">
                Search
              </button>
              {search ? (
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    setDraft("");
                    setSearch("");
                    setOffset(0);
                  }}
                >
                  Clear
                </button>
              ) : null}
            </form>

            <div className="seg" role="group" aria-label="Rows per page">
              {LIMITS.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={limit === value ? "is-active" : ""}
                  aria-pressed={limit === value}
                  onClick={() => {
                    setLimit(value);
                    setOffset(0);
                  }}
                >
                  {value}
                </button>
              ))}
            </div>
          </div>
        }
      >
        <Async query={query} skeletonRows={8}>
          {(data) => (
            <div className="stack">
              <DataTable
                columns={[
                  "Session",
                  "Started",
                  "Channel",
                  "Length",
                  "Messages",
                  "Outcome",
                  "Flow",
                  "Ticket",
                ]}
                numeric={[4]}
                rows={(data.items ?? []).map((row) => [
                  <Link className="trace-id" to={`/conversations/${row.session_id}`} key={row.session_id}>
                    {row.session_id}
                  </Link>,
                  stamp(row.started_at),
                  row.channel,
                  row.duration_seconds === null || row.duration_seconds === undefined
                    ? null
                    : fmtDuration(row.duration_seconds * 1000),
                  row.message_count === null || row.message_count === undefined
                    ? null
                    : fmtInt(row.message_count),
                  row.containment_type ?? row.session_status,
                  row.inquiry_type,
                  row.ticket_id ? <span className="mono">{row.ticket_id}</span> : null,
                ])}
              />

              <div className="row">
                <span className="panel__basis">
                  Showing {fmtInt(from)}–{fmtInt(to)} of {fmtInt(data.total)} rows held
                </span>
                <span className="topbar__spacer" />
                <button
                  type="button"
                  className="btn"
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  disabled={offset === 0}
                >
                  ← Previous
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setOffset(offset + limit)}
                  disabled={offset + limit >= data.total}
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </Async>
      </Panel>
    </>
  );
}
