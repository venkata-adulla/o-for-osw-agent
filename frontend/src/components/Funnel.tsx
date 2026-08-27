/**
 * The guest journey funnel.
 *
 * Stages arrive as data (see `journey_stages`), so the chain is never layout.
 * Two things this component must never lose:
 *   - the per-stage loss chip, because the drop is the finding, not the total;
 *   - the `‖` basis break, because stage 1 is a different population from the
 *     stages below it and reading them as one series is the classic error.
 */
import { Fragment } from "react";
import { fmtInt, rampColor, type JourneyStage } from "../lib/api";

export default function Funnel({
  stages,
  basisBreakLabel = "basis change — a different population, not a drop",
  lossLabel = "lost here",
}: {
  stages: JourneyStage[];
  basisBreakLabel?: string;
  lossLabel?: string;
}) {
  const total = stages.length;
  if (total === 0) return <div className="empty">No stages in this extract.</div>;

  return (
    <div className="funnel">
      {stages.map((stage, i) => {
        // A stage with no percentage is shown for scale only (stage 1), so it
        // fills the meter and is labelled as context rather than as 100%.
        const pct = stage.pct_of_sample;
        const width = pct === null || pct === undefined ? 100 : Math.max(1.5, Math.min(100, pct));
        const fill = rampColor(total - 1 - i, total);
        const lost = stage.lost_here;

        return (
          <Fragment key={stage.code || `stage-${stage.stage_no}`}>
            {stage.basis_change ? (
              <div className="funnel__basis-break">{basisBreakLabel}</div>
            ) : null}

            {lost !== null && lost !== undefined && lost > 0 && i > 0 ? (
              <div className="funnel__loss">
                <span className="funnel__loss-value">−{fmtInt(lost)}</span>
                <span className="funnel__why">{lossLabel}</span>
              </div>
            ) : null}

            <div className="funnel__stage">
              <div className="funnel__count">{fmtInt(stage.reached)}</div>
              <div className="funnel__meter">
                <div className="funnel__meter-track">
                  <div
                    className="funnel__meter-fill"
                    style={{ width: `${width}%`, background: fill }}
                  />
                </div>
                <div className="funnel__caption">
                  <span className="funnel__name">
                    {stage.stage_no}. {stage.label}
                  </span>
                  <span className="funnel__pct">
                    {pct === null || pct === undefined ? "— of sample" : `${pct}%`}
                  </span>
                  {stage.why ? <span className="funnel__why">{stage.why}</span> : null}
                </div>
              </div>
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}
