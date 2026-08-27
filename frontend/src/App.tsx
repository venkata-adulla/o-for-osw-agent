/**
 * App shell: the left rail groups the product the way the operating model does --
 * one command centre, then the business view, then the technical view, then the
 * governance that makes both trustworthy.
 */
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "./lib/api";

import CommandCenter from "./pages/CommandCenter";
import GuestJourney from "./pages/GuestJourney";
import Tickets from "./pages/Tickets";
import CruiseLines from "./pages/CruiseLines";
import Products from "./pages/Products";
import Customers from "./pages/Customers";
import Conversations from "./pages/Conversations";
import ConversationDetail from "./pages/ConversationDetail";
import Traces from "./pages/Traces";
import TraceDetail from "./pages/TraceDetail";
import Metrics from "./pages/Metrics";
import Logs from "./pages/Logs";
import Baggage from "./pages/Baggage";
import Profiles from "./pages/Profiles";
import Diagnose from "./pages/Diagnose";
import Standards from "./pages/Standards";
import Provenance from "./pages/Provenance";

interface NavItem {
  to: string;
  glyph: string;
  label: string;
}

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Command centre",
    items: [{ to: "/", glyph: "◎", label: "One picture" }],
  },
  {
    group: "Business view",
    items: [
      { to: "/journey", glyph: "⇥", label: "Guest journey" },
      { to: "/tickets", glyph: "▤", label: "Tickets & requests" },
      { to: "/lines", glyph: "⚓", label: "Cruise lines & ships" },
      { to: "/products", glyph: "❑", label: "Products & services" },
      { to: "/customers", glyph: "◍", label: "Customers" },
      { to: "/conversations", glyph: "❝", label: "Conversations" },
    ],
  },
  {
    group: "Technical view",
    items: [
      { to: "/traces", glyph: "⑂", label: "Traces" },
      { to: "/metrics", glyph: "⌁", label: "Metrics" },
      { to: "/logs", glyph: "≡", label: "Logs" },
      { to: "/baggage", glyph: "◇", label: "Baggage" },
      { to: "/profiles", glyph: "▥", label: "Profiles" },
    ],
  },
  {
    group: "Trust & scale",
    items: [
      { to: "/diagnose", glyph: "⚕", label: "Diagnose" },
      { to: "/standards", glyph: "✓", label: "Standards" },
      { to: "/provenance", glyph: "⊞", label: "Where figures come from" },
    ],
  },
];

const CRUMBS: Record<string, string> = {
  "/": "One picture",
  "/journey": "Guest journey",
  "/tickets": "Tickets & requests",
  "/lines": "Cruise lines & ships",
  "/products": "Products & services",
  "/customers": "Customers",
  "/conversations": "Conversations",
  "/traces": "Traces",
  "/metrics": "Metrics",
  "/logs": "Logs",
  "/baggage": "Baggage",
  "/profiles": "Profiles",
  "/diagnose": "Diagnose",
  "/standards": "Standards",
  "/provenance": "Provenance",
};

interface IncidentState {
  state: "healthy" | "incident";
  incident: { code: string; title: string; severity: string } | null;
}

interface BotRow {
  bot_id: string;
  bot_name: string;
  environment: string;
  instrumented: boolean;
  data_held: boolean;
  note: string;
}

function Rail() {
  return (
    <nav className="rail" aria-label="Sections">
      <div className="rail__brand">
        <span className="rail__mark" aria-hidden="true">
          O
        </span>
        <span>
          <span className="rail__name">O for OSW</span>
          <br />
          <span className="rail__sub">Command centre</span>
        </span>
      </div>

      {NAV.map((group) => (
        <div className="rail__group" key={group.group}>
          <div className="rail__group-label">{group.group}</div>
          {group.items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => `rail__link${isActive ? " is-active" : ""}`}
            >
              <span className="rail__glyph" aria-hidden="true">
                {item.glyph}
              </span>
              {item.label}
            </NavLink>
          ))}
        </div>
      ))}

      <div className="rail__foot">
        Business view and technical view over one context.
        <br />
        OpenTelemetry end to end — vendor-neutral, no lock-in.
      </div>
    </nav>
  );
}

function TopBar() {
  const location = useLocation();
  const client = useQueryClient();

  const incident = useQuery<IncidentState>({
    queryKey: ["/api/incident/state"],
    queryFn: () => apiGet<IncidentState>("/api/incident/state"),
    refetchInterval: 30_000,
  });

  const freshness = useQuery<{ updated_at: string | null; next_run_at: string | null }>({
    queryKey: ["/api/meta/freshness"],
    queryFn: () => apiGet("/api/meta/freshness"),
  });

  const bots = useQuery<{ items: BotRow[] }>({
    queryKey: ["/api/meta/bots"],
    queryFn: () => apiGet("/api/meta/bots"),
  });

  const toggle = useMutation({
    mutationFn: (state: "healthy" | "incident") =>
      apiPost<IncidentState>("/api/incident/simulate", { state }),
    onSuccess: () => {
      // Every panel re-reads, so the whole product agrees about the incident.
      void client.invalidateQueries();
    },
  });

  const isIncident = incident.data?.state === "incident";
  const crumb = CRUMBS[location.pathname] ?? "Detail";

  // A bare "HH:MM" is ambiguous the moment the underlying event isn't from
  // today -- and with no scheduler actually re-running the ETL in this
  // environment, "Updated" can genuinely be many hours (or days) stale. A
  // relative age is unambiguous regardless of the viewer's assumptions about
  // "today"; the exact clock time is still available on hover.
  const magnitude = (mins: number): string => {
    const abs = Math.abs(mins);
    return abs < 60 ? `${abs}m` : abs < 60 * 24 ? `${Math.round(abs / 60)}h` : `${Math.round(abs / 1440)}d`;
  };
  const agoText = (iso: string | null | undefined): string => {
    if (!iso) return "—";
    const then = Date.parse(iso);
    if (Number.isNaN(then)) return "—";
    const mins = Math.round((Date.now() - then) / 60_000);
    if (Math.abs(mins) < 1) return "just now";
    return mins > 0 ? `${magnitude(mins)} ago` : `in ${magnitude(mins)}`;
  };
  const exactText = (iso: string | null | undefined): string =>
    iso ? new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "—";

  return (
    <header className="topbar">
      <span className="topbar__crumb">
        OSW / <b>{crumb}</b>
      </span>

      <span className="pill pill--spec">OpenTelemetry 1.60</span>

      <span className="topbar__spacer" />

      {/* Bot switcher. Serena and AiVA are listed but disabled until their data
          lands -- showing them greyed is more honest than hiding the gap. */}
      <label className="control" htmlFor="bot-switcher">
        <span className="control__label">Bot</span>
        <select
          id="bot-switcher"
          className="control__value"
          style={{ border: "none", background: "none", padding: 0 }}
          defaultValue="marina"
        >
          {(bots.data?.items ?? [{ bot_id: "marina", bot_name: "Marina", data_held: true } as BotRow]).map(
            (bot) => (
              <option key={bot.bot_id} value={bot.bot_id} disabled={!bot.data_held}>
                {bot.bot_name}
                {bot.data_held ? "" : " — no data held"}
              </option>
            ),
          )}
        </select>
      </label>

      <span className="control" aria-label="Reporting period">
        <span className="control__label">Period</span>
        <span className="control__value">13–19 Aug 2026</span>
      </span>

      <button
        type="button"
        className="control"
        disabled
        title="No prior period exists in this extract, so there is nothing to compare against."
      >
        <span className="control__label">Compare</span>
        <span className="control__value">Off · no prior period</span>
      </button>

      <span
        className="control"
        aria-label="Data freshness"
        title={`Last ETL success: ${exactText(freshness.data?.updated_at)} (your local time)\nNext scheduled run: ${exactText(freshness.data?.next_run_at)}`}
      >
        <span className="control__label">Updated</span>
        <span className="control__value">
          {agoText(freshness.data?.updated_at)}
          {" · "}
          {freshness.data?.next_run_at && Date.parse(freshness.data.next_run_at) < Date.now()
            ? `next run overdue by ${magnitude(Math.round((Date.now() - Date.parse(freshness.data.next_run_at)) / 60_000))}`
            : `next ${agoText(freshness.data?.next_run_at)}`}
        </span>
      </span>

      <button type="button" className="btn" onClick={() => window.print()}>
        Export view
      </button>

      <button
        type="button"
        className={`btn ${isIncident ? "btn--accent" : "btn--alarm"}`}
        onClick={() => toggle.mutate(isIncident ? "healthy" : "incident")}
        disabled={toggle.isPending}
      >
        {isIncident ? "✓ Restore healthy" : "⚡ Simulate incident"}
      </button>

      <span className={`pill ${isIncident ? "" : "pill--live"}`}>{isIncident ? "SEV-2" : "Live"}</span>
    </header>
  );
}

export default function App() {
  return (
    <div className="app">
      <Rail />
      <div>
        <TopBar />
        <main className="page">
          <Routes>
            <Route path="/" element={<CommandCenter />} />
            <Route path="/journey" element={<GuestJourney />} />
            <Route path="/tickets" element={<Tickets />} />
            <Route path="/lines" element={<CruiseLines />} />
            <Route path="/products" element={<Products />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/conversations" element={<Conversations />} />
            <Route path="/conversations/:sessionId" element={<ConversationDetail />} />
            <Route path="/traces" element={<Traces />} />
            <Route path="/traces/:traceId" element={<TraceDetail />} />
            <Route path="/metrics" element={<Metrics />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/baggage" element={<Baggage />} />
            <Route path="/profiles" element={<Profiles />} />
            <Route path="/diagnose" element={<Diagnose />} />
            <Route path="/standards" element={<Standards />} />
            <Route path="/provenance" element={<Provenance />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
