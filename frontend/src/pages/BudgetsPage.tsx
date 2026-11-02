
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

type BudgetType = "OPEX" | "CAPEX";

type Budget = {
  id: number;
  name: string;
  financial_year: string;
  budget_type: BudgetType;
  planned_amount: string | number;
  approved_amount: string | number;
  created_at: string;
};

type BudgetForm = {
  name: string;
  financial_year: string;
  budget_type: BudgetType;
  planned_amount: string;
  approved_amount: string;
};

type BudgetEditForm = {
  planned_amount: string;
  approved_amount: string;
};

const OPEX_CATEGORIES = [
  "AMC & IT CONSUMABLES",
  "APPLICATION SUBSCRIPTION SUPPORT",
  "INFRASTRUCTURE MANAGED SERVICES & CLOUD",
  "NETWORK CONNECTIVITY",
] as const;

function getCurrentFinancialYear() {
  const now = new Date();
  const year = now.getFullYear();
  const startYear = now.getMonth() >= 3 ? year : year - 1;
  return `${startYear}-${startYear + 1}`;
}

function amount(value: string | number) {
  const number = Number(value);
  return Number.isFinite(number)
    ? number.toLocaleString("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 2,
      })
    : "₹0.00";
}

function getErrorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) =>
          item && typeof item === "object" && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : String(item)
        )
        .join("; ");
    }
  }
  return fallback;
}

const emptyForm = (): BudgetForm => ({
  name: OPEX_CATEGORIES[0],
  financial_year: getCurrentFinancialYear(),
  budget_type: "OPEX",
  planned_amount: "",
  approved_amount: "0.00",
});

export default function BudgetsPage() {
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [form, setForm] = useState<BudgetForm>(emptyForm);
  const [editingBudget, setEditingBudget] = useState<Budget | null>(null);
  const [editForm, setEditForm] = useState<BudgetEditForm>({
    planned_amount: "",
    approved_amount: "",
  });

  const [search, setSearch] = useState("");
  const [yearFilter, setYearFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const token = sessionStorage.getItem("access_token");

  const loadBudgets = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const response = await fetch("/api/budgets", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const data = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(getErrorMessage(data, "Unable to load budgets."));
      }
      if (!Array.isArray(data)) {
        throw new Error("Unexpected response received from the budget API.");
      }

      setBudgets(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load budgets.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadBudgets();
  }, [loadBudgets]);

  const financialYears = useMemo(
    () =>
      [...new Set(budgets.map((budget) => budget.financial_year))].sort(
        (a, b) => b.localeCompare(a)
      ),
    [budgets]
  );

  const filteredBudgets = useMemo(() => {
    const term = search.trim().toLowerCase();

    return budgets.filter((budget) => {
      const matchesSearch =
        budget.name.toLowerCase().includes(term) ||
        budget.financial_year.toLowerCase().includes(term);
      const matchesYear = !yearFilter || budget.financial_year === yearFilter;
      const matchesType = !typeFilter || budget.budget_type === typeFilter;
      return matchesSearch && matchesYear && matchesType;
    });
  }, [budgets, search, yearFilter, typeFilter]);

  const totals = useMemo(
    () =>
      filteredBudgets.reduce(
        (result, budget) => {
          result.planned += Number(budget.planned_amount) || 0;
          result.approved += Number(budget.approved_amount) || 0;
          result.opex += budget.budget_type === "OPEX" ? 1 : 0;
          result.capex += budget.budget_type === "CAPEX" ? 1 : 0;
          return result;
        },
        { planned: 0, approved: 0, opex: 0, capex: 0 }
      ),
    [filteredBudgets]
  );

  function changeBudgetType(budget_type: BudgetType) {
    setForm({
      ...form,
      budget_type,
      name: budget_type === "CAPEX" ? "CAPEX" : OPEX_CATEGORIES[0],
    });
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");

    const planned = Number(form.planned_amount);
    const approved = Number(form.approved_amount);
    const [startYear, endYear] = form.financial_year.split("-").map(Number);

    if (!/^\d{4}-\d{4}$/.test(form.financial_year) || endYear !== startYear + 1) {
      setError("Enter a valid financial year, for example 2026-2027.");
      return;
    }

    if (
      form.planned_amount.trim() === "" ||
      form.approved_amount.trim() === "" ||
      !Number.isFinite(planned) ||
      !Number.isFinite(approved) ||
      planned < 0 ||
      approved < 0
    ) {
      setError("Enter valid, non-negative planned and approved amounts.");
      return;
    }

    if (approved > planned) {
      setError("Approved amount cannot exceed planned amount.");
      return;
    }

    const category = form.budget_type === "CAPEX" ? "CAPEX" : form.name;
    if (form.budget_type === "OPEX" && !OPEX_CATEGORIES.includes(category as typeof OPEX_CATEGORIES[number])) {
      setError("Select a valid OPEX category.");
      return;
    }

    setSaving(true);

    try {
      const response = await fetch("/api/budgets", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          name: category,
          financial_year: form.financial_year,
          budget_type: form.budget_type,
          planned_amount: planned.toFixed(2),
          approved_amount: approved.toFixed(2),
        }),
      });

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(getErrorMessage(data, "Unable to create budget."));
      }

      setForm(emptyForm());
      setSuccess(`Budget "${data.name}" created successfully.`);
      await loadBudgets();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create budget.");
    } finally {
      setSaving(false);
    }
  }

  function startEditing(budget: Budget) {
    setEditingBudget(budget);
    setEditForm({
      planned_amount: String(budget.planned_amount),
      approved_amount: String(budget.approved_amount),
    });
    setError("");
    setSuccess("");
  }

  async function handleUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingBudget) return;

    setError("");
    setSuccess("");

    const planned = Number(editForm.planned_amount);
    const approved = Number(editForm.approved_amount);

    if (
      editForm.planned_amount.trim() === "" ||
      editForm.approved_amount.trim() === "" ||
      !Number.isFinite(planned) ||
      !Number.isFinite(approved) ||
      planned < 0 ||
      approved < 0
    ) {
      setError("Enter valid, non-negative budget amounts.");
      return;
    }

    if (approved > planned) {
      setError("Approved amount cannot exceed planned amount.");
      return;
    }

    setSaving(true);

    try {
      const response = await fetch(`/api/budgets/${editingBudget.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          planned_amount: planned.toFixed(2),
          approved_amount: approved.toFixed(2),
        }),
      });

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(getErrorMessage(data, "Unable to update budget."));
      }

      setSuccess(`Budget "${editingBudget.name}" updated successfully.`);
      setEditingBudget(null);
      await loadBudgets();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update budget.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="budgets-page">
      <header className="budgets-heading">
        <div>
          <p className="budgets-eyebrow">FINANCIAL MANAGEMENT</p>
          <h1>Budget Register</h1>
          <p className="budgets-subtitle">
            Manage planned and approved allocations by financial year and category.
          </p>
        </div>
        <button
          className="budgets-refresh-button"
          type="button"
          onClick={() => void loadBudgets()}
          disabled={loading}
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </header>

      {error && (
        <div className="budgets-alert budgets-alert-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError("")} aria-label="Dismiss error">×</button>
        </div>
      )}

      {success && (
        <div className="budgets-alert budgets-alert-success" role="status">
          <span>{success}</span>
          <button type="button" onClick={() => setSuccess("")} aria-label="Dismiss message">×</button>
        </div>
      )}

      <section className="budgets-summary" aria-label="Budget summary">
        <article className="budgets-summary-card">
          <span>Total budgets</span>
          <strong>{filteredBudgets.length}</strong>
          <small>Matching current filters</small>
        </article>
        <article className="budgets-summary-card">
          <span>Total planned</span>
          <strong>{amount(totals.planned)}</strong>
          <small>Planned allocation</small>
        </article>
        <article className="budgets-summary-card">
          <span>Total approved</span>
          <strong>{amount(totals.approved)}</strong>
          <small>Approved allocation</small>
        </article>
        <article className="budgets-summary-card">
          <span>Budget types</span>
          <strong>{totals.opex} OPEX / {totals.capex} CAPEX</strong>
          <small>Count by type</small>
        </article>
      </section>

      <section className="budgets-form-card">
        <div className="budgets-section-heading">
          <div>
            <h2>Create a budget allocation</h2>
            <p>Choose an approved category and enter its financial allocation.</p>
          </div>
        </div>

        <form className="budgets-form" onSubmit={handleCreate}>
          <div className="budgets-form-grid">
            <label>
              Budget type <span>*</span>
              <select
                value={form.budget_type}
                onChange={(event) => changeBudgetType(event.target.value as BudgetType)}
              >
                <option value="OPEX">OPEX — Operating expenditure</option>
                <option value="CAPEX">CAPEX — Capital expenditure</option>
              </select>
            </label>

            {form.budget_type === "OPEX" ? (
              <label>
                OPEX category <span>*</span>
                <select
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                  required
                >
                  {OPEX_CATEGORIES.map((category) => (
                    <option key={category} value={category}>{category}</option>
                  ))}
                </select>
              </label>
            ) : (
              <label>
                Budget category
                <input value="CAPEX" readOnly />
              </label>
            )}

            <label>
              Financial year <span>*</span>
              <input
                value={form.financial_year}
                onChange={(event) => setForm({ ...form, financial_year: event.target.value })}
                placeholder="2026-2027"
                pattern="[0-9]{4}-[0-9]{4}"
                title="Use YYYY-YYYY format, for example 2026-2027"
                required
              />
            </label>

            <label>
              Planned amount (₹) <span>*</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.planned_amount}
                onChange={(event) => setForm({ ...form, planned_amount: event.target.value })}
                placeholder="0.00"
                required
              />
            </label>

            <label>
              Approved amount (₹) <span>*</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.approved_amount}
                onChange={(event) => setForm({ ...form, approved_amount: event.target.value })}
                placeholder="0.00"
                required
              />
            </label>
          </div>

          <p className="budgets-form-note">
            Each category can have one allocation per financial year. Approved amount
            must not exceed planned amount.
          </p>

          <div className="budgets-form-actions">
            <button type="submit" className="budgets-primary-button" disabled={saving}>
              {saving ? "Saving..." : "Create allocation"}
            </button>
            <button
              type="button"
              className="budgets-secondary-button"
              onClick={() => setForm(emptyForm())}
              disabled={saving}
            >
              Clear form
            </button>
          </div>
        </form>
      </section>

      {editingBudget && (
        <section className="budgets-form-card budgets-edit-card">
          <div className="budgets-section-heading">
            <div>
              <h2>Edit allocation amounts</h2>
              <p>{editingBudget.name} · {editingBudget.financial_year} · {editingBudget.budget_type}</p>
            </div>
            <button
              type="button"
              className="budgets-secondary-button"
              onClick={() => setEditingBudget(null)}
            >
              Cancel
            </button>
          </div>

          <form className="budgets-form" onSubmit={handleUpdate}>
            <div className="budgets-form-grid budgets-edit-grid">
              <label>
                Planned amount (₹) <span>*</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={editForm.planned_amount}
                  onChange={(event) => setEditForm({ ...editForm, planned_amount: event.target.value })}
                  required
                />
              </label>
              <label>
                Approved amount (₹) <span>*</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={editForm.approved_amount}
                  onChange={(event) => setEditForm({ ...editForm, approved_amount: event.target.value })}
                  required
                />
              </label>
            </div>
            <div className="budgets-form-actions">
              <button type="submit" className="budgets-primary-button" disabled={saving}>
                {saving ? "Saving..." : "Save changes"}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="budgets-list-card">
        <div className="budgets-section-heading budgets-list-heading">
          <div>
            <h2>Budget register</h2>
            <p>{filteredBudgets.length} allocation(s) found</p>
          </div>
        </div>

        <div className="budgets-filters">
          <label className="budgets-search-field">
            Search category
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search categories or financial years..."
            />
          </label>

          <label>
            Financial year
            <select value={yearFilter} onChange={(event) => setYearFilter(event.target.value)}>
              <option value="">All financial years</option>
              {financialYears.map((year) => <option key={year} value={year}>{year}</option>)}
            </select>
          </label>

          <label>
            Budget type
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              <option value="">All types</option>
              <option value="OPEX">OPEX</option>
              <option value="CAPEX">CAPEX</option>
            </select>
          </label>

          <button
            type="button"
            className="budgets-secondary-button budgets-clear-filters"
            onClick={() => {
              setSearch("");
              setYearFilter("");
              setTypeFilter("");
            }}
          >
            Clear filters
          </button>
        </div>

        {loading ? (
          <div className="budgets-empty">Loading budgets...</div>
        ) : filteredBudgets.length === 0 ? (
          <div className="budgets-empty">
            <strong>No budgets found</strong>
            <p>Create an allocation or adjust your search and filters.</p>
          </div>
        ) : (
          <div className="budgets-table-wrapper">
            <table className="budgets-table">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Financial year</th>
                  <th>Type</th>
                  <th>Planned amount</th>
                  <th>Approved amount</th>
                  <th>Unapproved balance</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredBudgets.map((budget) => {
                  const planned = Number(budget.planned_amount) || 0;
                  const approved = Number(budget.approved_amount) || 0;

                  return (
                    <tr key={budget.id}>
                      <td>
                        <div className="budgets-name-cell">
                          <strong>{budget.name}</strong>
                          <small>Budget #{budget.id}</small>
                        </div>
                      </td>
                      <td>{budget.financial_year}</td>
                      <td>
                        <span className={`budgets-type-badge budgets-type-${budget.budget_type.toLowerCase()}`}>
                          {budget.budget_type}
                        </span>
                      </td>
                      <td className="budgets-money-cell">{amount(planned)}</td>
                      <td className="budgets-money-cell">{amount(approved)}</td>
                      <td className="budgets-money-cell">{amount(planned - approved)}</td>
                      <td>
                        <div className="budgets-row-actions">
                          <button type="button" className="budgets-edit-button" onClick={() => startEditing(budget)}>
                            Edit amounts
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
