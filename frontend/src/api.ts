/** Typed API client mirroring backend pydantic schemas. */

export type CalculateRequest = {
  account_size: string;
  risk_percent: string;
  entry: string;
  stop: string;
  target: string;
};

export type PlanStatus = "planned" | "open" | "closed" | "skipped";
export type ExitReason = "target_hit" | "stop_hit" | "manual_exit" | "other";

export type CreatePlanRequest = CalculateRequest & {
  symbol: string;
  notes?: string | null;
  setup_tag?: string | null;
  is_paper?: boolean;
  checklist_id?: number | null;
};

export type UpdatePlanRequest = {
  status?: PlanStatus;
  notes?: string | null;
  setup_tag?: string | null;
  is_paper?: boolean;
  actual_entry?: string | null;
  actual_exit?: string | null;
  shares_traded?: number | null;
  exit_reason?: ExitReason | null;
  lessons?: string | null;
};

export type CalculateResponse = {
  max_risk_dollars: string;
  risk_per_share: string;
  shares: number;
  actual_risk_dollars: string;
  reward_per_share: string;
  potential_profit: string;
  risk_reward_ratio: string;
  position_cost: string;
  exceeds_account: boolean;
};

export type TradePlanResponse = {
  id: number;
  created_at: string;
  symbol: string;
  account_size: string;
  risk_percent: string;
  entry: string;
  stop: string;
  target: string;
  shares: number;
  actual_risk: string;
  risk_reward: string;
  notes: string | null;
  status: PlanStatus;
  is_paper: boolean;
  setup_tag: string | null;
  actual_entry: string | null;
  actual_exit: string | null;
  shares_traded: number | null;
  exit_reason: ExitReason | null;
  opened_at: string | null;
  closed_at: string | null;
  lessons: string | null;
  realized_pnl: string | null;
  r_multiple: string | null;
  checklist_id: number | null;
  checklist_score: number | null;
};

export type JournalStatsBlock = {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: string;
  avg_win: string;
  avg_loss: string;
  avg_r: string | null;
  expectancy_r: string | null;
  total_pnl: string;
  best_trade: string | null;
  worst_trade: string | null;
  max_drawdown: string;
};

export type TagStatsBlock = JournalStatsBlock & {
  tag: string;
};

export type CumulativePnlPoint = {
  closed_at: string;
  cumulative_pnl: string;
};

export type ChecklistScoreGroup = {
  count: number;
  win_rate: string;
  expectancy_r: string | null;
};

export type JournalStatsResponse = {
  overall: JournalStatsBlock;
  by_tag: TagStatsBlock[];
  cumulative_pnl: CumulativePnlPoint[];
  by_checklist_score: {
    met: ChecklistScoreGroup;
    below: ChecklistScoreGroup;
  };
};

export type ChecklistRule = {
  id?: number;
  position: number;
  label: string;
  rule_type: string;
  operator: string;
  threshold: string | null;
  required: boolean;
};

export type Checklist = {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  rules: ChecklistRule[];
};

export type ChecklistUpsertRequest = {
  name: string;
  description?: string | null;
  rules: Array<{
    position: number;
    label: string;
    rule_type: string;
    operator: string;
    threshold?: string | null;
    required: boolean;
  }>;
};

export type ChecklistRuleResult = {
  label: string;
  passed: boolean | null;
  actual: string | null;
  threshold: string | null;
  required: boolean;
  rule_type: string;
  operator: string;
};

export type ChecklistEvaluateResponse = {
  checklist_id: number;
  checklist_name: string;
  results: ChecklistRuleResult[];
  score: number;
  unknown_count: number;
  required_failed: string[];
  verdict: string;
};

export const CHECKLIST_RULE_TYPES = [
  "gap_percent",
  "relative_volume",
  "avg_daily_volume",
  "last_price",
  "has_recent_news",
  "price_above_vwap",
  "price_above_prev_day_high",
  "price_above_prev_day_low",
  "entry_above_sma_20",
  "entry_above_sma_50",
  "risk_reward",
  "spread_percent",
  "stop_distance_percent",
  "days_to_earnings",
] as const;

export const CHECKLIST_OPERATORS = [">=", "<=", ">", "<", "=="] as const;

export type JournalStatsQuery = {
  is_paper?: boolean | null;
  setup_tag?: string | null;
  from?: string | null;
  to?: string | null;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  try {
    const body: unknown = await response.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof (body as { detail: unknown }).detail === "string"
    ) {
      message = (body as { detail: string }).detail;
    }
  } catch {
    // keep default message
  }
  return new ApiError(response.status, message);
}

export async function calculatePlan(
  body: CalculateRequest,
): Promise<CalculateResponse> {
  const response = await fetch("/api/plans/calculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as CalculateResponse;
}

export async function createPlan(
  body: CreatePlanRequest,
): Promise<TradePlanResponse> {
  const response = await fetch("/api/plans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as TradePlanResponse;
}

export async function listPlans(): Promise<TradePlanResponse[]> {
  const response = await fetch("/api/plans");
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as TradePlanResponse[];
}

export async function deletePlan(id: number): Promise<void> {
  const response = await fetch(`/api/plans/${id}`, { method: "DELETE" });
  if (!response.ok) {
    throw await parseError(response);
  }
}

export async function updatePlan(
  id: number,
  body: UpdatePlanRequest,
): Promise<TradePlanResponse> {
  const response = await fetch(`/api/plans/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as TradePlanResponse;
}

export async function getJournalStats(
  query: JournalStatsQuery = {},
): Promise<JournalStatsResponse> {
  const params = new URLSearchParams();
  if (query.is_paper === true || query.is_paper === false) {
    params.set("is_paper", String(query.is_paper));
  }
  if (query.setup_tag) {
    params.set("setup_tag", query.setup_tag);
  }
  if (query.from) {
    params.set("from", query.from);
  }
  if (query.to) {
    params.set("to", query.to);
  }
  const qs = params.toString();
  const response = await fetch(
    qs ? `/api/journal/stats?${qs}` : "/api/journal/stats",
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as JournalStatsResponse;
}

export async function listChecklists(): Promise<Checklist[]> {
  const response = await fetch("/api/checklists");
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as Checklist[];
}

export async function createChecklist(
  body: ChecklistUpsertRequest,
): Promise<Checklist> {
  const response = await fetch("/api/checklists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as Checklist;
}

export async function updateChecklist(
  id: number,
  body: ChecklistUpsertRequest,
): Promise<Checklist> {
  const response = await fetch(`/api/checklists/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as Checklist;
}

export async function deleteChecklist(id: number): Promise<void> {
  const response = await fetch(`/api/checklists/${id}`, { method: "DELETE" });
  if (!response.ok) {
    throw await parseError(response);
  }
}

export async function evaluateChecklist(
  id: number,
  body: { symbol: string; entry: string; stop: string; target: string },
): Promise<ChecklistEvaluateResponse> {
  const response = await fetch(`/api/checklists/${id}/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as ChecklistEvaluateResponse;
}

export type WatchlistCreateRequest = {
  symbol: string;
  notes?: string | null;
};

export type WatchlistItem = {
  id: number;
  symbol: string;
  added_at: string;
  notes: string | null;
};

export type ScannerFilters = {
  min_price?: string;
  max_price?: string;
  min_gap_percent?: string;
  min_relative_volume?: string;
  min_avg_volume?: string;
};

export type EarningsRisk = "today_or_tomorrow" | "this_week" | "later" | "none";

export type ScannerResultItem = {
  symbol: string;
  last_price: string;
  gap_percent: string;
  relative_volume: string;
  avg_daily_volume: string;
  today_volume: number;
  has_recent_news?: boolean | null;
  count_last_24h?: number | null;
  next_earnings_date?: string | null;
  days_until_earnings?: number | null;
  earnings_risk?: EarningsRisk | string | null;
};

export type ScannerErrorItem = {
  symbol: string;
  error: string;
};

export type ScannerExcludedItem = ScannerResultItem & {
  reason: string;
};

export type ScannerResponse = {
  scanned: number;
  results: ScannerResultItem[];
  excluded: ScannerExcludedItem[];
  errors: ScannerErrorItem[];
};

export async function listWatchlist(): Promise<WatchlistItem[]> {
  const response = await fetch("/api/watchlist");
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as WatchlistItem[];
}

export async function addWatchlistItem(
  body: WatchlistCreateRequest,
): Promise<WatchlistItem> {
  const response = await fetch("/api/watchlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as WatchlistItem;
}

export async function deleteWatchlistItem(symbol: string): Promise<void> {
  const response = await fetch(`/api/watchlist/${encodeURIComponent(symbol)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw await parseError(response);
  }
}

export async function runScanner(
  filters: ScannerFilters,
): Promise<ScannerResponse> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") {
      params.set(key, value);
    }
  }
  const query = params.toString();
  const response = await fetch(`/api/scanner${query ? `?${query}` : ""}`);
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as ScannerResponse;
}

export type IntradayBar = {
  timestamp: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: number;
};

export type KeyLevels = {
  prev_day_high: string | null;
  prev_day_low: string | null;
  prev_day_close: string | null;
  today_open: string | null;
};

export type ChartTimeframe = "1Min" | "5Min" | "15Min" | "1Hour" | "1Day";

export type TickerDetail = {
  symbol: string;
  timeframe: ChartTimeframe | string;
  last_price: string;
  bars: IntradayBar[];
  vwap: string[];
  levels: KeyLevels;
  sma_20: string | null;
  sma_50: string | null;
  gap_percent: string | null;
  next_earnings_date?: string | null;
  days_until_earnings?: number | null;
  earnings_risk?: EarningsRisk | string | null;
  earnings_time_of_day?: string | null;
};

export type TickerEarningsResponse = {
  symbol: string;
  next_earnings_date: string | null;
  days_until_earnings: number | null;
  earnings_risk: EarningsRisk | string;
  time_of_day: string | null;
  eps_estimate: string | null;
};

export async function getTickerEarnings(
  symbol: string,
): Promise<TickerEarningsResponse> {
  const response = await fetch(
    `/api/tickers/${encodeURIComponent(symbol)}/earnings`,
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as TickerEarningsResponse;
}

export async function getTickerDetail(
  symbol: string,
  timeframe: ChartTimeframe = "5Min",
  options: { refresh?: boolean } = {},
): Promise<TickerDetail> {
  const params = new URLSearchParams({ timeframe });
  if (options.refresh) {
    params.set("refresh", "true");
  }
  const response = await fetch(
    `/api/tickers/${encodeURIComponent(symbol)}/detail?${params.toString()}`,
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as TickerDetail;
}

export type NewsItem = {
  id: string;
  headline: string;
  summary: string;
  source: string;
  url: string;
  created_at: string;
  symbols: string[];
};

export type TickerNewsResponse = {
  symbol: string;
  items: NewsItem[];
  count_last_24h: number;
  has_recent_news: boolean;
};

export async function getTickerNews(
  symbol: string,
  limit = 10,
): Promise<TickerNewsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  const response = await fetch(
    `/api/tickers/${encodeURIComponent(symbol)}/news?${params.toString()}`,
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as TickerNewsResponse;
}

export type BacktestStopRule = "fixed_percent" | "prev_day_low" | "today_open";
export type BacktestExitReason = "target_hit" | "stop_hit" | "close";

export type BacktestParameters = {
  min_gap_percent: string;
  min_relative_volume: string;
  min_price: string;
  min_avg_volume: string;
  entry_rule: string;
  stop_rule: string;
  stop_percent: string;
  target_r: string;
  cost_per_share: string;
  risk_per_trade_percent: string;
  starting_account: string;
  skip_earnings_days?: number;
};

export type BacktestCreateRequest = {
  symbols?: string[] | string | null;
  use_watchlist?: boolean;
  start_date: string;
  end_date: string;
  name?: string | null;
  min_gap_percent?: string;
  min_relative_volume?: string;
  min_price?: string;
  min_avg_volume?: string;
  entry_rule?: string;
  stop_rule?: BacktestStopRule | string;
  stop_percent?: string;
  target_r?: string;
  cost_per_share?: string;
  risk_per_trade_percent?: string;
  starting_account?: string;
  skip_earnings_days?: number;
};

export type BacktestTrade = {
  symbol: string;
  date: string;
  entry: string;
  stop: string;
  target: string;
  exit: string;
  exit_reason: BacktestExitReason | string;
  shares: number;
  pnl: string;
  r_multiple: string;
  gap_percent: string;
};

export type BacktestEquityPoint = {
  date: string;
  equity: string;
};

export type BacktestErrorItem = {
  symbol: string;
  error: string;
};

export type BacktestResult = {
  id: number;
  created_at: string;
  name: string | null;
  parameters: BacktestParameters;
  symbols: string[];
  start_date: string;
  end_date: string;
  summary: JournalStatsBlock;
  by_year: Record<string, JournalStatsBlock>;
  equity_curve: BacktestEquityPoint[];
  trades: BacktestTrade[];
  errors: BacktestErrorItem[];
  skipped_days: number;
  earnings_trades_skipped?: number;
  earnings_data_unavailable?: boolean;
};

export type BacktestListItem = {
  id: number;
  created_at: string;
  name: string | null;
  symbols: string[];
  start_date: string;
  end_date: string;
  parameters: BacktestParameters;
  summary: JournalStatsBlock;
};

export async function runBacktest(
  body: BacktestCreateRequest,
): Promise<BacktestResult> {
  const response = await fetch("/api/backtests", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as BacktestResult;
}

export async function listBacktests(): Promise<BacktestListItem[]> {
  const response = await fetch("/api/backtests");
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as BacktestListItem[];
}

export async function getBacktest(id: number): Promise<BacktestResult> {
  const response = await fetch(`/api/backtests/${id}`);
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as BacktestResult;
}

export async function deleteBacktest(id: number): Promise<void> {
  const response = await fetch(`/api/backtests/${id}`, { method: "DELETE" });
  if (!response.ok) {
    throw await parseError(response);
  }
}

export type AgentName =
  | "NOVA"
  | "ORIN"
  | "VESK"
  | "LUMA"
  | "KIRA"
  | "DASH"
  | "SYSTEM"
  | "HUMAN";

export type ProposalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "expired"
  | "vetoed"
  | "executed"
  | "failed"
  | "cancelled";

export type AgentBacktestGate = {
  allowed: boolean;
  warning: string | null;
  requires_confirmation: boolean;
  message: string;
  latest_backtest_id: number | null;
  latest_trade_count: number;
  latest_expectancy_r: string | null;
};

export type AgentSettings = {
  enabled: boolean;
  kill_switch: boolean;
  max_open_positions: number;
  max_trades_per_day: number;
  daily_loss_limit_percent: string;
  risk_per_trade_percent: string;
  proposal_ttl_minutes: number;
  min_orin_score: number;
  min_checklist_score: number;
  checklist_id: number | null;
  cycle_interval_minutes: number;
  scheduler_enabled: boolean;
  backtest_weak_confirmed: boolean;
  backtest_gate: AgentBacktestGate;
  agent_jobs: Record<string, string>;
  paper_url_required: string;
};

export type AgentSettingsUpdate = {
  enabled?: boolean;
  kill_switch?: boolean;
  max_open_positions?: number;
  max_trades_per_day?: number;
  daily_loss_limit_percent?: string;
  risk_per_trade_percent?: string;
  proposal_ttl_minutes?: number;
  min_orin_score?: number;
  min_checklist_score?: number;
  checklist_id?: number | null;
  cycle_interval_minutes?: number;
  scheduler_enabled?: boolean;
  confirm_weak_backtest?: boolean;
};

export type AgentProposal = {
  id: number;
  created_at: string | null;
  cycle_id: string;
  symbol: string;
  status: ProposalStatus | string;
  entry: string;
  stop: string;
  target: string;
  shares: number | null;
  max_loss: string | null;
  orin_score: number | null;
  orin_expected_move_percent: string | null;
  checklist_score: number | null;
  vesk_result: { approved?: boolean; reasons?: string[] } | null;
  luma_reasoning: string | null;
  expires_at: string | null;
  approved_at: string | null;
  order_id: string | null;
  journal_plan_id: number | null;
};

export type AgentEvent = {
  id: number;
  created_at: string | null;
  cycle_id: string;
  agent: AgentName | string;
  event_type: string;
  symbol: string | null;
  proposal_id: number | null;
  duration_ms: number | null;
  payload: Record<string, unknown>;
};

export type CycleSummary = {
  cycle_id: string;
  skipped: boolean;
  skip_reason?: string | null;
  nova_candidates: number;
  orin_scores: number;
  vesk_approved: number;
  vesk_vetoed: number;
  proposed: number;
  watched: number;
  skipped_decisions: number;
  stage_timings_ms: Record<string, number>;
};

export type AgentReviewPayload = {
  id: number;
  created_at: string;
  report: {
    win_rate?: string | null;
    expectancy_r?: string | null;
    grades?: Array<Record<string, unknown>>;
    orin_calibration?: Array<Record<string, unknown>>;
    veto_reasons?: Record<string, number>;
    stage_timings_ms?: Record<string, number>;
    slowest_stage?: string | null;
    expired_unapproved?: number;
    suggested_experiments?: string[];
  };
};

export async function getAgentSettings(): Promise<AgentSettings> {
  const response = await fetch("/api/agents/settings");
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as AgentSettings;
}

export async function updateAgentSettings(
  body: AgentSettingsUpdate,
): Promise<AgentSettings> {
  const response = await fetch("/api/agents/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as AgentSettings;
}

export async function toggleAgentKillSwitch(): Promise<AgentSettings> {
  const response = await fetch("/api/agents/kill-switch", { method: "POST" });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as AgentSettings;
}

export async function runAgentCycle(force = false): Promise<CycleSummary> {
  const params = force ? "?force=true" : "";
  const response = await fetch(`/api/agents/run-cycle${params}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as CycleSummary;
}

export async function listAgentProposals(
  status?: string,
): Promise<AgentProposal[]> {
  const params = status ? `?status=${encodeURIComponent(status)}` : "";
  const response = await fetch(`/api/agents/proposals${params}`);
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as AgentProposal[];
}

export async function approveAgentProposal(
  id: number,
): Promise<{ proposal: AgentProposal; kira: Record<string, unknown> }> {
  const response = await fetch(`/api/agents/proposals/${id}/approve`, {
    method: "POST",
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as {
    proposal: AgentProposal;
    kira: Record<string, unknown>;
  };
}

export async function rejectAgentProposal(id: number): Promise<AgentProposal> {
  const response = await fetch(`/api/agents/proposals/${id}/reject`, {
    method: "POST",
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as AgentProposal;
}

export async function listAgentEvents(filters: {
  agent?: string;
  symbol?: string;
  event_type?: string;
} = {}): Promise<AgentEvent[]> {
  const params = new URLSearchParams();
  if (filters.agent) params.set("agent", filters.agent);
  if (filters.symbol) params.set("symbol", filters.symbol);
  if (filters.event_type) params.set("event_type", filters.event_type);
  const query = params.toString();
  const response = await fetch(`/api/agents/events${query ? `?${query}` : ""}`);
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as AgentEvent[];
}

export async function runAgentReview(): Promise<AgentReviewPayload> {
  const response = await fetch("/api/agents/review/run", { method: "POST" });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as AgentReviewPayload;
}

export async function getLatestAgentReview(): Promise<AgentReviewPayload> {
  const response = await fetch("/api/agents/review/latest");
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as AgentReviewPayload;
}
