/**
 * Guest journey — the chat-to-document chain (P-54): where guests quit,
 * whether the paperwork reached the ticket, and whether the service team was
 * asked to do the same job twice.
 */
import {
  fmtInt,
  usePanel,
  type Callout,
  type CountItem,
  type JourneyStage,
} from "../lib/api";
import {
  Async,
  BarList,
  Callouts,
  DataTable,
  Note,
  PageHead,
  Panel,
  SectionRule,
  TableToggle,
} from "../components/primitives";
import Funnel from "../components/Funnel";
import TrendChart from "../components/TrendChart";

/* ------------------------------------------------------------------ shapes */

interface ChainTableRow {
  stage: string;
  reached: number | null;
  of_sample: string | number | null;
  lost_here: number | null;
  why: string;
}

interface ChainResponse {
  stages: JourneyStage[];
  callouts: Callout[];
  table_rows?: ChainTableRow[];
}

interface QuitReason {
  code: string;
  label: string;
  count: number;
  category: string;
}

interface QuitResponse {
  items: QuitReason[];
  totals: { never_spoke: number; paperwork: number; mid_flow: number };
}

interface OutcomeDay {
  day: string;
  reviewed: number | null;
  ticket_created: number | null;
  no_ticket: number | null;
  was_read: boolean;
}

interface OutcomesResponse {
  reviewed: number;
  made_request: number;
  never_spoke: number;
  got_ticket: number;
  no_ticket: number;
  tickets: number;
  duplicates: number;
  by_day: OutcomeDay[];
}

interface EnrichmentOutcome {
  code: string;
  label: string;
  count: number;
  meaning: string;
}

interface EnrichmentFailure {
  code: string;
  label: string;
  count: number;
  is_intake: boolean;
}

interface EnrichmentResponse {
  outcomes: EnrichmentOutcome[];
  failures: EnrichmentFailure[];
  automation_gaps: { change: string; effect: string }[];
}

interface DuplicatePair {
  ticket_a: number | string;
  ticket_b: number | string;
  is_exact_repeat: boolean;
  evidence: string;
}

interface DuplicatesResponse {
  sessions: number;
  extra_tickets: number;
  exact_repeats: number;
  pairs: DuplicatePair[];
  cause: string;
}

interface DurationsResponse {
  fastest_text: string;
  typical_text: string;
  longest_text: string;
  basis: string;
}

/* ------------------------------------------------------------------ helpers */

const dash = (n: number | null | undefined): string => (n === null || n === undefined ? "—" : fmtInt(n));

const dayLabel = (iso: string): string => {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
};

const sum = (values: (number | null | undefined)[]): number =>
  values.reduce((acc: number, v) => acc + (v ?? 0), 0);

const countOf = (
  items: { code: string; label: string; count: number }[],
  code: string,
  hint: string,
): number | null => {
  const hit =
    items.find((i) => i.code === code) ??
    items.find((i) => i.label.toLowerCase().includes(hint));
  return hit ? hit.count : null;
};

const callout = (
  code: string,
  label: string,
  value_text: string,
  body: string,
  tone: Callout["tone"] = "neutral",
): Callout => ({ code, label, value_text, body, tone });

/* ------------------------------------------------------------------ copy */

const ENRICHMENT_FAIL_NOTE =
  "Not one failure is a pipeline fault. Four of five are missing intake data — a cabin " +
  "number, a purchase date, a ship the system does not recognise. Fix the intake and the " +
  "enrichment fixes itself.";

const SHIP_NAME_LINE =
  "'Holland America Westerdam' was rejected until the guest simplified it to 'Holland " +
  "America'. That is the same naming gap that blocks the ship panel — here it costs a " +
  "guest their paperwork.";

/* ------------------------------------------------------------------ page */

export default function GuestJourney() {
  const chain = usePanel<ChainResponse>("/api/journey/chain");
  const quit = usePanel<QuitResponse>("/api/journey/quit-reasons");
  const outcomes = usePanel<OutcomesResponse>("/api/journey/outcomes");
  const enrichment = usePanel<EnrichmentResponse>("/api/journey/enrichment");
  const duplicates = usePanel<DuplicatesResponse>("/api/journey/duplicates");
  const durations = usePanel<DurationsResponse>("/api/journey/durations");

  return (
    <>
      <PageHead
        eyebrow="Business view"
        title="Guest journey — chat to document"
        lede="A guest opens the chat. How often does paperwork actually land on a ticket? This is the only chain that follows one conversation all the way to the document on the ticket."
      />

      {/* ---------------------------------------------------------- P-54 */}
      <SectionRule title="End to end — chat to document" note="14–19 Aug" />
      <Panel
        title="End to end — chat to document"
        question="A guest opens the chat. How often does paperwork actually land on a ticket?"
        meta={chain.data?.meta}
        readout={
          <>
            Fewer than half of conversations finish the job. The chain loses most at stage 4 —
            25 guests abandoned or were failed before a ticket existed — and then loses 15 more{" "}
            <b>after</b> a ticket was raised, where the guest has been told their request is in
            hand.
          </>
        }
      >
        <Async query={chain} skeletonRows={6}>
          {(data) => {
            const stages = data.stages ?? [];
            const rows: ChainTableRow[] =
              data.table_rows ??
              stages.map((s) => ({
                stage: `${s.stage_no}. ${s.label}`,
                reached: s.reached,
                of_sample: s.pct_of_sample === null || s.pct_of_sample === undefined ? null : `${s.pct_of_sample}%`,
                lost_here: s.lost_here,
                why: s.why,
              }));
            return (
              <div className="stack">
                <Funnel stages={stages} />
                {data.callouts?.length ? <Callouts items={data.callouts} /> : null}
                <TableToggle label="Show the chain as a table">
                  <DataTable
                    columns={["Stage", "Reached", "Of sample", "Lost here", "Why"]}
                    numeric={[1, 2, 3]}
                    rows={rows.map((r) => [r.stage, dash(r.reached), r.of_sample, r.lost_here, r.why])}
                  />
                </TableToggle>
              </div>
            );
          }}
        </Async>
      </Panel>

      {/* ---------------------------------------------------- quit reasons */}
      <SectionRule title="Where guests quit" note="new" />
      <Panel
        title="Where guests quit"
        question="Which question ends the conversation?"
        meta={quit.data?.meta}
      >
        <Async query={quit} skeletonRows={5}>
          {(data) => {
            const items: CountItem[] = (data.items ?? []).map((i) => ({
              label: i.label,
              count: i.count,
            }));
            const totals = data.totals;
            return (
              <div className="stack">
                <BarList items={items} />
                <Callouts
                  items={[
                    callout(
                      "never_spoke",
                      "Never spoke at all",
                      dash(totals?.never_spoke),
                      "not a bot problem — greeted and left without typing",
                    ),
                    callout(
                      "paperwork",
                      "Stopped at paperwork",
                      dash(totals?.paperwork),
                      "cabin number, booking number, card digits, spa record name",
                      "critical",
                    ),
                    callout(
                      "mid_flow",
                      "Quit mid-flow",
                      dash(totals?.mid_flow),
                      "started a request and did not finish it",
                      "warning",
                    ),
                  ]}
                />
                <div className="readout">
                  {dash(totals?.never_spoke)} never typed a word — those are not a bot problem. Of
                  the {dash(totals?.mid_flow)} who did quit mid-flow,{" "}
                  <b>{dash(totals?.paperwork)} stopped at a piece of paperwork</b> the guest simply
                  did not have to hand: cabin number, booking number, card digits, spa record name.
                </div>
                <TableToggle label="Show the reasons as a table">
                  <DataTable
                    columns={["Reason", "Count", "Category"]}
                    numeric={[1]}
                    rows={(data.items ?? []).map((i) => [
                      i.label,
                      fmtInt(i.count),
                      <span className="tag" key={i.code}>
                        {i.category}
                      </span>,
                    ])}
                  />
                </TableToggle>
              </div>
            );
          }}
        </Async>
      </Panel>

      {/* ------------------------------------------------------ P-32 outcomes */}
      <SectionRule title="What the conversation produced" />
      <div className="grid grid--wide">
        <Panel
          title="What the conversation produced"
          question="Where do guests actually end up?"
          meta={outcomes.data?.meta}
        >
          <Async query={outcomes} skeletonRows={4}>
            {(data) => (
              <div className="stack">
                <Callouts
                  items={[
                    callout(
                      "reviewed",
                      "Reviewed",
                      dash(data.reviewed),
                      "sessions in this window",
                    ),
                    callout(
                      "made_request",
                      "Made a request",
                      dash(data.made_request),
                      `−${dash(data.never_spoke)} never spoke`,
                    ),
                    callout(
                      "got_ticket",
                      "Got a ticket",
                      dash(data.got_ticket),
                      `−${dash(data.no_ticket)} did not`,
                      "warning",
                    ),
                    callout(
                      "tickets",
                      "Tickets",
                      dash(data.tickets),
                      `+${dash(data.duplicates)} duplicates`,
                      "critical",
                    ),
                  ]}
                />
                <div className="readout">
                  One session in three ends with nothing. {dash(data.no_ticket)} of{" "}
                  {dash(data.made_request)} guests who started a request never got a ticket. And{" "}
                  {dash(data.got_ticket)} requests produced {dash(data.tickets)} tickets, so the
                  queue is slightly larger than the demand behind it.
                </div>
                <TableToggle label="Show by day">
                  <DataTable
                    columns={["Day", "Reviewed", "Ticket", "None"]}
                    numeric={[1, 2, 3]}
                    rows={[
                      ...(data.by_day ?? [])
                        .filter((d) => d.was_read)
                        .map((d) => [dayLabel(d.day), dash(d.reviewed), dash(d.ticket_created), dash(d.no_ticket)]),
                      [
                        "Total",
                        fmtInt(sum((data.by_day ?? []).map((d) => d.reviewed))),
                        fmtInt(sum((data.by_day ?? []).map((d) => d.ticket_created))),
                        fmtInt(sum((data.by_day ?? []).map((d) => d.no_ticket))),
                      ],
                    ]}
                  />
                </TableToggle>
              </div>
            )}
          </Async>
        </Panel>

        <Panel
          title="Reviewed sessions by day"
          question="How does daily volume break down?"
          readout="Tuesday sees the highest volume of the week; weekends are quieter."
        >
          <Async query={outcomes} skeletonRows={4}>
            {(data) => {
              const days = (data.by_day ?? []).filter((d) => d.was_read);
              return (
                <TrendChart
                  xKey="day"
                  height={220}
                  data={days.map((d) => ({
                    day: dayLabel(d.day),
                    reviewed: d.reviewed,
                    ticket_created: d.ticket_created,
                    no_ticket: d.no_ticket,
                  }))}
                  series={[
                    { key: "reviewed", label: "Reviewed" },
                    { key: "ticket_created", label: "Ticket created" },
                    { key: "no_ticket", label: "No ticket" },
                  ]}
                />
              );
            }}
          </Async>
        </Panel>
      </div>

      {/* ---------------------------------------------------- P-55 enrichment */}
      <SectionRule title="Document enrichment" />
      <div className="grid grid--wide">
        <Panel
          title="Document enrichment"
          question="Did the guest's paperwork actually reach the ticket?"
          meta={enrichment.data?.meta}
          readout="This is the status the Zendesk API cannot give you. Five of the six lifecycle events tag the ticket; DocumentCreated attaches the file instead of tagging, and the ticket API returns no attachments field."
        >
          <Async query={enrichment} skeletonRows={5}>
            {(data) => {
              const list = data.outcomes ?? [];
              return (
                <div className="stack">
                  <Callouts
                    items={[
                      callout(
                        "attached",
                        "Attached",
                        dash(countOf(list, "created", "creat")),
                        "document attached to the ticket",
                        "good",
                      ),
                      callout(
                        "stalled",
                        "Stalled",
                        dash(countOf(list, "transaction_initiated_only", "transaction")),
                        "returns file made, transaction never finished",
                        "warning",
                      ),
                      callout(
                        "failed",
                        "Failed",
                        dash(countOf(list, "failed", "fail")),
                        "no document reached the ticket",
                        "critical",
                      ),
                    ]}
                  />
                  <DataTable
                    columns={["Status", "Count", "What it means"]}
                    numeric={[1]}
                    rows={list.map((o) => [o.label, fmtInt(o.count), o.meaning])}
                  />
                  <TableToggle label="How to make this automatic">
                    <DataTable
                      columns={["Change", "Effect"]}
                      rows={(data.automation_gaps ?? []).map((g) => [g.change, g.effect])}
                    />
                  </TableToggle>
                </div>
              );
            }}
          </Async>
        </Panel>

        <Panel
          title="Why enrichment failed"
          question="Is it the pipeline, or the intake?"
          basis="The 5 failures and the 4 stalled transactions"
          actions={<span className="pill">new</span>}
        >
          <Async query={enrichment} skeletonRows={4}>
            {(data) => {
              const failures = data.failures ?? [];
              return (
                <div className="stack">
                  <BarList items={failures.map((f) => ({ label: f.label, count: f.count }))} />
                  <DataTable
                    columns={["Failure", "Count", "Cause"]}
                    numeric={[1]}
                    rows={failures.map((f) => [
                      f.label,
                      fmtInt(f.count),
                      <span className="tag" key={f.code}>
                        {f.is_intake ? "intake data" : "pipeline"}
                      </span>,
                    ])}
                  />
                  <Note note={{ severity: "critical", body: ENRICHMENT_FAIL_NOTE }} />
                  <div className="readout">{SHIP_NAME_LINE}</div>
                </div>
              );
            }}
          </Async>
        </Panel>
      </div>

      {/* ------------------------------------------------------- duplicates */}
      <SectionRule title="Duplicate tickets" note="new" />
      <Panel
        title="Duplicate tickets"
        question="Is the service team being asked to do the same job twice?"
        meta={duplicates.data?.meta}
        readout={
          <>
            343000 and 343003 are the same refund twice — identical 6 bottles, $769.32 on both.
            The bot's <b>'anything else?'</b> prompt restarted the whole intake and the guest,
            following instructions, completed it again. Both were rated 5 out of 5.
          </>
        }
      >
        <Async query={duplicates} skeletonRows={3}>
          {(data) => {
            const hasThinNote = (data.meta?.notes ?? []).some((n) => n.severity === "thin");
            return (
              <div className="stack">
                <Callouts
                  items={[
                    callout("sessions", "Sessions", dash(data.sessions), "sessions that produced a duplicate"),
                    callout(
                      "extra",
                      "Extra tickets",
                      dash(data.extra_tickets),
                      "work the service team did not need",
                      "warning",
                    ),
                    callout(
                      "exact",
                      "Exact repeats",
                      dash(data.exact_repeats),
                      "identical request, twice",
                      "critical",
                    ),
                  ]}
                />
                <DataTable
                  columns={["Pair", "Tickets", "Exact repeat", "Evidence"]}
                  numeric={[1]}
                  rows={(data.pairs ?? []).map((p) => [
                    <span className="mono" key={`${p.ticket_a}-${p.ticket_b}`}>
                      {p.ticket_a} + {p.ticket_b}
                    </span>,
                    2,
                    p.is_exact_repeat ? "yes" : "no",
                    p.evidence,
                  ])}
                />
                {data.cause && !hasThinNote ? (
                  <Note note={{ severity: "thin", body: data.cause }} />
                ) : null}
              </div>
            );
          }}
        </Async>
      </Panel>

      {/* -------------------------------------------------------- P-36 length */}
      <SectionRule title="Length and duration" />
      <Panel
        title="Length and duration"
        question="How long does the bot hold a guest?"
        meta={durations.data?.meta}
        basis={durations.data?.basis}
      >
        <Async query={durations} skeletonRows={2}>
          {(data) => (
            <Callouts
              items={[
                callout("fastest", "Fastest", data.fastest_text, "opened and closed"),
                callout("typical", "Typical", data.typical_text, "median session length"),
                callout(
                  "longest",
                  "Longest",
                  data.longest_text,
                  "one guest completing a return",
                  "warning",
                ),
              ]}
            />
          )}
        </Async>
      </Panel>
    </>
  );
}
