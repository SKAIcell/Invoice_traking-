
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
      .filter((item) => {
        return (
          item.invoice_number.toLowerCase().includes(searchTerm) ||
          (item.party_name ?? "").toLowerCase().includes(searchTerm) ||
          String(item.id).includes(searchTerm)
        );
      })
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
    } else if (!value.trim()) {
      onSelect("");
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

  const [selectedInvoiceId, setSelectedInvoiceId] = useState(
    invoice ? String(invoice.id) : "",
  );

  const [form, setForm] = useState<PaymentForm>({
    invoice_id: invoice ? String(invoice.id) : "",
    payment_date: getToday(),
    amount: "",
    reference_number: "",
    notes: "",
  });

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
      setSelectedInvoiceId(String(invoice.id));
      setForm((current) => ({
        ...current,
        invoice_id: String(invoice.id),
      }));
    }
  }, [invoice]);

  const selectedInvoice = useMemo(() => {
    if (!selectedInvoiceId) return null;

    return (
      invoices.find((item) => item.id === Number(selectedInvoiceId)) ??
      (invoice?.id === Number(selectedInvoiceId) ? invoice : null)
    );
  }, [invoices, selectedInvoiceId, invoice]);

  const filteredPayments = useMemo(() => {
    return payments
      .filter((payment) =>
        selectedInvoiceId
          ? payment.invoice_id === Number(selectedInvoiceId)
          : true,
      )
      .filter((payment) => {
        if (!search.trim()) return true;

        const query = search.toLowerCase();

        return (
          String(payment.id).includes(query) ||
          String(payment.invoice_id).includes(query) ||
          (payment.reference_number ?? "").toLowerCase().includes(query) ||
          (payment.notes ?? "").toLowerCase().includes(query)
        );
      })
      .sort(
        (a, b) =>
          new Date(b.payment_date).getTime() -
          new Date(a.payment_date).getTime(),
      );
  }, [payments, selectedInvoiceId, search]);

  const totalPaid = selectedInvoice
    ? Number(selectedInvoice.total_paid ?? 0)
    : 0;

  const balanceDue = selectedInvoice
    ? Number(selectedInvoice.balance_due ?? 0)
    : 0;

  const invoiceAmount = selectedInvoice
    ? Number(selectedInvoice.amount ?? 0)
    : 0;

  const totalPaymentsDisplayed = filteredPayments.reduce(
    (total, payment) => total + Number(payment.amount),
    0,
  );

  function updateForm(field: keyof PaymentForm, value: string) {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function handleInvoiceChange(value: string) {
    setSelectedInvoiceId(value);
    updateForm("invoice_id", value);
    setSuccess("");
    setError("");
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

      setForm((current) => ({
        ...current,
        amount: "",
        reference_number: "",
        notes: "",
        payment_date: getToday(),
      }));

      await loadData();
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
            Record vendor payments and monitor invoice settlement history.
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
        </div>
      </div>

      {error && (
        <div className="payments-alert payments-alert-error" role="alert">
          {error}
        </div>
      )}

      {success && (
        <div className="payments-alert payments-alert-success" role="status">
          {success}
        </div>
      )}

      <div className="payments-invoice-selector">
        <div className="payments-invoice-selector-field">
          <label htmlFor="payment-invoice-select">Search invoice</label>

          <InvoiceSearch
            id="payment-invoice-select"
            invoices={invoices}
            selectedId={selectedInvoiceId}
            onSelect={handleInvoiceChange}
            placeholder="Type invoice number, vendor or ID..."
          />
        </div>

        {selectedInvoice && (
          <div className="payments-selected-invoice">
            <span>Selected invoice</span>
            <strong>{selectedInvoice.invoice_number}</strong>
            <span>{selectedInvoice.party_name ?? "Unknown vendor"}</span>

            {selectedInvoice.order_id && onOpenOrder && (
              <button
                type="button"
                className="payments-text-button"
                onClick={() => void onOpenOrder(selectedInvoice.order_id)}
              >
                View related order
              </button>
            )}
          </div>
        )}
      </div>

      {selectedInvoice && (
        <div className="payments-summary-grid">
          <article className="payments-summary-card">
            <span className="payments-summary-label">Invoice amount</span>
            <strong>{formatAmount(invoiceAmount)}</strong>
          </article>

          <article className="payments-summary-card">
            <span className="payments-summary-label">Total paid</span>
            <strong>{formatAmount(totalPaid)}</strong>
          </article>

          <article className="payments-summary-card">
            <span className="payments-summary-label">Balance due</span>
            <strong>{formatAmount(balanceDue)}</strong>
          </article>
        </div>
      )}

      <div className="payments-content-grid">
        <section className="payments-panel payments-form-panel">
          <div className="payments-panel-heading">
            <div>
              <h2>Record a payment</h2>
              <p>Enter the payment details below.</p>
            </div>
          </div>

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
                  setSelectedInvoiceId(value);
                  setError("");
                  setSuccess("");
                }}
                placeholder="Search invoice number or vendor..."
              />
            </div>

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

            {selectedInvoice && (
              <p className="payments-balance-hint">
                Outstanding balance: <strong>{formatAmount(balanceDue)}</strong>
              </p>
            )}

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

            <button
              type="submit"
              className="payments-submit-button"
              disabled={saving || loading}
            >
              {saving ? "Recording payment..." : "Record payment"}
            </button>
          </form>
        </section>

        <section className="payments-panel payments-history-panel">
          <div className="payments-panel-heading">
            <div>
              <h2>Payment history</h2>
              <p>
                {selectedInvoice
                  ? `Payments recorded against ${selectedInvoice.invoice_number}.`
                  : "All recorded invoice payments."}
              </p>
            </div>

            <span className="payments-history-count">
              {filteredPayments.length}{" "}
              {filteredPayments.length === 1 ? "record" : "records"}
            </span>
          </div>

          <div className="payments-history-toolbar">
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search reference, payment ID or notes..."
              aria-label="Search payment history"
            />

            <span>
              Displayed total:{" "}
              <strong>{formatAmount(totalPaymentsDisplayed)}</strong>
            </span>
          </div>

          {loading ? (
            <div className="payments-empty-state">
              Loading payment records...
            </div>
          ) : filteredPayments.length === 0 ? (
            <div className="payments-empty-state">
              <strong>No payment records found</strong>
              <p>
                Payments recorded against the selected invoice will appear here.
              </p>
            </div>
          ) : (
            <div className="payments-table-wrapper">
              <table className="payments-table">
                <thead>
                  <tr>
                    <th>Payment ID</th>
                    <th>Invoice ID</th>
                    <th>Payment date</th>
                    <th>Amount</th>
                    <th>Reference number</th>
                    <th>Notes</th>
                  </tr>
                </thead>

                <tbody>
                  {filteredPayments.map((payment) => (
                    <tr key={payment.id}>
                      <td>#{payment.id}</td>
                      <td>{payment.invoice_id}</td>
                      <td>{formatDate(payment.payment_date)}</td>
                      <td className="payments-amount-cell">
                        {formatAmount(payment.amount)}
                      </td>
                      <td>{payment.reference_number || "—"}</td>
                      <td>{payment.notes || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <div className="payments-page-footer">
        <span>Skipper Limited · Internal Finance Operations</span>
        <span>Payment records are linked to invoice records</span>
      </div>
    </section>
  );
}
