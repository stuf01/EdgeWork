import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  CalculateResponse,
  ChartTimeframe,
  Checklist,
  ChecklistEvaluateResponse,
  NewsItem,
  TickerDetail,
  calculatePlan,
  createPlan,
  evaluateChecklist,
  getTickerDetail,
  getTickerNews,
  listChecklists,
} from "../api";
import Chart from "../components/Chart";
import {
  emptyPlanLevels,
  assessPlacement,
  nextPlacementStep,
  placementInstruction,
  type PlanLevels,
} from "../lib/planOnChart";
import { formatRuleComparison } from "../lib/checklistPanel";
import {
  readAccountSize,
  readRiskPercent,
  writeAccountSize,
  writeRiskPercent,
} from "../lib/planStorage";

const CHICAGO = "America/Chicago";

function formatRelativeTime(iso: string, now = new Date()): string {
  const then = new Date(iso).getTime();
  const diffMs = Math.max(0, now.getTime() - then);
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 48) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatChicagoFull(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    timeZone: CHICAGO,
    dateStyle: "medium",
    timeStyle: "short",
  });
}

const TIMEFRAME_OPTIONS: Array<{ value: ChartTimeframe; label: string }> = [
  { value: "1Min", label: "1m" },
  { value: "5Min", label: "5m" },
  { value: "15Min", label: "15m" },
  { value: "1Hour", label: "1h" },
  { value: "1Day", label: "1D" },
];

const TIMEFRAME_STORAGE_KEY = "edgework.chartTimeframe";

function readStoredTimeframe(): ChartTimeframe {
  try {
    const raw = window.localStorage.getItem(TIMEFRAME_STORAGE_KEY);
    if (TIMEFRAME_OPTIONS.some((option) => option.value === raw)) {
      return raw as ChartTimeframe;
    }
  } catch {
    // ignore storage errors
  }
  return "5Min";
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

function formatSignedPercent(value: string | null | undefined): string {
  if (value == null || value === "") {
    return "—";
  }
  const num = Number(value);
  if (Number.isNaN(num)) {
    return String(value);
  }
  const sign = num > 0 ? "+" : "";
  return `${sign}${num.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
}

type LevelRow = {
  key: string;
  label: string;
  value: string | null;
};

export default function TickerDetailPage() {
  const { symbol = "" } = useParams();
  const [timeframe, setTimeframe] = useState<ChartTimeframe>(readStoredTimeframe);
  const [detail, setDetail] = useState<TickerDetail | null>(null);
  const [pageLoading, setPageLoading] = useState(true);
  const [chartLoading, setChartLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [newsItems, setNewsItems] = useState<NewsItem[]>([]);
  const [newsCount24h, setNewsCount24h] = useState(0);
  const [hasRecentNews, setHasRecentNews] = useState(false);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [planMode, setPlanMode] = useState(false);
  const [planLevels, setPlanLevels] = useState<PlanLevels>(emptyPlanLevels);
  const [accountSize, setAccountSize] = useState(() => readAccountSize());
  const [riskPercent, setRiskPercent] = useState(() => readRiskPercent("1"));
  const [planNotes, setPlanNotes] = useState("");
  const [setupTag, setSetupTag] = useState("");
  const [isPaper, setIsPaper] = useState(true);
  const [calcResult, setCalcResult] = useState<CalculateResponse | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [checklists, setChecklists] = useState<Checklist[]>([]);
  const [checklistId, setChecklistId] = useState<number | null>(null);
  const [checklistEval, setChecklistEval] =
    useState<ChecklistEvaluateResponse | null>(null);
  const [checklistError, setChecklistError] = useState<string | null>(null);
  const [checklistBusy, setChecklistBusy] = useState(false);

  const placementStep = useMemo(
    () => nextPlacementStep(planLevels),
    [planLevels],
  );

  const onPlanLevelsChange = useCallback((levels: PlanLevels) => {
    setPlanLevels(levels);
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(TIMEFRAME_STORAGE_KEY, timeframe);
    } catch {
      // ignore storage errors
    }
  }, [timeframe]);

  useEffect(() => {
    writeAccountSize(accountSize);
  }, [accountSize]);

  useEffect(() => {
    writeRiskPercent(riskPercent);
  }, [riskPercent]);

  useEffect(() => {
    let cancelled = false;
    listChecklists()
      .then((rows) => {
        if (cancelled) {
          return;
        }
        setChecklists(rows);
        const preferred =
          rows.find((row) => row.name === "Breakout basics") ?? rows[0] ?? null;
        setChecklistId((prev) => prev ?? preferred?.id ?? null);
      })
      .catch(() => {
        // checklist UI is optional if list fails
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const runChecklistEvaluate = useCallback(async () => {
    if (
      !detail ||
      checklistId == null ||
      planLevels.entry == null ||
      planLevels.stop == null ||
      planLevels.target == null
    ) {
      return;
    }
    setChecklistBusy(true);
    setChecklistError(null);
    try {
      const result = await evaluateChecklist(checklistId, {
        symbol: detail.symbol,
        entry: String(planLevels.entry),
        stop: String(planLevels.stop),
        target: String(planLevels.target),
      });
      setChecklistEval(result);
    } catch (err: unknown) {
      setChecklistEval(null);
      setChecklistError(
        err instanceof ApiError ? err.message : "Checklist evaluate failed",
      );
    } finally {
      setChecklistBusy(false);
    }
  }, [checklistId, detail, planLevels]);

  useEffect(() => {
    if (
      planLevels.entry == null ||
      planLevels.stop == null ||
      planLevels.target == null
    ) {
      setCalcResult(null);
      setCalcError(null);
      return;
    }
    const handle = window.setTimeout(() => {
      calculatePlan({
        account_size: accountSize || "0",
        risk_percent: riskPercent || "0",
        entry: String(planLevels.entry),
        stop: String(planLevels.stop),
        target: String(planLevels.target),
      })
        .then((result) => {
          setCalcResult(result);
          setCalcError(null);
        })
        .catch((err: unknown) => {
          setCalcResult(null);
          setCalcError(
            err instanceof ApiError ? err.message : "Calculate failed",
          );
        });
    }, 200);
    return () => window.clearTimeout(handle);
  }, [accountSize, riskPercent, planLevels]);

  useEffect(() => {
    if (
      !planMode ||
      checklistId == null ||
      planLevels.entry == null ||
      planLevels.stop == null ||
      planLevels.target == null
    ) {
      return;
    }
    const handle = window.setTimeout(() => {
      void runChecklistEvaluate();
    }, 250);
    return () => window.clearTimeout(handle);
  }, [planMode, checklistId, planLevels, runChecklistEvaluate]);

  const detailRef = useRef(detail);
  detailRef.current = detail;

  const loadTickerDetail = useCallback(
    async (options: { refresh?: boolean; replacePage?: boolean } = {}) => {
      const refresh = Boolean(options.refresh);
      const replacePage = Boolean(options.replacePage);
      if (replacePage) {
        setPageLoading(true);
        setDetail(null);
      } else {
        setChartLoading(true);
      }
      setError(null);
      try {
        const payload = await getTickerDetail(symbol, timeframe, { refresh });
        setDetail(payload);
      } catch (err: unknown) {
        setError(
          err instanceof ApiError ? err.message : "Failed to load ticker",
        );
        if (replacePage) {
          setDetail(null);
        }
      } finally {
        setPageLoading(false);
        setChartLoading(false);
      }
    },
    [symbol, timeframe],
  );

  useEffect(() => {
    const current = detailRef.current;
    const replacePage =
      current === null || current.symbol !== symbol.toUpperCase();
    void loadTickerDetail({ replacePage });
  }, [loadTickerDetail, symbol]);

  useEffect(() => {
    let cancelled = false;
    setNewsLoading(true);
    setNewsError(null);
    getTickerNews(symbol)
      .then((payload) => {
        if (!cancelled) {
          setNewsItems(payload.items);
          setNewsCount24h(payload.count_last_24h);
          setHasRecentNews(payload.has_recent_news);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setNewsItems([]);
          setNewsCount24h(0);
          setHasRecentNews(false);
          setNewsError(
            err instanceof ApiError ? err.message : "Failed to load news",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setNewsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  async function copyPrice(label: string, value: string | null) {
    if (!value) {
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
      window.setTimeout(() => setCopied(null), 1500);
    } catch {
      setError(`Could not copy ${label} to clipboard`);
    }
  }

  function resetPlanLines() {
    setPlanLevels(emptyPlanLevels());
    setCalcResult(null);
    setCalcError(null);
    setSaveMessage(null);
  }

  async function savePlanFromChart() {
    if (
      !detail ||
      planLevels.entry == null ||
      planLevels.stop == null ||
      planLevels.target == null
    ) {
      return;
    }
    setSaving(true);
    setSaveMessage(null);
    try {
      const saved = await createPlan({
        symbol: detail.symbol,
        account_size: accountSize,
        risk_percent: riskPercent,
        entry: String(planLevels.entry),
        stop: String(planLevels.stop),
        target: String(planLevels.target),
        notes: planNotes.trim() ? planNotes.trim() : null,
        setup_tag: setupTag.trim() ? setupTag.trim() : null,
        is_paper: isPaper,
        checklist_id: checklistId,
      });
      setSaveMessage(`Saved plan #${saved.id} for ${saved.symbol}`);
    } catch (err: unknown) {
      setCalcError(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function plannerHref(): string {
    const params = new URLSearchParams();
    if (detail) {
      params.set("symbol", detail.symbol);
    }
    if (planLevels.entry != null) {
      params.set("entry", String(planLevels.entry));
    } else if (detail) {
      params.set("entry", detail.last_price);
    }
    if (planLevels.stop != null) {
      params.set("stop", String(planLevels.stop));
    }
    if (planLevels.target != null) {
      params.set("target", String(planLevels.target));
    }
    if (accountSize) {
      params.set("account_size", accountSize);
    }
    if (riskPercent) {
      params.set("risk_percent", riskPercent);
    }
    return `/?${params.toString()}`;
  }

  const placementReview = useMemo(() => {
    const account = Number(accountSize);
    const risk = Number(riskPercent);
    const last = detail ? Number(detail.last_price) : null;
    return assessPlacement(
      planLevels,
      Number.isFinite(account) ? account : 0,
      Number.isFinite(risk) ? risk : 0,
      Number.isFinite(last) ? last : null,
    );
  }, [accountSize, riskPercent, planLevels, detail]);

  const showVwap = timeframe !== "1Day";
  const levels: LevelRow[] = detail
    ? [
        { key: "pdh", label: "Prev day high", value: detail.levels.prev_day_high },
        { key: "pdl", label: "Prev day low", value: detail.levels.prev_day_low },
        {
          key: "pdc",
          label: "Prev day close",
          value: detail.levels.prev_day_close,
        },
        { key: "open", label: "Today open", value: detail.levels.today_open },
        {
          key: "vwap",
          label: "VWAP (last)",
          value: showVwap ? (detail.vwap.at(-1) ?? null) : null,
        },
        { key: "sma20", label: "SMA 20", value: detail.sma_20 },
        { key: "sma50", label: "SMA 50", value: detail.sma_50 },
      ]
    : [];

  return (
    <div className="page">
      <header className="header ticker-header">
        <div>
          <p className="breadcrumb">
            <Link to="/scanner">Scanner</Link> / {symbol.toUpperCase()}
          </p>
          <h1>{symbol.toUpperCase()}</h1>
          <p>Chart with VWAP (intraday) and key levels.</p>
        </div>
        {detail ? (
          <Link
            className="button-link"
            to={`/?symbol=${encodeURIComponent(detail.symbol)}&entry=${encodeURIComponent(detail.last_price)}`}
          >
            Plan trade
          </Link>
        ) : null}
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}
      {pageLoading ? <p className="empty">Loading ticker detail…</p> : null}

      {!pageLoading && detail ? (
        <div className="ticker-layout">
          <section className="panel chart-panel">
            <div className="chart-toolbar">
              <div className="timeframe-row" role="group" aria-label="Timeframe">
                {TIMEFRAME_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={
                      option.value === timeframe
                        ? "timeframe-btn active"
                        : "timeframe-btn"
                    }
                    disabled={chartLoading}
                    onClick={() => setTimeframe(option.value)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              <div className="chart-toolbar-actions">
                <button
                  type="button"
                  className="timeframe-btn"
                  disabled={chartLoading}
                  onClick={() => void loadTickerDetail({ refresh: true })}
                >
                  {chartLoading ? "Refreshing…" : "Refresh"}
                </button>
                <button
                  type="button"
                  className={planMode ? "timeframe-btn active" : "timeframe-btn"}
                  onClick={() => setPlanMode((prev) => !prev)}
                >
                  Plan on chart
                </button>
              </div>
            </div>
            {planMode ? (
              <p className="plan-instruction">{placementInstruction(placementStep)}</p>
            ) : null}
            <p className="chart-session-note">
              Chart times are Central. Regular session opens at 8:30 AM CT
              (9:30 AM Eastern) and closes at 3:00 PM CT (4:00 PM Eastern).
            </p>
            <div className="chart-stage">
              {chartLoading ? (
                <div className="chart-loading" role="status">
                  Loading {timeframe} bars…
                </div>
              ) : null}
              <Chart
                bars={detail.bars}
                vwap={detail.vwap}
                levels={detail.levels}
                timeframe={timeframe}
                showVwap={showVwap}
                planMode={planMode}
                planLevels={planLevels}
                onPlanLevelsChange={onPlanLevelsChange}
              />
            </div>
          </section>

          {planMode ? (
            <aside className="panel plan-panel">
              <h2>Chart plan</h2>
              <label>
                Account size ($)
                <input
                  value={accountSize}
                  onChange={(e) => setAccountSize(e.target.value)}
                  inputMode="decimal"
                />
              </label>
              <label>
                Risk percent (%)
                <input
                  value={riskPercent}
                  onChange={(e) => setRiskPercent(e.target.value)}
                  inputMode="decimal"
                />
              </label>
              <label>
                Notes (optional)
                <input
                  value={planNotes}
                  onChange={(e) => setPlanNotes(e.target.value)}
                  placeholder="Setup notes"
                />
              </label>
              <label>
                Setup tag (optional)
                <input
                  value={setupTag}
                  onChange={(e) => setSetupTag(e.target.value)}
                  placeholder="breakout"
                />
              </label>
              <label className="toggle-field">
                Paper trade
                <span className="toggle-row">
                  <input
                    type="checkbox"
                    checked={isPaper}
                    onChange={(e) => setIsPaper(e.target.checked)}
                  />
                  <span>{isPaper ? "Paper" : "Real"}</span>
                </span>
              </label>

              <label>
                Checklist
                <select
                  value={checklistId ?? ""}
                  onChange={(e) =>
                    setChecklistId(
                      e.target.value ? Number(e.target.value) : null,
                    )
                  }
                >
                  {checklists.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="secondary"
                disabled={
                  checklistBusy ||
                  checklistId == null ||
                  planLevels.entry == null ||
                  planLevels.stop == null ||
                  planLevels.target == null
                }
                onClick={() => void runChecklistEvaluate()}
              >
                {checklistBusy ? "Evaluating…" : "Evaluate"}
              </button>

              {checklistError ? (
                <div className="error-banner" role="alert">
                  {checklistError}
                </div>
              ) : null}
              {checklistEval ? (
                <div className="checklist-eval">
                  <div
                    className={
                      checklistEval.verdict === "Meets your rules"
                        ? "verdict-banner pass"
                        : "verdict-banner fail"
                    }
                    role="status"
                  >
                    <strong>{checklistEval.score}/100</strong> —{" "}
                    {checklistEval.verdict}
                  </div>
                  {checklistEval.verdict !== "Meets your rules" ? (
                    <div className="amber-note" role="status">
                      Rules not fully met — you can still save; the journal will
                      track how these setups perform.
                    </div>
                  ) : null}
                  <ul className="rule-results">
                    {checklistEval.results.map((row) => (
                      <li key={`${row.rule_type}-${row.label}`}>
                        <span
                          className={
                            row.passed === true
                              ? "rule-icon pass"
                              : row.passed === false
                                ? "rule-icon fail"
                                : "rule-icon unknown"
                          }
                          aria-hidden
                        >
                          {row.passed === true
                            ? "✓"
                            : row.passed === false
                              ? "✗"
                              : "?"}
                        </span>
                        <span className="rule-label">
                          {row.label}
                          {row.required ? (
                            <span className="required-badge">required</span>
                          ) : null}
                        </span>
                        <span className="rule-values">
                          {formatRuleComparison(
                            row.actual,
                            row.operator,
                            row.threshold,
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <dl className="summary-list">
                <div>
                  <dt>Entry</dt>
                  <dd>
                    {planLevels.entry != null
                      ? formatMoney(planLevels.entry)
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Stop</dt>
                  <dd>
                    {planLevels.stop != null
                      ? formatMoney(planLevels.stop)
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Target</dt>
                  <dd>
                    {planLevels.target != null
                      ? formatMoney(planLevels.target)
                      : "—"}
                  </dd>
                </div>
              </dl>

              {calcError ? (
                <div className="error-banner" role="alert">
                  {calcError}
                </div>
              ) : null}

              {placementReview ? (
                <div
                  className={`placement-review placement-${placementReview.verdict}`}
                  role="status"
                >
                  <strong>{placementReview.headline}</strong>
                  <ul>
                    {placementReview.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {calcResult?.shares === 0 ? (
                <div className="warning-banner" role="status">
                  Potential profit shows {formatMoney(0)} because size is 0
                  shares — your stop distance costs more per share than the
                  risk budget allows. Tighten the stop or raise account / risk
                  %.
                </div>
              ) : null}

              {calcResult ? (
                <dl className="summary-list">
                  <div>
                    <dt>Max risk</dt>
                    <dd>{formatMoney(calcResult.max_risk_dollars)}</dd>
                  </div>
                  <div>
                    <dt>Risk / share</dt>
                    <dd>{formatMoney(calcResult.risk_per_share)}</dd>
                  </div>
                  <div>
                    <dt>Shares</dt>
                    <dd>{calcResult.shares}</dd>
                  </div>
                  <div>
                    <dt>Actual risk</dt>
                    <dd>{formatMoney(calcResult.actual_risk_dollars)}</dd>
                  </div>
                  <div>
                    <dt>Potential profit</dt>
                    <dd>{formatMoney(calcResult.potential_profit)}</dd>
                  </div>
                  <div>
                    <dt>R:R</dt>
                    <dd>
                      {Number.isFinite(Number(calcResult.risk_reward_ratio))
                        ? `${Number(calcResult.risk_reward_ratio).toFixed(2)}:1`
                        : calcResult.risk_reward_ratio}
                    </dd>
                  </div>
                  <div>
                    <dt>Position cost</dt>
                    <dd>{formatMoney(calcResult.position_cost)}</dd>
                  </div>
                </dl>
              ) : null}

              {saveMessage ? (
                <p className="copy-toast" role="status">
                  {saveMessage}
                </p>
              ) : null}

              <div className="actions">
                <button type="button" className="secondary" onClick={resetPlanLines}>
                  Reset lines
                </button>
                <button
                  type="button"
                  disabled={
                    saving ||
                    planLevels.entry == null ||
                    planLevels.stop == null ||
                    planLevels.target == null ||
                    Boolean(calcError)
                  }
                  onClick={() => void savePlanFromChart()}
                >
                  {saving ? "Saving…" : "Save plan"}
                </button>
                <Link className="button-link" to={plannerHref()}>
                  Open in Planner
                </Link>
              </div>
            </aside>
          ) : (
          <aside className="panel summary-panel">
            <h2>Summary</h2>
            <dl className="summary-list">
              <div>
                <dt>Last price</dt>
                <dd>{formatMoney(detail.last_price)}</dd>
              </div>
              <div>
                <dt>Gap %</dt>
                <dd
                  className={
                    Number(detail.gap_percent) > 0
                      ? "gap-pos"
                      : Number(detail.gap_percent) < 0
                        ? "gap-neg"
                        : undefined
                  }
                >
                  {formatSignedPercent(detail.gap_percent)}
                </dd>
              </div>
            </dl>

            <h3>Levels</h3>
            <p className="muted copy-hint">Click a level to copy its price.</p>
            <ul className="level-list">
              {levels.map((item) => (
                <li key={item.key}>
                  <button
                    type="button"
                    className="level-btn"
                    disabled={!item.value}
                    onClick={() => void copyPrice(item.label, item.value)}
                  >
                    <span>{item.label}</span>
                    <strong>{formatMoney(item.value)}</strong>
                  </button>
                </li>
              ))}
            </ul>
            {copied ? (
              <p className="copy-toast" role="status">
                Copied {copied}
              </p>
            ) : null}
          </aside>
          )}

          <section className="panel news-panel">
            <h2>News</h2>
            {newsLoading ? <p className="empty">Loading news…</p> : null}
            {newsError ? (
              <div className="error-banner" role="alert">
                {newsError}
              </div>
            ) : null}
            {!newsLoading && !newsError ? (
              <p
                className={
                  hasRecentNews ? "news-status recent" : "news-status quiet"
                }
              >
                {hasRecentNews
                  ? `News in the last 24 hours: ${newsCount24h}`
                  : "No news in the last 24 hours"}
              </p>
            ) : null}
            {!newsLoading && !newsError && newsItems.length === 0 ? (
              <p className="empty">No headlines available for this symbol.</p>
            ) : null}
            {!newsLoading && newsItems.length > 0 ? (
              <ul className="news-list">
                {newsItems.map((item) => (
                  <li key={item.id}>
                    {item.url ? (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="news-headline"
                      >
                        {item.headline || "(untitled)"}
                      </a>
                    ) : (
                      <span className="news-headline">
                        {item.headline || "(untitled)"}
                      </span>
                    )}
                    <div className="news-meta">
                      <span>{item.source || "Unknown source"}</span>
                      <span
                        title={formatChicagoFull(item.created_at)}
                        className="news-time"
                      >
                        {formatRelativeTime(item.created_at)}
                      </span>
                    </div>
                    {item.summary ? (
                      <p className="news-summary">{item.summary}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        </div>
      ) : null}
    </div>
  );
}
