import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  CHECKLIST_OPERATORS,
  CHECKLIST_RULE_TYPES,
  Checklist,
  ChecklistRule,
  createChecklist,
  deleteChecklist,
  listChecklists,
  updateChecklist,
} from "../api";

type DraftRule = {
  key: string;
  position: number;
  label: string;
  rule_type: string;
  operator: string;
  threshold: string;
  required: boolean;
};

function toDraft(rule: ChecklistRule, index: number): DraftRule {
  return {
    key: `existing-${rule.id ?? index}`,
    position: rule.position,
    label: rule.label,
    rule_type: rule.rule_type,
    operator: rule.operator,
    threshold: rule.threshold ?? "",
    required: rule.required,
  };
}

function emptyRule(position: number): DraftRule {
  return {
    key: `new-${Date.now()}-${position}`,
    position,
    label: "",
    rule_type: "gap_percent",
    operator: ">=",
    threshold: "",
    required: false,
  };
}

export default function ChecklistsPage() {
  const [checklists, setChecklists] = useState<Checklist[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [rules, setRules] = useState<DraftRule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const rows = await listChecklists();
      setChecklists(rows);
      if (rows.length > 0 && selectedId == null) {
        const first = rows[0];
        if (first) {
          selectChecklist(first);
        }
      } else if (selectedId != null) {
        const match = rows.find((row) => row.id === selectedId);
        if (match) {
          selectChecklist(match);
        }
      }
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Failed to load checklists");
    } finally {
      setBusy(false);
    }
  }, [selectedId]);

  useEffect(() => {
    void load();
    // initial load only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function selectChecklist(checklist: Checklist) {
    setSelectedId(checklist.id);
    setName(checklist.name);
    setDescription(checklist.description ?? "");
    setRules(checklist.rules.map((rule, index) => toDraft(rule, index)));
    setMessage(null);
  }

  function startNew() {
    setSelectedId(null);
    setName("");
    setDescription("");
    setRules([emptyRule(0)]);
    setMessage(null);
  }

  function updateRule(key: string, patch: Partial<DraftRule>) {
    setRules((prev) =>
      prev.map((rule) => (rule.key === key ? { ...rule, ...patch } : rule)),
    );
  }

  function addRule() {
    setRules((prev) => [...prev, emptyRule(prev.length)]);
  }

  function removeRule(key: string) {
    setRules((prev) =>
      prev
        .filter((rule) => rule.key !== key)
        .map((rule, index) => ({ ...rule, position: index })),
    );
  }

  function moveRule(key: string, direction: -1 | 1) {
    setRules((prev) => {
      const index = prev.findIndex((rule) => rule.key === key);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= prev.length) {
        return prev;
      }
      const current = prev[index];
      const neighbor = prev[nextIndex];
      if (!current || !neighbor) {
        return prev;
      }
      const copy = [...prev];
      copy[index] = neighbor;
      copy[nextIndex] = current;
      return copy.map((rule, i) => ({ ...rule, position: i }));
    });
  }

  async function save() {
    setBusy(true);
    setError(null);
    setMessage(null);
    const body = {
      name: name.trim(),
      description: description.trim() || null,
      rules: rules.map((rule, index) => ({
        position: index,
        label: rule.label.trim() || rule.rule_type,
        rule_type: rule.rule_type,
        operator: rule.operator,
        threshold: rule.threshold.trim() ? rule.threshold.trim() : null,
        required: rule.required,
      })),
    };
    try {
      const saved =
        selectedId == null
          ? await createChecklist(body)
          : await updateChecklist(selectedId, body);
      setMessage(`Saved “${saved.name}”`);
      const rows = await listChecklists();
      setChecklists(rows);
      selectChecklist(saved);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (selectedId == null) {
      return;
    }
    if (!window.confirm("Delete this checklist?")) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteChecklist(selectedId);
      setSelectedId(null);
      setName("");
      setDescription("");
      setRules([]);
      const rows = await listChecklists();
      setChecklists(rows);
      if (rows[0]) {
        selectChecklist(rows[0]);
      }
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1>Checklists</h1>
          <p>Configure setup rules that score a trade idea before you take it.</p>
        </div>
        <button type="button" className="secondary" onClick={startNew}>
          New checklist
        </button>
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}
      {message ? <p className="copy-toast" role="status">{message}</p> : null}

      <div className="checklist-layout">
        <aside className="panel">
          <h2>Saved</h2>
          <ul className="checklist-nav">
            {checklists.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={
                    item.id === selectedId
                      ? "checklist-nav-btn active"
                      : "checklist-nav-btn"
                  }
                  onClick={() => selectChecklist(item)}
                >
                  {item.name}
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="panel">
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Description
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>

          <div className="checklist-rules-header">
            <h2>Rules</h2>
            <button type="button" className="secondary" onClick={addRule}>
              Add rule
            </button>
          </div>

          {rules.map((rule) => (
            <div className="rule-editor" key={rule.key}>
              <label>
                Label
                <input
                  value={rule.label}
                  onChange={(e) => updateRule(rule.key, { label: e.target.value })}
                />
              </label>
              <label>
                Type
                <select
                  value={rule.rule_type}
                  onChange={(e) =>
                    updateRule(rule.key, { rule_type: e.target.value })
                  }
                >
                  {CHECKLIST_RULE_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Operator
                <select
                  value={rule.operator}
                  onChange={(e) =>
                    updateRule(rule.key, { operator: e.target.value })
                  }
                >
                  {CHECKLIST_OPERATORS.map((op) => (
                    <option key={op} value={op}>
                      {op}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Threshold
                <input
                  value={rule.threshold}
                  onChange={(e) =>
                    updateRule(rule.key, { threshold: e.target.value })
                  }
                  placeholder="e.g. 2 or 1 for true"
                />
              </label>
              <label className="toggle-field">
                Required
                <input
                  type="checkbox"
                  checked={rule.required}
                  onChange={(e) =>
                    updateRule(rule.key, { required: e.target.checked })
                  }
                />
              </label>
              <div className="row-actions">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => moveRule(rule.key, -1)}
                >
                  Up
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => moveRule(rule.key, 1)}
                >
                  Down
                </button>
                <button
                  type="button"
                  className="danger"
                  onClick={() => removeRule(rule.key)}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}

          <div className="actions">
            <button type="button" disabled={busy || !name.trim()} onClick={() => void save()}>
              {selectedId == null ? "Create" : "Save changes"}
            </button>
            {selectedId != null ? (
              <button
                type="button"
                className="danger"
                disabled={busy}
                onClick={() => void remove()}
              >
                Delete
              </button>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}
