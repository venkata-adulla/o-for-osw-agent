/**
 * Flame graph.
 *
 * The API returns a flat frame list; the tree is rebuilt here from `parent_id`.
 * Each frame's width is its share of samples, and its horizontal offset is the
 * running total of its siblings -- so a child always sits inside its parent.
 * Depth drives the colour, using the shared ordinal ramp (root darkest).
 */
import type { ReactNode } from "react";
import { rampColor } from "../lib/api";

export interface ProfileFrame {
  id: number;
  parent_id: number | null;
  function_name: string;
  pct: number;
  self_ms: number | null;
  depth: number;
}

interface Placed {
  frame: ProfileFrame;
  offset: number;
}

/** Mirrors rampColor's step arithmetic so text contrast can follow the fill. */
function rampStep(index: number, total: number): number {
  return Math.min(5, Math.max(1, Math.round(((index + 1) / Math.max(1, total)) * 5)));
}

function place(frames: ProfileFrame[]): Placed[] {
  const ids = new Set(frames.map((f) => f.id));
  const byParent = new Map<number | null, ProfileFrame[]>();
  for (const frame of frames) {
    const key = frame.parent_id !== null && ids.has(frame.parent_id) ? frame.parent_id : null;
    const siblings = byParent.get(key);
    if (siblings) siblings.push(frame);
    else byParent.set(key, [frame]);
  }

  const placed: Placed[] = [];
  const seen = new Set<number>();
  const walk = (parent: number | null, start: number) => {
    let cursor = start;
    for (const frame of byParent.get(parent) ?? []) {
      if (seen.has(frame.id)) continue;
      seen.add(frame.id);
      placed.push({ frame, offset: cursor });
      walk(frame.id, cursor);
      cursor += Math.max(0, frame.pct);
    }
  };
  walk(null, 0);
  return placed;
}

export default function FlameGraph({
  frames,
  label = "Flame graph",
}: {
  frames: ProfileFrame[];
  label?: string;
}) {
  const placed = place(frames);
  const rows = new Map<number, Placed[]>();
  for (const item of placed) {
    const row = rows.get(item.frame.depth);
    if (row) row.push(item);
    else rows.set(item.frame.depth, [item]);
  }
  const depths = [...rows.keys()].sort((a, b) => a - b);
  const maxDepth = depths.length > 0 ? depths[depths.length - 1] : 0;

  return (
    <div className="flame" role="group" aria-label={label}>
      {depths.map((depth) => {
        const items = (rows.get(depth) ?? []).slice().sort((a, b) => a.offset - b.offset);
        const cells: ReactNode[] = [];
        let cursor = 0;
        items.forEach((item, i) => {
          const gap = item.offset - cursor;
          if (gap > 0.05) {
            cells.push(
              <span
                key={`gap-${depth}-${i}`}
                aria-hidden="true"
                style={{ flex: `0 0 ${gap}%`, minWidth: 0 }}
              />,
            );
          }
          const inverted = maxDepth - depth;
          const step = rampStep(inverted, maxDepth + 1);
          cells.push(
            <div
              key={item.frame.id}
              className="flame__frame"
              style={{
                flex: `0 1 ${Math.max(item.frame.pct, 0.8)}%`,
                background: rampColor(inverted, maxDepth + 1),
                color: step <= 2 ? "var(--ink)" : "#fff",
              }}
              title={`${item.frame.function_name} — ${item.frame.pct}% of samples${
                item.frame.self_ms !== null ? ` · ${item.frame.self_ms} ms self` : ""
              } · depth ${item.frame.depth}`}
            >
              {item.frame.function_name}
              <span>{item.frame.pct}%</span>
            </div>,
          );
          cursor = item.offset + Math.max(0, item.frame.pct);
        });
        return (
          <div className="flame__row" key={depth}>
            {cells}
          </div>
        );
      })}
    </div>
  );
}
