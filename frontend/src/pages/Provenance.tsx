/**
 * Where every figure comes from.
 *
 * Three separate extracts, three separate windows, three separate caps. Both
 * APIs cap at 100 rows, so the two 100s are a coincidence and not a match —
 * which is the whole reason this page exists.
 */
import { fmtInt, usePanel, type Callout } from "../lib/api";
import {
  Async,
  Callouts,
  DataTable,
  Note,
  PageHead,
  Panel,
  SectionRule,
} from "../components/primitives";

interface PopulationFigure {
  value_text: string;
  label: string;
}

interface Population {
  code: string;
  letter: string;
  label: string;
  source_system: string;
  window_from: string | null;
  window_to: string | null;
  row_count: number | null;
  is_capped: boolean;
  cap_rows: number | null;
  more_available: boolean;
  caveat: string;
  figures: PopulationFigure[];
}

interface CoverageItem {
  code: string;
  label: string;
  numerator: number;
  denominator: number;
  pct: number;
  basis: string;
}

const PERIOD_TOTAL_WARNING =
  "No figure on this screen is a period total. Zendesk reports 345 tickets and we hold 100 " +
  "of them. Kore.ai reports more sessions available beyond its 100. The review covers 5 days " +
  "of 19. Every count here is a floor, and every percentage is computed inside its own page — " +
  "never across the three.";

const INTRO =
  "Three separate extracts. Both APIs cap at 100, so the two 100s below are a coincidence, not a match.";

const windowText = (population: Population): string => {
  const from = population.window_from;
  const to = population.window_to;
  const range = from && to ? `${from} → ${to}` : (from ?? to ?? "window not recorded");
  const cap = population.is_capped
    ? ` · capped at ${fmtInt(population.cap_rows)} rows${population.more_available ? " · more available" : ""}`
    : "";
  const rows = population.row_count === null || population.row_count === undefined
    ? ""
    : ` · ${fmtInt(population.row_count)} rows held`;
  return `${population.source_system} · ${range}${rows}${cap}`;
};

const coverageColor = (pct: number): string => {
  if (pct >= 95) return "var(--good)";
  if (pct >= 80) return "var(--o3)";
  if (pct >= 40) return "var(--warning)";
  return "var(--critical)";
};

export default function Provenance() {
  const populations = usePanel<{ items: Population[] }>("/api/meta/populations");
  const coverage = usePanel<{ items: CoverageItem[] }>("/api/meta/coverage");

  return (
    <>
      <PageHead
        eyebrow="Trust & scale"
        title="Where every figure comes from"
        lede={INTRO}
      />

      <SectionRule title="Three populations" note="A · Kore.ai  B · Zendesk  C · Hand review" />

      <Async query={populations} skeletonRows={4}>
        {(data) => (
          <div className="stack">
            <div className="grid grid--3">
              {(data.items ?? []).map((population) => {
                const figures: Callout[] = (population.figures ?? []).map((figure, i) => ({
                  code: `${population.code}-${i}`,
                  label: figure.label,
                  value_text: figure.value_text,
                  body: "",
                  tone: "neutral",
                }));
                return (
                  <Panel
                    key={population.code}
                    title={`${population.letter} · ${population.label}`}
                    basis={windowText(population)}
                  >
                    <div className="stack">
                      <Callouts items={figures} />
                      {population.caveat ? (
                        <Note note={{ severity: "caveat", body: population.caveat }} />
                      ) : null}
                    </div>
                  </Panel>
                );
              })}
            </div>

            {(data.meta?.notes ?? []).some((note) => note.severity === "critical") ? (
              (data.meta?.notes ?? [])
                .filter((note) => note.severity === "critical")
                .map((note, i) => <Note note={note} key={`meta-critical-${i}`} />)
            ) : (
              <Note note={{ severity: "critical", body: PERIOD_TOTAL_WARNING }} />
            )}
          </div>
        )}
      </Async>

      <SectionRule title="Data coverage" note="within page 1" />
      <Panel
        title="Data coverage"
        question="What fraction of the records actually carry each field?"
        meta={coverage.data?.meta}
        basis={coverage.data?.meta?.basis ?? "Of the bot-raised tickets, except where a row says otherwise."}
      >
        <Async query={coverage} skeletonRows={7}>
          {(data) => {
            const items = data.items ?? [];
            return (
              <div className="stack">
                <div className="bars">
                  {items.map((item) => (
                    <div className="bar" key={item.code}>
                      <div className="bar__label" title={item.label}>
                        {item.label}
                      </div>
                      <div className="bar__track">
                        <div
                          className="bar__fill"
                          style={{
                            width: `${Math.max(0, Math.min(100, item.pct))}%`,
                            background: coverageColor(item.pct),
                          }}
                        />
                      </div>
                      <div className="bar__value">
                        {item.pct}%
                        <span className="bar__pct">
                          {fmtInt(item.numerator)}/{fmtInt(item.denominator)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>

                <DataTable
                  columns={["Metric", "Pct", "Detail"]}
                  numeric={[1]}
                  rows={items.map((item) => [
                    item.label,
                    `${item.pct}%`,
                    item.basis || `${fmtInt(item.numerator)} of ${fmtInt(item.denominator)}`,
                  ])}
                />
              </div>
            );
          }}
        </Async>
      </Panel>
    </>
  );
}
