
import { useEffect, useMemo, useState, type FormEvent } from "react";
import "../styles/Payments.css";
import type { InvoiceRegisterRow } from "./InvoicesPage";

type PaymentsPageProps = {
  invoice?: InvoiceRegisterRow | null;
  onBackToInvoices?: () => void;
  onOpenOrder?: (orderId: number) => void | Promise<void>;
};

type Payment = {
  id: number;
  invoice_id: number;
  payment_date: string;
  amount: string | number;
  reference_number: string | null;
  notes: string | null;
  created_at: string;
};

type PaymentForm = {
  invoice_id: string;
  payment_date: string;
  amount: string;
  reference_number: string;
  notes: string;
};

const API_URL = "/api";

function getToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function formatAmount(value: string | number | null | undefined): string {
  const amount = Number(value ?? 0);

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(Number.isFinite(amount) ? amount : 0);
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(`${value.slice(0, 10)}T00:00:00`);

  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function getInvoiceLabel(invoice: InvoiceRegisterRow): string {
  return `${invoice.invoice_number} — ${invoice.party_name ?? "Unknown vendor"}`;
}

type InvoiceSearchProps = {
  invoices: InvoiceRegisterRow[];
  selectedId: string;
  onSelect: (id: string) => void;
  placeholder?: string;
  id: string;
};

function InvoiceSearch({
  invoices,
  selectedId,
  onSelect,
  placeholder = "Search invoice number or vendor...",
  id,
}: InvoiceSearchProps) {
  const selectedInvoice = invoices.find(
    (item) => String(item.id) === selectedId,
  );

  const [query, setQuery] = useState(
    selectedInvoice ? getInvoiceLabel(selectedInvoice) : "",
  );

  const [showResults, setShowResults] = useState(false);

  useEffect(() => {
    setQuery(selectedInvoice ? getInvoiceLabel(selectedInvoice) : "");
  }, [selectedId, selectedInvoice]);

  const results = useMemo(() => {
    const searchTerm = query.trim().toLowerCase();

    if (!searchTerm) return invoices.slice(0, 8);

    return invoices
      .filter(
        (item) =>
          item.invoice_number.toLowerCase().includes(searchTerm) ||
          (item.party_name ?? "").toLowerCase().includes(searchTerm) ||
          String(item.id).includes(searchTerm),
      )
      .slice(0, 8);
  }, [invoices, query]);

  function handleChange(value: string) {
    setQuery(value);
    setShowResults(true);

    const exactMatch = invoices.find(
      (item) => getInvoiceLabel(item).toLowerCase() === value.toLowerCase(),
    );

    if (exactMatch) {
      onSelect(String(exactMatch.id));
      setShowResults(false);
    } else {
      onSelect("");
    }
  }

  function chooseInvoice(item: InvoiceRegisterRow) {
    setQuery(getInvoiceLabel(item));
    onSelect(String(item.id));
    setShowResults(false);
  }

  return (
    <div className="payments-invoice-search">
      <input
        id={id}
        type="text"
        autoComplete="off"
        value={query}
        placeholder={placeholder}
        onChange={(event) => handleChange(event.target.value)}
        onFocus={() => setShowResults(true)}
        onBlur={() => {
          window.setTimeout(() => setShowResults(false), 180);
        }}
      />

      {showResults && (
        <div className="payments-invoice-search-results">
          {results.length > 0 ? (
            results.map((item) => (
              <button
                key={item.id}
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => chooseInvoice(item)}
                className="payments-invoice-search-option"
              >
                <strong>{item.invoice_number}</strong>
                <span>{item.party_name ?? "Unknown vendor"}</span>
                <small>
                  Invoice #{item.id} · Balance: {formatAmount(item.balance_due)}
                </small>
              </button>
            ))
          ) : (
            <div className="payments-invoice-search-empty">
              No matching invoices found.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function PaymentsPage({
  invoice,
  onBackToInvoices,
  onOpenOrder,
}: PaymentsPageProps) {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [invoices, setInvoices] = useState<InvoiceRegisterRow[]>([]);

  // History filter is independent of the invoice selected in the form.
  const [historyInvoiceId, setHistoryInvoiceId] = useState(
    invoice ? String(invoice.id) : "",
  );

  const [form, setForm] = useState<PaymentForm>({
    invoice_id: invoice ? String(invoice.id) : "",
    payment_date: getToday(),
    amount: "",
    reference_number: "",
    notes: "",
  });

  const [modalOpen, setModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");

  const accessToken = sessionStorage.getItem("access_token");

  const headers: HeadersInit = {
    Authorization: `Bearer ${accessToken ?? ""}`,
  };

  async function loadData() {
    setLoading(true);
    setError("");

    try {
      const [paymentsResponse, invoicesResponse] = await Promise.all([
        fetch(`${API_URL}/payments`, { headers }),
        fetch(`${API_URL}/invoices/register`, { headers }),
      ]);

      if (
        paymentsResponse.status === 401 ||
        invoicesResponse.status === 401
      ) {
        throw new Error(
          "Your session may have expired. Please sign in again.",
        );
      }

      if (!paymentsResponse.ok) {
        throw new Error("Unable to load payment records.");
      }

      if (!invoicesResponse.ok) {
        throw new Error("Unable to load invoice records.");
      }

      const paymentData: Payment[] = await paymentsResponse.json();
      const invoiceData: InvoiceRegisterRow[] =
        await invoicesResponse.json();

      setPayments(paymentData);
      setInvoices(invoiceData);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load payment data.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  useEffect(() => {
    if (invoice) {
      setHistoryInvoiceId(String(invoice.id));

      setForm((current) => ({
        ...current,
        invoice_id: String(invoice.id),
      }));
    }
  }, [invoice]);

  // Close the modal with the Escape key.
  useEffect(() => {
    if (!modalOpen) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !saving) {
        setModalOpen(false);
        setError("");
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [modalOpen, saving]);

  const historyInvoice = useMemo(() => {
    if (!historyInvoiceId) return null;

    return (
      invoices.find((item) => item.id === Number(historyInvoiceId)) ??
      (invoice?.id === Number(historyInvoiceId) ? invoice : null)
    );
  }, [invoices, historyInvoiceId, invoice]);

  const formInvoice = useMemo(() => {
    if (!form.invoice_id) return null;

    return (
      invoices.find((item) => item.id === Number(form.invoice_id)) ??
      (invoice?.id === Number(form.invoice_id) ? invoice : null)
    );
  }, [invoices, form.invoice_id, invoice]);

  const filteredPayments = useMemo(() => {
    const query = search.trim().toLowerCase();

    return payments
      .filter((payment) =>
        historyInvoiceId
          ? payment.invoice_id === Number(historyInvoiceId)
          : true,
      )
      .filter((payment) => {
        if (!query) return true;

        const relatedInvoice = invoices.find(
          (item) => item.id === payment.invoice_id,
        );

        return (
          String(payment.id).includes(query) ||
          String(payment.invoice_id).includes(query) ||
          (payment.reference_number ?? "").toLowerCase().includes(query) ||
          (payment.notes ?? "").toLowerCase().includes(query) ||
          (relatedInvoice?.invoice_number ?? "").toLowerCase().includes(query) ||
          (relatedInvoice?.party_name ?? "").toLowerCase().includes(query)
        );
      })
      .sort(
        (a, b) =>
          new Date(b.payment_date).getTime() -
          new Date(a.payment_date).getTime(),
      );
  }, [payments, historyInvoiceId, search, invoices]);

  const totalPaymentsDisplayed = filteredPayments.reduce(
    (total, payment) => total + Number(payment.amount),
    0,
  );

  const totalPaymentsAll = payments.reduce(
    (total, payment) => total + Number(payment.amount),
    0,
  );

  const invoicesWithPayments = new Set(
    payments.map((payment) => payment.invoice_id),
  ).size;

  function updateForm(field: keyof PaymentForm, value: string) {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function openPaymentModal() {
    setError("");
    setSuccess("");

    setForm({
      invoice_id: invoice ? String(invoice.id) : "",
      payment_date: getToday(),
      amount: "",
      reference_number: "",
      notes: "",
    });

    setModalOpen(true);
  }

  function closePaymentModal() {
    if (saving) return;

    setModalOpen(false);
    setError("");
  }

  function handleHistoryInvoiceChange(value: string) {
    setHistoryInvoiceId(value);
    setSearch("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setError("");
    setSuccess("");

    if (!form.invoice_id) {
      setError("Please select an invoice from the search results.");
      return;
    }

    const paymentAmount = Number(form.amount);

    if (!Number.isFinite(paymentAmount) || paymentAmount <= 0) {
      setError("Enter a valid payment amount greater than zero.");
      return;
    }

    const invoiceRecord = invoices.find(
      (item) => item.id === Number(form.invoice_id),
    );

    if (!invoiceRecord) {
      setError("The selected invoice could not be found.");
      return;
    }

    const outstanding = Number(invoiceRecord.balance_due ?? 0);

    if (paymentAmount > outstanding) {
      setError(
        `Payment amount cannot exceed the outstanding balance of ${formatAmount(outstanding)}.`,
      );
      return;
    }

    setSaving(true);

    try {
      const response = await fetch(`${API_URL}/payments`, {
        method: "POST",
        headers: {
          ...headers,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          invoice_id: Number(form.invoice_id),
          payment_date: form.payment_date,
          amount: paymentAmount,
          reference_number: form.reference_number.trim() || null,
          notes: form.notes.trim() || null,
        }),
      });

      const responseData = await response.json().catch(() => null);

      if (response.status === 401) {
        throw new Error(
          "Your session may have expired. Please sign in again.",
        );
      }

      if (!response.ok) {
        throw new Error(
          responseData?.detail || "Unable to record the payment.",
        );
      }

      setSuccess("Payment recorded successfully.");
      setModalOpen(false);

      // Keep the existing history filter. If the page was opened from
      // an invoice, that invoice context remains selected.
      await loadData();

      setForm({
        invoice_id: invoice ? String(invoice.id) : "",
        payment_date: getToday(),
        amount: "",
        reference_number: "",
        notes: "",
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to record payment.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="payments-page">
      <div className="payments-page-header">
        <div>
          <p className="payments-eyebrow">FINANCE OPERATIONS</p>
          <h1>Payment Management</h1>
          <p className="payments-subtitle">
            Monitor vendor payments and manage invoice settlement records.
          </p>
        </div>

        <div className="payments-header-actions">
          {onBackToInvoices && (
            <button
              type="button"
              className="payments-secondary-button"
              onClick={onBackToInvoices}
            >
              Back to invoices
            </button>
          )}

          <button
            type="button"
            className="payments-secondary-button"
            onClick={() => void loadData()}
            disabled={loading}
          >
            Refresh records
          </button>

          <button
            type="button"
            className="payments-record-button"
            onClick={openPaymentModal}
          >
            <span className="payments-record-button-icon">+</span>
            Record Payment
          </button>
        </div>
      </div>

      {error && !modalOpen && (
        <div className="payments-alert payments-alert-error" role="alert">
          {error}
        </div>
      )}

      {success && (
        <div className="payments-alert payments-alert-success" role="status">
          {success}
        </div>
      )}

      <div className="payments-overview-grid">
        <article className="payments-overview-card payments-overview-primary">
          <div className="payments-overview-icon">₹</div>
          <div>
            <span>Total payments recorded</span>
            <strong>{formatAmount(totalPaymentsAll)}</strong>
            <small>Across all invoice payments</small>
          </div>
        </article>

        <article className="payments-overview-card">
          <div className="payments-overview-icon payments-overview-icon-blue">
            <span>#</span>
          </div>
          <div>
            <span>Payment records</span>
            <strong>{payments.length.toLocaleString("en-IN")}</strong>
            <small>Total recorded transactions</small>
          </div>
        </article>

        <article className="payments-overview-card">
          <div className="payments-overview-icon payments-overview-icon-teal">
            <span>↗</span>
          </div>
          <div>
            <span>Invoices with payments</span>
            <strong>{invoicesWithPayments.toLocaleString("en-IN")}</strong>
            <small>Distinct invoices settled in part or full</small>
          </div>
        </article>
      </div>

      <section className="payments-panel payments-history-panel">
        <div className="payments-panel-heading">
          <div>
            <p className="payments-section-eyebrow">TRANSACTION REGISTER</p>
            <h2>Payment History</h2>
            <p>
              {historyInvoice
                ? `Payments recorded against ${historyInvoice.invoice_number}.`
                : "View and track all recorded invoice payments."}
            </p>
          </div>

          <span className="payments-history-count">
            {filteredPayments.length}{" "}
            {filteredPayments.length === 1 ? "record" : "records"}
          </span>
        </div>

        <div className="payments-history-toolbar">
          <div className="payments-history-filters">
            <div className="payments-filter-field">
              <label htmlFor="payment-history-invoice">Filter by invoice</label>
              <InvoiceSearch
                id="payment-history-invoice"
                invoices={invoices}
                selectedId={historyInvoiceId}
                onSelect={handleHistoryInvoiceChange}
                placeholder="All invoices — search to filter"
              />
            </div>

            <div className="payments-filter-field payments-history-search">
              <label htmlFor="payment-history-search">Search records</label>
              <input
                id="payment-history-search"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Payment ID, vendor, reference or notes..."
              />
            </div>

            {historyInvoiceId && (
              <button
                type="button"
                className="payments-clear-filter"
                onClick={() => handleHistoryInvoiceChange("")}
              >
                Clear invoice filter
              </button>
            )}
          </div>

          <div className="payments-displayed-total">
            <span>Displayed payment total</span>
            <strong>{formatAmount(totalPaymentsDisplayed)}</strong>
          </div>
        </div>

        {loading ? (
          <div className="payments-empty-state">
            <span className="payments-loading-indicator" />
            Loading payment records...
          </div>
        ) : filteredPayments.length === 0 ? (
          <div className="payments-empty-state">
            <div className="payments-empty-icon">₹</div>
            <strong>No payment records found</strong>
            <p>
              {search || historyInvoiceId
                ? "Try changing your search or clearing the invoice filter."
                : "Payment records will appear here after the first payment is recorded."}
            </p>
            {!search && !historyInvoiceId && (
              <button
                type="button"
                className="payments-empty-action"
                onClick={openPaymentModal}
              >
                Record your first payment
              </button>
            )}
          </div>
        ) : (
          <div className="payments-table-wrapper">
            <table className="payments-table">
              <thead>
                <tr>
                  <th>Payment ID</th>
                  <th>Invoice</th>
                  <th>Vendor</th>
                  <th>Payment date</th>
                  <th>Amount</th>
                  <th>Reference number</th>
                  <th>Notes</th>
                </tr>
              </thead>

              <tbody>
                {filteredPayments.map((payment) => {
                  const relatedInvoice = invoices.find(
                    (item) => item.id === payment.invoice_id,
                  );

                  return (
                    <tr key={payment.id}>
                      <td>
                        <span className="payments-id-badge">
                          #{payment.id}
                        </span>
                      </td>
                      <td>
                        <strong className="payments-invoice-number">
                          {relatedInvoice?.invoice_number ??
                            `Invoice #${payment.invoice_id}`}
                        </strong>
                        <small className="payments-table-subtext">
                          ID: {payment.invoice_id}
                        </small>
                      </td>
                      <td>
                        {relatedInvoice?.party_name ?? "—"}
                      </td>
                      <td>{formatDate(payment.payment_date)}</td>
                      <td className="payments-amount-cell">
                        {formatAmount(payment.amount)}
                      </td>
                      <td>{payment.reference_number || "—"}</td>
                      <td className="payments-notes-cell">
                        {payment.notes || "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="payments-table-footer">
          <span>
            Showing {filteredPayments.length} of {payments.length} payment
            records
          </span>
          <span>Amounts displayed in INR (₹)</span>
        </div>
      </section>

      <div className="payments-page-footer">
        <span>Skipper Limited · Internal Finance Operations</span>
        <span>Payment records are linked to invoice records</span>
      </div>

      {modalOpen && (
        <div
          className="payments-modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closePaymentModal();
            }
          }}
        >
          <section
            className="payments-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="payments-modal-title"
          >
            <div className="payments-modal-header">
              <div>
                <p className="payments-section-eyebrow">FINANCE OPERATIONS</p>
                <h2 id="payments-modal-title">Record a Payment</h2>
                <p>Enter the details of the vendor invoice payment.</p>
              </div>

              <button
                type="button"
                className="payments-modal-close"
                onClick={closePaymentModal}
                disabled={saving}
                aria-label="Close payment form"
              >
                ×
              </button>
            </div>

            {error && (
              <div className="payments-alert payments-alert-error" role="alert">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="payments-form">
              <div className="payments-form-field">
                <label htmlFor="payment-form-invoice">
                  Invoice <span>*</span>
                </label>

                <InvoiceSearch
                  id="payment-form-invoice"
                  invoices={invoices}
                  selectedId={form.invoice_id}
                  onSelect={(value) => {
                    updateForm("invoice_id", value);
                    setError("");
                  }}
                  placeholder="Search invoice number or vendor..."
                />
              </div>

              {formInvoice && (
                <div className="payments-modal-invoice-info">
                  <div>
                    <span>Selected vendor</span>
                    <strong>
                      {formInvoice.party_name ?? "Unknown vendor"}
                    </strong>
                  </div>
                  <div>
                    <span>Outstanding balance</span>
                    <strong>
                      {formatAmount(formInvoice.balance_due)}
                    </strong>
                  </div>
                  {formInvoice.order_id && onOpenOrder && (
                    <button
                      type="button"
                      className="payments-text-button"
                      onClick={() => void onOpenOrder(formInvoice.order_id)}
                    >
                      View related order
                    </button>
                  )}
                </div>
              )}

              <div className="payments-form-row">
                <div className="payments-form-field">
                  <label htmlFor="payment-date">
                    Payment date <span>*</span>
                  </label>
                  <input
                    id="payment-date"
                    type="date"
                    value={form.payment_date}
                    onChange={(event) =>
                      updateForm("payment_date", event.target.value)
                    }
                    required
                  />
                </div>

                <div className="payments-form-field">
                  <label htmlFor="payment-amount">
                    Payment amount (₹) <span>*</span>
                  </label>
                  <input
                    id="payment-amount"
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={form.amount}
                    onChange={(event) =>
                      updateForm("amount", event.target.value)
                    }
                    placeholder="Enter amount"
                    required
                  />
                </div>
              </div>

              <div className="payments-form-field">
                <label htmlFor="payment-reference">Reference number</label>
                <input
                  id="payment-reference"
                  type="text"
                  value={form.reference_number}
                  onChange={(event) =>
                    updateForm("reference_number", event.target.value)
                  }
                  placeholder="UTR / transaction reference"
                  maxLength={100}
                />
              </div>

              <div className="payments-form-field">
                <label htmlFor="payment-notes">Notes</label>
                <textarea
                  id="payment-notes"
                  value={form.notes}
                  onChange={(event) =>
                    updateForm("notes", event.target.value)
                  }
                  placeholder="Additional payment remarks..."
                  rows={3}
                />
              </div>

              <div className="payments-modal-actions">
                <button
                  type="button"
                  className="payments-modal-cancel"
                  onClick={closePaymentModal}
                  disabled={saving}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  className="payments-submit-button"
                  disabled={saving || loading}
                >
                  {saving ? "Recording payment..." : "Confirm Payment"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
