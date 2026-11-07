import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  ScannerErrorItem,
  ScannerExcludedItem,
  ScannerResultItem,
  WatchlistItem,
  addWatchlistItem,
  deleteWatchlistItem,
  listWatchlist,
  runScanner,
} from "../api";
import { FieldLabel } from "../components/FieldLabel";

const FILTER_HELP = {
  min_price:
    "Exclude symbols whose last price is below this dollar amount (helps skip very cheap names).",
  max_price:
    "Exclude symbols whose last price is above this dollar amount (caps how expensive a name can be).",
  min_gap_percent:
    "Minimum absolute gap percent: |(today’s open − previous close) / previous close × 100|. Up or down gaps both count.",
  min_relative_volume:
    "Minimum today_volume ÷ average daily volume. Values above 1 mean today’s volume is above the recent average.",
  min_avg_volume:
    "Minimum average volume over the last 20 completed daily bars (today excluded). Filters out thinly traded names.",
} as const;

type FilterState = {
  min_price: string;
  max_price: string;
  min_gap_percent: string;
  min_relative_volume: string;
  min_avg_volume: string;
};

const DEFAULT_FILTERS: FilterState = {
  min_price: "5",
  max_price: "500",
  min_gap_percent: "2",
  min_relative_volume: "1.5",
  min_avg_volume: "500000",
};

type SortKey =
  | "symbol"
  | "last_price"
  | "gap_percent"
  | "relative_volume"
  | "avg_daily_volume"
  | "today_volume"
  | "news";

function newsSortValue(row: ScannerResultItem): number {
  if (row.has_recent_news == null && row.count_last_24h == null) {
    return -1;
  }
  return row.count_last_24h ?? (row.has_recent_news ? 1 : 0);
}

function compareRows(
  a: ScannerResultItem,
  b: ScannerResultItem,
  key: SortKey,
  direction: "asc" | "desc",
): number {
  const mul = direction === "asc" ? 1 : -1;
  if (key === "symbol") {
    return a.symbol.localeCompare(b.symbol) * mul;
  }
  if (key === "today_volume") {
    return (a.today_volume - b.today_volume) * mul;
  }
  if (key === "news") {
    return (newsSortValue(a) - newsSortValue(b)) * mul;
  }
  const left = Number(a[key]);
  const right = Number(b[key]);
  return (left - right) * mul;
}

function NewsCell({ row }: { row: ScannerResultItem }) {
  if (row.has_recent_news == null && row.count_last_24h == null) {
    return <span className="news-unknown">—</span>;
  }
  if (row.has_recent_news) {
    return (
      <span className="news-dot recent" title={`${row.count_last_24h ?? 0} in last 24h`}>
        {row.count_last_24h ?? "•"}
      </span>
    );
  }
  return (
    <span className="news-dot none" title="No news in last 24h">
      0
    </span>
  );
}

function formatNumber(value: string | number): string {
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num)) {
    return String(value);
  }
  return num.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

export default function ScannerPage() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [symbolInput, setSymbolInput] = useState("");
  const [notesInput, setNotesInput] = useState("");
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [results, setResults] = useState<ScannerResultItem[]>([]);
  const [excluded, setExcluded] = useState<ScannerExcludedItem[]>([]);
  const [scanErrors, setScanErrors] = useState<ScannerErrorItem[]>([]);
  const [scannedCount, setScannedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [hasScanned, setHasScanned] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("gap_percent");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [whyRow, setWhyRow] = useState<ScannerExcludedItem | null>(null);

  const refreshWatchlist = useCallback(async () => {
    const rows = await listWatchlist();
    setWatchlist(rows);
  }, []);

  useEffect(() => {
    refreshWatchlist().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Failed to load watchlist");
    });
  }, [refreshWatchlist]);

  useEffect(() => {
    if (!whyRow) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setWhyRow(null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [whyRow]);

  const sortedResults = useMemo(() => {
    const copy = [...results];
    copy.sort((a, b) => compareRows(a, b, sortKey, sortDir));
    return copy;
  }, [results, sortKey, sortDir]);

  async function onAddSymbol(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await addWatchlistItem({
        symbol: symbolInput,
        notes: notesInput.trim() ? notesInput.trim() : null,
      });
      setSymbolInput("");
      setNotesInput("");
      await refreshWatchlist();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Failed to add symbol");
    } finally {
      setBusy(false);
    }
  }

  async function onRemoveSymbol(symbol: string) {
    setError(null);
    setBusy(true);
    try {
      await deleteWatchlistItem(symbol);
      await refreshWatchlist();
    } catch (err: unknown) {
      setError(
        err instanceof ApiError ? err.message : "Failed to remove symbol",
      );
    } finally {
      setBusy(false);
    }
  }

  async function onScan(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setScanning(true);
    setHasScanned(true);
    try {
      const payload = await runScanner({
        min_price: filters.min_price,
        max_price: filters.max_price,
        min_gap_percent: filters.min_gap_percent,
        min_relative_volume: filters.min_relative_volume,
        min_avg_volume: filters.min_avg_volume,
      });
      setScannedCount(payload.scanned);
      setResults(payload.results);
      setExcluded(payload.excluded);
      setScanErrors(payload.errors);
      setSortKey("gap_percent");
      setSortDir("desc");
    } catch (err: unknown) {
      setScannedCount(0);
      setResults([]);
      setExcluded([]);
      setScanErrors([]);
      setError(err instanceof ApiError ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir(key === "symbol" ? "asc" : "desc");
  }

  function sortMarker(key: SortKey): string {
    if (sortKey !== key) {
      return "";
    }
    return sortDir === "asc" ? " ↑" : " ↓";
  }

  return (
    <div className="page">
      <header className="header">
        <h1>Scanner</h1>
        <p>
          Gap and relative-volume scan across your watchlist. Click any symbol
          (watchlist or results) to open its chart page.
        </p>
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <section className="panel">
        <h2>Watchlist</h2>
        <form className="form watchlist-form" onSubmit={onAddSymbol}>
          <label>
            Symbol
            <input
              value={symbolInput}
              onChange={(e) => setSymbolInput(e.target.value.toUpperCase())}
              placeholder="AAPL"
              required
            />
          </label>
          <label>
            Notes (optional)
            <input
              value={notesInput}
              onChange={(e) => setNotesInput(e.target.value)}
              placeholder="Catalyst / reason"
            />
          </label>
          <div className="actions">
            <button type="submit" disabled={busy}>
              Add
            </button>
          </div>
        </form>

        {watchlist.length === 0 ? (
          <p className="empty">No symbols yet. Add tickers to scan.</p>
        ) : (
          <ul className="watchlist">
            {watchlist.map((item) => (
              <li key={item.id}>
                <div>
                  <Link
                    className="symbol-link"
                    to={`/ticker/${encodeURIComponent(item.symbol)}`}
                  >
                    {item.symbol}
                  </Link>
                  {item.notes ? (
                    <span className="muted"> — {item.notes}</span>
                  ) : null}
                </div>
                <button
                  type="button"
                  className="danger"
                  disabled={busy}
                  onClick={() => void onRemoveSymbol(item.symbol)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <h2>Filters</h2>
        <form className="form" onSubmit={onScan}>
          <label>
            <FieldLabel text="Min price" tip={FILTER_HELP.min_price} />
            <input
              value={filters.min_price}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, min_price: e.target.value }))
              }
              inputMode="decimal"
            />
          </label>
          <label>
            <FieldLabel text="Max price" tip={FILTER_HELP.max_price} />
            <input
              value={filters.max_price}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, max_price: e.target.value }))
              }
              inputMode="decimal"
            />
          </label>
          <label>
            <FieldLabel text="Min |gap| %" tip={FILTER_HELP.min_gap_percent} />
            <input
              value={filters.min_gap_percent}
              onChange={(e) =>
                setFilters((prev) => ({
                  ...prev,
                  min_gap_percent: e.target.value,
                }))
              }
              inputMode="decimal"
            />
          </label>
          <label>
            <FieldLabel
              text="Min relative volume"
              tip={FILTER_HELP.min_relative_volume}
            />
            <input
              value={filters.min_relative_volume}
              onChange={(e) =>
                setFilters((prev) => ({
                  ...prev,
                  min_relative_volume: e.target.value,
                }))
              }
              inputMode="decimal"
            />
          </label>
          <label>
            <FieldLabel text="Min avg volume" tip={FILTER_HELP.min_avg_volume} />
            <input
              value={filters.min_avg_volume}
              onChange={(e) =>
                setFilters((prev) => ({
                  ...prev,
                  min_avg_volume: e.target.value,
                }))
              }
              inputMode="decimal"
            />
          </label>
          <div className="actions full">
            <button type="submit" disabled={scanning || watchlist.length === 0}>
              {scanning ? "Scanning…" : "Run scan"}
            </button>
          </div>
        </form>
      </section>

      <section className="plans">
        <h2>Results</h2>
        {scanning ? <p className="empty">Loading market data…</p> : null}
        {!scanning && !hasScanned ? (
          <p className="empty">Run a scan to see matching symbols.</p>
        ) : null}
        {!scanning && hasScanned ? (
          <p className="scan-summary">
            Scanned {scannedCount} watchlist symbol
            {scannedCount === 1 ? "" : "s"} · {results.length} matched ·{" "}
            {excluded.length} filtered out · {scanErrors.length} error
            {scanErrors.length === 1 ? "" : "s"}
          </p>
        ) : null}
        {!scanning &&
        hasScanned &&
        results.length === 0 &&
        excluded.length === 0 &&
        scanErrors.length === 0 ? (
          <p className="empty">Watchlist is empty.</p>
        ) : null}
        {!scanning &&
        hasScanned &&
        results.length === 0 &&
        (excluded.length > 0 || scanErrors.length > 0) ? (
          <p className="empty">
            No symbols matched these filters. See filtered/error sections below,
            or loosen the thresholds.
          </p>
        ) : null}
        {sortedResults.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>
                    <button
                      type="button"
                      className="sort-btn"
                      onClick={() => toggleSort("symbol")}
                    >
                      Symbol{sortMarker("symbol")}
                    </button>
                  </th>
                  <th>
                    <button
                      type="button"
                      className="sort-btn"
                      onClick={() => toggleSort("last_price")}
                    >
                      Last{sortMarker("last_price")}
                    </button>
                  </th>
                  <th>
                    <button
                      type="button"
                      className="sort-btn"
                      onClick={() => toggleSort("gap_percent")}
                    >
                      Gap %{sortMarker("gap_percent")}
                    </button>
                  </th>
                  <th>
                    <button
                      type="button"
                      className="sort-btn"
                      onClick={() => toggleSort("relative_volume")}
                    >
                      Rel vol{sortMarker("relative_volume")}
                    </button>
                  </th>
                  <th>
                    <button
                      type="button"
                      className="sort-btn"
                      onClick={() => toggleSort("avg_daily_volume")}
                    >
                      Avg vol{sortMarker("avg_daily_volume")}
                    </button>
                  </th>
                  <th>
                    <button
                      type="button"
                      className="sort-btn"
                      onClick={() => toggleSort("today_volume")}
                    >
                      Today vol{sortMarker("today_volume")}
                    </button>
                  </th>
                  <th>
                    <button
                      type="button"
                      className="sort-btn"
                      onClick={() => toggleSort("news")}
                    >
                      News{sortMarker("news")}
                    </button>
                  </th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {sortedResults.map((row) => {
                  const gap = Number(row.gap_percent);
                  const gapClass =
                    gap > 0 ? "gap-pos" : gap < 0 ? "gap-neg" : undefined;
                  return (
                    <tr key={row.symbol}>
                      <td>
                        <Link
                          className="symbol-link"
                          to={`/ticker/${encodeURIComponent(row.symbol)}`}
                        >
                          {row.symbol}
                        </Link>
                      </td>
                      <td>{formatNumber(row.last_price)}</td>
                      <td className={gapClass}>
                        {formatNumber(row.gap_percent)}%
                      </td>
                      <td>{formatNumber(row.relative_volume)}</td>
                      <td>{formatNumber(row.avg_daily_volume)}</td>
                      <td>{formatNumber(row.today_volume)}</td>
                      <td>
                        <NewsCell row={row} />
                      </td>
                      <td>
                        <Link
                          className="button-link"
                          to={`/?symbol=${encodeURIComponent(row.symbol)}&entry=${encodeURIComponent(row.last_price)}`}
                        >
                          Plan trade
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}

        {excluded.length > 0 ? (
          <div className="scan-excluded">
            <h3>Filtered out (still scanned)</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Last</th>
                    <th>Gap %</th>
                    <th>Rel vol</th>
                    <th>Avg vol</th>
                    <th>Today vol</th>
                    <th>Why</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {excluded.map((row) => {
                    const gap = Number(row.gap_percent);
                    const gapClass =
                      gap > 0 ? "gap-pos" : gap < 0 ? "gap-neg" : undefined;
                    return (
                      <tr key={row.symbol}>
                        <td>
                          <Link
                            className="symbol-link"
                            to={`/ticker/${encodeURIComponent(row.symbol)}`}
                          >
                            {row.symbol}
                          </Link>
                        </td>
                        <td>{formatNumber(row.last_price)}</td>
                        <td className={gapClass}>
                          {formatNumber(row.gap_percent)}%
                        </td>
                        <td>{formatNumber(row.relative_volume)}</td>
                        <td>{formatNumber(row.avg_daily_volume)}</td>
                        <td>{formatNumber(row.today_volume)}</td>
                        <td>
                          <button
                            type="button"
                            className="secondary"
                            onClick={() => setWhyRow(row)}
                          >
                            View
                          </button>
                        </td>
                        <td>
                          <Link
                            className="button-link"
                            to={`/?symbol=${encodeURIComponent(row.symbol)}&entry=${encodeURIComponent(row.last_price)}`}
                          >
                            Plan trade
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {scanErrors.length > 0 ? (
          <div className="scan-errors">
            <h3>Symbol errors</h3>
            <ul>
              {scanErrors.map((item) => (
                <li key={item.symbol}>
                  <strong>{item.symbol}</strong>: {item.error}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      {whyRow ? (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setWhyRow(null)}
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="why-modal-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <h2 id="why-modal-title">{whyRow.symbol} filter reason</h2>
              <button
                type="button"
                className="secondary"
                onClick={() => setWhyRow(null)}
              >
                Close
              </button>
            </div>
            <p className="modal-meta">
              Last {formatNumber(whyRow.last_price)} · Gap{" "}
              {formatNumber(whyRow.gap_percent)}% · Rel vol{" "}
              {formatNumber(whyRow.relative_volume)}
            </p>
            <div className="modal-body">{whyRow.reason}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
