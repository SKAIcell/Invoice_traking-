
import { useCallback, useEffect, useMemo, useState } from 'react';

type OrderCategoryFilter = 'ALL' | 'OPEX' | 'CAPEX';

type InvoiceStatusCounts = {
  PAID: number;
  PART_PAID: number;
  OVERDUE: number;
  ON_HOLD: number;
  UNPAID: number;
};

type DashboardSummary = {
  total_vendor_order_amount: string | number;
  total_balance_payout_due: string | number;
  invoice_status_counts: InvoiceStatusCounts;
};

type BudgetRecord = {
  id: number;
  name: string;
  financial_year: string;
  budget_type: 'OPEX' | 'CAPEX';
  planned_amount: string | number;
  approved_amount: string | number;
};

type OrderRecord = {
  id: number;
  order_type: string;
  order_number: string;
  party_id: number;
  party_name?: string | null;
  party_code?: string | null;
  budget_id: number | null;
  budget_name?: string | null;
  order_date: string;
  amount: string | number;
  status: string;
  location?: string | null;
  description?: string | null;
};

type VendorRecord = {
  id: number;
  party_type: string;
  code: string;
  name: string;
  address?: string | null;
  is_active: boolean;
};

type StatusItem = {
  label: string;
  key: keyof InvoiceStatusCounts;
  description: string;
  className: string;
};

type DashboardPageProps = {
  onVendorSelect: (vendorId: number, vendorName: string) => void;
  onOrderSelect?: (order: OrderRecord) => void;
  onBudgetOrdersSelect: (category: OrderCategoryFilter) => void;
};

type BudgetSummary = {
  type: 'OPEX' | 'CAPEX';
  approved: number;
  orderPlaced: number;
  available: number;
  utilization: number;
  budgetCount: number;
};

type VendorSummary = {
  id: number;
  name: string;
  code: string;
  location: string;
  orderCount: number;
  orderValue: number;
  orders: OrderRecord[];
};

const FINANCIAL_YEAR = '2026-2027';

const CATEGORY_FILTERS: {
  value: OrderCategoryFilter;
  label: string;
}[] = [
  { value: 'ALL', label: 'All' },
  { value: 'OPEX', label: 'OPEX' },
  { value: 'CAPEX', label: 'CAPEX' },
];

const STATUS_ITEMS: StatusItem[] = [
  {
    label: 'Paid',
    key: 'PAID',
    description: 'Payment completed',
    className: 'status-paid',
  },
  {
    label: 'Part paid',
    key: 'PART_PAID',
    description: 'Balance remains',
    className: 'status-part-paid',
  },
  {
    label: 'Overdue',
    key: 'OVERDUE',
    description: 'Past the due date',
    className: 'status-overdue',
  },
  {
    label: 'On hold',
    key: 'ON_HOLD',
    description: 'Requires review',
    className: 'status-on-hold',
  },
  {
    label: 'Unpaid',
    key: 'UNPAID',
    description: 'Payment pending',
    className: 'status-unpaid',
  },
];

function formatCurrency(value: string | number | undefined | null) {
  if (value === undefined || value === null) return '—';

  const amount = Number(value);

  if (!Number.isFinite(amount)) return '—';

  return amount.toLocaleString('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  });
}

function formatCount(value: number | null | undefined) {
  if (value === null || value === undefined) return '—';
  return value.toLocaleString('en-IN');
}

function readArray<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];

  if (
    data !== null &&
    typeof data === 'object' &&
    'items' in data &&
    Array.isArray(data.items)
  ) {
    return data.items as T[];
  }

  throw new Error('An API returned an unexpected response format.');
}

async function fetchApi<T>(path: string, headers: HeadersInit): Promise<T> {
  const response = await fetch(path, { headers });

  if (!response.ok) {
    throw new Error(`${path} request failed (HTTP ${response.status}).`);
  }

  return response.json() as Promise<T>;
}

function DonutChart({
  summary,
  color,
  onUtilizedSelect,
}: {
  summary: BudgetSummary;
  color: string;
  onUtilizedSelect: () => void;
}) {
  const radius = 62;
  const circumference = 2 * Math.PI * radius;

  const placedRatio =
    summary.approved > 0
      ? Math.min(summary.orderPlaced / summary.approved, 1)
      : 0;

  const placedLength = circumference * placedRatio;
  const availableLength = circumference - placedLength;
  const isOverBudget = summary.orderPlaced > summary.approved;
  const displayUtilization =
    summary.approved > 0 ? `${summary.utilization.toFixed(1)}%` : '—';

  const hasUtilizedOrders = summary.orderPlaced > 0;

  function handleUtilizedKeyDown(
    event: React.KeyboardEvent<SVGCircleElement>,
  ) {
    if (!hasUtilizedOrders) return;

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onUtilizedSelect();
    }
  }

  return (
    <div className="budget-donut-layout">
      <div
        className="budget-donut"
        role="group"
        aria-label={`${summary.type} budget utilization ${summary.utilization.toFixed(1)} percent`}
      >
        <svg viewBox="0 0 160 160" aria-hidden="true">
          <circle
            cx="80"
            cy="80"
            r={radius}
            fill="none"
            stroke="#e9eef4"
            strokeWidth="19"
          />

          {summary.approved > 0 && (
            <>
              <circle
                cx="80"
                cy="80"
                r={radius}
                fill="none"
                stroke={color}
                strokeWidth="19"
                strokeDasharray={`${placedLength} ${circumference}`}
                strokeDashoffset="0"
                transform="rotate(-90 80 80)"
                pointerEvents={hasUtilizedOrders ? 'stroke' : 'none'}
                role={hasUtilizedOrders ? 'button' : undefined}
                tabIndex={hasUtilizedOrders ? 0 : undefined}
                aria-label={
                  hasUtilizedOrders
                    ? `Open ${summary.type} orders`
                    : undefined
                }
                style={{
                  cursor: hasUtilizedOrders ? 'pointer' : 'default',
                  outline: 'none',
                }}
                onClick={() => {
                  if (hasUtilizedOrders) onUtilizedSelect();
                }}
                onKeyDown={handleUtilizedKeyDown}
              />

              <circle
                cx="80"
                cy="80"
                r={radius}
                fill="none"
                stroke="#dce5ee"
                strokeWidth="19"
                strokeDasharray={`${availableLength} ${circumference}`}
                strokeDashoffset={-placedLength}
                transform="rotate(-90 80 80)"
                pointerEvents="none"
              />
            </>
          )}
        </svg>

        <div className="budget-donut-center">
          <strong>{displayUtilization}</strong>
          <span>{isOverBudget ? 'Over budget' : 'Utilized'}</span>
        </div>
      </div>

      <div className="budget-legend">
        <div className="budget-legend-item">
          <span
            className="budget-legend-dot"
            style={{ background: color }}
          />
          <div>
            <span>Order placed</span>
            <strong>{formatCurrency(summary.orderPlaced)}</strong>
          </div>
        </div>

        <div className="budget-legend-item">
          <span
            className="budget-legend-dot"
            style={{ background: '#dce5ee' }}
          />
          <div>
            <span>Available budget</span>
            <strong>{formatCurrency(Math.max(summary.available, 0))}</strong>
          </div>
        </div>

        {isOverBudget && (
          <div className="budget-overrun-note">
            Over budget by{' '}
            {formatCurrency(summary.orderPlaced - summary.approved)}
          </div>
        )}
{/* 
        {hasUtilizedOrders && (
          // <button
          //   type="button"
          //   className="budget-orders-link"
          //   onClick={onUtilizedSelect}
          // >
          //   View {summary.type} orders
          // </button>
        )} */}
      </div>
    </div>
  );
}

function BudgetCard({
  summary,
  color,
  onBudgetOrdersSelect,
}: {
  summary: BudgetSummary;
  color: string;
  onBudgetOrdersSelect: (category: OrderCategoryFilter) => void;
}) {
  return (
    <article
      className={`budget-summary-card budget-${summary.type.toLowerCase()}`}
    >
      <div className="budget-card-heading">
        <div>
          <span className="budget-type-label">{summary.type} BUDGET</span>
          <h4>
            {summary.type === 'OPEX'
              ? 'Operating expenditure'
              : 'Capital expenditure'}
          </h4>
        </div>

        <span className="budget-count">
          {summary.budgetCount}{' '}
          {summary.budgetCount === 1 ? 'budget' : 'budgets'}
        </span>
      </div>

      <DonutChart
        summary={summary}
        color={color}
        onUtilizedSelect={() => onBudgetOrdersSelect(summary.type)}
      />

      <div className="budget-approved">
        <span>Approved budget</span>
        <strong>{formatCurrency(summary.approved)}</strong>
      </div>

      {summary.approved === 0 && (
        <p className="budget-empty-note">
          No approved budget recorded for this category and financial year.
        </p>
      )}

      
    </article>
  );
}

function DashboardPage({
  onVendorSelect,
  onOrderSelect,
  onBudgetOrdersSelect,
}: DashboardPageProps) {
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [budgets, setBudgets] = useState<BudgetRecord[]>([]);
  const [orders, setOrders] = useState<OrderRecord[]>([]);
  const [vendors, setVendors] = useState<VendorRecord[]>([]);

  const [dashboardError, setDashboardError] = useState('');
  const [budgetError, setBudgetError] = useState('');
  const [vendorError, setVendorError] = useState('');

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [vendorSearch, setVendorSearch] = useState('');
  const [categoryFilter, setCategoryFilter] =
    useState<OrderCategoryFilter>('ALL');

  const loadDashboard = useCallback(async (isRefresh = false) => {
    const token = sessionStorage.getItem('access_token');

    if (!token) {
      setDashboardError('Your session is unavailable. Please sign in again.');
      setLoading(false);
      setRefreshing(false);
      return;
    }

    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setDashboardError('');
    setBudgetError('');
    setVendorError('');

    const headers = {
      Authorization: `Bearer ${token}`,
    };

    const results = await Promise.allSettled([
      fetchApi<DashboardSummary>('/api/dashboard/summary', headers),
      fetchApi<unknown>(
        `/api/budgets?financial_year=${FINANCIAL_YEAR}`,
        headers,
      ),
      fetchApi<unknown>('/api/orders', headers),
      fetchApi<unknown>(
        '/api/parties?party_type=VENDOR&is_active=true&limit=100',
        headers,
      ),
      fetchApi<unknown>(
        '/api/parties?party_type=CUSTOMER&is_active=true&limit=100',
        headers,
      ),
    ]);

    const [
      dashboardResult,
      budgetResult,
      orderResult,
      vendorResult,
      customerResult,
    ] = results;

    if (dashboardResult.status === 'fulfilled') {
      const summary = dashboardResult.value;

      if (summary.invoice_status_counts) {
        setDashboard(summary);
      } else {
        setDashboardError(
          'The dashboard returned incomplete invoice status data.',
        );
      }
    } else {
      setDashboardError(
        dashboardResult.reason instanceof Error
          ? dashboardResult.reason.message
          : 'Unable to load dashboard data.',
      );
    }

    if (budgetResult.status === 'fulfilled') {
      try {
        setBudgets(readArray<BudgetRecord>(budgetResult.value));
      } catch (error) {
        setBudgets([]);
        setBudgetError(
          error instanceof Error
            ? error.message
            : 'Unable to read budget data.',
        );
      }
    } else {
      setBudgets([]);
      setBudgetError(
        budgetResult.reason instanceof Error
          ? budgetResult.reason.message
          : 'Unable to load budgets.',
      );
    }

    if (orderResult.status === 'fulfilled') {
      try {
        setOrders(readArray<OrderRecord>(orderResult.value));
      } catch (error) {
        setOrders([]);
        setVendorError(
          error instanceof Error
            ? error.message
            : 'Unable to read order data.',
        );
      }
    } else {
      setOrders([]);
      setVendorError(
        orderResult.reason instanceof Error
          ? orderResult.reason.message
          : 'Unable to load orders.',
      );
    }

    const loadedParties: VendorRecord[] = [];
    let partyLoadFailed = false;

    if (vendorResult.status === 'fulfilled') {
      try {
        loadedParties.push(...readArray<VendorRecord>(vendorResult.value));
      } catch {
        partyLoadFailed = true;
      }
    } else {
      partyLoadFailed = true;
    }

    if (customerResult.status === 'fulfilled') {
      try {
        loadedParties.push(...readArray<VendorRecord>(customerResult.value));
      } catch {
        partyLoadFailed = true;
      }
    } else {
      partyLoadFailed = true;
    }

    setVendors(loadedParties);

    if (partyLoadFailed) {
      setVendorError(
        'Some vendor or customer details could not be loaded. Order records may still be displayed.',
      );
    }

    setLastUpdated(new Date());
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const budgetSummaries = useMemo<BudgetSummary[]>(() => {
    return (['OPEX', 'CAPEX'] as const).map((type) => {
      const categoryBudgets = budgets.filter(
        (budget) =>
          budget.budget_type === type &&
          budget.financial_year === FINANCIAL_YEAR,
      );

      const approved = categoryBudgets.reduce(
        (total, budget) => total + Number(budget.approved_amount || 0),
        0,
      );

      const budgetIds = new Set(categoryBudgets.map((budget) => budget.id));

      // Purchase orders are linked to CAPEX budgets by the current data model.
      // Service orders are displayed under OPEX, but have no budget_id.
      // Count orders against their matching financial-year budget.
// PO amounts contribute to CAPEX; SO amounts contribute to OPEX.
const expectedOrderType = type === 'CAPEX' ? 'PO' : 'SO';

const orderPlaced = orders
  .filter(
    (order) =>
      order.order_type === expectedOrderType &&
      order.budget_id !== null &&
      budgetIds.has(order.budget_id) &&
      order.status.toUpperCase() !== 'CANCELLED',
  )
  .reduce(
    (total, order) => total + Number(order.amount || 0),
    0,
  );

      const available = approved - orderPlaced;
      const utilization =
        approved > 0 ? (orderPlaced / approved) * 100 : 0;

      return {
        type,
        approved,
        orderPlaced,
        available,
        utilization,
        budgetCount: categoryBudgets.length,
      };
    });
  }, [budgets, orders]);

  const vendorSummaries = useMemo<VendorSummary[]>(() => {
    const partyMap = new Map<number, VendorRecord>();
    vendors.forEach((party) => partyMap.set(party.id, party));

    const grouped = new Map<number, VendorSummary>();

    orders
      .filter(
        (order) =>
          (order.order_type === 'PO' || order.order_type === 'SO') &&
          order.status.toUpperCase() !== 'CANCELLED',
      )
      .forEach((order) => {
        const party = partyMap.get(order.party_id);
        const partyName =
          party?.name ||
          order.party_name ||
          `${order.order_type === 'SO' ? 'Customer' : 'Vendor'} #${order.party_id}`;
        const partyCode = party?.code || order.party_code || '';
        const partyLocation =
          order.location?.trim() ||
          party?.address?.trim() ||
          'Location not recorded';

        const existing = grouped.get(order.party_id);

        if (existing) {
          existing.orderCount += 1;
          existing.orderValue += Number(order.amount || 0);
          existing.orders.push(order);

          if (
            existing.location === 'Location not recorded' &&
            partyLocation !== 'Location not recorded'
          ) {
            existing.location = partyLocation;
          }
        } else {
          grouped.set(order.party_id, {
            id: order.party_id,
            name: partyName,
            code: partyCode,
            location: partyLocation,
            orderCount: 1,
            orderValue: Number(order.amount || 0),
            orders: [order],
          });
        }
      });

    return Array.from(grouped.values()).sort(
      (a, b) => b.orderValue - a.orderValue,
    );
  }, [orders, vendors]);

  const categoryFilteredVendors = useMemo(() => {
    return vendorSummaries
      .map((party) => {
        const matchingOrders = party.orders.filter((order) => {
          if (categoryFilter === 'OPEX') return order.order_type === 'SO';
          if (categoryFilter === 'CAPEX') return order.order_type === 'PO';
          return true;
        });

        return {
          ...party,
          orders: matchingOrders,
          orderCount: matchingOrders.length,
          orderValue: matchingOrders.reduce(
            (total, order) => total + Number(order.amount || 0),
            0,
          ),
        };
      })
      .filter((party) => party.orders.length > 0)
      .sort((a, b) => b.orderValue - a.orderValue);
  }, [vendorSummaries, categoryFilter]);

  const filteredVendors = useMemo(() => {
    const search = vendorSearch.trim().toLowerCase();

    if (!search) return categoryFilteredVendors;

    return categoryFilteredVendors.filter((party) => {
      const matchingParty =
        party.name.toLowerCase().includes(search) ||
        party.code.toLowerCase().includes(search) ||
        party.location.toLowerCase().includes(search);

      const matchingOrder = party.orders.some((order) =>
        order.order_number.toLowerCase().includes(search),
      );

      return matchingParty || matchingOrder;
    });
  }, [vendorSearch, categoryFilteredVendors]);

  const maxVendorValue = Math.max(
    ...filteredVendors.map((party) => party.orderValue),
    1,
  );

  const categoryHeading =
    categoryFilter === 'OPEX'
      ? 'Service order details'
      : categoryFilter === 'CAPEX'
        ? 'Vendor-wise purchase order details'
        : 'Vendor wise order details';

  const chartHeading =
    categoryFilter === 'OPEX'
      ? 'Service order value by customer'
      : categoryFilter === 'CAPEX'
        ? 'Purchase order value by vendor'
        : 'Order value by vendor';

  return (
    <section className="page-content dashboard-page">
      <header className="dashboard-heading">
        <div>
          <p className="eyebrow">FINANCE OPERATIONS</p>
          <h2>Dashboard</h2>
          <p className="page-description">
            Monitor budget utilization, vendor commitments, outstanding payments
            and invoice activity across finance operations.
          </p>
        </div>

        <button
          className="dashboard-refresh-button"
          type="button"
          onClick={() => void loadDashboard(true)}
          disabled={loading || refreshing}
        >
          {refreshing ? 'Refreshing...' : 'Refresh data'}
        </button>
      </header>

      <div className="dashboard-meta">
        <span className="dashboard-live-indicator" />
        <span>
          {loading
            ? 'Loading financial data...'
            : dashboardError || budgetError || vendorError
              ? 'Some dashboard data needs attention'
              : 'Financial year overview'}
        </span>

        {lastUpdated && (
          <span className="dashboard-updated">
            Last updated:{' '}
            {lastUpdated.toLocaleTimeString('en-IN', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        )}
      </div>

      {dashboardError && (
        <div className="dashboard-alert" role="alert">
          <strong>Unable to load dashboard summary</strong>
          <span>{dashboardError}</span>
          <button
            type="button"
            onClick={() => void loadDashboard(true)}
            disabled={refreshing}
          >
            Try again
          </button>
        </div>
      )}

      {(budgetError || vendorError) && (
        <div className="dashboard-inline-warning" role="status">
          {budgetError && <p>Budget data: {budgetError}</p>}
          {vendorError && <p>Vendor/order data: {vendorError}</p>}
        </div>
      )}

      <section className="dashboard-budget-section">
        <div className="dashboard-section-heading">
          <div>
            <h3>Budget utilization</h3>
            <p>
              Financial year {FINANCIAL_YEAR} · Approved budget compared with
              purchase order commitments.
            </p>
          </div>
        </div>

        <div className="budget-cards-grid">
          <BudgetCard
            summary={budgetSummaries[0]}
            color="#3978bd"
            onBudgetOrdersSelect={onBudgetOrdersSelect}
          />
          <BudgetCard
            summary={budgetSummaries[1]}
            color="#299b73"
            onBudgetOrdersSelect={onBudgetOrdersSelect}
          />
        </div>

        <p className="dashboard-footnote">
  OPEX utilization is calculated from non-cancelled service orders
  linked to OPEX budgets. CAPEX utilization is calculated from
  non-cancelled purchase orders linked to CAPEX budgets.
</p>
      </section>

      <section className="dashboard-vendors-section">
        <div className="dashboard-section-heading vendor-section-heading">
          <div>
            <h3>{categoryHeading}</h3>
            <p>
              Select a party to view its orders, or select an order number to
              open its invoice details.
            </p>
          </div>

          <div className="vendor-dashboard-controls">
            <div
              className="vendor-category-filters"
              role="group"
              aria-label="Filter orders by category"
            >
              {CATEGORY_FILTERS.map((filter) => (
                <button
                  key={filter.value}
                  type="button"
                  className={`vendor-category-filter ${
                    categoryFilter === filter.value ? 'active' : ''
                  }`}
                  aria-pressed={categoryFilter === filter.value}
                  onClick={() => setCategoryFilter(filter.value)}
                >
                  {filter.label}
                </button>
              ))}
            </div>

            <input
              className="vendor-dashboard-search"
              type="search"
              value={vendorSearch}
              onChange={(event) => setVendorSearch(event.target.value)}
              placeholder="Search party, order or location"
              aria-label="Search vendor or customer orders"
            />
          </div>
        </div>

        <div className="vendor-order-chart">
          <div className="vendor-chart-heading">
            <h4>{chartHeading}</h4>
            <span>Highest value first</span>
          </div>

          {filteredVendors.length === 0 ? (
            <p className="dashboard-empty-state">
              {loading
                ? 'Loading vendor and customer orders...'
                : `No ${categoryFilter === 'ALL' ? '' : `${categoryFilter} `}orders match your search.`}
            </p>
          ) : (
            <div className="vendor-bars">
              {filteredVendors.slice(0, 6).map((party) => {
                const width = Math.max(
                  2,
                  (party.orderValue / maxVendorValue) * 100,
                );

                return (
                  <button
                    type="button"
                    className="vendor-bar-row"
                    key={party.id}
                    onClick={() => onVendorSelect(party.id, party.name)}
                    title={`Open orders for ${party.name}`}
                  >
                    <span className="vendor-bar-name">{party.name}</span>

                    <span className="vendor-bar-track">
                      <span
                        className="vendor-bar-fill"
                        style={{ width: `${width}%` }}
                      />
                    </span>

                    <strong className="vendor-bar-value">
                      {formatCurrency(party.orderValue)}
                    </strong>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="vendor-table-wrapper">
          <table className="vendor-orders-table">
            <thead>
              <tr>
                <th>{categoryFilter === 'OPEX' ? 'Customer' : categoryFilter === 'CAPEX' ? 'Vendor' : 'Vendor / customer'}</th>
                <th>Order count</th>
                <th>Order value</th>
                <th>Location</th>
                <th>Order numbers</th>
              </tr>
            </thead>

            <tbody>
              {filteredVendors.map((party) => (
                <tr key={party.id}>
                  <td>
                    <button
                      className="vendor-name-link"
                      type="button"
                      onClick={() => onVendorSelect(party.id, party.name)}
                      title={`View orders for ${party.name}`}
                    >
                      {party.name}
                    </button>

                    {party.code && (
                      <span className="vendor-code">{party.code}</span>
                    )}
                  </td>

                  <td>{formatCount(party.orderCount)}</td>

                  <td className="vendor-value-cell">
                    {formatCurrency(party.orderValue)}
                  </td>

                  <td>{party.location}</td>

                  <td>
                    <div className="vendor-order-links">
                      {party.orders.map((order) =>
                        onOrderSelect ? (
                          <button
                            className="order-number-link"
                            type="button"
                            key={order.id}
                            onClick={() => onOrderSelect(order)}
                            title={`Open invoices for ${order.order_number}`}
                          >
                            {order.order_number}
                          </button>
                        ) : (
                          <span className="order-number-text" key={order.id}>
                            {order.order_number}
                          </span>
                        ),
                      )}
                    </div>
                  </td>
                </tr>
              ))}

              {!loading && filteredVendors.length === 0 && (
                <tr>
                  <td colSpan={5} className="vendor-table-empty">
                    No matching order records found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="dashboard-status-section">
        <div className="dashboard-section-heading">
          <div>
            <h3>Invoice status</h3>
            <p>Review the current distribution of invoice statuses.</p>
          </div>
        </div>

        <div className="status-grid">
          {STATUS_ITEMS.map((item) => (
            <article
              className={`status-card ${item.className}`}
              key={item.key}
            >
              <div className="status-card-top">
                <span className="status-label">{item.label}</span>
                <span className="status-indicator" aria-hidden="true" />
              </div>

              <strong>
                {formatCount(dashboard?.invoice_status_counts[item.key])}
              </strong>

              <small>{item.description}</small>
            </article>
          ))}
        </div>
      </section>

      <footer className="page-footer">
        Skipper Limited · Internal Finance Operations
      </footer>
    </section>
  );
}

export default DashboardPage;
