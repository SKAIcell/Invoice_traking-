import { useEffect, useRef, useState } from 'react';
import InvoicesPage, {
  type Invoice,
  type InvoiceRegisterRow,
} from './pages/InvoicesPage';
import CompanyLogo from "./components/CompanyLogo";
import OrdersPage from './pages/OrdersPage';
import BudgetsPage from './pages/BudgetsPage';
import OrderInvoicesPage from './pages/OrderInvoicesPage';
import DashboardPage from './pages/DashboardPage';
import VendorsPage from './pages/VendorsPage';
import PaymentsPage from './pages/PaymentsPage';

type OrderCategoryFilter = 'ALL' | 'OPEX' | 'CAPEX';

type SelectedOrder = {
  id: number;
  order_type: string;
  order_number: string;
  party_id: number;
  party_name?: string | null;
  budget_id: number | null;
  budget_name?: string | null;
  financial_year?: string;
  order_date: string;
  order_period?: string | null;
  location?: string | null;
  amount: string | number;
  submitted_invoice_amount?: string | number;
  available_order_value?: string | number;
  total_submitted_invoice?: number;
  status: string;
  description?: string | null;
  order_file_path?: string | null;
  approval_file_path?: string | null;
};

type AppNavigationState = {
  activePage: string;
  selectedOrder: SelectedOrder | null;
  selectedPaymentInvoice: InvoiceRegisterRow | null;
  selectedVendorId: number | null;
  selectedVendorName: string;
  initialCategoryFilter: OrderCategoryFilter;
  invoiceEditorMode: 'create' | 'edit' | null;
  selectedInvoiceToEdit: Invoice | null;
};

const DEFAULT_NAVIGATION_STATE: AppNavigationState = {
  activePage: 'dashboard',
  selectedOrder: null,
  selectedPaymentInvoice: null,
  selectedVendorId: null,
  selectedVendorName: '',
  initialCategoryFilter: 'ALL',
  invoiceEditorMode: null,
  selectedInvoiceToEdit: null,
};



function App() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [activePage, setActivePage] = useState('dashboard');

  const [selectedPaymentInvoice, setSelectedPaymentInvoice] =
    useState<InvoiceRegisterRow | null>(null);

  const [selectedOrder, setSelectedOrder] =
    useState<SelectedOrder | null>(null);

  const [selectedVendorId, setSelectedVendorId] =
    useState<number | null>(null);

  const [selectedVendorName, setSelectedVendorName] = useState('');

  const [initialCategoryFilter, setInitialCategoryFilter] =
    useState<OrderCategoryFilter>('ALL');

  const [invoiceEditorMode, setInvoiceEditorMode] = useState<
    'create' | 'edit' | null
  >(null);

  const [selectedInvoiceToEdit, setSelectedInvoiceToEdit] =
    useState<Invoice | null>(null);

  // Keeps the latest navigation context available to navigation handlers.
  const navigationStateRef = useRef<AppNavigationState>({
    ...DEFAULT_NAVIGATION_STATE,
  });

  // Apply a saved navigation state to the React application.
  function applyNavigationState(next: AppNavigationState) {
    navigationStateRef.current = next;

    setActivePage(next.activePage);
    setSelectedOrder(next.selectedOrder);
    setSelectedPaymentInvoice(next.selectedPaymentInvoice);
    setSelectedVendorId(next.selectedVendorId);
    setSelectedVendorName(next.selectedVendorName);
    setInitialCategoryFilter(next.initialCategoryFilter);
    setInvoiceEditorMode(next.invoiceEditorMode);
    setSelectedInvoiceToEdit(next.selectedInvoiceToEdit);
  }

  // Save a new application view in the browser's history.
  function navigateToState(next: AppNavigationState) {
    applyNavigationState(next);

    window.history.pushState(
      {
        invoiceTracker: true,
        appState: next,
      },
      '',
      window.location.href,
    );
  }

  // Restore the application view when browser Back or Forward is clicked.
  useEffect(() => {
    const token = sessionStorage.getItem('access_token');

    if (!token) {
      return;
    }

    const savedState = window.history.state;

    if (savedState?.invoiceTracker && savedState.appState) {
      applyNavigationState(savedState.appState as AppNavigationState);
    } else {
      window.history.replaceState(
        {
          invoiceTracker: true,
          appState: navigationStateRef.current,
        },
        '',
        window.location.href,
      );
    }

    function handlePopState(event: PopStateEvent) {
      if (event.state?.invoiceTracker && event.state.appState) {
        applyNavigationState(event.state.appState as AppNavigationState);
      }
    }

    window.addEventListener('popstate', handlePopState);

    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      const responseText = await response.text();

      let data: {
        access_token?: string;
        username?: string;
        role?: string;
        detail?: string;
      } = {};

      if (responseText.trim()) {
        try {
          data = JSON.parse(responseText);
        } catch {
          throw new Error(
            `Server returned an invalid response (HTTP ${response.status}).`,
          );
        }
      }

      if (!response.ok) {
        throw new Error(
          data.detail || `Sign-in failed (HTTP ${response.status}).`,
        );
      }

      if (!data.access_token) {
        throw new Error('Login response did not contain an access token.');
      }

      sessionStorage.setItem('access_token', data.access_token);

      if (data.username) {
        sessionStorage.setItem('username', data.username);
      }

      if (data.role) {
        sessionStorage.setItem('role', data.role);
      }

      // Start a fresh application history after login.
      window.history.replaceState(null, '', window.location.href);
      window.location.reload();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to connect to the server. Please try again.',
      );
    } finally {
      setLoading(false);
    }
  }

  const token = sessionStorage.getItem('access_token');
  const loggedInUser = sessionStorage.getItem('username');
  const role = sessionStorage.getItem('role');

  if (!token) {
    return (
      <main className="login-page">
        <section className="login-brand-panel">
          <div className="brand-lockup">
            <CompanyLogo />
            <div>
              <h1>Skipper Limited</h1>
              <p>Finance Operations</p>
            </div>
          </div>

          <div className="brand-message">
            <p className="eyebrow">CORPORATE FINANCE</p>
            <h2>Invoice and vendor payment management.</h2>
            <p>
              A central workspace for tracking purchase orders, invoices,
              vendor commitments and outstanding payments.
            </p>
          </div>

          <div className="brand-footer">Internal business application</div>
        </section>

        <section className="login-form-panel">
          <div className="login-form-wrap">
            <div className="mobile-brand">
              <CompanyLogo />
              <span>Skipper Limited</span>
            </div>

            <p className="eyebrow">WELCOME BACK</p>
            <h2>Sign in to your account</h2>
            <p className="login-description">
              Enter your company account credentials to continue.
            </p>

            <form onSubmit={handleLogin}>
              <label htmlFor="username">Username</label>
              <input
                id="username"
                name="username"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Enter your username"
                required
              />

              <label htmlFor="password">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter your password"
                required
              />

              {error && (
                <div className="error-message" role="alert">
                  {error}
                </div>
              )}

              <button
                className="primary-button"
                type="submit"
                disabled={loading}
              >
                {loading ? 'Signing in...' : 'Sign in securely'}
              </button>
            </form>

            <p className="security-note">
              Access is restricted to authorised company users.
            </p>

            <p className="login-copyright">
              Skipper Limited · Finance Operations
            </p>
          </div>
        </section>
      </main>
    );
  }

  const navigationItems = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'invoices', label: 'Invoices' },
    { id: 'orders', label: 'Orders' },
    { id: 'payments', label: 'Payments' },
    { id: 'vendors', label: 'Vendors' },
    { id: 'budgets', label: 'Budgets' },
  ];

  const pageTitle =
    navigationItems.find((item) => item.id === activePage)?.label ??
    'Dashboard';

  function openVendorOrders(vendorId: number, vendorName: string) {
    const nextState: AppNavigationState = {
      ...navigationStateRef.current,
      activePage: 'orders',
      selectedVendorId: vendorId,
      selectedVendorName: vendorName,
      initialCategoryFilter: 'ALL',
      selectedOrder: null,
      selectedInvoiceToEdit: null,
      invoiceEditorMode: null,
    };

    navigateToState(nextState);
  }

  async function openInvoicePayments(invoiceId: number) {
    try {
      const accessToken = sessionStorage.getItem('access_token');

      if (!accessToken) {
        throw new Error('Your session has expired. Please sign in again.');
      }

      const response = await fetch('/api/invoices/register', {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (!response.ok) {
        throw new Error('Unable to load invoice payment details.');
      }

      const invoiceRows: InvoiceRegisterRow[] = await response.json();

      const matchingInvoice = invoiceRows.find(
        (item) => item.id === invoiceId,
      );

      if (!matchingInvoice) {
        throw new Error('Invoice register record could not be found.');
      }

      const nextState: AppNavigationState = {
        ...navigationStateRef.current,
        activePage: 'payments',
        selectedPaymentInvoice: matchingInvoice,
      };

      navigateToState(nextState);
    } catch (err) {
      window.alert(
        err instanceof Error
          ? err.message
          : 'Unable to open payment details.',
      );
    }
  }

  function openOrderInvoices(order: SelectedOrder) {
    const nextState: AppNavigationState = {
      ...navigationStateRef.current,
      activePage: 'orders',
      selectedVendorId: null,
      selectedVendorName: '',
      selectedInvoiceToEdit: null,
      invoiceEditorMode: null,
      selectedOrder: order,
    };

    navigateToState(nextState);
  }

  function openBudgetOrders(category: OrderCategoryFilter) {
    const nextState: AppNavigationState = {
      ...navigationStateRef.current,
      activePage: 'orders',
      initialCategoryFilter: category,
      selectedVendorId: null,
      selectedVendorName: '',
      selectedOrder: null,
      selectedInvoiceToEdit: null,
      invoiceEditorMode: null,
    };

    navigateToState(nextState);
  }

  function handleNavigation(pageId: string) {
    const currentState = navigationStateRef.current;

    const nextState: AppNavigationState = {
      ...currentState,
      activePage: pageId,
      selectedPaymentInvoice:
        pageId === 'payments' ? null : currentState.selectedPaymentInvoice,
      selectedOrder: null,
      selectedInvoiceToEdit: null,
      invoiceEditorMode: null,
      selectedVendorId:
        pageId === 'orders' ? null : currentState.selectedVendorId,
      selectedVendorName:
        pageId === 'orders' ? '' : currentState.selectedVendorName,
      initialCategoryFilter:
        pageId === 'orders' ? 'ALL' : currentState.initialCategoryFilter,
    };

    navigateToState(nextState);
  }

  async function openOrderFromPaymentHistory(orderId: number) {
    try {
      const accessToken = sessionStorage.getItem('access_token');

      if (!accessToken) {
        throw new Error('Your session has expired. Please sign in again.');
      }

      const response = await fetch(`/api/orders/${orderId}`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (!response.ok) {
        const errorText = await response.text();

        throw new Error(
          `Order request failed (HTTP ${response.status}): ${
            errorText || response.statusText
          }`,
        );
      }

      const order: SelectedOrder = await response.json();

      const nextState: AppNavigationState = {
        ...navigationStateRef.current,
        activePage: 'orders',
        selectedVendorId: null,
        selectedVendorName: '',
        initialCategoryFilter: 'ALL',
        selectedInvoiceToEdit: null,
        invoiceEditorMode: null,
        selectedOrder: order,
      };

      navigateToState(nextState);
    } catch (err) {
      console.error('Error opening order from payment history:', err);

      window.alert(
        err instanceof Error
          ? err.message
          : 'Unable to open this order. Please try again.',
      );
    }
  }

  function backToOrderDetails() {
    const currentState = navigationStateRef.current;

    navigateToState({
      ...currentState,
      invoiceEditorMode: null,
      selectedInvoiceToEdit: null,
    });
  }

  function addInvoiceToOrder(order: SelectedOrder) {
    navigateToState({
      ...navigationStateRef.current,
      selectedOrder: order,
      invoiceEditorMode: 'create',
      selectedInvoiceToEdit: null,
    });
  }

  function editInvoiceForOrder(invoice: Invoice) {
    navigateToState({
      ...navigationStateRef.current,
      invoiceEditorMode: 'edit',
      selectedInvoiceToEdit: invoice,
    });
  }

  function backFromOrderInvoices() {
    navigateToState({
      ...navigationStateRef.current,
      selectedOrder: null,
      selectedInvoiceToEdit: null,
      invoiceEditorMode: null,
    });
  }

  function backToInvoicesFromPayments() {
    navigateToState({
      ...navigationStateRef.current,
      activePage: 'invoices',
      selectedPaymentInvoice: null,
    });
  }

  function handleLogout() {
    sessionStorage.clear();
    window.history.replaceState(null, '', window.location.href);
    window.location.reload();
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <CompanyLogo />
          <div>
            <h1>Skipper Limited</h1>
            <p>Finance Operations</p>
          </div>
        </div>

        <p className="workspace-label">WORKSPACE</p>

        <nav className="navigation" aria-label="Main navigation">
          {navigationItems.map((item) => (
            <a
              key={item.id}
              className={`nav-item ${
                activePage === item.id ? 'active' : ''
              }`}
              href={`#${item.id}`}
              onClick={(event) => {
                event.preventDefault();
                handleNavigation(item.id);
              }}
            >
              {item.label}
            </a>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="user-avatar">
            {(loggedInUser || 'U').slice(0, 1).toUpperCase()}
          </div>

          <div className="user-details">
            <strong>{loggedInUser}</strong>
            <span>{role}</span>
          </div>

          <button className="logout-button" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <span>Finance Operations / {pageTitle}</span>
          <span className="user-role">{role}</span>
        </header>

        {activePage === 'dashboard' && (
          <DashboardPage
            onVendorSelect={openVendorOrders}
            onOrderSelect={openOrderInvoices}
            onBudgetOrdersSelect={openBudgetOrders}
          />
        )}

        {activePage === 'invoices' && (
          <InvoicesPage
            onPaymentDetails={(invoice) => {
              void openInvoicePayments(invoice.id);
            }}
          />
        )}

        {activePage === 'orders' &&
          (selectedOrder ? (
            invoiceEditorMode ? (
              <InvoicesPage
                key={`${selectedOrder.id}-${invoiceEditorMode}-${
                  selectedInvoiceToEdit?.id ?? 'new'
                }`}
                orderContext={selectedOrder}
                initialInvoiceToEdit={selectedInvoiceToEdit}
                onBackToOrder={backToOrderDetails}
              />
            ) : (
              <OrderInvoicesPage
                order={selectedOrder}
                onBack={backFromOrderInvoices}
                onAddInvoice={addInvoiceToOrder}
                onEditInvoice={editInvoiceForOrder}
                onPaymentDetails={(invoice) => {
                  void openInvoicePayments(invoice.id);
                }}
              />
            )
          ) : (
            <OrdersPage
              onOpenOrder={openOrderInvoices}
              initialVendorId={selectedVendorId}
              initialVendorName={selectedVendorName}
              initialCategoryFilter={initialCategoryFilter}
            />
          ))}

        {activePage === 'budgets' && <BudgetsPage />}

        {activePage === 'vendors' && (
          <VendorsPage onVendorSelect={openVendorOrders} />
        )}

        {activePage === 'payments' && (
          <PaymentsPage
            invoice={selectedPaymentInvoice}
            onOpenOrder={openOrderFromPaymentHistory}
            onBackToInvoices={backToInvoicesFromPayments}
          />
        )}
      </main>
    </div>
  );
}

export default App;