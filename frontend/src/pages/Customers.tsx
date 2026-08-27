/**
 * Customers — how often one guest has to ask the bot twice.
 *
 * A floor, not a ceiling: repeat contact arriving by email or phone is not in
 * this extract at all, so the caveat is the point of the panel.
 */
import { fmtDate, fmtInt, usePanel, type Callout } from "../lib/api";
import { Async, Callouts, DataTable, Note, PageHead, Panel, SectionRule } from "../components/primitives";

interface TopRepeatGuest {
  requester_id: string;
  ticket_count: number;
  ticket_ids: string[];
  chasing_older: boolean;
  last_ticket_at: string | null;
}

interface RepeatResponse {
  guests: number;
  repeat_guests: number;
  repeat_pct: number | null;
  their_tickets: number;
  raised_two_plus: number;
  chasing_older: number;
  method: string;
  top_repeat_guests: TopRepeatGuest[];
}

/** A rough word for a fraction, computed rather than guessed, so it can never
 * drift from the number sitting right next to it. */
function fractionWord(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return "some";
  if (pct >= 45) return "nearly one guest in two";
  if (pct >= 28) return "close to one guest in three";
  if (pct >= 20) return "about one guest in five";
  if (pct >= 13) return "roughly one guest in seven";
  return "a small share of guests";
}

const dash = (n: number | null | undefined): string => (n === null || n === undefined ? "—" : fmtInt(n));

const pct = (n: number | null | undefined): string =>
  n === null || n === undefined ? "—" : `${n}%`;

const callout = (
  code: string,
  label: string,
  value_text: string,
  body: string,
  tone: Callout["tone"] = "neutral",
): Callout => ({ code, label, value_text, body, tone });

export default function Customers() {
  const repeat = usePanel<RepeatResponse>("/api/customers/repeat");

  const data = repeat.data;

  return (
    <>
      <PageHead
        eyebrow="Business view · population B"
        title="Customers"
        lede="How often does one guest have to ask the bot twice?"
      />

      <SectionRule
        title="Guests who came back"
        note={
          data
            ? `${fmtInt(data.repeat_guests)} of ${fmtInt(data.guests)} guests came back · bot-raised only`
            : "bot-raised only"
        }
      />

      <Panel
        title="Guests who came back"
        question="How often does one guest have to ask the bot twice?"
        meta={repeat.data?.meta}
        readout={
          data ? (
            <>
              {fractionWord(data.repeat_pct).charAt(0).toUpperCase() + fractionWord(data.repeat_pct).slice(1)}{" "}
              had to come back —{" "}
              <b>
                {fmtInt(data.repeat_guests)} of {fmtInt(data.guests)} ({pct(data.repeat_pct)})
              </b>
              , between them raising {fmtInt(data.their_tickets)} tickets.
            </>
          ) : undefined
        }
      >
        <Async query={repeat} skeletonRows={3}>
          {(d) => (
            <div className="stack">
              <Callouts
                items={[
                  callout(
                    "repeat",
                    "Repeat guests",
                    `${dash(d.repeat_guests)} of ${dash(d.guests)}`,
                    `${pct(d.repeat_pct)} of the guests who used it`,
                    "warning",
                  ),
                  callout(
                    "tickets",
                    "Their tickets",
                    dash(d.their_tickets),
                    "tickets raised by those guests",
                  ),
                  callout(
                    "two_plus",
                    "Raised 2+ bot tickets",
                    dash(d.raised_two_plus),
                    "same guest, more than one request",
                  ),
                  callout(
                    "chasing",
                    "Chasing an older ticket",
                    dash(d.chasing_older),
                    "a follow-up pointing back at earlier work",
                    "critical",
                  ),
                ]}
              />
              {d.method ? (
                <Note note={{ severity: "info", body: `How they were identified: ${d.method}` }} />
              ) : null}
            </div>
          )}
        </Async>
      </Panel>

      <SectionRule title="Who these guests are" note="requester_id only, never a name" />
      <Panel
        title="Top repeat guests"
        question="Which specific guests came back, and how many times?"
        meta={repeat.data?.meta}
      >
        <Async query={repeat} skeletonRows={4}>
          {(d) =>
            d.top_repeat_guests.length === 0 ? (
              <p className="readout">No repeat guest carries more detail than the counts above.</p>
            ) : (
              <DataTable
                columns={["Requester", "Tickets", "Ticket IDs", "Chasing an older ticket", "Last ticket"]}
                numeric={[1]}
                rows={d.top_repeat_guests.map((g) => [
                  g.requester_id,
                  fmtInt(g.ticket_count),
                  g.ticket_ids.join(", "),
                  g.chasing_older ? "yes" : "no",
                  g.last_ticket_at ? fmtDate(g.last_ticket_at) : "—",
                ])}
              />
            )
          }
        </Async>
      </Panel>
    </>
  );
}
