/**
 * The command centre — one glance, in the order leadership reads it:
 * is anything broken, what is the business seeing, what is the platform doing,
 * how the whole thing is organised, where the request actually goes, which
 * signals we hold, and how far the guest gets.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { usePanel, type Callout, type JourneyStage, type Kpi } from "../lib/api";
import {
  Async,
  Callouts,
  KpiTile,
  Note,
  PageHead,
  Panel,
  SectionRule,
  SignalCard,
} from "../components/primitives";
import Funnel from "../components/Funnel";
import HealthBanner from "../components/HealthBanner";
import Topology from "../components/Topology";

interface KpiResponse {
  view: string;
  state: string;
  items: Kpi[];
}

interface ModelItem {
  code: string;
  title: string;
  body: string;
}

interface OperatingModelResponse {
  pillars: ModelItem[];
  signals: ModelItem[];
  journey_stages: ModelItem[];
}

interface SignalItem {
  signal: string;
  glyph: string;
  volume_text: string;
  coverage_text: string;
  description: string;
  route: string;
}

interface JourneyResponse {
  source: "telemetry" | "review";
  basis: string;
  stages: JourneyStage[];
  callouts: Callout[];
}

const SOURCE_NOTE =
  "Two different views, never one series. Live telemetry counts conversations over the " +
  "last 24 hours — 1,284 started, 962 with a document attached. The extended view covers " +
  "a focused 5-day window — 74 sessions, 31 with a document attached. A percentage from " +
  "one basis can never be compared with the other.";

const title = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);

export default function CommandCenter() {
  const business = usePanel<KpiResponse>("/api/overview/kpis", { view: "business" });
  const technical = usePanel<KpiResponse>("/api/overview/kpis", { view: "technical" });
  const model = usePanel<OperatingModelResponse>("/api/overview/operating-model");
  const signals = usePanel<{ items: SignalItem[] }>("/api/overview/signals");

  const [source, setSource] = useState<"telemetry" | "review">("telemetry");
  const journey = usePanel<JourneyResponse>("/api/overview/journey", { source });

  return (
    <>
      <PageHead
        eyebrow="Step 1 · See — one operating picture"
        title="One picture of every OSW automation"
        lede="A unified observability model for every OSW automation — one place for the business view and the technical view of every AI agent and automation, built on open standards."
      />

      <HealthBanner />

      <SectionRule
        title="Business view — how conversations are going"
        note="every figure here is a page, not a period total"
      />
      <Async query={business} skeletonRows={2}>
        {(data) => (
          <div className="grid grid--kpi">
            {data.items.map((kpi) => (
              <KpiTile key={kpi.code} kpi={kpi} />
            ))}
          </div>
        )}
      </Async>

      <SectionRule
        title="Technical view — what happens behind each one"
        note="vs previous 24 hours"
      />
      <Async query={technical} skeletonRows={2}>
        {(data) => (
          <div className="grid grid--kpi">
            {data.items.map((kpi) => (
              <KpiTile key={kpi.code} kpi={kpi} />
            ))}
          </div>
        )}
      </Async>

      <SectionRule title="The operating model" note="Illustrative product views — representative data for discussion" />
      <Panel
        title="One place for both views"
        question="Business view · Technical view · Open standards · One place"
        meta={model.data?.meta}
      >
        <Async query={model} skeletonRows={3}>
          {(data) => (
            <div className="stack">
              <div className="reqs">
                {(data.pillars ?? []).map((pillar) => (
                  <div className="req" key={pillar.code}>
                    <div className="req__badge">{pillar.code}</div>
                    <div className="req__title">{pillar.title}</div>
                    <div className="req__body">{pillar.body}</div>
                  </div>
                ))}
              </div>

              <div>
                <div className="panel__basis">Five signals, one context — OpenTelemetry</div>
                <div className="reqs">
                  {(data.signals ?? []).map((signal) => (
                    <div className="req" key={signal.code}>
                      <div className="req__title">{signal.title}</div>
                      <div className="req__body">{signal.body}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="panel__basis">The guest journey — see every stage, live</div>
                <div className="row">
                  {(data.journey_stages ?? []).map((stage, i) => (
                    <span className="row" key={stage.code}>
                      {i > 0 ? (
                        <span className="hop__arrow" aria-hidden="true">
                          →
                        </span>
                      ) : null}
                      <span className="tag">{stage.title}</span>
                    </span>
                  ))}
                </div>
                <div className="readout">
                  Follow guest journeys stage by stage — with a path to live production
                  monitoring; when a stage stalls, diagnosis starts with one click.
                </div>
              </div>
            </div>
          )}
        </Async>
      </Panel>

      <SectionRule title="Where the request actually goes" note="7 hops · plus the telemetry path" />
      <Topology />

      <SectionRule title="Signal coverage" note="five signals, one context" />
      <Async query={signals} skeletonRows={2}>
        {(data) => (
          <div className="signals">
            {data.items.map((item) => (
              <SignalCard
                key={item.signal}
                glyph={item.glyph}
                name={title(item.signal)}
                volume={item.volume_text}
                coverage={item.coverage_text}
                desc={item.description}
                to={item.route}
              />
            ))}
          </div>
        )}
      </Async>

      <SectionRule title="Business + technical telemetry" note="guest journey" />
      <Panel
        title="Guest journey — see every stage, live"
        question="How far does a guest actually get?"
        meta={journey.data?.meta}
        basis={journey.data?.basis}
        actions={
          <div className="row">
            <div className="seg" role="group" aria-label="Journey basis">
              <button
                type="button"
                className={source === "telemetry" ? "is-active" : ""}
                aria-pressed={source === "telemetry"}
                onClick={() => setSource("telemetry")}
              >
                Live
              </button>
              <button
                type="button"
                className={source === "review" ? "is-active" : ""}
                aria-pressed={source === "review"}
                onClick={() => setSource("review")}
              >
                Extended view
              </button>
            </div>
            <Link to="/traces">Explore traces →</Link>
          </div>
        }
      >
        <div className="stack">
          <div className="row">
            <span className="pill">
              {source === "telemetry" ? "Basis: live telemetry" : "Basis: extended session detail"}
            </span>
          </div>

          <Async query={journey} skeletonRows={5}>
            {(data) => (
              <div className="stack">
                <Funnel stages={data.stages ?? []} />
                {data.callouts?.length ? <Callouts items={data.callouts} /> : null}
              </div>
            )}
          </Async>

          <Note note={{ severity: "info", body: SOURCE_NOTE }} />
        </div>
      </Panel>
    </>
  );
}
