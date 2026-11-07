import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ApiError,
  CalculateResponse,
  TradePlanResponse,
  calculatePlan,
  createPlan,
  deletePlan,
  listPlans,
} from "../api";
import { FieldLabel } from "../components/FieldLabel";
import {
  readAccountSize,
  readRiskPercent,
  writeAccountSize,
  writeRiskPercent,
} from "../lib/planStorage";

type FormState = {
  symbol: string;
  account_size: string;
  risk_percent: string;
  entry: string;
  stop: string;
  target: string;
  notes: string;
  setup_tag: string;
  is_paper: boolean;
};

const INITIAL_FORM: FormState = {
  symbol: "",
  account_size: "",
  risk_percent: "1",
  entry: "",
  stop: "",
  target: "",
  notes: "",
  setup_tag: "",
  is_paper: true,
};

const FIELD_HELP = {
  symbol: "Ticker symbol for the stock or ETF you plan to buy (e.g. AAPL).",
  account_size:
    "Total trading capital in dollars used to size the position and check affordability.",
  risk_percent:
    "Maximum percent of account you are willing to lose if the stop is hit (default 1%).",
  entry: "Planned buy price. Must be above the stop and below the target.",
  stop: "Exit price if the trade goes against you. Must be below entry (risk per share = entry − stop).",
  target:
    "Profit-taking sell price. Must be above entry (reward per share = target − entry).",
  notes: "Optional free-text reminder about the setup, catalyst, or thesis.",
  setup_tag: "Optional label for the setup type (e.g. breakout, pullback).",
  is_paper: "Paper trades are simulated; turn off for live account fills.",
} as const;

const RESULT_HELP = {
  max_risk:
    "Account size × risk percent / 100 — the most you intend to lose on this trade.",
  risk_per_share: "Entry − stop. Dollar risk for each share if stopped out.",
  shares:
    "Floor(max risk ÷ risk per share). Whole shares only; remainder is unused risk.",
  actual_risk:
    "Shares × risk per share. Slightly less than max risk when size is rounded down.",
  reward_per_share: "Target − entry. Dollar gain per share if the target is hit.",
  potential_profit: "Shares × reward per share if the full target is reached.",
  risk_reward:
    "Reward per share ÷ risk per share, shown as reward:risk (e.g. 3.00:1 means $3 potential profit for each $1 risked).",
  position_cost: "Shares × entry. Total cash needed to open the long position.",
} as const;

/** Format API decimal strings as USD, e.g. 1.5 -> $1.50, 1500 -> $1,500.00 */
function formatMoney(value: string | number): string {
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

/** Reward:risk as traders read it, e.g. 3 -> "3.00:1". */
function formatRiskReward(value: string | number): string {
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num)) {
    return String(value);
  }
  return `${num.toFixed(2)}:1`;
}

export default function PlannerPage() {
  const [searchParams] = useSearchParams();
  const [form, setForm] = useState<FormState>(() => ({
    ...INITIAL_FORM,
    account_size: readAccountSize(""),
    risk_percent: readRiskPercent("1"),
  }));
  const [result, setResult] = useState<CalculateResponse | null>(null);
  const [plans, setPlans] = useState<TradePlanResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notesPlan, setNotesPlan] = useState<TradePlanResponse | null>(null);

  useEffect(() => {
    const symbol = searchParams.get("symbol");
    const entry = searchParams.get("entry");
    const stop = searchParams.get("stop");
    const target = searchParams.get("target");
    const accountSize = searchParams.get("account_size");
    const riskPercent = searchParams.get("risk_percent");
    if (
      !symbol &&
      !entry &&
      !stop &&
      !target &&
      !accountSize &&
      !riskPercent
    ) {
      return;
    }
    setForm((prev) => ({
      ...prev,
      symbol: symbol ? symbol.toUpperCase() : prev.symbol,
      entry: entry ?? prev.entry,
      stop: stop ?? prev.stop,
      target: target ?? prev.target,
      account_size: accountSize ?? prev.account_size,
      risk_percent: riskPercent ?? prev.risk_percent,
    }));
  }, [searchParams]);

  useEffect(() => {
    writeAccountSize(form.account_size);
  }, [form.account_size]);

  useEffect(() => {
    writeRiskPercent(form.risk_percent);
  }, [form.risk_percent]);

  const refreshPlans = useCallback(async () => {
    const rows = await listPlans();
    setPlans(rows);
  }, []);

  useEffect(() => {
    refreshPlans().catch((err: unknown) => {
      const message =
        err instanceof Error ? err.message : "Failed to load plans";
      setError(message);
    });
  }, [refreshPlans]);

  useEffect(() => {
    if (!notesPlan) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setNotesPlan(null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [notesPlan]);

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function calcPayload() {
    return {
      account_size: form.account_size,
      risk_percent: form.risk_percent,
      entry: form.entry,
      stop: form.stop,
      target: form.target,
    };
  }

  async function onCalculate(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const data = await calculatePlan(calcPayload());
      setResult(data);
    } catch (err: unknown) {
      setResult(null);
      setError(err instanceof ApiError ? err.message : "Calculate failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSave() {
    setError(null);
    setBusy(true);
    try {
      const saved = await createPlan({
        ...calcPayload(),
        symbol: form.symbol,
        notes: form.notes.trim() ? form.notes.trim() : null,
        setup_tag: form.setup_tag.trim() ? form.setup_tag.trim() : null,
        is_paper: form.is_paper,
      });
      setResult(await calculatePlan(calcPayload()));
      setPlans((prev) => [saved, ...prev.filter((p) => p.id !== saved.id)]);
      await refreshPlans();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(id: number) {
    setError(null);
    setBusy(true);
    try {
      await deletePlan(id);
      setPlans((prev) => prev.filter((p) => p.id !== id));
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="header">
        <h1>Trade Planner</h1>
        <p>Size long-side trades from account risk and price levels.</p>
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <form className="form" onSubmit={onCalculate}>
        <label>
          <FieldLabel text="Symbol" tip={FIELD_HELP.symbol} />
          <input
            value={form.symbol}
            onChange={(e) =>
              updateField("symbol", e.target.value.toUpperCase())
            }
            placeholder="AAPL"
            required
          />
        </label>
        <label>
          <FieldLabel text="Account size ($)" tip={FIELD_HELP.account_size} />
          <input
            value={form.account_size}
            onChange={(e) => updateField("account_size", e.target.value)}
            inputMode="decimal"
            required
          />
        </label>
        <label>
          <FieldLabel text="Risk percent (%)" tip={FIELD_HELP.risk_percent} />
          <input
            value={form.risk_percent}
            onChange={(e) => updateField("risk_percent", e.target.value)}
            inputMode="decimal"
            required
          />
        </label>
        <label>
          <FieldLabel text="Entry" tip={FIELD_HELP.entry} />
          <input
            value={form.entry}
            onChange={(e) => updateField("entry", e.target.value)}
            inputMode="decimal"
            required
          />
        </label>
        <label>
          <FieldLabel text="Stop" tip={FIELD_HELP.stop} />
          <input
            value={form.stop}
            onChange={(e) => updateField("stop", e.target.value)}
            inputMode="decimal"
            required
          />
        </label>
        <label>
          <FieldLabel text="Target" tip={FIELD_HELP.target} />
          <input
            value={form.target}
            onChange={(e) => updateField("target", e.target.value)}
            inputMode="decimal"
            required
          />
        </label>
        <label className="full">
          <FieldLabel text="Notes (optional)" tip={FIELD_HELP.notes} />
          <input
            value={form.notes}
            onChange={(e) => updateField("notes", e.target.value)}
            placeholder="Setup notes"
          />
        </label>
        <label>
          <FieldLabel text="Setup tag (optional)" tip={FIELD_HELP.setup_tag} />
          <input
            value={form.setup_tag}
            onChange={(e) => updateField("setup_tag", e.target.value)}
            placeholder="breakout"
            list="planner-setup-tags"
          />
        </label>
        <label className="toggle-field">
          <FieldLabel text="Paper trade" tip={FIELD_HELP.is_paper} />
          <input
            type="checkbox"
            checked={form.is_paper}
            onChange={(e) => updateField("is_paper", e.target.checked)}
          />
          <span>{form.is_paper ? "Paper" : "Real"}</span>
        </label>
        <datalist id="planner-setup-tags">
          {Array.from(
            new Set(
              plans
                .map((p) => p.setup_tag)
                .filter((tag): tag is string => Boolean(tag)),
            ),
          )
            .sort()
            .map((tag) => (
              <option key={tag} value={tag} />
            ))}
        </datalist>
        <div className="actions full">
          <button type="submit" disabled={busy}>
            Calculate
          </button>
          <button type="button" disabled={busy} onClick={() => void onSave()}>
            Save plan
          </button>
        </div>
      </form>

      {result ? (
        <section className="results">
          {result.exceeds_account ? (
            <div className="warning-banner" role="status">
              <strong>Position cost exceeds account size.</strong>
              <br />
              This plan needs {formatMoney(result.position_cost)} to buy{" "}
              {result.shares} shares at your entry, but account size is only{" "}
              {formatMoney(form.account_size)} (short by about{" "}
              {formatMoney(
                Number(result.position_cost) - Number(form.account_size),
              )}
              ).
              <br />
              Fix by doing one or more of the following: raise{" "}
              <strong>Account size</strong> to at least{" "}
              {formatMoney(result.position_cost)}; lower{" "}
              <strong>Risk percent</strong> so fewer shares are sized; or widen
              the stop (move <strong>Stop</strong> farther below entry) so risk
              per share is larger and share count drops. Then recalculate.
            </div>
          ) : null}
          <div className="result-card">
            <h2>Calculation</h2>
            <dl>
              <div>
                <dt>
                  <FieldLabel text="Max risk" tip={RESULT_HELP.max_risk} />
                </dt>
                <dd>{formatMoney(result.max_risk_dollars)}</dd>
              </div>
              <div>
                <dt>
                  <FieldLabel
                    text="Risk / share"
                    tip={RESULT_HELP.risk_per_share}
                  />
                </dt>
                <dd>{formatMoney(result.risk_per_share)}</dd>
              </div>
              <div>
                <dt>
                  <FieldLabel text="Shares" tip={RESULT_HELP.shares} />
                </dt>
                <dd>{result.shares}</dd>
              </div>
              <div>
                <dt>
                  <FieldLabel text="Actual risk" tip={RESULT_HELP.actual_risk} />
                </dt>
                <dd>{formatMoney(result.actual_risk_dollars)}</dd>
              </div>
              <div>
                <dt>
                  <FieldLabel
                    text="Reward / share"
                    tip={RESULT_HELP.reward_per_share}
                  />
                </dt>
                <dd>{formatMoney(result.reward_per_share)}</dd>
              </div>
              <div>
                <dt>
                  <FieldLabel
                    text="Potential profit"
                    tip={RESULT_HELP.potential_profit}
                  />
                </dt>
                <dd>{formatMoney(result.potential_profit)}</dd>
              </div>
              <div>
                <dt>
                  <FieldLabel text="R:R ratio" tip={RESULT_HELP.risk_reward} />
                </dt>
                <dd>{formatRiskReward(result.risk_reward_ratio)}</dd>
              </div>
              <div>
                <dt>
                  <FieldLabel
                    text="Position cost"
                    tip={RESULT_HELP.position_cost}
                  />
                </dt>
                <dd>{formatMoney(result.position_cost)}</dd>
              </div>
            </dl>
          </div>
        </section>
      ) : null}

      <section className="plans">
        <h2>Saved plans</h2>
        {plans.length === 0 ? (
          <p className="empty">No saved plans yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Entry</th>
                  <th>Stop</th>
                  <th>Target</th>
                  <th>Shares</th>
                  <th>Actual risk</th>
                  <th>R:R</th>
                  <th>Created</th>
                  <th>Notes</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {plans.map((plan) => (
                  <tr key={plan.id}>
                    <td>{plan.symbol}</td>
                    <td>{formatMoney(plan.entry)}</td>
                    <td>{formatMoney(plan.stop)}</td>
                    <td>{formatMoney(plan.target)}</td>
                    <td>{plan.shares}</td>
                    <td>{formatMoney(plan.actual_risk)}</td>
                    <td>{formatRiskReward(plan.risk_reward)}</td>
                    <td>{new Date(plan.created_at).toLocaleString()}</td>
                    <td>
                      <button
                        type="button"
                        className="secondary"
                        disabled={!plan.notes}
                        onClick={() => setNotesPlan(plan)}
                      >
                        {plan.notes ? "View" : "None"}
                      </button>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="danger"
                        disabled={busy}
                        onClick={() => void onDelete(plan.id)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {notesPlan ? (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setNotesPlan(null)}
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="notes-modal-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <h2 id="notes-modal-title">{notesPlan.symbol} notes</h2>
              <button
                type="button"
                className="secondary"
                onClick={() => setNotesPlan(null)}
              >
                Close
              </button>
            </div>
            <p className="modal-meta">
              Entry {formatMoney(notesPlan.entry)} · Stop{" "}
              {formatMoney(notesPlan.stop)} · Target{" "}
              {formatMoney(notesPlan.target)}
            </p>
            <div className="modal-body">
              {notesPlan.notes ?? "No notes for this plan."}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
