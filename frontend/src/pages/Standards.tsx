/**
 * Standards -- the implementation blueprint.
 *
 * Six requirements, one collector path, eight acceptance statements. The last
 * section matters most: the OTLP ingest counters are read from the receiver, so
 * the pipeline on this page is demonstrably running rather than merely described.
 */
import { Async, DataTable, PageHead, Panel, SectionRule } from "../components/primitives";
import { fmtInt, fmtTime, usePanel } from "../lib/api";

interface Requirement {
  code: string;
  badge: string;
  title: string;
  body: string;
  is_required: boolean;
  is_met: boolean;
}

interface IngestSignal {
  signal: string;
  // The backend's real field is `batches`; `count` is kept as a fallback in
  // case an older payload shape is ever served.
  batches?: number;
  count?: number;
  promoted?: number | null;
  last_received_at?: string | null;
}

interface IngestStats {
  // `batches_total` is what the backend actually returns; `total` is kept as
  // a fallback only.
  batches_total?: number;
  total?: number;
  promoted?: number;
  endpoint?: string;
  note?: string;
  last_received_at?: string | null;
  by_signal?: IngestSignal[];
  signals?: IngestSignal[];
  items?: IngestSignal[];
}

interface CollectorPath {
  steps: { step_no: number; code: string; title: string; detail: string }[];
  env_block: string;
  ingest?: IngestStats;
}

interface Checklist {
  passing: number;
  total: number;
  items: { code: string; statement: string; is_passing: boolean }[];
}

interface PrivacyItem {
  code: string;
  title: string;
  body: string;
  points?: string[];
  bullets?: string[];
}

interface Privacy {
  items: PrivacyItem[];
  ingest?: IngestStats;
}

const ENV_COMMENT = "# Every service identifies itself with Resource attributes";

export default function Standards() {
  const requirements = usePanel<{ items: Requirement[] }>("/api/standards/requirements");
  const collector = usePanel<CollectorPath>("/api/standards/collector-path");
  const checklist = usePanel<Checklist>("/api/standards/checklist");
  const privacy = usePanel<Privacy>("/api/standards/privacy");

  const passing = checklist.data
    ? `${checklist.data.passing} / ${checklist.data.total}`
    : "—";
  const ingest = collector.data?.ingest ?? privacy.data?.ingest;
  const ingestRows = ingest?.by_signal ?? ingest?.signals ?? ingest?.items ?? [];
  const ingestTotal = ingest?.batches_total ?? ingest?.total ?? null;
  const ingestPromoted =
    ingest?.promoted ??
    (ingestRows.length > 0
      ? ingestRows.reduce((sum, row) => sum + (row.promoted ?? 0), 0)
      : null);

  return (
    <>
      <PageHead
        eyebrow="Trust & scale · Standards"
        title="Implementation blueprint"
        lede="What “OpenTelemetry compliant” means for OSW — a practical contract your development team can implement and test."
      />

      <div className="row">
        <span className="pill pill--spec">Reference design</span>
        <span className="pill">OpenTelemetry Spec 1.60</span>
      </div>

      <SectionRule title="The contract" note="Six requirements · all required" />

      <Async query={requirements} skeletonRows={6}>
        {(d) => (
          <div className="reqs">
            {d.items.map((req) => (
              <div className="req" key={req.code}>
                <div className="req__no">{req.code}</div>
                <span className="req__badge">{req.badge}</span>
                <div className="req__title">{req.title}</div>
                <div className="req__body">{req.body}</div>
                <div className="req__state">
                  {req.is_required ? "Required" : "Recommended"} {req.is_met ? "✓" : "—"}
                </div>
              </div>
            ))}
          </div>
        )}
      </Async>

      <SectionRule title="Collector path" note="Vendor-neutral signal pipeline" />

      <Panel
        title="One export contract"
        question="Services export once, to a Collector. The Collector decides where signals go — so a backend can change without touching a service."
      >
        <Async query={collector} skeletonRows={4}>
          {(d) => (
            <>
              <div className="grid grid--kpi">
                {(d.steps ?? []).map((step) => (
                  <div className="steps" key={step.step_no}>
                    <div className="step">
                      <span className="step__no">{step.code}</span>
                      <div>
                        <div className="step__title">{step.title}</div>
                        <div className="step__body">{step.detail}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="panel__basis">Environment — every service, the same four lines</div>
              <pre className="code">
                {(d.env_block ?? "").trimStart().startsWith("#")
                  ? d.env_block
                  : `${ENV_COMMENT}\n${d.env_block ?? ""}`}
              </pre>
            </>
          )}
        </Async>
      </Panel>

      <SectionRule title="Definition of done" note={`Acceptance checklist ${passing}`} />

      <Panel
        title="Acceptance checklist"
        question="Eight statements a reviewer can test against a running service. Nothing here is a matter of opinion."
        basis={checklist.data ? `${passing} passing` : undefined}
      >
        <Async query={checklist} skeletonRows={8}>
          {(d) => (
            <div className="checklist">
              {d.items.map((item) => (
                <div className="checklist__item" key={item.code}>
                  <span
                    className={`checklist__tick${item.is_passing ? "" : " is-open"}`}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  <span className="checklist__statement">{item.statement}</span>
                  <span className="checklist__code">{item.code}</span>
                </div>
              ))}
            </div>
          )}
        </Async>
      </Panel>

      <SectionRule title="Privacy and scale" note="By design, not by review" />

      <Async query={privacy} skeletonRows={4}>
        {(d) => (
          <div className="grid grid--split">
            {(d.items ?? []).map((item) => (
              <Panel title={item.title} key={item.code}>
                <div className="req__body">{item.body}</div>
                <div className="checklist">
                  {(item.points ?? item.bullets ?? []).map((point) => (
                    <div className="checklist__item" key={point}>
                      <span className="checklist__tick" aria-hidden="true">
                        ✓
                      </span>
                      <span className="checklist__statement">{point}</span>
                    </div>
                  ))}
                </div>
              </Panel>
            ))}
          </div>
        )}
      </Async>

      <SectionRule
        title="Live OTLP ingest"
        note="Proof the collector path is running, not just documented"
      />

      <Panel
        title="OTLP receiver — what has actually arrived"
        question="These counters come from the ingest table behind /v1/traces, /v1/metrics and /v1/logs. If the Collector stopped forwarding, this panel would stop moving."
        basis={
          ingest?.endpoint
            ? `Endpoint ${ingest.endpoint}`
            : "Endpoints /v1/traces · /v1/metrics · /v1/logs"
        }
        readout={ingest?.note}
      >
        {ingest === undefined ? (
          <div className="note note--thin">
            <span className="note__glyph" aria-hidden="true">
              ~
            </span>
            <span>
              The governance endpoints report no OTLP ingest counters yet. Until the Collector
              forwards its first batch there is nothing to prove here — which is the honest
              reading, not an error.
            </span>
          </div>
        ) : (
          <>
            <div className="callouts">
              <div className="callout callout--good">
                <div className="callout__label">Batches received</div>
                <div className="callout__value">{fmtInt(ingestTotal)}</div>
                <div className="callout__body">Payloads persisted by the OTLP receiver.</div>
              </div>
              <div className="callout">
                <div className="callout__label">Promoted</div>
                <div className="callout__value">{fmtInt(ingestPromoted)}</div>
                <div className="callout__body">
                  Batches promoted into spans, metrics and log records.
                </div>
              </div>
              <div className="callout">
                <div className="callout__label">Last signal</div>
                <div className="callout__value mono">
                  {ingest.last_received_at ? fmtTime(ingest.last_received_at) : "—"}
                </div>
                <div className="callout__body">Most recent batch accepted.</div>
              </div>
            </div>

            {ingestRows.length > 0 ? (
              <DataTable
                columns={["Signal", "Batches", "Promoted", "Last received"]}
                numeric={[1, 2]}
                rows={ingestRows.map((row) => [
                  <span className="mono">{row.signal}</span>,
                  fmtInt(row.batches ?? row.count ?? null),
                  fmtInt(row.promoted ?? null),
                  <span className="mono">
                    {row.last_received_at ? fmtTime(row.last_received_at) : "—"}
                  </span>,
                ])}
              />
            ) : null}
          </>
        )}
      </Panel>
    </>
  );
}
