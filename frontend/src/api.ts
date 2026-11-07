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

export type ScannerResultItem = {
  symbol: string;
  last_price: string;
  gap_percent: string;
  relative_volume: string;
  avg_daily_volume: string;
  today_volume: number;
  has_recent_news?: boolean | null;
  count_last_24h?: number | null;
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
};

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
