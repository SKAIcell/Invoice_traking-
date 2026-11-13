
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import '../styles/opex-allocation.css';

type BudgetType = 'OPEX' | 'CAPEX';
type RequestType = 'CREATE' | 'UPDATE';
type RequestStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

type Budget = {
  id: number;
  name: string;
  financial_year: string;
  budget_type: BudgetType;
  planned_amount: string | number;
  approved_amount: string | number;
};

type Subcategory = {
  id: number;
  budget_id: number;
  name: string;
  planned_amount: string | number;
  approved_amount: string | number;
  created_at: string;
};

type ApprovalRequest = {
  id: number;
  budget_id: number;
  subcategory_id: number | null;
  request_type: RequestType;
  status: RequestStatus;
  name: string;
  planned_amount: string | number;
  approved_amount: string | number | null;
  requested_by_id: number;
  decided_by_id: number | null;
  requested_at: string;
  decided_at: string | null;
  remarks: string | null;
};

const OPEX_CATEGORIES = [
  'AMC & IT CONSUMABLES',
  'APPLICATION SUBSCRIPTION SUPPORT',
  'INFRASTRUCTURE MANAGED SERVICES & CLOUD',
  'NETWORK CONNECTIVITY',
];

function formatAmount(value: string | number | null | undefined) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function formatDate(value: string | null | undefined) {
  if (!value) return '—';

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function getToken() {
  return sessionStorage.getItem('access_token');
}

async function apiRequest<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();

  if (!token) {
    throw new Error('Your session has expired. Please sign in again.');
  }

  const response = await fetch(url, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });

  const text = await response.text();

  let data: any = {};

  if (text.trim()) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(`Invalid server response (HTTP ${response.status}).`);
    }
  }

  if (!response.ok) {
    throw new Error(
      data.detail || data.message || `Request failed (HTTP ${response.status}).`,
    );
  }

  return data as T;
}

type Props = {
  onBack: () => void;
};

function OpexAllocationPage({ onBack }: Props) {
  const role = sessionStorage.getItem('role') || '';
  const isITHead = role === 'IT_HEAD';

  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [selectedBudgetId, setSelectedBudgetId] = useState<number | null>(null);

  const [allocations, setAllocations] = useState<Subcategory[]>([]);
  const [myRequests, setMyRequests] = useState<ApprovalRequest[]>([]);
  const [pendingRequests, setPendingRequests] = useState<ApprovalRequest[]>([]);

  const [loading, setLoading] = useState(true);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const [search, setSearch] = useState('');
  const [requestType, setRequestType] = useState<'CREATE' | 'UPDATE'>('CREATE');
  const [editingSubcategory, setEditingSubcategory] = useState<Subcategory | null>(null);
  const [subcategoryName, setSubcategoryName] = useState('');
  const [plannedAmount, setPlannedAmount] = useState('');
  const [approvedAmounts, setApprovedAmounts] = useState<Record<number, string>>({});
  const [remarks, setRemarks] = useState<Record<number, string>>({});

  const selectedBudget = useMemo(
    () => budgets.find((budget) => budget.id === selectedBudgetId) ?? null,
    [budgets, selectedBudgetId],
  );

  const loadBudgets = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const data = await apiRequest<Budget[]>('/api/budgets');

      const opexBudgets = data.filter(
        (budget) =>
          budget.budget_type === 'OPEX' &&
          OPEX_CATEGORIES.includes(budget.name),
      );

      setBudgets(opexBudgets);

      setSelectedBudgetId((current) => {
        if (current && opexBudgets.some((budget) => budget.id === current)) {
          return current;
        }

        return opexBudgets[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load OPEX budgets.');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadPageData = useCallback(async () => {
    if (!selectedBudgetId) {
      setAllocations([]);
      setMyRequests([]);
      return;
    }

    setDetailsLoading(true);
    setError('');

    try {
      const [allocationData, requestData] = await Promise.all([
        apiRequest<Subcategory[]>(
          `/api/budgets/${selectedBudgetId}/subcategories`,
        ),
        apiRequest<ApprovalRequest[]>(
          '/api/budgets/subcategory-approval-requests/mine',
        ),
      ]);

      setAllocations(allocationData);
      setMyRequests(
        requestData.filter((request) => request.budget_id === selectedBudgetId),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load allocations.');
    } finally {
      setDetailsLoading(false);
    }
  }, [selectedBudgetId]);

  const loadPendingRequests = useCallback(async () => {
    if (!isITHead) return;

    try {
      const data = await apiRequest<ApprovalRequest[]>(
        '/api/budgets/subcategory-approval-requests/pending',
      );

      setPendingRequests(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load pending approvals.');
    }
  }, [isITHead]);

  useEffect(() => {
    void loadBudgets();
  }, [loadBudgets]);

  useEffect(() => {
    void loadPageData();
  }, [loadPageData]);

  useEffect(() => {
    void loadPendingRequests();
  }, [loadPendingRequests]);

  function resetForm() {
    setRequestType('CREATE');
    setEditingSubcategory(null);
    setSubcategoryName('');
    setPlannedAmount('');
  }

  function startCreateRequest() {
    resetForm();
    setError('');
    setSuccess('');
  }

  function startUpdateRequest(item: Subcategory) {
    setRequestType('UPDATE');
    setEditingSubcategory(item);
    setSubcategoryName(item.name);
    setPlannedAmount(String(item.planned_amount));
    setError('');
    setSuccess('');
  }

  async function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedBudget) {
      setError('Please select an OPEX budget category.');
      return;
    }

    const amount = Number(plannedAmount);

    if (!Number.isFinite(amount) || amount < 0) {
      setError('Enter a valid planned amount.');
      return;
    }

    if (requestType === 'CREATE' && !subcategoryName.trim()) {
      setError('Enter a subcategory name.');
      return;
    }

    setSaving(true);
    setError('');
    setSuccess('');

    try {
      if (requestType === 'CREATE') {
        await apiRequest<ApprovalRequest>(
          `/api/budgets/${selectedBudget.id}/subcategories/requests`,
          {
            method: 'POST',
            body: JSON.stringify({
              name: subcategoryName.trim(),
              planned_amount: amount,
            }),
          },
        );

        setSuccess('New allocation request submitted for IT Head approval.');
      } else if (editingSubcategory) {
        await apiRequest<ApprovalRequest>(
          `/api/budgets/subcategories/${editingSubcategory.id}/requests`,
          {
            method: 'PATCH',
            body: JSON.stringify({
              planned_amount: amount,
            }),
          },
        );

        setSuccess('Allocation update request submitted for IT Head approval.');
      }

      resetForm();
      await loadPageData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to submit request.');
    } finally {
      setSaving(false);
    }
  }

  async function decideRequest(request: ApprovalRequest, decision: 'approve' | 'reject') {
    const approvedAmount = approvedAmounts[request.id];
    const requestRemarks = remarks[request.id] || '';

    if (decision === 'approve') {
      if (approvedAmount === undefined || approvedAmount.trim() === '') {
        setError(`Enter an approved amount for request #${request.id}.`);
        return;
      }

      const amount = Number(approvedAmount);

      if (
        !Number.isFinite(amount) ||
        amount <= 0 ||
        amount > Number(request.planned_amount)
      ) {
        setError(
          `Approved amount for request #${request.id} must be greater than zero and cannot exceed its planned amount.`,
        );
        return;
      }

      if (!window.confirm(`Approve allocation request #${request.id}?`)) return;
    } else {
      if (!window.confirm(`Reject allocation request #${request.id}?`)) return;
    }

    setSaving(true);
    setError('');
    setSuccess('');

    try {
      await apiRequest(
        `/api/budgets/subcategory-approval-requests/${request.id}/${decision}`,
        {
          method: 'POST',
          body: JSON.stringify({
            ...(decision === 'approve'
              ? { approved_amount: Number(approvedAmount) }
              : {}),
            remarks: requestRemarks.trim() || null,
          }),
        },
      );

      setSuccess(
        decision === 'approve'
          ? `Request #${request.id} approved. Accounts notification will be sent by the backend.`
          : `Request #${request.id} rejected.`,
      );

      await Promise.all([loadPendingRequests(), loadPageData(), loadBudgets()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to process approval.');
    } finally {
      setSaving(false);
    }
  }

  const filteredAllocations = allocations.filter((item) =>
    item.name.toLowerCase().includes(search.toLowerCase()),
  );

  const filteredPending = pendingRequests.filter((request) =>
    !selectedBudgetId || request.budget_id === selectedBudgetId,
  );

  const plannedTotal = allocations.reduce(
    (sum, item) => sum + Number(item.planned_amount || 0),
    0,
  );

  const approvedTotal = allocations.reduce(
    (sum, item) => sum + Number(item.approved_amount || 0),
    0,
  );

  const selectedRequests = myRequests.filter(
    (request) => request.budget_id === selectedBudgetId,
  );

  return (
    <section className="opex-page">
      <div className="opex-page-header">
        <div>
          <p className="opex-eyebrow">BUDGET MANAGEMENT / OPEX</p>
          <h1>OPEX Allocation Management</h1>
          <p className="opex-subtitle">
            Manage category-level allocations through the IT Head approval workflow.
          </p>
        </div>

        <button className="opex-button opex-button-secondary" onClick={onBack}>
          ← Back to Budget Register
        </button>
      </div>

      {error && <div className="opex-alert opex-alert-error">{error}</div>}
      {success && <div className="opex-alert opex-alert-success">{success}</div>}

      {loading ? (
        <div className="opex-loading">Loading OPEX budgets…</div>
      ) : (
        <>
          <div className="opex-category-panel">
            <div className="opex-category-heading">
              <div>
                <span className="opex-section-label">SELECT CATEGORY</span>
                <h2>OPEX Budget Category</h2>
              </div>

              <select
                value={selectedBudgetId ?? ''}
                onChange={(event) =>
                  setSelectedBudgetId(event.target.value ? Number(event.target.value) : null)
                }
              >
                {budgets.length === 0 && <option value="">No OPEX budgets found</option>}

                {budgets.map((budget) => (
                  <option key={budget.id} value={budget.id}>
                    {budget.name} · {budget.financial_year}
                  </option>
                ))}
              </select>
            </div>

            {selectedBudget && (
              <div className="opex-summary-grid">
                <div className="opex-summary-card">
                  <span>Planned allocation</span>
                  <strong>{formatAmount(plannedTotal)}</strong>
                </div>

                <div className="opex-summary-card">
                  <span>Approved allocation</span>
                  <strong>{formatAmount(approvedTotal)}</strong>
                </div>

                <div className="opex-summary-card">
                  <span>Active subcategories</span>
                  <strong>{allocations.length}</strong>
                </div>

                <div className="opex-summary-card">
                  <span>Pending requests</span>
                  <strong>
                    {isITHead
                      ? filteredPending.length
                      : selectedRequests.filter((item) => item.status === 'PENDING').length}
                  </strong>
                </div>
              </div>
            )}
          </div>

          {selectedBudget && (
            <>
              {!isITHead && (
                <div className="opex-content-card">
                  <div className="opex-card-header">
                    <div>
                      <span className="opex-section-label">ALLOCATION REQUEST</span>
                      <h2>{editingSubcategory ? 'Request allocation update' : 'Add subcategory allocation'}</h2>
                    </div>

                    {editingSubcategory && (
                      <button
                        className="opex-button opex-button-secondary"
                        onClick={startCreateRequest}
                      >
                        Cancel update
                      </button>
                    )}
                  </div>

                  <form className="opex-request-form" onSubmit={submitRequest}>
                    <div className="opex-form-field opex-form-field-wide">
                      <label>Budget category</label>
                      <input value={selectedBudget.name} readOnly />
                    </div>

                    <div className="opex-form-field">
                      <label>Financial year</label>
                      <input value={selectedBudget.financial_year} readOnly />
                    </div>

                    {requestType === 'CREATE' && (
                      <div className="opex-form-field">
                        <label htmlFor="subcategory-name">Subcategory name</label>
                        <input
                          id="subcategory-name"
                          value={subcategoryName}
                          onChange={(event) => setSubcategoryName(event.target.value)}
                          maxLength={200}
                          placeholder="Enter allocation name"
                          required
                        />
                      </div>
                    )}

                    <div className="opex-form-field">
                      <label htmlFor="planned-amount">Planned amount (₹)</label>
                      <input
                        id="planned-amount"
                        type="number"
                        min="0"
                        step="0.01"
                        value={plannedAmount}
                        onChange={(event) => setPlannedAmount(event.target.value)}
                        placeholder="0.00"
                        required
                      />
                    </div>

                    <div className="opex-form-actions">
                      <button
                        type="submit"
                        className="opex-button opex-button-primary"
                        disabled={saving}
                      >
                        {saving
                          ? 'Submitting…'
                          : editingSubcategory
                            ? 'Submit update request'
                            : 'Submit allocation request'}
                      </button>
                    </div>

                    <p className="opex-form-note">
                      Changes take effect only after IT Head approval. The active allocation
                      remains unchanged while a request is pending.
                    </p>
                  </form>
                </div>
              )}

              <div className="opex-content-card">
                <div className="opex-card-header">
                  <div>
                    <span className="opex-section-label">ACTIVE ALLOCATIONS</span>
                    <h2>Subcategory register</h2>
                  </div>

                  <input
                    className="opex-search"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search subcategories…"
                  />
                </div>

                {detailsLoading ? (
                  <div className="opex-loading">Loading allocations…</div>
                ) : (
                  <div className="opex-table-wrap">
                    <table className="opex-table">
                      <thead>
                        <tr>
                          <th>Subcategory</th>
                          <th>Planned amount</th>
                          <th>Approved amount</th>
                          <th>Created</th>
                          {!isITHead && <th>Action</th>}
                        </tr>
                      </thead>

                      <tbody>
                        {filteredAllocations.map((item) => (
                          <tr key={item.id}>
                            <td>
                              <strong>{item.name}</strong>
                            </td>
                            <td>{formatAmount(item.planned_amount)}</td>
                            <td>{formatAmount(item.approved_amount)}</td>
                            <td>{formatDate(item.created_at)}</td>
                            {!isITHead && (
                              <td>
                                <button
                                  className="opex-table-action"
                                  onClick={() => startUpdateRequest(item)}
                                >
                                  Request update
                                </button>
                              </td>
                            )}
                          </tr>
                        ))}

                        {filteredAllocations.length === 0 && (
                          <tr>
                            <td colSpan={isITHead ? 4 : 5} className="opex-empty">
                              No active subcategory allocations found.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {isITHead && (
                <div className="opex-content-card">
                  <div className="opex-card-header">
                    <div>
                      <span className="opex-section-label">IT HEAD REVIEW</span>
                      <h2>Pending approval requests</h2>
                    </div>
                    <span className="opex-count-pill">{filteredPending.length} pending</span>
                  </div>

                  {filteredPending.length === 0 ? (
                    <div className="opex-empty-state">
                      No pending allocation requests for this category.
                    </div>
                  ) : (
                    <div className="opex-approval-list">
                      {filteredPending.map((request) => {
                        const requestBudget = budgets.find(
                          (budget) => budget.id === request.budget_id,
                        );

                        return (
                          <article className="opex-approval-card" key={request.id}>
                            <div className="opex-approval-top">
                              <div>
                                <span className="opex-request-id">REQUEST #{request.id}</span>
                                <h3>{request.name}</h3>
                                <p>
                                  {requestBudget?.name || `Budget #${request.budget_id}`}
                                  {requestBudget ? ` · ${requestBudget.financial_year}` : ''}
                                </p>
                              </div>

                              <span className="opex-status opex-status-pending">PENDING</span>
                            </div>

                            <div className="opex-request-details">
                              <div>
                                <span>Request type</span>
                                <strong>{request.request_type}</strong>
                              </div>
                              <div>
                                <span>Planned amount</span>
                                <strong>{formatAmount(request.planned_amount)}</strong>
                              </div>
                              <div>
                                <span>Requested on</span>
                                <strong>{formatDate(request.requested_at)}</strong>
                              </div>
                            </div>

                            <div className="opex-approval-fields">
                              <div className="opex-form-field">
                                <label>Approved amount (₹)</label>
                                <input
                                  type="number"
                                  min="0.01"
                                  max={Number(request.planned_amount)}
                                  step="0.01"
                                  value={approvedAmounts[request.id] ?? String(request.planned_amount)}
                                  onChange={(event) =>
                                    setApprovedAmounts((current) => ({
                                      ...current,
                                      [request.id]: event.target.value,
                                    }))
                                  }
                                />
                              </div>

                              <div className="opex-form-field">
                                <label>Remarks</label>
                                <input
                                  value={remarks[request.id] || ''}
                                  onChange={(event) =>
                                    setRemarks((current) => ({
                                      ...current,
                                      [request.id]: event.target.value,
                                    }))
                                  }
                                  placeholder="Optional remarks"
                                  maxLength={2000}
                                />
                              </div>
                            </div>

                            <div className="opex-approval-actions">
                              <button
                                className="opex-button opex-button-approve"
                                disabled={saving}
                                onClick={() => void decideRequest(request, 'approve')}
                              >
                                Approve allocation
                              </button>

                              <button
                                className="opex-button opex-button-reject"
                                disabled={saving}
                                onClick={() => void decideRequest(request, 'reject')}
                              >
                                Reject request
                              </button>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              <div className="opex-content-card">
                <div className="opex-card-header">
                  <div>
                    <span className="opex-section-label">WORKFLOW TRACKING</span>
                    <h2>{isITHead ? 'Pending request overview' : 'My request history'}</h2>
                  </div>
                </div>

                {isITHead ? (
                  <p className="opex-form-note">
                    IT Head requests are displayed in the pending approval section above.
                    Requester history is available to the user who submitted each request.
                  </p>
                ) : (
                  <div className="opex-table-wrap">
                    <table className="opex-table">
                      <thead>
                        <tr>
                          <th>Request ID</th>
                          <th>Subcategory</th>
                          <th>Type</th>
                          <th>Planned amount</th>
                          <th>Approved amount</th>
                          <th>Submitted</th>
                          <th>Decision date</th>
                          <th>Status</th>
                          <th>Remarks</th>
                        </tr>
                      </thead>

                      <tbody>
                        {selectedRequests.map((request) => (
                          <tr key={request.id}>
                            <td>#{request.id}</td>
                            <td>{request.name}</td>
                            <td>{request.request_type}</td>
                            <td>{formatAmount(request.planned_amount)}</td>
                            <td>{formatAmount(request.approved_amount)}</td>
                            <td>{formatDate(request.requested_at)}</td>
                            <td>{formatDate(request.decided_at)}</td>
                            <td>
                              <span
                                className={`opex-status opex-status-${request.status.toLowerCase()}`}
                              >
                                {request.status}
                              </span>
                            </td>
                            <td>{request.remarks || '—'}</td>
                          </tr>
                        ))}

                        {selectedRequests.length === 0 && (
                          <tr>
                            <td colSpan={9} className="opex-empty">
                              No allocation requests submitted for this category yet.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}

export default OpexAllocationPage;
