import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  ExitReason,
  JournalStatsResponse,
  TradePlanResponse,
  deletePlan,
  getJournalStats,
  listPlans,
  updatePlan,
} from "../api";
import CumPnlChart from "../components/CumPnlChart";

type PaperFilter = "all" | "paper" | "real";
type SortKey =
  | "created_at"
  | "symbol"
  | "status"
  | "setup_tag"
  | "entry"
  | "realized_pnl"
  | "r_multiple";

type DialogMode =
  | { kind: "open"; plan: TradePlanResponse }
  | { kind: "close"; plan: TradePlanResponse }
  | { kind: "edit"; plan: TradePlanResponse }
  | null;

function formatMoney(value: string | number | null | undefined): string {
  if (value == null || value === "") {
    return "—";
  }
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num)) {
    return String(value);
  }
  return num.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatR(value: string | null | undefined): string {
  if (value == null || value === "") {
    return "—";
  }
  const num = Number(value);
  if (Number.isNaN(num)) {
    return String(value);
  }
  return `${num.toFixed(2)}R`;
}

function formatPct(rate: string): string {
  const num = Number(rate);
  if (Number.isNaN(num)) {
    return rate;
  }
  return `${(num * 100).toFixed(1)}%`;
}

function pnlClass(value: string | null | undefined): string | undefined {
  if (value == null) {
    return undefined;
  }
  const num = Number(value);
  if (Number.isNaN(num) || num === 0) {
    return undefined;
  }
  return num > 0 ? "pnl-pos" : "pnl-neg";
}

const EXIT_REASONS: Array<{ value: ExitReason; label: string }> = [
  { value: "target_hit", label: "Target hit" },
  { value: "stop_hit", label: "Stop hit" },
  { value: "manual_exit", label: "Manual exit" },
  { value: "other", label: "Other" },
];

export default function JournalPage() {
  const [plans, setPlans] = useState<TradePlanResponse[]>([]);
  const [stats, setStats] = useState<JournalStatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [paperFilter, setPaperFilter] = useState<PaperFilter>("all");
  const [tagFilter, setTagFilter] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("created_at");
  const [sortAsc, setSortAsc] = useState(false);
  const [dialog, setDialog] = useState<DialogMode>(null);
  const [dialogEntry, setDialogEntry] = useState("");
  const [dialogShares, setDialogShares] = useState("");
  const [dialogExit, setDialogExit] = useState("");
  const [dialogReason, setDialogReason] = useState<ExitReason>("manual_exit");
  const [dialogLessons, setDialogLessons] = useState("");
  const [dialogNotes, setDialogNotes] = useState("");
  const [dialogTag, setDialogTag] = useState("");

  const tagSuggestions = useMemo(() => {
    const tags = new Set<string>();
    for (const plan of plans) {
      if (plan.setup_tag) {
        tags.add(plan.setup_tag);
      }
    }
    return Array.from(tags).sort();
  }, [plans]);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const query = {
        is_paper:
          paperFilter === "all" ? null : paperFilter === "paper" ? true : false,
        setup_tag: tagFilter.trim() || null,
        from: fromDate ? new Date(`${fromDate}T00:00:00Z`).toISOString() : null,
        to: toDate ? new Date(`${toDate}T23:59:59Z`).toISOString() : null,
      };
      const [planRows, statsPayload] = await Promise.all([
        listPlans(),
        getJournalStats(query),
      ]);
      setPlans(planRows);
      setStats(statsPayload);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Failed to load journal");
    } finally {
      setBusy(false);
    }
  }, [paperFilter, tagFilter, fromDate, toDate]);

  useEffect(() => {
    void load();
  }, [load]);

  const filteredPlans = useMemo(() => {
    let rows = [...plans];
    if (paperFilter === "paper") {
      rows = rows.filter((p) => p.is_paper);
    } else if (paperFilter === "real") {
      rows = rows.filter((p) => !p.is_paper);
    }
    if (tagFilter.trim()) {
      const tag = tagFilter.trim().toLowerCase();
      rows = rows.filter((p) => (p.setup_tag ?? "").toLowerCase() === tag);
    }
    if (fromDate) {
      const fromMs = new Date(`${fromDate}T00:00:00Z`).getTime();
      rows = rows.filter((p) => new Date(p.created_at).getTime() >= fromMs);
    }
    if (toDate) {
      const toMs = new Date(`${toDate}T23:59:59Z`).getTime();
      rows = rows.filter((p) => new Date(p.created_at).getTime() <= toMs);
    }
    rows.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const aNum = av == null ? Number.NEGATIVE_INFINITY : Number(av);
      const bNum = bv == null ? Number.NEGATIVE_INFINITY : Number(bv);
      let cmp = 0;
      if (
        sortKey === "realized_pnl" ||
        sortKey === "r_multiple" ||
        sortKey === "entry"
      ) {
        cmp = aNum - bNum;
      } else {
        cmp = String(av ?? "").localeCompare(String(bv ?? ""));
      }
      return sortAsc ? cmp : -cmp;
    });
    return rows;
  }, [plans, paperFilter, tagFilter, fromDate, toDate, sortKey, sortAsc]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc((prev) => !prev);
    } else {
      setSortKey(key);
      setSortAsc(key === "symbol" || key === "status" || key === "setup_tag");
    }
  }

  function openMarkOpen(plan: TradePlanResponse) {
    setDialog({ kind: "open", plan });
    setDialogEntry(plan.entry);
    setDialogShares(String(plan.shares));
  }

  function openClose(plan: TradePlanResponse) {
    setDialog({ kind: "close", plan });
    setDialogExit(plan.target);
    setDialogReason("manual_exit");
    setDialogLessons(plan.lessons ?? "");
  }

  function openEdit(plan: TradePlanResponse) {
    setDialog({ kind: "edit", plan });
    setDialogTag(plan.setup_tag ?? "");
    setDialogNotes(plan.notes ?? "");
    setDialogLessons(plan.lessons ?? "");
  }

  async function submitDialog() {
    if (!dialog) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (dialog.kind === "open") {
        await updatePlan(dialog.plan.id, {
          status: "open",
          actual_entry: dialogEntry,
          shares_traded: Number(dialogShares),
        });
      } else if (dialog.kind === "close") {
        await updatePlan(dialog.plan.id, {
          status: "closed",
          actual_exit: dialogExit,
          exit_reason: dialogReason,
          lessons: dialogLessons.trim() || null,
        });
      } else {
        await updatePlan(dialog.plan.id, {
          setup_tag: dialogTag.trim() || null,
          notes: dialogNotes.trim() || null,
          lessons: dialogLessons.trim() || null,
        });
      }
      setDialog(null);
      await load();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }

  async function skipPlan(plan: TradePlanResponse) {
    setBusy(true);
    setError(null);
    try {
      await updatePlan(plan.id, { status: "skipped" });
      await load();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Skip failed");
    } finally {
      setBusy(false);
    }
  }

  async function removePlan(plan: TradePlanResponse) {
    if (!window.confirm(`Delete plan #${plan.id} (${plan.symbol})?`)) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deletePlan(plan.id);
      await load();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  }

  const overall = stats?.overall;
  const closedCount = overall?.total_trades ?? 0;

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1>Trade Journal</h1>
          <p>Review closed trades, expectancy, and setup performance.</p>
        </div>
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}
      {closedCount > 0 && closedCount < 30 ? (
        <div className="amber-note" role="status">
          Results from a small number of trades can be misleading.
        </div>
      ) : null}

      <section className="panel journal-filters">
        <label>
          Paper / real
          <select
            value={paperFilter}
            onChange={(e) => setPaperFilter(e.target.value as PaperFilter)}
          >
            <option value="all">All</option>
            <option value="paper">Paper</option>
            <option value="real">Real</option>
          </select>
        </label>
        <label>
          Setup tag
          <input
            list="journal-tag-suggestions"
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            placeholder="All tags"
          />
        </label>
        <label>
          From
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
          />
        </label>
        <button type="button" className="secondary" disabled={busy} onClick={() => void load()}>
          Refresh
        </button>
      </section>

      {overall ? (
        <section className="stats-grid">
          <article className="stat-card">
            <h3>Total trades</h3>
            <p>{overall.total_trades}</p>
          </article>
          <article className="stat-card">
            <h3>Win rate</h3>
            <p>{formatPct(overall.win_rate)}</p>
          </article>
          <article className="stat-card">
            <h3>Expectancy (R)</h3>
            <p>{overall.expectancy_r != null ? formatR(overall.expectancy_r) : "—"}</p>
          </article>
          <article className="stat-card">
            <h3>Total P&L</h3>
            <p className={pnlClass(overall.total_pnl)}>
              {formatMoney(overall.total_pnl)}
            </p>
          </article>
          <article className="stat-card">
            <h3>Average win</h3>
            <p className="pnl-pos">{formatMoney(overall.avg_win)}</p>
          </article>
          <article className="stat-card">
            <h3>Average loss</h3>
            <p className="pnl-neg">{formatMoney(overall.avg_loss)}</p>
          </article>
          <article className="stat-card">
            <h3>Max drawdown</h3>
            <p className="pnl-neg">{formatMoney(overall.max_drawdown)}</p>
          </article>
        </section>
      ) : null}

      {stats?.by_checklist_score ? (
        <section className="panel checklist-compare">
          <h2>Checklist score</h2>
          <p className="muted">
            Closed trades that met rules (score ≥ 70) vs those that did not.
          </p>
          <div className="stats-grid">
            <article className="stat-card">
              <h3>Met rules</h3>
              <p>{stats.by_checklist_score.met.count} trades</p>
              <p className="muted tiny">
                Win {formatPct(stats.by_checklist_score.met.win_rate)} · Exp{" "}
                {stats.by_checklist_score.met.expectancy_r != null
                  ? formatR(stats.by_checklist_score.met.expectancy_r)
                  : "—"}
              </p>
            </article>
            <article className="stat-card">
              <h3>Below 70</h3>
              <p>{stats.by_checklist_score.below.count} trades</p>
              <p className="muted tiny">
                Win {formatPct(stats.by_checklist_score.below.win_rate)} · Exp{" "}
                {stats.by_checklist_score.below.expectancy_r != null
                  ? formatR(stats.by_checklist_score.below.expectancy_r)
                  : "—"}
              </p>
            </article>
          </div>
        </section>
      ) : null}

      <section className="panel">
        <h2>Cumulative P&L</h2>
        {stats && stats.cumulative_pnl.length > 0 ? (
          <CumPnlChart points={stats.cumulative_pnl} />
        ) : (
          <p className="empty">No closed trades yet for this filter.</p>
        )}
      </section>

      <section className="panel">
        <h2>By setup</h2>
        {stats && stats.by_tag.length > 0 ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Tag</th>
                  <th>Trades</th>
                  <th>Win rate</th>
                  <th>Expectancy</th>
                  <th>Total P&L</th>
                  <th>Avg win</th>
                  <th>Avg loss</th>
                  <th>Max DD</th>
                </tr>
              </thead>
              <tbody>
                {stats.by_tag.map((row) => (
                  <tr key={row.tag}>
                    <td>{row.tag}</td>
                    <td>{row.total_trades}</td>
                    <td>{formatPct(row.win_rate)}</td>
                    <td>{row.expectancy_r != null ? formatR(row.expectancy_r) : "—"}</td>
                    <td className={pnlClass(row.total_pnl)}>
                      {formatMoney(row.total_pnl)}
                    </td>
                    <td className="pnl-pos">{formatMoney(row.avg_win)}</td>
                    <td className="pnl-neg">{formatMoney(row.avg_loss)}</td>
                    <td className="pnl-neg">{formatMoney(row.max_drawdown)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty">No tagged closed trades yet.</p>
        )}
      </section>

      <section className="panel">
        <h2>All plans</h2>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>
                  <button type="button" className="sort-btn" onClick={() => toggleSort("created_at")}>
                    Date
                  </button>
                </th>
                <th>
                  <button type="button" className="sort-btn" onClick={() => toggleSort("symbol")}>
                    Symbol
                  </button>
                </th>
                <th>
                  <button type="button" className="sort-btn" onClick={() => toggleSort("status")}>
                    Status
                  </button>
                </th>
                <th>
                  <button type="button" className="sort-btn" onClick={() => toggleSort("setup_tag")}>
                    Setup
                  </button>
                </th>
                <th>Entry / Stop / Target</th>
                <th>
                  <button type="button" className="sort-btn" onClick={() => toggleSort("realized_pnl")}>
                    Result $
                  </button>
                </th>
                <th>
                  <button type="button" className="sort-btn" onClick={() => toggleSort("r_multiple")}>
                    Result R
                  </button>
                </th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredPlans.map((plan) => (
                <tr key={plan.id}>
                  <td>{new Date(plan.created_at).toLocaleDateString()}</td>
                  <td>
                    <strong>{plan.symbol}</strong>
                    <div className="muted tiny">
                      {plan.is_paper ? "paper" : "real"}
                    </div>
                  </td>
                  <td>
                    <span className={`status-pill status-${plan.status}`}>
                      {plan.status}
                    </span>
                  </td>
                  <td>{plan.setup_tag ?? "—"}</td>
                  <td className="levels-cell">
                    {formatMoney(plan.entry)} / {formatMoney(plan.stop)} /{" "}
                    {formatMoney(plan.target)}
                  </td>
                  <td className={pnlClass(plan.realized_pnl)}>
                    {plan.status === "closed"
                      ? formatMoney(plan.realized_pnl)
                      : "—"}
                  </td>
                  <td className={pnlClass(plan.realized_pnl)}>
                    {plan.status === "closed" ? formatR(plan.r_multiple) : "—"}
                  </td>
                  <td>
                    <div className="row-actions">
                      {plan.status === "planned" ? (
                        <>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => openMarkOpen(plan)}
                          >
                            Mark open
                          </button>
                          <button
                            type="button"
                            className="secondary"
                            disabled={busy}
                            onClick={() => void skipPlan(plan)}
                          >
                            Skip
                          </button>
                        </>
                      ) : null}
                      {plan.status === "open" ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => openClose(plan)}
                        >
                          Close trade
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="secondary"
                        disabled={busy}
                        onClick={() => openEdit(plan)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="danger"
                        disabled={busy}
                        onClick={() => void removePlan(plan)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {filteredPlans.length === 0 ? (
          <p className="empty">No plans match these filters.</p>
        ) : null}
      </section>

      <datalist id="journal-tag-suggestions">
        {tagSuggestions.map((tag) => (
          <option key={tag} value={tag} />
        ))}
      </datalist>

      {dialog ? (
        <div className="modal-backdrop" role="presentation">
          <div className="modal" role="dialog" aria-modal="true">
            <h2>
              {dialog.kind === "open"
                ? `Mark open — ${dialog.plan.symbol}`
                : dialog.kind === "close"
                  ? `Close trade — ${dialog.plan.symbol}`
                  : `Edit — ${dialog.plan.symbol}`}
            </h2>
            {dialog.kind === "open" ? (
              <>
                <label>
                  Actual entry
                  <input
                    value={dialogEntry}
                    onChange={(e) => setDialogEntry(e.target.value)}
                    inputMode="decimal"
                  />
                </label>
                <label>
                  Shares
                  <input
                    value={dialogShares}
                    onChange={(e) => setDialogShares(e.target.value)}
                    inputMode="numeric"
                  />
                </label>
              </>
            ) : null}
            {dialog.kind === "close" ? (
              <>
                <label>
                  Actual exit
                  <input
                    value={dialogExit}
                    onChange={(e) => setDialogExit(e.target.value)}
                    inputMode="decimal"
                  />
                </label>
                <label>
                  Exit reason
                  <select
                    value={dialogReason}
                    onChange={(e) =>
                      setDialogReason(e.target.value as ExitReason)
                    }
                  >
                    {EXIT_REASONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Lessons (optional)
                  <textarea
                    value={dialogLessons}
                    onChange={(e) => setDialogLessons(e.target.value)}
                    rows={3}
                  />
                </label>
              </>
            ) : null}
            {dialog.kind === "edit" ? (
              <>
                <label>
                  Setup tag
                  <input
                    list="journal-tag-suggestions"
                    value={dialogTag}
                    onChange={(e) => setDialogTag(e.target.value)}
                    placeholder="breakout, pullback…"
                  />
                </label>
                <label>
                  Notes
                  <textarea
                    value={dialogNotes}
                    onChange={(e) => setDialogNotes(e.target.value)}
                    rows={2}
                  />
                </label>
                <label>
                  Lessons
                  <textarea
                    value={dialogLessons}
                    onChange={(e) => setDialogLessons(e.target.value)}
                    rows={3}
                  />
                </label>
              </>
            ) : null}
            <div className="actions">
              <button
                type="button"
                className="secondary"
                onClick={() => setDialog(null)}
              >
                Cancel
              </button>
              <button type="button" disabled={busy} onClick={() => void submitDialog()}>
                Save
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
