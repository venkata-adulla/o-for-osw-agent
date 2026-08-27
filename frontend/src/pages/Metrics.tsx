/**
 * Metrics -- rates, distributions and outcomes.
 *
 * The catalog is the point of this page: a small set of instruments with approved,
 * low-cardinality dimensions. That is what keeps a dashboard fast and its cost
 * predictable, and it is why identifiers never appear as labels here.
 */
import Histogram from "../components/Histogram";
import { Async, BarList, PageHead, Panel, SectionRule } from "../components/primitives";
import { fmtInt, usePanel, type CountItem } from "../lib/api";

interface MetricSummaryItem {
  code: string;
  label: string;
  value_text: string;
  unit: string;
  description: string;
  instrument: string;
  window: string;
}

interface MetricSummaries {
  active_series: number;
  items: MetricSummaryItem[];
}

interface HistogramResponse {
  instrument: string;
  unit: string;
  total: number;
  buckets: { bucket_label: string; count: number }[];
  explainer: string;
}

interface OutcomesResponse {
  instrument: string;
  total: number;
  items: { result: string; count: number; is_error: boolean }[];
  note: string;
}

interface CatalogResponse {
  namespace: string;
  items: {
    name: string;
    kind: string;
    unit: string;
    description: string;
    dimensions: string[];
  }[];
  glossary: { term: string; body: string }[];
}

const DURATION_INSTRUMENT = "osw.conversation.duration";
const ENRICHMENT_INSTRUMENT = "osw.enrichment.operation";

const pretty = (value: string) => value.replace(/_/g, " ");

function outcomeTone(result: string, isError: boolean): string {
  if (isError) return "critical";
  if (/reject|invalid|refus/i.test(result)) return "warning";
  return "good";
}

export default function Metrics() {
  const summaries = usePanel<MetricSummaries>("/api/metrics/summaries");
  const histogram = usePanel<HistogramResponse>("/api/metrics/histogram", {
    instrument: DURATION_INSTRUMENT,
  });
  const outcomes = usePanel<OutcomesResponse>("/api/metrics/outcomes", {
    instrument: ENRICHMENT_INSTRUMENT,
  });
  const catalog = usePanel<CatalogResponse>("/api/metrics/catalog");

  const activeSeries = summaries.data?.active_series;

  return (
    <>
      <PageHead
        eyebrow="Technical view · Metrics"
        title="Rates, distributions and outcomes"
        lede="Low-cardinality dimensions keep dashboards fast and costs predictable. Every instrument below is a small, approved set of categories — never a customer identifier."
      />

      <SectionRule
        title="Instruments"
        note={activeSeries === undefined ? "Active series —" : `${fmtInt(activeSeries)} active series`}
      />

      <Async query={summaries} skeletonRows={4}>
        {(d) => (
          <div className="grid grid--kpi">
            {d.items.map((m) => (
              <div className="panel kpi" key={m.code}>
                <div className="kpi__label">{m.label}</div>
                <div className="kpi__value">
                  {m.value_text}
                  {m.unit ? <span className="kpi__unit">{m.unit}</span> : null}
                </div>
                <div className="kpi__sub">{m.description}</div>
                <div className="kpi__foot">
                  <span className="mono">{m.instrument}</span> · window {m.window}
                </div>
              </div>
            ))}
          </div>
        )}
      </Async>

      <SectionRule title="Distributions and outcomes" note="One instrument, many buckets" />

      <div className="grid grid--split">
        <Panel
          title={
            histogram.data
              ? `Histogram · ${fmtInt(histogram.data.total)} guest sessions`
              : "Histogram · conversation duration"
          }
          question="Conversation duration — time from the guest's first message until the chat is completed or abandoned."
          basis={
            histogram.data
              ? `${histogram.data.instrument} · unit ${histogram.data.unit}`
              : undefined
          }
        >
          <Async query={histogram} skeletonRows={6}>
            {(d) => (
              <>
                <Histogram buckets={d.buckets} total={d.total} />
                <div className="note note--info">
                  <span className="note__glyph" aria-hidden="true">
                    i
                  </span>
                  <span>
                    {d.explainer.toLowerCase().startsWith("what is p95") ? (
                      d.explainer
                    ) : (
                      <>
                        <b>What is p95?</b> {d.explainer}
                      </>
                    )}
                  </span>
                </div>
              </>
            )}
          </Async>
        </Panel>

        <Panel
          title={
            outcomes.data
              ? `Outcome dimensions · ${fmtInt(outcomes.data.total)} operations`
              : "Outcome dimensions · enrichment operations"
          }
          question="Attempts to validate or add business context — such as cruise line, ship alias, booking details or document metadata — before the request continues."
          basis={outcomes.data ? outcomes.data.instrument : undefined}
          readout="Input rejections are counted separately from system errors: the guest gave something the service could not accept, but the service itself did not fail. Mixing the two would hide real outages behind bad intake."
        >
          <Async query={outcomes} skeletonRows={4}>
            {(d) => {
              const items: CountItem[] = d.items.map((row) => ({
                label: pretty(row.result),
                count: row.count,
                share_pct: d.total > 0 ? Math.round((row.count / d.total) * 1000) / 10 : null,
                tone: outcomeTone(row.result, row.is_error),
              }));
              return (
                <>
                  <BarList items={items} showPct colorMode="tone" />
                  <div className="note note--caveat">
                    <span className="note__glyph" aria-hidden="true">
                      !
                    </span>
                    <span>{d.note}</span>
                  </div>
                </>
              );
            }}
          </Async>
        </Panel>
      </div>

      <SectionRule title="Metric catalog" note="Custom namespace osw.*" />

      <Panel
        title="OSW business metric instruments"
        question="Every instrument, its type, its unit and the only dimensions it is allowed to carry."
        basis={catalog.data ? `Namespace ${catalog.data.namespace}` : undefined}
        readout={
          <>
            Dimensions are approved categories, not free text. Holding them to a short list is
            what keeps the series count at{" "}
            <b>{activeSeries === undefined ? "a knowable number" : fmtInt(activeSeries)}</b> instead
            of one series per guest — the difference between a dashboard that answers in
            milliseconds and one that cannot be afforded.
          </>
        }
      >
        <Async query={catalog} skeletonRows={7}>
          {(d) => (
            <>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Instrument</th>
                      <th>Type</th>
                      <th>Unit</th>
                      <th>Allowed dimensions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.items.length === 0 ? (
                      <tr>
                        <td colSpan={4}>
                          <div className="empty">No instruments registered.</div>
                        </td>
                      </tr>
                    ) : (
                      d.items.map((row) => (
                        <tr key={row.name}>
                          <td className="strong">
                            <span className="mono">{row.name}</span>
                            {row.description ? (
                              <div className="span-row__op">{row.description}</div>
                            ) : null}
                          </td>
                          <td>{row.kind}</td>
                          <td>
                            <span className="mono">{row.unit}</span>
                          </td>
                          <td>
                            {row.dimensions.length === 0
                              ? "—"
                              : row.dimensions.map((dim) => (
                                  <span className="tag" key={dim}>
                                    {dim}
                                  </span>
                                ))}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              <div className="callouts">
                {d.glossary.map((entry) => (
                  <div className="callout" key={entry.term}>
                    <div className="callout__label">{entry.term}</div>
                    <div className="callout__body">{entry.body}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </Async>
      </Panel>
    </>
  );
}
