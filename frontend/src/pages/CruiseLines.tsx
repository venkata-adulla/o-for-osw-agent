/**
 * Cruise lines & ships — which partners generate the most guest contact, and
 * what mood the guest arrives in.
 *
 * These are raw counts with no sailing or passenger divisor, which is exactly
 * why the caveat travels with every figure.
 */
import { fmtInt, usePanel, type CountItem } from "../lib/api";
import {
  Async,
  BarList,
  DataTable,
  PageHead,
  Panel,
  SectionRule,
  TableToggle,
} from "../components/primitives";

interface ContactsResponse {
  named: number;
  total: number;
  items: { cruise_line: string; ticket_count: number; share_pct: number | null }[];
}

interface ShipsResponse {
  items: { ship_name: string; cruise_line: string | null; ticket_count: number }[];
}

interface MoodResponse {
  scored: number;
  total: number;
  unhappy: number;
  unhappy_pct: number | null;
  items: { sentiment: string; count: number; tone: string | null }[];
}

const dash = (n: number | null | undefined): string => (n === null || n === undefined ? "—" : fmtInt(n));

export default function CruiseLines() {
  const contacts = usePanel<ContactsResponse>("/api/lines/contacts");
  const ships = usePanel<ShipsResponse>("/api/lines/ships");
  const mood = usePanel<MoodResponse>("/api/lines/mood");

  const named = contacts.data?.named;
  const total = contacts.data?.total;

  return (
    <>
      <PageHead
        eyebrow="Business view · population B"
        title="Cruise lines & ships"
        lede="Which partners generate the most guest contact — and how happy those guests are when they reach us."
      />

      <SectionRule
        title="Contacts by cruise line"
        note={
          named === undefined || total === undefined
            ? "bot-raised only"
            : `cruise line named on ${fmtInt(named)} of ${fmtInt(total)} bot-raised tickets`
        }
      />

      <Panel
        title="Contacts by cruise line"
        question="Which partners generate the most guest contact?"
        meta={contacts.data?.meta}
      >
        <Async query={contacts} skeletonRows={5}>
          {(data) => {
            const items: CountItem[] = (data.items ?? []).map((i) => ({
              label: i.cruise_line,
              count: i.ticket_count,
              share_pct: i.share_pct,
            }));
            return (
              <div className="stack">
                <BarList items={items} showPct />
                <TableToggle label="Show the cruise lines as a table">
                  <DataTable
                    columns={["Cruise line", "Tickets", `Share of ${dash(data.named)} named`]}
                    numeric={[1, 2]}
                    rows={(data.items ?? []).map((i) => [
                      i.cruise_line,
                      fmtInt(i.ticket_count),
                      i.share_pct === null || i.share_pct === undefined ? null : `${i.share_pct}%`,
                    ])}
                  />
                </TableToggle>
              </div>
            );
          }}
        </Async>
      </Panel>

      <SectionRule title="Ships named" note="parsed from free text, not a field" />
      <Panel
        title="Ships named on a ticket"
        question="Which ship was the guest sailing on?"
        meta={ships.data?.meta}
      >
        <Async query={ships} skeletonRows={5}>
          {(data) => (
            <DataTable
              columns={["Ship", "Cruise line", "Tickets"]}
              numeric={[2]}
              rows={(data.items ?? []).map((s) => [
                s.ship_name,
                s.cruise_line,
                fmtInt(s.ticket_count),
              ])}
            />
          )}
        </Async>
      </Panel>

      <SectionRule title="Guest mood" note="every bot-raised ticket is scored" />
      <Panel
        title="Guest mood"
        question="How happy are guests when they reach us?"
        meta={mood.data?.meta}
        readout={
          mood.data ? (
            <>
              <b>
                {dash(mood.data.unhappy)} of {dash(mood.data.total)} arrive unhappy —{" "}
                {mood.data.unhappy_pct === null || mood.data.unhappy_pct === undefined
                  ? "—"
                  : `${mood.data.unhappy_pct}%`}
                .
              </b>{" "}
              Every bot-raised ticket is scored, so unlike the other channels there is no gap
              here. Not one is positive.
            </>
          ) : undefined
        }
      >
        <Async query={mood} skeletonRows={4}>
          {(data) => {
            const items: CountItem[] = (data.items ?? []).map((i) => ({
              label: i.sentiment,
              count: i.count,
              tone: i.tone,
            }));
            return (
              <div className="stack">
                <div className="panel__basis">
                  {dash(data.scored)} of {dash(data.total)} bot-raised tickets carry a mood score
                </div>
                <BarList items={items} colorMode="tone" />
              </div>
            );
          }}
        </Async>
      </Panel>
    </>
  );
}
