import { NavLink, Route, Routes } from "react-router-dom";
import AgentsPage from "./pages/AgentsPage";
import BacktestPage from "./pages/BacktestPage";
import ChecklistsPage from "./pages/ChecklistsPage";
import JournalPage from "./pages/JournalPage";
import PlannerPage from "./pages/PlannerPage";
import ScannerPage from "./pages/ScannerPage";
import TickerDetailPage from "./pages/TickerDetailPage";
import { useTheme } from "./theme/ThemeContext";

export default function App() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="app-shell">
      <nav className="top-nav">
        <div className="brand-row">
          <div className="brand">EdgeWork</div>
          <div className="theme-switch" role="group" aria-label="Color theme">
            <button
              type="button"
              className={
                theme === "dark" ? "theme-btn active" : "theme-btn"
              }
              aria-pressed={theme === "dark"}
              onClick={() => setTheme("dark")}
            >
              Dark Mode
            </button>
            <span className="theme-sep" aria-hidden>
              |
            </span>
            <button
              type="button"
              className={
                theme === "light" ? "theme-btn active" : "theme-btn"
              }
              aria-pressed={theme === "light"}
              onClick={() => setTheme("light")}
            >
              Light Mode
            </button>
          </div>
        </div>
        <div className="nav-links">
          <NavLink to="/" end>
            Planner
          </NavLink>
          <NavLink to="/scanner">Scanner</NavLink>
          <NavLink to="/journal">Journal</NavLink>
          <NavLink to="/checklists">Checklists</NavLink>
          <NavLink to="/backtest">Backtest</NavLink>
          <NavLink to="/agents">Agents</NavLink>
        </div>
      </nav>
      <Routes>
        <Route path="/" element={<PlannerPage />} />
        <Route path="/scanner" element={<ScannerPage />} />
        <Route path="/journal" element={<JournalPage />} />
        <Route path="/checklists" element={<ChecklistsPage />} />
        <Route path="/backtest" element={<BacktestPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/ticker/:symbol" element={<TickerDetailPage />} />
      </Routes>
    </div>
  );
}
