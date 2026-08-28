/**
 * Tickets & requests — what the bot actually put into the service queue, and
 * whether the two systems (Kore.ai sessions, Zendesk tickets) agree.
 *
 * The activity chart is the honest one: a NULL day is a day absent from that
 * extract, drawn as a gap, never as zero.
 */
import { fmtDate, fmtInt, usePanel, type Callout, type CountItem, type Kpi } from "../lib/api";
import {
  Async,
  BarList,
  Callouts,
  DataTable,
  KpiTile,
  Note,
  PageHead,
  Panel,
  SectionRule,
  TableToggle,
} from "../components/primitives";
import TrendChart from "../components/TrendChart";

/* ------------------------------------------------------------------ shapes */

interface SummaryResponse {
  total: number;
  bot_raised: number;
  requests_raised: number;
  requests_pct: number | null;
  still_waiting: { untouched: number; open: number; solved: number; note: string };
}

interface StatusResponse {
  items: { status: string; count: number; tone: string | null }[];
}

interface ActivityRow {
  day: string;
  conversations: number | null;
  bot_tickets: number | null;
  in_kore_extract: boolean;
  in_zendesk_extract: boolean;
}

interface CorrelationResponse {
  conversations: number;
  carry_ticket_number: number;
  backend_step_done: number;
  note: string;
}

interface BackendFailuresResponse {
  items: { tag: string; label: string; ticket_count: number; stage: string | null }[];
  affected: number;
  total: number;
}

interface RecentTicket {
  ticket_id: number;
  created_at: string | null;
  status: string | null;
  priority: string | null;
  cruise_line: string | null;
  ship_name: string | null;
  inquiry_type: string | null;
  sentiment: string | null;
  is_bot_raised: boolean;
}

/* ------------------------------------------------------------------ helpers */

const dash = (n: number | null | undefined): string => (n === null || n === undefined ? "—" : fmtInt(n));

const sum = (values: (number | null | undefined)[]): number =>
  values.reduce((acc: number, v) => acc + (v ?? 0), 0);

const tile = (
  code: string,
  label: string,
  value_text: string,
  sub_text: string,
  footnote: string,
  tone: Kpi["tone"] = "neutral",
  panel_id = "",
): Kpi => ({
  code,
  label,
  value_text,
  unit: "",
  sub_text,
  delta_text: null,
  delta_direction: null,
  delta_is_good: null,
  tone,
  panel_id,
  footnote,
});

const callout = (
  code: string,
  label: string,
  value_text: string,
  body: string,
  tone: Callout["tone"] = "neutral",
): Callout => ({ code, label, value_text, body, tone });

const AXIS_NOTE =
  "Kore page covers 13–18 Aug · Zendesk export covers 17–19 Aug · tickets are bot-raised only";

const TABLE_NOTE =
  "— means the day is absent from that extract, not that nothing happened. The review " +
  "sheets record traffic on 15, 16 and 19 Aug.";

/* ------------------------------------------------------------------ page */

export default function Tickets() {
  const summary = usePanel<SummaryResponse>("/api/tickets/summary");
  const status = usePanel<StatusResponse>("/api/tickets/status");
  const activity = usePanel<{ items: ActivityRow[] }>("/api/tickets/activity");
  const correlation = usePanel<CorrelationResponse>("/api/tickets/correlation");
  const failures = usePanel<BackendFailuresResponse>("/api/tickets/backend-failures");
  const recent = usePanel<{ items: RecentTicket[] }>("/api/tickets/recent", { limit: 50 });

  return (
    <>
      <PageHead
        eyebrow="Business view"
        title="Tickets & requests"
        lede="What the bot put into the service queue — and whether anyone has picked it up."
      />

      <Async query={summary} skeletonRows={2}>
        {(data) => (
          <div className="grid grid--kpi">
            <KpiTile
              kpi={tile(
                "total",
                "Tickets in extract",
                fmtInt(data.total),
                "one API page · 17–19 Aug",
                "Not a period total. Zendesk reports 345 tickets and we hold 100 of them.",
                "neutral",
              )}
            />
            <KpiTile
              kpi={tile(
                "bot_raised",
                "Bot-raised",
                fmtInt(data.bot_raised),
                "filtered from the page of 100",
                "Every panel on this screen uses these bot-raised tickets, and nothing else.",
                "neutral",
              )}
            />
            <KpiTile
              kpi={tile(
                "requests",
                "Requests raised",
                fmtInt(data.requests_raised),
                data.requests_pct === null || data.requests_pct === undefined
                  ? "— of conversations"
                  : `${data.requests_pct}% of conversations`,
                "Conversations that produced a Zendesk ticket, matched by ticket number.",
                "neutral",
              )}
            />
            <KpiTile
              kpi={tile(
                "waiting",
                "Still waiting",
                `${dash(data.still_waiting?.untouched)} of ${dash(data.bot_raised)}`,
                `Untouched · ${dash(data.still_waiting?.open)} open, ${dash(
                  data.still_waiting?.solved,
                )} solved`,
                data.still_waiting?.note ?? "",
                "critical",
              )}
            />
          </div>
        )}
      </Async>

      {/* ------------------------------------------------------------ status */}
      <SectionRule title="Where the queue stands" note="bot-raised only" />
      <div className="grid grid--split">
        <Panel
          title="Ticket status"
          question="Has anything been picked up?"
          meta={status.data?.meta}
        >
          <Async query={status} skeletonRows={4}>
            {(data) => {
              const items: CountItem[] = (data.items ?? []).map((i) => ({
                label: i.status,
                count: i.count,
                tone: i.tone,
              }));
              return <BarList items={items} colorMode="tone" />;
            }}
          </Async>
        </Panel>

        <Panel
          title="Conversation to ticket journey"
          question="Does the link between the two systems hold?"
          meta={correlation.data?.meta}
          // The API computes this note from whatever the ETL actually holds
          // (real ETL can load more than the reference's 100-session sample),
          // so it must come from the response rather than being quoted here —
          // a hardcoded number next to a live one is exactly the inconsistency
          // this product exists to avoid.
          readout={correlation.data?.note}
        >
          <Async query={correlation} skeletonRows={3}>
            {(data) => {
              const hasInfo = (data.meta?.notes ?? []).some((n) => n.severity === "info");
              return (
                <div className="stack">
                  <Callouts
                    items={[
                      callout(
                        "conversations",
                        "Conversations",
                        dash(data.conversations),
                        "the Kore.ai session page",
                      ),
                      callout(
                        "carry",
                        "Carry a ticket number",
                        dash(data.carry_ticket_number),
                        "TicketID written on the session",
                        "warning",
                      ),
                      callout(
                        "backend",
                        "Back-end step done",
                        dash(data.backend_step_done),
                        "every one succeeded",
                        "good",
                      ),
                    ]}
                  />
                  {data.note && !hasInfo ? (
                    <Note note={{ severity: "info", body: data.note }} />
                  ) : null}
                </div>
              );
            }}
          </Async>
        </Panel>
      </div>

      {/* ---------------------------------------------------------- activity */}
      <SectionRule title="Activity over time" note="two extracts, one axis" />
      <Panel
        title="Activity over time"
        question="Is use growing, flat or falling?"
        meta={activity.data?.meta}
        readout="Both lines are the bot now. On 18 Aug, 26 conversations produced 21 tickets — the one day the two systems can be compared, and they broadly agree. The tickets line runs one day later than the chats, which is the enrichment and intake lag."
      >
        <Async query={activity} skeletonRows={5}>
          {(data) => {
            const rows = data.items ?? [];
            const absent = rows
              .filter((r) => r.conversations === null && r.bot_tickets === null)
              .map((r) => fmtDate(r.day));
            const peakChats = rows.reduce<ActivityRow | null>(
              (best, r) =>
                r.conversations !== null && (best === null || (best.conversations ?? 0) < r.conversations)
                  ? r
                  : best,
              null,
            );
            const peakTickets = rows.reduce<ActivityRow | null>(
              (best, r) =>
                r.bot_tickets !== null && (best === null || (best.bot_tickets ?? 0) < r.bot_tickets)
                  ? r
                  : best,
              null,
            );

            return (
              <div className="stack">
                <TrendChart
                  xKey="day"
                  height={260}
                  data={rows.map((r) => ({
                    day: fmtDate(r.day),
                    conversations: r.conversations,
                    bot_tickets: r.bot_tickets,
                  }))}
                  series={[
                    { key: "conversations", label: "Conversations" },
                    { key: "bot_tickets", label: "Bot-raised tickets" },
                  ]}
                />

                <div className="row">
                  {peakChats?.conversations != null ? (
                    <span className="tag">
                      {fmtInt(peakChats.conversations)} chats · {fmtDate(peakChats.day)}
                    </span>
                  ) : null}
                  {peakTickets?.bot_tickets != null ? (
                    <span className="tag">
                      {fmtInt(peakTickets.bot_tickets)} tickets · {fmtDate(peakTickets.day)}
                    </span>
                  ) : null}
                  {absent.length ? (
                    <span className="tag">no data in either extract · {absent.join(" · ")}</span>
                  ) : null}
                </div>

                <div className="panel__basis">{AXIS_NOTE}</div>

                <DataTable
                  columns={["Day", "Conversations", "Bot-raised tickets", "In Kore", "In Zendesk"]}
                  numeric={[1, 2]}
                  rows={[
                    ...rows.map((r) => [
                      fmtDate(r.day),
                      r.conversations === null || r.conversations === undefined
                        ? null
                        : fmtInt(r.conversations),
                      r.bot_tickets === null || r.bot_tickets === undefined
                        ? null
                        : fmtInt(r.bot_tickets),
                      r.in_kore_extract ? "yes" : "—",
                      r.in_zendesk_extract ? "yes" : "—",
                    ]),
                    [
                      "In extract",
                      fmtInt(sum(rows.map((r) => r.conversations))),
                      fmtInt(sum(rows.map((r) => r.bot_tickets))),
                      "",
                      "",
                    ],
                  ]}
                />

                <Note note={{ severity: "thin", body: TABLE_NOTE }} />
              </div>
            );
          }}
        </Async>
      </Panel>

      {/* -------------------------------------------------- backend failures */}
      <SectionRule title="Back-end failures carried on tickets" note="bot-raised only" />
      <Panel
        title="Back-end failures"
        question="Which automation step failed behind the ticket?"
        meta={failures.data?.meta}
      >
        <Async query={failures} skeletonRows={4}>
          {(data) => (
            <div className="stack">
              <div className="panel__basis">
                {dash(data.affected)} of {dash(data.total)} bot-raised tickets carry a failure tag
              </div>
              <BarList items={(data.items ?? []).map((i) => ({ label: i.label, count: i.ticket_count }))} />
              <TableToggle label="Show the failure tags as a table">
                <DataTable
                  columns={["Failure", "Tickets", "Stage", "Tag"]}
                  numeric={[1]}
                  rows={(data.items ?? []).map((i) => [
                    i.label,
                    fmtInt(i.ticket_count),
                    i.stage,
                    <span className="mono" key={i.tag}>
                      {i.tag}
                    </span>,
                  ])}
                />
              </TableToggle>
            </div>
          )}
        </Async>
      </Panel>

      {/* ------------------------------------------------------------ recent */}
      <SectionRule title="Recent tickets" note="most recent first" />
      <Panel title="Recent tickets" meta={recent.data?.meta}>
        <Async query={recent} skeletonRows={6}>
          {(data) => (
            <DataTable
              columns={[
                "Ticket",
                "Created",
                "Status",
                "Priority",
                "Cruise line",
                "Ship",
                "Flow",
                "Mood",
                "Bot-raised",
              ]}
              rows={(data.items ?? []).map((t) => [
                <span className="mono" key={t.ticket_id}>
                  {t.ticket_id}
                </span>,
                t.created_at ? fmtDate(t.created_at) : null,
                t.status,
                t.priority,
                t.cruise_line,
                t.ship_name,
                t.inquiry_type,
                t.sentiment,
                t.is_bot_raised ? "yes" : "no",
              ])}
            />
          )}
        </Async>
      </Panel>
    </>
  );
}
