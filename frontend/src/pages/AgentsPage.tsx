import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AgentEvent,
  AgentProposal,
  AgentReviewPayload,
  AgentSettings,
  ApiError,
  CycleSummary,
  approveAgentProposal,
  getAgentSettings,
  getLatestAgentReview,
  listAgentEvents,
  listAgentProposals,
  rejectAgentProposal,
  runAgentCycle,
  runAgentReview,
  toggleAgentKillSwitch,
  updateAgentSettings,
} from "../api";

const LOG_POLL_MS = 2000;

type Tab = "control" | "proposals" | "review";

const AGENT_COLORS: Record<string, string> = {
  NOVA: "agent-nova",
  ORIN: "agent-orin",
  VESK: "agent-vesk",
  LUMA: "agent-luma",
  KIRA: "agent-kira",
  DASH: "agent-dash",
  SYSTEM: "agent-system",
  HUMAN: "agent-human",
};

function formatCountdown(expiresAt: string | null): string {
  if (!expiresAt) return "—";
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const mins = Math.floor(ms / 60000);
  const secs = Math.floor((ms % 60000) / 1000);
  return `${mins}m ${secs}s`;
}

function eventSummary(row: AgentEvent): string {
  const payload = row.payload || {};
  if (typeof payload.summary === "string" && payload.summary.trim()) {
    return payload.summary;
  }
  if (row.event_type === "cycle_skipped" && payload.reason) {
    return `Cycle skipped (${String(payload.reason)})`;
  }
  if (row.event_type === "cycle_start") {
    return "Cycle started";
  }
  if (row.event_type === "cycle_complete") {
    return "Cycle finished";
  }
  if (row.symbol) {
    return `${row.agent} ${row.event_type} on ${row.symbol}`;
  }
  return `${row.agent} · ${row.event_type}`;
}

function eventDetails(row: AgentEvent): string[] {
  const payload = row.payload || {};
  if (Array.isArray(payload.details)) {
    return payload.details.map((item) => String(item)).filter(Boolean);
  }
  return [];
}

export default function AgentsPage() {
  const [tab, setTab] = useState<Tab>("control");
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [proposals, setProposals] = useState<AgentProposal[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [review, setReview] = useState<AgentReviewPayload | null>(null);
  const [lastCycle, setLastCycle] = useState<CycleSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [eventAgent, setEventAgent] = useState("");
  const [expandedEvent, setExpandedEvent] = useState<number | null>(null);
  const [confirmWeak, setConfirmWeak] = useState(false);
  const [logLive, setLogLive] = useState(true);
  const logRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);
  const prevNewestIdRef = useRef<number | null>(null);

  const loadAll = useCallback(async () => {
    setError(null);
    try {
      const [s, p, e] = await Promise.all([
        getAgentSettings(),
        listAgentProposals(),
        listAgentEvents(),
      ]);
      setSettings(s);
      setProposals(p);
      setEvents(e);
      try {
        setReview(await getLatestAgentReview());
      } catch {
        setReview(null);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load agents");
    }
  }, []);

  const refreshLog = useCallback(async () => {
    try {
      const [e, p] = await Promise.all([
        listAgentEvents(),
        listAgentProposals(),
      ]);
      setEvents(e);
      setProposals(p);
    } catch {
      // Keep showing the last good log during polling errors.
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (tab !== "control" || !logLive) {
      return;
    }
    const id = window.setInterval(() => {
      void refreshLog();
    }, LOG_POLL_MS);
    return () => window.clearInterval(id);
  }, [tab, logLive, refreshLog]);

  const pending = useMemo(
    () => proposals.filter((row) => row.status === "pending"),
    [proposals],
  );
  const vetoed = useMemo(
    () => proposals.filter((row) => row.status === "vetoed"),
    [proposals],
  );

  const filteredEvents = useMemo(() => {
    const rows = eventAgent
      ? events.filter((row) => row.agent === eventAgent)
      : events;
    // Chronological: oldest first so new lines appear at the bottom.
    return [...rows].sort((a, b) => a.id - b.id);
  }, [events, eventAgent]);

  useEffect(() => {
    const newest = filteredEvents[filteredEvents.length - 1];
    const newestId = newest?.id ?? null;
    const grew =
      newestId != null &&
      prevNewestIdRef.current != null &&
      newestId !== prevNewestIdRef.current;
    prevNewestIdRef.current = newestId;

    const el = logRef.current;
    if (!el) {
      return;
    }
    if (stickToBottomRef.current || grew) {
      el.scrollTop = el.scrollHeight;
    }
  }, [filteredEvents]);

  const onLogScroll = () => {
    const el = logRef.current;
    if (!el) {
      return;
    }
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distance < 48;
  };

  const onSaveSettings = async () => {
    if (!settings) return;
    setBusy(true);
    setError(null);
    try {
      const next = await updateAgentSettings({
        enabled: settings.enabled,
        max_open_positions: settings.max_open_positions,
        max_trades_per_day: settings.max_trades_per_day,
        daily_loss_limit_percent: settings.daily_loss_limit_percent,
        risk_per_trade_percent: settings.risk_per_trade_percent,
        proposal_ttl_minutes: settings.proposal_ttl_minutes,
        min_orin_score: settings.min_orin_score,
        min_checklist_score: settings.min_checklist_score,
        checklist_id: settings.checklist_id,
        cycle_interval_minutes: settings.cycle_interval_minutes,
        scheduler_enabled: settings.scheduler_enabled,
        confirm_weak_backtest: confirmWeak || undefined,
      });
      setSettings(next);
      setConfirmWeak(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const onKill = async () => {
    setBusy(true);
    setError(null);
    try {
      setSettings(await toggleAgentKillSwitch());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Kill switch failed");
    } finally {
      setBusy(false);
    }
  };

  const onRunCycle = async () => {
    setBusy(true);
    setError(null);
    try {
      const summary = await runAgentCycle(true);
      setLastCycle(summary);
      await loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Cycle failed");
    } finally {
      setBusy(false);
    }
  };

  const onApprove = async (id: number) => {
    setBusy(true);
    setError(null);
    try {
      await approveAgentProposal(id);
      await loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Approve failed");
    } finally {
      setBusy(false);
    }
  };

  const onReject = async (id: number) => {
    setBusy(true);
    setError(null);
    try {
      await rejectAgentProposal(id);
      await loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reject failed");
    } finally {
      setBusy(false);
    }
  };

  const onReview = async () => {
    setBusy(true);
    setError(null);
    try {
      setReview(await runAgentReview());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Review failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="page">
      <header className="header">
        <div>
          <h1>Agents</h1>
          <p>Paper trading loop — human approval required before any order.</p>
        </div>
      </header>

      <div className="earnings-banner risk-high" role="status">
        Paper trading only. Simulated results. Not financial advice.
      </div>

      {error ? (
        <div className="error-banner" role="alert">
          {error}
        </div>
      ) : null}

      <div className="agents-tabs" role="tablist" aria-label="Agents sections">
        {(
          [
            ["control", "Control"],
            ["proposals", "Proposals"],
            ["review", "Review"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? "timeframe-btn active" : "timeframe-btn"}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "control" && settings ? (
        <section className="panel">
          <h2>Control</h2>
          {settings.backtest_gate.warning ? (
            <div className="warning-banner" role="status">
              {settings.backtest_gate.warning}
            </div>
          ) : null}
          {!settings.backtest_gate.allowed ? (
            <p className="muted-note">{settings.backtest_gate.message}</p>
          ) : null}

          <div className="agents-control-grid">
            <label className="toggle-field">
              Enabled
              <input
                type="checkbox"
                checked={settings.enabled}
                onChange={(e) =>
                  setSettings({ ...settings, enabled: e.target.checked })
                }
              />
            </label>
            <label className="toggle-field">
              Scheduler
              <input
                type="checkbox"
                checked={settings.scheduler_enabled}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    scheduler_enabled: e.target.checked,
                  })
                }
              />
            </label>
            {settings.backtest_gate.requires_confirmation ? (
              <label className="toggle-field">
                Confirm weak backtest
                <input
                  type="checkbox"
                  checked={confirmWeak}
                  onChange={(e) => setConfirmWeak(e.target.checked)}
                />
              </label>
            ) : null}
          </div>

          <div className="form-grid backtest-form" style={{ marginTop: "1rem" }}>
            <label>
              Max open positions
              <input
                type="number"
                value={settings.max_open_positions}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    max_open_positions: Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Max trades / day
              <input
                type="number"
                value={settings.max_trades_per_day}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    max_trades_per_day: Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Daily loss limit %
              <input
                value={settings.daily_loss_limit_percent}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    daily_loss_limit_percent: e.target.value,
                  })
                }
              />
            </label>
            <label>
              Risk per trade %
              <input
                value={settings.risk_per_trade_percent}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    risk_per_trade_percent: e.target.value,
                  })
                }
              />
            </label>
            <label>
              Proposal TTL (minutes)
              <input
                type="number"
                value={settings.proposal_ttl_minutes}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    proposal_ttl_minutes: Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Min ORIN score
              <input
                type="number"
                value={settings.min_orin_score}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    min_orin_score: Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Min checklist score
              <input
                type="number"
                value={settings.min_checklist_score}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    min_checklist_score: Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Cycle interval (minutes)
              <input
                type="number"
                value={settings.cycle_interval_minutes}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    cycle_interval_minutes: Number(e.target.value),
                  })
                }
              />
            </label>
          </div>

          <div className="form-actions" style={{ marginTop: "1rem", gap: "0.75rem" }}>
            <button type="button" disabled={busy} onClick={() => void onSaveSettings()}>
              Save settings
            </button>
            <button
              type="button"
              className="kill-switch-btn"
              disabled={busy}
              onClick={() => void onKill()}
            >
              {settings.kill_switch ? "Clear kill switch" : "KILL SWITCH"}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => void onRunCycle()}
            >
              Run cycle now
            </button>
          </div>

          {lastCycle ? (
            <p className="muted-note" style={{ marginTop: "1rem" }}>
              Last cycle {lastCycle.cycle_id.slice(0, 8)}…
              {lastCycle.skipped
                ? ` skipped (${lastCycle.skip_reason})`
                : ` — ${lastCycle.proposed} proposed, ${lastCycle.vesk_vetoed} vetoed`}
            </p>
          ) : null}

          <h3 style={{ marginTop: "1.5rem" }}>Agent jobs</h3>
          <ul className="agent-job-list">
            {Object.entries(settings.agent_jobs).map(([name, job]) => (
              <li key={name}>
                <strong className={AGENT_COLORS[name] || ""}>{name}</strong> — {job}
              </li>
            ))}
          </ul>

          <div className="panel-header-row" style={{ marginTop: "1.75rem" }}>
            <h2>Activity log</h2>
            <div className="form-actions" style={{ gap: "0.5rem" }}>
              <label className="muted-note">
                Filter{" "}
                <select
                  value={eventAgent}
                  onChange={(e) => setEventAgent(e.target.value)}
                >
                  <option value="">All agents</option>
                  {Object.keys(AGENT_COLORS).map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="toggle-field">
                Live
                <input
                  type="checkbox"
                  checked={logLive}
                  onChange={(e) => setLogLive(e.target.checked)}
                />
              </label>
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => void refreshLog()}
              >
                Refresh log
              </button>
            </div>
          </div>
          <p className="muted-note">
            Live updates every {LOG_POLL_MS / 1000}s. Newest entries append at
            the bottom — expand a row for full agent detail.
          </p>
          {filteredEvents.length === 0 ? (
            <p className="empty">No activity yet. Run a cycle to populate the log.</p>
          ) : (
            <div
              className="event-timeline event-timeline-scroll"
              ref={logRef}
              onScroll={onLogScroll}
            >
              {filteredEvents.map((row) => {
                const details = eventDetails(row);
                const open = expandedEvent === row.id;
                return (
                  <button
                    key={row.id}
                    type="button"
                    className={`event-row ${AGENT_COLORS[row.agent] || ""}`}
                    onClick={() =>
                      setExpandedEvent((prev) => (prev === row.id ? null : row.id))
                    }
                  >
                    <div className="event-row-main event-row-main-detail">
                      <strong>{row.agent}</strong>
                      <span className="event-summary">{eventSummary(row)}</span>
                      <span className="muted-note">
                        {row.duration_ms != null ? `${row.duration_ms} ms` : ""}
                      </span>
                      <span className="muted-note">
                        {row.created_at
                          ? new Date(row.created_at).toLocaleString()
                          : ""}
                      </span>
                    </div>
                    {open ? (
                      <div className="event-expand">
                        {details.length > 0 ? (
                          <ul className="event-details">
                            {details.map((line) => (
                              <li key={line}>{line}</li>
                            ))}
                          </ul>
                        ) : null}
                        <pre className="event-payload">
                          {JSON.stringify(row.payload, null, 2)}
                        </pre>
                      </div>
                    ) : null}
                  </button>
                );
              })}
            </div>
          )}
        </section>
      ) : null}

      {tab === "proposals" ? (
        <section className="panel">
          <h2>Pending proposals</h2>
          {pending.length === 0 ? (
            <p className="empty">No pending proposals.</p>
          ) : (
            <div className="proposal-grid">
              {pending.map((row) => (
                <article key={row.id} className="proposal-card">
                  <header>
                    <strong>{row.symbol}</strong>
                    <span className="muted-note">
                      expires {formatCountdown(row.expires_at)}
                    </span>
                  </header>
                  <p>
                    Entry {row.entry} · Stop {row.stop} · Target {row.target}
                  </p>
                  <p>
                    Shares {row.shares ?? "—"} · Max loss {row.max_loss ?? "—"}
                  </p>
                  <p>
                    ORIN {row.orin_score ?? "—"} (
                    {row.orin_expected_move_percent ?? "—"}%) · Checklist{" "}
                    {row.checklist_score ?? "—"}
                  </p>
                  <p className="muted-note">{row.luma_reasoning}</p>
                  <div className="form-actions">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onApprove(row.id)}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy}
                      onClick={() => void onReject(row.id)}
                    >
                      Reject
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}

          <h2 style={{ marginTop: "1.5rem" }}>Vetoed (no approve)</h2>
          {vetoed.length === 0 ? (
            <p className="empty">No vetoed proposals.</p>
          ) : (
            <div className="proposal-grid">
              {vetoed.map((row) => (
                <article key={row.id} className="proposal-card vetoed">
                  <header>
                    <strong>{row.symbol}</strong>
                    <span className="earnings-badge risk-high">vetoed</span>
                  </header>
                  <p className="muted-note">{row.luma_reasoning}</p>
                  <ul>
                    {(row.vesk_result?.reasons || []).map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          )}
        </section>
      ) : null}

      {tab === "review" ? (
        <section className="panel">
          <div className="panel-header-row">
            <h2>DASH review</h2>
            <button type="button" disabled={busy} onClick={() => void onReview()}>
              Run review
            </button>
          </div>
          {!review ? (
            <p className="empty">No review yet.</p>
          ) : (
            <>
              <div className="summary-cards">
                <div className="summary-card">
                  <h3>Win rate</h3>
                  <p>{review.report.win_rate ?? "—"}</p>
                </div>
                <div className="summary-card">
                  <h3>Expectancy R</h3>
                  <p>{review.report.expectancy_r ?? "—"}</p>
                </div>
                <div className="summary-card">
                  <h3>Expired unapproved</h3>
                  <p>{review.report.expired_unapproved ?? 0}</p>
                </div>
                <div className="summary-card">
                  <h3>Slowest stage</h3>
                  <p>{review.report.slowest_stage ?? "—"}</p>
                </div>
              </div>

              <h3>Suggested experiments</h3>
              <ul>
                {(review.report.suggested_experiments || []).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>

              <h3>VESK veto reasons</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Reason</th>
                      <th>Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(review.report.veto_reasons || {}).map(
                      ([reason, count]) => (
                        <tr key={reason}>
                          <td>{reason}</td>
                          <td>{count}</td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>

              <h3>ORIN calibration</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Bucket</th>
                      <th>Count</th>
                      <th>Avg predicted</th>
                      <th>Avg actual</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(review.report.orin_calibration || []).map((row) => (
                      <tr key={String(row.bucket)}>
                        <td>{String(row.bucket)}</td>
                        <td>{String(row.count)}</td>
                        <td>{String(row.avg_predicted ?? "—")}</td>
                        <td>{String(row.avg_actual ?? "—")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h3>Trade grades</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Proposal</th>
                      <th>Symbol</th>
                      <th>Process</th>
                      <th>Outcome</th>
                      <th>R</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(review.report.grades || []).map((row) => (
                      <tr key={String(row.proposal_id)}>
                        <td>{String(row.proposal_id)}</td>
                        <td>{String(row.symbol)}</td>
                        <td>{String(row.process_grade)}</td>
                        <td>{String(row.outcome_grade)}</td>
                        <td>{String(row.r_multiple ?? "—")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      ) : null}
    </main>
  );
}
