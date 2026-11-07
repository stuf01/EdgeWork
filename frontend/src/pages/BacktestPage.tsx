import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  ApiError,
  BacktestListItem,
  BacktestResult,
  BacktestStopRule,
  BacktestTrade,
  deleteBacktest,
  getBacktest,
  listBacktests,
  listWatchlist,
  runBacktest,
} from "../api";
import EquityCurveChart from "../components/EquityCurveChart";

type TradeSortKey =
  | "date"
  | "symbol"
  | "entry"
  | "exit"
  | "exit_reason"
  | "shares"
  | "pnl"
  | "r_multiple"
  | "gap_percent";

function defaultEnd(): string {
  return new Date().toISOString().slice(0, 10);
}

function defaultStart(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 1);
  return d.toISOString().slice(0, 10);
}

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

function flatSummary(
  summary: BacktestResult["summary"] | BacktestListItem["summary"] | Record<string, unknown>,
): BacktestResult["summary"] {
  if (
    summary &&
    typeof summary === "object" &&
    "total_trades" in summary &&
    typeof (summary as { total_trades: unknown }).total_trades === "number"
  ) {
    return summary as BacktestResult["summary"];
  }
  const nested = (summary as { summary?: BacktestResult["summary"] } | null)?.summary;
  if (nested && typeof nested.total_trades === "number") {
    return nested;
  }
  return {
    total_trades: 0,
    wins: 0,
    losses: 0,
    win_rate: "0",
    avg_win: "0",
    avg_loss: "0",
    avg_r: null,
    expectancy_r: null,
    total_pnl: "0",
    best_trade: null,
    worst_trade: null,
    max_drawdown: "0",
  };
}

function SummaryCards({
  summary,
}: {
  summary: BacktestResult["summary"] | BacktestListItem["summary"];
}) {
  summary = flatSummary(summary);
  return (
    <div className="stats-grid">
      <div className="stat-card">
        <h3>Total trades</h3>
        <p>{summary.total_trades}</p>
      </div>
      <div className="stat-card">
        <h3>Win rate</h3>
        <p>{formatPct(summary.win_rate)}</p>
      </div>
      <div className="stat-card">
        <h3>Expectancy (R)</h3>
        <p>{formatR(summary.expectancy_r)}</p>
      </div>
      <div className="stat-card">
        <h3>Total P&amp;L</h3>
        <p className={pnlClass(summary.total_pnl)}>
          {formatMoney(summary.total_pnl)}
        </p>
      </div>
      <div className="stat-card">
        <h3>Max drawdown</h3>
        <p>{formatMoney(summary.max_drawdown)}</p>
      </div>
      <div className="stat-card">
        <h3>Avg win</h3>
        <p className="pnl-pos">{formatMoney(summary.avg_win)}</p>
      </div>
      <div className="stat-card">
        <h3>Avg loss</h3>
        <p className="pnl-neg">{formatMoney(summary.avg_loss)}</p>
      </div>
    </div>
  );
}

export default function BacktestPage() {
  const [name, setName] = useState("");
  const [symbolsText, setSymbolsText] = useState("");
  const [useWatchlist, setUseWatchlist] = useState(false);
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(defaultEnd);
  const [minGapPercent, setMinGapPercent] = useState("2");
  const [minRelativeVolume, setMinRelativeVolume] = useState("2");
  const [minPrice, setMinPrice] = useState("5");
  const [minAvgVolume, setMinAvgVolume] = useState("500000");
  const [stopRule, setStopRule] = useState<BacktestStopRule>("fixed_percent");
  const [stopPercent, setStopPercent] = useState("2");
  const [targetR, setTargetR] = useState("2");
  const [costPerShare, setCostPerShare] = useState("0.02");
  const [riskPercent, setRiskPercent] = useState("1");
  const [startingAccount, setStartingAccount] = useState("10000");

  const [result, setResult] = useState<BacktestResult | null>(null);
  const [pastRuns, setPastRuns] = useState<BacktestListItem[]>([]);
  const [compareIds, setCompareIds] = useState<number[]>([]);
  const [compareA, setCompareA] = useState<BacktestResult | null>(null);
  const [compareB, setCompareB] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [sortKey, setSortKey] = useState<TradeSortKey>("date");
  const [sortAsc, setSortAsc] = useState(false);
  const resultsRef = useRef<HTMLElement | null>(null);

  const refreshRuns = useCallback(async () => {
    try {
      const rows = await listBacktests();
      setPastRuns(rows);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Failed to load past runs";
      setError(message);
    }
  }, []);

  useEffect(() => {
    void refreshRuns();
  }, [refreshRuns]);

  const fillWatchlist = async () => {
    setError(null);
    try {
      const items = await listWatchlist();
      setSymbolsText(items.map((item) => item.symbol).join(", "));
      setUseWatchlist(true);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Failed to load watchlist";
      setError(message);
    }
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const symbols = symbolsText
        .split(",")
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);
      const payload = await runBacktest({
        symbols: symbols.length ? symbols : undefined,
        use_watchlist: useWatchlist || symbols.length === 0,
        start_date: startDate,
        end_date: endDate,
        name: name.trim() || null,
        min_gap_percent: minGapPercent,
        min_relative_volume: minRelativeVolume,
        min_price: minPrice,
        min_avg_volume: minAvgVolume,
        entry_rule: "break_prev_high",
        stop_rule: stopRule,
        stop_percent: stopPercent,
        target_r: targetR,
        cost_per_share: costPerShare,
        risk_per_trade_percent: riskPercent,
        starting_account: startingAccount,
      });
      showResult(payload);
      await refreshRuns();
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Backtest failed";
      setError(message);
    } finally {
      setBusy(false);
    }
  };

  const showResult = (payload: BacktestResult) => {
    setResult(payload);
    setCompareA(null);
    setCompareB(null);
    setCompareIds([]);
    requestAnimationFrame(() => {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  const openRun = async (id: number) => {
    setBusy(true);
    setError(null);
    try {
      const payload = await getBacktest(id);
      showResult(payload);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Failed to open run";
      setError(message);
    } finally {
      setBusy(false);
    }
  };

  const removeRun = async (id: number) => {
    setBusy(true);
    setError(null);
    try {
      await deleteBacktest(id);
      if (result?.id === id) {
        setResult(null);
      }
      setCompareIds((prev) => prev.filter((x) => x !== id));
      await refreshRuns();
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Failed to delete run";
      setError(message);
    } finally {
      setBusy(false);
    }
  };

  const toggleCompare = (id: number) => {
    setCompareIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((x) => x !== id);
      }
      if (prev.length >= 2) {
        const second = prev[1];
        return second === undefined ? [id] : [second, id];
      }
      return [...prev, id];
    });
  };

  const runCompare = async () => {
    const idA = compareIds[0];
    const idB = compareIds[1];
    if (idA === undefined || idB === undefined || compareIds.length !== 2) {
      setError("Select exactly two past runs to compare");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const [a, b] = await Promise.all([getBacktest(idA), getBacktest(idB)]);
      setCompareA(a);
      setCompareB(b);
      setResult(null);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Compare failed";
      setError(message);
    } finally {
      setBusy(false);
    }
  };

  const sortedTrades = useMemo(() => {
    if (!result) {
      return [] as BacktestTrade[];
    }
    const rows = [...result.trades];
    rows.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      let cmp = 0;
      if (typeof av === "number" && typeof bv === "number") {
        cmp = av - bv;
      } else {
        const an = Number(av);
        const bn = Number(bv);
        if (!Number.isNaN(an) && !Number.isNaN(bn) && String(av) !== "" && String(bv) !== "") {
          cmp = an - bn;
        } else {
          cmp = String(av).localeCompare(String(bv));
        }
      }
      return sortAsc ? cmp : -cmp;
    });
    return rows;
  }, [result, sortKey, sortAsc]);

  const toggleSort = (key: TradeSortKey) => {
    if (sortKey === key) {
      setSortAsc((v) => !v);
    } else {
      setSortKey(key);
      setSortAsc(key === "symbol" || key === "exit_reason");
    }
  };

  const yearRows = useMemo(() => {
    if (!result) {
      return [];
    }
    return Object.entries(result.by_year).sort(([a], [b]) => a.localeCompare(b));
  }, [result]);

  return (
    <main className="page backtest-page">
      <header className="page-header">
        <h1>Backtest</h1>
        <p className="lede">
          Long-side daily gap-and-breakout simulation with planner-style sizing.
        </p>
      </header>

      {error ? (
        <div className="error-banner" role="alert">
          {error}
        </div>
      ) : null}

      <section className="panel">
        <h2>Parameters</h2>
        <form className="form-grid backtest-form" onSubmit={onSubmit}>
          <label>
            Name (optional)
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Gap breakout Q1"
            />
          </label>
          <label className="span-2">
            Symbols (comma-separated)
            <input
              value={symbolsText}
              onChange={(e) => {
                setSymbolsText(e.target.value);
                setUseWatchlist(false);
              }}
              placeholder="AAPL, MSFT, NVDA"
            />
          </label>
          <div className="form-actions span-2">
            <button type="button" className="secondary" onClick={() => void fillWatchlist()}>
              Use my watchlist
            </button>
            {useWatchlist ? (
              <span className="muted-note">Watchlist will be included on run.</span>
            ) : null}
          </div>
          <label>
            Start date
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              required
            />
          </label>
          <label>
            End date
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              required
            />
          </label>
          <label>
            Min gap %
            <input
              value={minGapPercent}
              onChange={(e) => setMinGapPercent(e.target.value)}
              required
            />
          </label>
          <label>
            Min relative volume
            <input
              value={minRelativeVolume}
              onChange={(e) => setMinRelativeVolume(e.target.value)}
              required
            />
          </label>
          <label>
            Min price
            <input
              value={minPrice}
              onChange={(e) => setMinPrice(e.target.value)}
              required
            />
          </label>
          <label>
            Min avg volume
            <input
              value={minAvgVolume}
              onChange={(e) => setMinAvgVolume(e.target.value)}
              required
            />
          </label>
          <label>
            Stop rule
            <select
              value={stopRule}
              onChange={(e) => setStopRule(e.target.value as BacktestStopRule)}
            >
              <option value="fixed_percent">Fixed percent</option>
              <option value="prev_day_low">Previous day low</option>
              <option value="today_open">Today&apos;s open</option>
            </select>
          </label>
          <label>
            Stop percent
            <input
              value={stopPercent}
              onChange={(e) => setStopPercent(e.target.value)}
              required
              disabled={stopRule !== "fixed_percent"}
            />
          </label>
          <label>
            Target R
            <input
              value={targetR}
              onChange={(e) => setTargetR(e.target.value)}
              required
            />
          </label>
          <label>
            Cost per share
            <input
              value={costPerShare}
              onChange={(e) => setCostPerShare(e.target.value)}
              required
            />
          </label>
          <label>
            Risk per trade %
            <input
              value={riskPercent}
              onChange={(e) => setRiskPercent(e.target.value)}
              required
            />
          </label>
          <label>
            Starting account
            <input
              value={startingAccount}
              onChange={(e) => setStartingAccount(e.target.value)}
              required
            />
          </label>
          <div className="form-actions span-2">
            <button type="submit" disabled={busy}>
              {busy ? "Running…" : "Run backtest"}
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="panel-header-row">
          <h2>Past runs</h2>
          <button
            type="button"
            className="secondary"
            disabled={busy || compareIds.length !== 2}
            onClick={() => void runCompare()}
          >
            Compare selected
          </button>
        </div>
        {pastRuns.length === 0 ? (
          <p className="muted-note">No saved runs yet.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Compare</th>
                <th>When</th>
                <th>Name</th>
                <th>Range</th>
                <th>Trades</th>
                <th>P&amp;L</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {pastRuns.map((run) => {
                const stats = flatSummary(run.summary);
                return (
                <tr key={run.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={compareIds.includes(run.id)}
                      onChange={() => toggleCompare(run.id)}
                      aria-label={`Select run ${run.id} for compare`}
                    />
                  </td>
                  <td>{new Date(run.created_at).toLocaleString()}</td>
                  <td>{run.name || `Run #${run.id}`}</td>
                  <td>
                    {run.start_date} → {run.end_date}
                  </td>
                  <td>{stats.total_trades}</td>
                  <td className={pnlClass(stats.total_pnl)}>
                    {formatMoney(stats.total_pnl)}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button type="button" onClick={() => void openRun(run.id)}>
                        Open
                      </button>
                      <button
                        type="button"
                        className="danger"
                        onClick={() => void removeRun(run.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              );
              })}
            </tbody>
          </table>
        )}
      </section>

      {compareA && compareB ? (
        <section className="panel">
          <h2>Compare</h2>
          <div className="compare-grid">
            <div>
              <h3>
                {compareA.name || `Run #${compareA.id}`}{" "}
                <span className="muted-note">
                  ({compareA.start_date} → {compareA.end_date})
                </span>
              </h3>
              <SummaryCards summary={compareA.summary} />
            </div>
            <div>
              <h3>
                {compareB.name || `Run #${compareB.id}`}{" "}
                <span className="muted-note">
                  ({compareB.start_date} → {compareB.end_date})
                </span>
              </h3>
              <SummaryCards summary={compareB.summary} />
            </div>
          </div>
        </section>
      ) : null}

      {result ? (
        <section className="panel results-panel" ref={resultsRef}>
          <div className="assumptions-notice">
            <strong>Assumptions:</strong> On same-day stop and target conflicts,
            the stop is assumed hit first. Estimated spread/slippage costs are
            subtracted per share. Simulation uses daily bars only (no intraday
            path). Free single-exchange market data may differ from your live
            fills. Past results do not predict future results.
          </div>

          {result.summary.total_trades < 100 ? (
            <div className="warning-banner" role="status">
              Fewer than 100 trades — treat these stats as fragile and
              directional only.
            </div>
          ) : null}

          {result.errors.length > 0 ? (
            <div className="warning-banner" role="status">
              Symbol errors:{" "}
              {result.errors
                .map((e) => `${e.symbol}: ${e.error}`)
                .join("; ")}
            </div>
          ) : null}

          <h2>
            Results
            {result.name ? ` — ${result.name}` : ` — Run #${result.id}`}
          </h2>
          <p className="muted-note">
            {result.symbols.join(", ")} · {result.start_date} → {result.end_date}{" "}
            · skipped days (insufficient history): {result.skipped_days}
          </p>

          <SummaryCards summary={result.summary} />

          <h3>Equity curve</h3>
          <EquityCurveChart points={result.equity_curve} />

          <h3>By year</h3>
          {yearRows.length === 0 ? (
            <p className="muted-note">No yearly breakdown.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Year</th>
                  <th>Trades</th>
                  <th>Win rate</th>
                  <th>Expectancy</th>
                  <th>Total P&amp;L</th>
                  <th>Max DD</th>
                </tr>
              </thead>
              <tbody>
                {yearRows.map(([year, stats]) => (
                  <tr key={year}>
                    <td>{year}</td>
                    <td>{stats.total_trades}</td>
                    <td>{formatPct(stats.win_rate)}</td>
                    <td>{formatR(stats.expectancy_r)}</td>
                    <td className={pnlClass(stats.total_pnl)}>
                      {formatMoney(stats.total_pnl)}
                    </td>
                    <td>{formatMoney(stats.max_drawdown)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h3>Trades</h3>
          <table className="data-table">
            <thead>
              <tr>
                {(
                  [
                    ["date", "Date"],
                    ["symbol", "Symbol"],
                    ["entry", "Entry"],
                    ["exit", "Exit"],
                    ["exit_reason", "Exit reason"],
                    ["shares", "Shares"],
                    ["pnl", "P&L"],
                    ["r_multiple", "R"],
                    ["gap_percent", "Gap %"],
                  ] as Array<[TradeSortKey, string]>
                ).map(([key, label]) => (
                  <th key={key}>
                    <button
                      type="button"
                      className="sort-btn"
                      onClick={() => toggleSort(key)}
                    >
                      {label}
                      {sortKey === key ? (sortAsc ? " ↑" : " ↓") : ""}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedTrades.length === 0 ? (
                <tr>
                  <td colSpan={9}>No trades in this run.</td>
                </tr>
              ) : (
                sortedTrades.map((trade, idx) => (
                  <tr key={`${trade.symbol}-${trade.date}-${idx}`}>
                    <td>{trade.date}</td>
                    <td>{trade.symbol}</td>
                    <td>{formatMoney(trade.entry)}</td>
                    <td>{formatMoney(trade.exit)}</td>
                    <td>{trade.exit_reason}</td>
                    <td>{trade.shares}</td>
                    <td className={pnlClass(trade.pnl)}>
                      {formatMoney(trade.pnl)}
                    </td>
                    <td>{formatR(trade.r_multiple)}</td>
                    <td>{Number(trade.gap_percent).toFixed(2)}%</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      ) : null}
    </main>
  );
}
