/**
 * Continuous profiles -- the code behind the latency.
 *
 * A trace says which span was slow. A profile says which function made it slow.
 * The correlation strip at the foot is the whole argument for keeping both.
 */
import { useState } from "react";
import FlameGraph, { type ProfileFrame } from "../components/FlameGraph";
import { Async, DataTable, PageHead, Panel, SectionRule } from "../components/primitives";
import { fmtInt, usePanel } from "../lib/api";

interface HotFunction {
  function_name: string;
  pct: number;
  total_ms: number;
}

interface ProfileResponse {
  service_name: string;
  profile_type: string;
  window_label: string;
  sample_hz: number;
  finding: string;
  frames: ProfileFrame[];
  hot_functions: HotFunction[];
}

interface CorrelationResponse {
  steps: { step_no: number; title: string; body: string }[];
}

const TYPES = [
  { value: "cpu", label: "CPU" },
  { value: "allocations", label: "Allocations" },
] as const;

type ProfileType = (typeof TYPES)[number]["value"];

export default function Profiles() {
  const [profileType, setProfileType] = useState<ProfileType>("cpu");

  const profile = usePanel<ProfileResponse>("/api/profiles", { type: profileType });
  const correlation = usePanel<CorrelationResponse>("/api/profiles/correlation");

  return (
    <>
      <PageHead
        eyebrow="Technical view · Profiles"
        title="Continuous profiles"
        lede="Find the code behind the latency. Sampled stack traces explain where CPU time and memory are being consumed."
      />

      <div className="row">
        <span className="control__label">Profile</span>
        <div className="seg" role="group" aria-label="Profile type">
          {TYPES.map((t) => (
            <button
              key={t.value}
              type="button"
              className={profileType === t.value ? "is-active" : undefined}
              aria-pressed={profileType === t.value}
              onClick={() => setProfileType(t.value)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <SectionRule
        title="Flame graph"
        note={
          profile.data
            ? `${profile.data.service_name} · ${profile.data.window_label} · ${profile.data.sample_hz} Hz`
            : "—"
        }
      />

      <Panel
        title={
          profile.data
            ? `Flame graph · ${profile.data.service_name}`
            : "Flame graph"
        }
        question="Each row is one stack depth. A frame's width is its share of samples, so a child always sits inside the parent that called it."
        basis={
          profile.data
            ? `${profile.data.profile_type} samples · ${profile.data.window_label} · ${profile.data.sample_hz} Hz`
            : undefined
        }
      >
        <Async query={profile} skeletonRows={6}>
          {(d) => (
            <>
              <FlameGraph
                frames={d.frames}
                label={`${d.profile_type} flame graph for ${d.service_name}`}
              />
              {d.finding ? (
                <div className="callouts">
                  <div className="callout callout--warning">
                    <div className="callout__label">Finding</div>
                    <div className="callout__body">{d.finding}</div>
                  </div>
                </div>
              ) : null}
            </>
          )}
        </Async>
      </Panel>

      <SectionRule title="Hot functions" note="Optimization candidates" />

      <Panel
        title="Hot functions"
        question="The functions holding the most samples in this window — the shortest list worth optimising."
      >
        <Async query={profile} skeletonRows={4}>
          {(d) => (
            <DataTable
              columns={["Function", "% of samples", "Total"]}
              numeric={[1, 2]}
              rows={d.hot_functions.map((f) => [
                <span className="mono">{f.function_name}</span>,
                `${f.pct}%`,
                `${fmtInt(f.total_ms)} ms`,
              ])}
            />
          )}
        </Async>
      </Panel>

      <SectionRule title="Trace-to-profile correlation" note="From symptom to code" />

      <Panel
        title="From symptom to code"
        question="The same context ties a metric alert to a slow span, and the slow span to the function inside it."
      >
        <Async query={correlation} skeletonRows={3}>
          {(d) => (
            <div className="grid grid--3">
              {d.steps.map((step) => (
                <div className="steps" key={step.step_no}>
                  <div className="step">
                    <span className="step__no">{step.step_no}</span>
                    <div>
                      <div className="step__title">{step.title}</div>
                      <div className="step__body">{step.body}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Async>
      </Panel>
    </>
  );
}
