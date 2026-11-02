
import "../styles/OrderInvoicesPage.css";
import { useEffect, useState, type ChangeEvent } from "react";

type Order = {
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
};

type Invoice = {
  id: number;
  invoice_type: string;
  invoice_number: string;
  order_id: number;
  party_id: number;
  financial_year: string;
  invoice_date: string;
  entry_date?: string | null;
  due_date: string;
  amount: string | number;
  total_paid?: string | number;
  balance_due?: string | number;
  status: string;
  description?: string | null;
  party_name?: string | null;
  vendor_name?: string | null;
  order_number?: string | null;
  budget_name?: string | null;
  budget_type?: string | null;
  period?: string | null;
  location?: string | null;
  remarks?: string | null;
  date_sent_to_accounts?: string | null;
  payment_status?: string;
  invoice_file_path?: string | null;
};

type ApiError = {
  detail?:
    | string
    | {
        message?: string;
        invalid_rows?: {
          excel_row?: number;
          errors?: string[];
        }[];
      }
    | { msg?: string }[];
};

type BulkImportRow = {
  excel_row: number;
  invoice_number: string;
  order_number: string;
  vendor_name: string;
  vendor_code: string;
  invoice_date: string | null;
  due_date: string | null;
  amount: string | null;
  period?: string | null;
  location?: string | null;
  description?: string | null;
  remarks?: string | null;
  errors: string[];
  is_valid: boolean;
};

type BulkImportPreview = {
  order_id: number;
  order_type: string;
  order_number: string;
  party_id: number;
  party_name: string;
  financial_year: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  existing_invoice_total: string;
  proposed_invoice_total: string;
  remaining_order_value: string;
  rows: BulkImportRow[];
};


type Props = {
  order: Order;
  onBack: () => void;
  onAddInvoice: (order: Order) => void;
  onEditInvoice: (invoice: Invoice) => void;
  onPaymentDetails?: (invoice: Invoice) => void;
};

function getToken(): string | null {
  return sessionStorage.getItem("access_token");
}

function formatCurrency(amount: string | number | undefined): string {
  return Number(amount || 0).toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  });
}

function formatDate(value?: string | null): string {
  return value ? value.slice(0, 10) : "—";
}

function getErrorMessage(data: ApiError, fallback: string): string {
  if (typeof data.detail === "string") {
    return data.detail;
  }

  if (data.detail && !Array.isArray(data.detail)) {
    const message = data.detail.message;

    const rowErrors = data.detail.invalid_rows
      ?.map((row) => {
        const errors = row.errors ?? [];

        return errors.length
          ? `Excel row ${row.excel_row ?? "?"}: ${errors.join(", ")}`
          : "";
      })
      .filter(Boolean);

    return [
      message || fallback,
      ...(rowErrors ?? []),
    ].join("\n");
  }

  if (Array.isArray(data.detail)) {
    return data.detail
      .map((item) => item.msg ?? "Invalid input")
      .join(", ");
  }

  return fallback;
}

async function readResponse(response: Response): Promise<unknown> {
  const text = await response.text();

  if (!text.trim()) return {};

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return {};
  }
}

function orderTypeLabel(type: string): string {
  if (type === "PO") return "Purchase Order";
  if (type === "SO") return "Service Order";
  return type;
}

function OrderInvoicesPage({
  order,
  onBack,
  onAddInvoice,
  onEditInvoice,
  onPaymentDetails,
}: Props) {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const [uploadingApproval, setUploadingApproval] = useState(false);
  const [downloadingApproval, setDownloadingApproval] = useState(false);
  const [approvalFile, setApprovalFile] = useState<File | null>(null);
  const [hasApproval, setHasApproval] = useState(false);

  const [dateDrafts, setDateDrafts] = useState<Record<number, string>>({});
  const [savingDateId, setSavingDateId] = useState<number | null>(null);

  const [showBulkImport, setShowBulkImport] = useState(false);
const [bulkImportFile, setBulkImportFile] = useState<File | null>(null);
const [bulkImportPreview, setBulkImportPreview] =
  useState<BulkImportPreview | null>(null);
const [previewingImport, setPreviewingImport] = useState(false);
const [confirmingImport, setConfirmingImport] = useState(false);

  // Invoice document controls
  const [openDocumentMenuId, setOpenDocumentMenuId] = useState<number | null>(
    null,
  );
  const [uploadingInvoiceId, setUploadingInvoiceId] = useState<number | null>(
    null,
  );
  const [uploadedDocumentIds, setUploadedDocumentIds] = useState<number[]>([]);

  const totalInvoiceAmount = invoices.reduce(
    (total, invoice) => total + Number(invoice.amount || 0),
    0,
  );

  const totalPaidToDate = invoices.reduce(
    (total, invoice) => total + Number(invoice.total_paid || 0),
    0,
  );

  const paymentDue = invoices.reduce(
    (total, invoice) =>
      total +
      Number(
        invoice.balance_due ??
          Math.max(
            0,
            Number(invoice.amount || 0) -
              Number(invoice.total_paid || 0),
          ),
      ),
    0,
  );

  const availableOrderValue = Math.max(
    0,
    Number(order.amount || 0) - totalInvoiceAmount,
  );


  function resetBulkImport() {
  setBulkImportFile(null);
  setBulkImportPreview(null);
  setShowBulkImport(false);
  setError("");
}

function handleBulkImportFileChange(
  event: ChangeEvent<HTMLInputElement>,
) {
  const file = event.target.files?.[0] ?? null;

  setBulkImportFile(file);
  setBulkImportPreview(null);
  setError("");
  setSuccess("");

  if (file && !/\.(xlsx|xlsm)$/i.test(file.name)) {
    setError("Please select an Excel .xlsx or .xlsm file.");
    setBulkImportFile(null);
    event.target.value = "";
  }
}

async function handleBulkImportPreview() {
  if (!bulkImportFile) {
    setError("Please select an Excel file first.");
    return;
  }

  const token = getToken();

  if (!token) {
    setError("Your session has expired. Please sign in again.");
    return;
  }

  try {
    setPreviewingImport(true);
    setError("");
    setSuccess("");
    setBulkImportPreview(null);

    const body = new FormData();
    body.append("file", bulkImportFile);

    const response = await fetch(
      `/api/orders/${order.id}/invoices/import/preview`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body,
      },
    );

    const data = await readResponse(response);

    if (!response.ok) {
      throw new Error(
        getErrorMessage(
          data as ApiError,
          "Unable to preview Excel import.",
        ),
      );
    }

    setBulkImportPreview(data as BulkImportPreview);
  } catch (err) {
    setError(
      err instanceof Error
        ? err.message
        : "Unable to preview Excel import.",
    );
  } finally {
    setPreviewingImport(false);
  }
}

async function handleBulkImportConfirm() {
  if (!bulkImportFile || !bulkImportPreview) {
    setError("Please select and preview the Excel file first.");
    return;
  }

  if (bulkImportPreview.invalid_rows > 0) {
    setError(
      "Please correct all invalid Excel rows before importing.",
    );
    return;
  }

  const confirmed = window.confirm(
    `Import ${bulkImportPreview.valid_rows} invoice(s) for order ${order.order_number}?`,
  );

  if (!confirmed) return;

  const token = getToken();

  if (!token) {
    setError("Your session has expired. Please sign in again.");
    return;
  }

  try {
    setConfirmingImport(true);
    setError("");
    setSuccess("");

    const body = new FormData();
    body.append("file", bulkImportFile);

    const response = await fetch(
      `/api/orders/${order.id}/invoices/import/confirm`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body,
      },
    );

    const data = await readResponse(response);

    if (!response.ok) {
      throw new Error(
        getErrorMessage(
          data as ApiError,
          "Unable to import invoices.",
        ),
      );
    }

    const result = data as {
      message?: string;
      imported_count?: number;
    };

    setSuccess(
      result.message ??
        `${result.imported_count ?? 0} invoice(s) imported successfully.`,
    );

    setBulkImportFile(null);
    setBulkImportPreview(null);
    setShowBulkImport(false);

    await loadInvoices();
  } catch (err) {
    setError(
      err instanceof Error
        ? err.message
        : "Unable to import invoices.",
    );
  } finally {
    setConfirmingImport(false);
  }
}

  function hasInvoiceDocument(invoice: Invoice): boolean {
    return Boolean(
      invoice.invoice_file_path ||
        uploadedDocumentIds.includes(invoice.id),
    );
  }

  async function loadInvoices() {
    const token = getToken();

    if (!token) {
      setError("Your session has expired. Please sign in again.");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError("");

      const response = await fetch(`/api/orders/${order.id}/invoices`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      const data = await readResponse(response);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data as ApiError, "Unable to load order invoices."),
        );
      }

      const invoiceList: Invoice[] = Array.isArray(data)
        ? (data as Invoice[])
        : [];

      const mappedInvoices = invoiceList.map((invoice) => ({
        ...invoice,
        invoice_type:
          invoice.invoice_type ??
          (order.order_type === "PO" ? "PURCHASE" : "SALES"),
        financial_year: invoice.financial_year ?? order.financial_year ?? "",
        status: invoice.payment_status ?? invoice.status ?? "UNPAID",
      }));

      setInvoices(mappedInvoices);

      setDateDrafts(
        Object.fromEntries(
          mappedInvoices.map((invoice) => [
            invoice.id,
            invoice.date_sent_to_accounts?.slice(0, 10) ?? "",
          ]),
        ),
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load order invoices.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function checkApproval() {
    const token = getToken();
    if (!token) return;

    try {
      const response = await fetch(`/api/orders/${order.id}/approval`, {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` },
      });

      setHasApproval(response.ok);
    } catch {
      setHasApproval(false);
    }
  }

  useEffect(() => {
    void loadInvoices();
    void checkApproval();
  }, [order.id]);

  // Upload or replace an invoice document
  async function handleInvoiceDocumentUpload(
    invoice: Invoice,
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0];

    if (!file) return;

    const allowedTypes = [
      "application/pdf",
      "image/jpeg",
      "image/png",
    ];

    const validExtension = /\.(pdf|jpg|jpeg|png)$/i.test(file.name);

    if (!validExtension || !allowedTypes.includes(file.type)) {
      setError("Only PDF, JPG, JPEG and PNG invoice documents are allowed.");
      event.target.value = "";
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setError("The invoice document must not exceed 10 MB.");
      event.target.value = "";
      return;
    }

    const token = getToken();

    if (!token) {
      setError("Your session has expired. Please sign in again.");
      event.target.value = "";
      return;
    }

    try {
      setUploadingInvoiceId(invoice.id);
      setError("");
      setSuccess("");

      const body = new FormData();
      body.append("file", file);

      const response = await fetch(
        `/api/invoices/${invoice.id}/invoice-copy`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body,
        },
      );

      const data = await readResponse(response);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(
            data as ApiError,
            "Unable to upload invoice document.",
          ),
        );
      }

      setUploadedDocumentIds((current) =>
        current.includes(invoice.id) ? current : [...current, invoice.id],
      );

      setOpenDocumentMenuId(null);
      setSuccess(
        `Invoice document for ${invoice.invoice_number} uploaded successfully.`,
      );

      await loadInvoices();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to upload invoice document.",
      );
    } finally {
      setUploadingInvoiceId(null);
      event.target.value = "";
    }
  }

  // View an invoice document using the authenticated API request
  async function handleInvoiceDocumentView(invoice: Invoice) {
    const token = getToken();

    if (!token) {
      setError("Your session has expired. Please sign in again.");
      return;
    }

    let previewWindow: Window | null = null;

    try {
      setError("");
      setSuccess("");

      // Open synchronously so the browser does not block the preview.
      previewWindow = window.open("", "_blank");

      const response = await fetch(
        `/api/invoices/${invoice.id}/invoice-copy`,
        {
          headers: { Authorization: `Bearer ${token}` },
        },
      );

      if (!response.ok) {
        const data = await readResponse(response);
        throw new Error(
          getErrorMessage(
            data as ApiError,
            "Unable to open invoice document.",
          ),
        );
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);

      if (previewWindow) {
        previewWindow.location.href = objectUrl;

        previewWindow.addEventListener(
          "beforeunload",
          () => URL.revokeObjectURL(objectUrl),
          { once: true },
        );
      } else {
        window.open(objectUrl, "_blank");
        setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
      }

      setOpenDocumentMenuId(null);
    } catch (err) {
      previewWindow?.close();

      setError(
        err instanceof Error
          ? err.message
          : "Unable to open invoice document.",
      );
    }
  }

  async function handleApprovalUpload() {
    if (!approvalFile) {
      setError("Choose an approval PDF or JPG file first.");
      return;
    }

    const allowedTypes = ["application/pdf", "image/jpeg"];
    const validExtension = /\.(pdf|jpg|jpeg)$/i.test(approvalFile.name);

    if (!validExtension || !allowedTypes.includes(approvalFile.type)) {
      setError("Only PDF and JPG/JPEG approval documents are allowed.");
      return;
    }

    if (approvalFile.size > 10 * 1024 * 1024) {
      setError("The approval document must not exceed 10 MB.");
      return;
    }

    const token = getToken();

    if (!token) {
      setError("Your session has expired. Please sign in again.");
      return;
    }

    try {
      setUploadingApproval(true);
      setError("");
      setSuccess("");

      const body = new FormData();
      body.append("file", approvalFile);

      const response = await fetch(`/api/orders/${order.id}/approval`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body,
      });

      const data = await readResponse(response);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(
            data as ApiError,
            "Unable to upload approval document.",
          ),
        );
      }

      setHasApproval(true);
      setApprovalFile(null);
      setSuccess("Approval document uploaded successfully.");

      const fileInput = document.getElementById(
        "order-approval-file",
      ) as HTMLInputElement | null;

      if (fileInput) fileInput.value = "";
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to upload approval document.",
      );
    } finally {
      setUploadingApproval(false);
    }
  }

  async function handleApprovalDownload() {
    const token = getToken();

    if (!token) {
      setError("Your session has expired. Please sign in again.");
      return;
    }

    try {
      setDownloadingApproval(true);
      setError("");

      const response = await fetch(`/api/orders/${order.id}/approval`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        const data = await readResponse(response);
        throw new Error(
          getErrorMessage(
            data as ApiError,
            "Unable to download approval document.",
          ),
        );
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = objectUrl;
      link.download = `approval-${order.order_number}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to download approval document.",
      );
    } finally {
      setDownloadingApproval(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setApprovalFile(event.target.files?.[0] ?? null);
    setError("");
    setSuccess("");
  }

  async function handleUpdateDateSent(invoice: Invoice, clear = false) {
    const token = getToken();

    if (!token) {
      setError("Your session has expired. Please sign in again.");
      return;
    }

    const dateValue = clear ? null : dateDrafts[invoice.id] || null;

    if (!clear && !dateValue) {
      setError("Select a date before saving.");
      return;
    }

    try {
      setSavingDateId(invoice.id);
      setError("");
      setSuccess("");

      const response = await fetch(
        `/api/invoices/${invoice.id}/date-sent-to-accounts`,
        {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            date_sent_to_accounts: dateValue,
          }),
        },
      );

      const data = await readResponse(response);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(
            data as ApiError,
            "Unable to update the date sent to Accounts.",
          ),
        );
      }

      setSuccess(
        clear
          ? "Date sent to Accounts cleared successfully."
          : "Date sent to Accounts updated successfully.",
      );

      await loadInvoices();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to update the date sent to Accounts.",
      );
    } finally {
      setSavingDateId(null);
    }
  }

  async function handleDeleteInvoice(invoice: Invoice) {
    const confirmed = window.confirm(
      `Delete invoice "${invoice.invoice_number}"? This action cannot be undone.`,
    );

    if (!confirmed) return;

    const token = getToken();

    if (!token) {
      setError("Your session has expired. Please sign in again.");
      return;
    }

    try {
      setDeletingId(invoice.id);
      setError("");
      setSuccess("");

      const response = await fetch(`/api/invoices/${invoice.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      const data = await readResponse(response);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data as ApiError, "Unable to delete invoice."),
        );
      }

      setUploadedDocumentIds((current) =>
        current.filter((id) => id !== invoice.id),
      );

      setSuccess(`Invoice ${invoice.invoice_number} deleted successfully.`);
      await loadInvoices();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to delete invoice.",
      );
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <section className="page-content order-invoices-page">
      <button type="button" className="secondary-button" onClick={onBack}>
        ← Back to Orders
      </button>

      <div className="order-details-heading">
        <div>
          <p className="eyebrow">ORDER DETAILS</p>
          <h2>{order.order_number}</h2>
          <p className="page-description">
            {orderTypeLabel(order.order_type)} · Review order commitments,
            approval documents, and linked invoices.
          </p>
        </div>

        <span
          className={`orders-status-badge status-${order.status.toLowerCase()}`}
        >
          {order.status}
        </span>
      </div>

      {error && (
        <div className="error-message" role="alert">
          {error}
        </div>
      )}

      {success && (
        <div className="notice" role="status">
          {success}
        </div>
      )}

      <div className="order-invoices-summary">
        <div>
          <span>Order Number</span>
          <strong>{order.order_number}</strong>
        </div>
        <div>
          <span>Order Type</span>
          <strong>{orderTypeLabel(order.order_type)}</strong>
        </div>
        <div>
          <span>Order Date</span>
          <strong>{formatDate(order.order_date)}</strong>
        </div>
        <div>
          <span>Financial Year</span>
          <strong>{order.financial_year || "—"}</strong>
        </div>
        <div>
          <span>Vendor</span>
          <strong>{order.party_name || `Party #${order.party_id}`}</strong>
        </div>
        <div>
          <span>Budget</span>
          <strong>{order.budget_name || "—"}</strong>
        </div>
        <div>
          <span>Order Period</span>
          <strong>{order.order_period || "—"}</strong>
        </div>
        <div>
          <span>Location</span>
          <strong>{order.location || "—"}</strong>
        </div>
        <div>
          <span>Order Status</span>
          <strong>{order.status}</strong>
        </div>
        <div>
          <span>Description</span>
          <strong>{order.description || "—"}</strong>
        </div>
      </div>

      <div className="linked-invoice-metrics">
        <div className="linked-invoice-metric">
          <span>Total Order Amount</span>
          <strong>{formatCurrency(order.amount)}</strong>
        </div>

        <div className="linked-invoice-metric">
          <span>Submitted Invoice Amount</span>
          <strong>{formatCurrency(totalInvoiceAmount)}</strong>
        </div>

        <div className="linked-invoice-metric">
          <span>Paid Up to Date</span>
          <strong>{formatCurrency(totalPaidToDate)}</strong>
        </div>

        <div className="linked-invoice-metric">
          <span>Payment Due</span>
          <strong>{formatCurrency(paymentDue)}</strong>
        </div>

        <div className="linked-invoice-metric">
          <span>Available Order Value</span>
          <strong>{formatCurrency(availableOrderValue)}</strong>
        </div>

        <div className="linked-invoice-metric">
          <span>Total Submitted Invoices</span>
          <strong>{invoices.length}</strong>
        </div>
      </div>


      <div className="order-invoices-heading">
  <div>
    <h3>Invoice Register</h3>
    <p>
      {invoices.length} invoice{invoices.length === 1 ? "" : "s"} linked
      to this order.
    </p>
  </div>

  <div className="order-invoice-heading-actions">
    <button
      type="button"
      className="secondary-button"
      onClick={() => {
        setShowBulkImport((current) => !current);
        setBulkImportPreview(null);
        setError("");
        setSuccess("");
      }}
    >
      {showBulkImport ? "Close Bulk Import" : "Bulk Import Excel"}
    </button>

    <button
      type="button"
      className="primary-button"
      onClick={() => onAddInvoice(order)}
    >
      + Add Invoice
    </button>
  </div>
</div>


{showBulkImport && (
  <section className="order-bulk-import-panel">
    <div className="order-bulk-import-header">
      <div>
        <h3>Bulk Import Invoices</h3>
        <p>
          Import multiple invoices for the selected order using Excel.
        </p>
      </div>

      <button
        type="button"
        className="secondary-button"
        onClick={resetBulkImport}
        disabled={previewingImport || confirmingImport}
      >
        Close
      </button>
    </div>

    <div className="order-bulk-import-order">
      <div>
        <span>Order Number</span>
        <strong>{order.order_number}</strong>
      </div>

      <div>
        Vendor
        <strong>{order.party_name || `Party #${order.party_id}`}</strong>
      </div>

      <div>
        <span>Financial Year</span>
        <strong>{order.financial_year || "—"}</strong>
      </div>

      <div>
        <span>Invoice Type</span>
        <strong>
          {order.order_type === "PO" ? "PURCHASE" : "SALES"}
        </strong>
      </div>
    </div>

    <div className="order-bulk-import-instructions">
      <strong>Excel columns</strong>
      <p>
  Required: Invoice Number, PO/SO Number, Vendor Name,
  Vendor Code, Invoice Date, Due Date and Amount.
</p>
      <p>
        Optional: Period, Location, Description and Remarks.
      </p>
      <p>
        The PO/SO Number and Vendor Name must match this selected order.
      </p>
    </div>

    <div className="order-bulk-import-file">
      <label htmlFor="order-bulk-import-file">
        Excel File (.xlsx or .xlsm)
      </label>

      <input
        id="order-bulk-import-file"
        type="file"
        accept=".xlsx,.xlsm"
        onChange={handleBulkImportFileChange}
        disabled={previewingImport || confirmingImport}
      />

      {bulkImportFile && (
        <p className="order-bulk-import-filename">
          Selected: {bulkImportFile.name}
        </p>
      )}

      <button
        type="button"
        className="primary-button"
        onClick={() => void handleBulkImportPreview()}
        disabled={!bulkImportFile || previewingImport || confirmingImport}
      >
        {previewingImport ? "Validating Excel..." : "Preview Import"}
      </button>
    </div>

    {bulkImportPreview && (
      <div className="order-bulk-import-preview">
        <h4>Import Preview</h4>

        <div className="order-bulk-import-summary">
          <div>
            <span>Total Rows</span>
            <strong>{bulkImportPreview.total_rows}</strong>
          </div>

          <div>
            <span>Valid Rows</span>
            <strong>{bulkImportPreview.valid_rows}</strong>
          </div>

          <div>
            <span>Invalid Rows</span>
            <strong>{bulkImportPreview.invalid_rows}</strong>
          </div>

          <div>
            <span>Existing Invoice Total</span>
            <strong>
              {formatCurrency(
                bulkImportPreview.existing_invoice_total,
              )}
            </strong>
          </div>

          <div>
            <span>New Invoice Total</span>
            <strong>
              {formatCurrency(
                bulkImportPreview.proposed_invoice_total,
              )}
            </strong>
          </div>

          <div>
            <span>Remaining Order Value</span>
            <strong>
              {formatCurrency(
                bulkImportPreview.remaining_order_value,
              )}
            </strong>
          </div>
        </div>

        <div className="table-container">
          <table className="order-bulk-import-table">
            <thead>
  <tr>
    <th>Excel Row</th>
    <th>Invoice Number</th>
    <th>PO/SO Number</th>
    <th>Vendor/Customer</th>
    <th>Vendor/Customer Code</th>
    <th>Invoice Date</th>
    <th>Due Date</th>
    <th>Amount</th>
    <th>Validation</th>
  </tr>
</thead>

            <tbody>
  {bulkImportPreview.rows.map((row) => (
    <tr key={row.excel_row}>
      <td>{row.excel_row}</td>
      <td>{row.invoice_number || "—"}</td>
      <td>{row.order_number || "—"}</td>
      <td>{row.vendor_name || "—"}</td>
      <td>{row.vendor_code || "—"}</td>
      <td>{formatDate(row.invoice_date)}</td>
      <td>{formatDate(row.due_date)}</td>
      <td>
        {row.amount ? formatCurrency(row.amount) : "—"}
      </td>
      <td>
        {row.is_valid ? (
          <span className="bulk-import-valid">Valid</span>
        ) : (
          <div className="bulk-import-invalid">
            <strong>Invalid</strong>
            <ul>
              {row.errors.map((message, index) => (
                <li key={`${row.excel_row}-${index}`}>
                  {message}
                </li>
              ))}
            </ul>
          </div>
        )}
      </td>
    </tr>
  ))}
</tbody>
          </table>
        </div>

        {bulkImportPreview.invalid_rows > 0 && (
          <div className="error-message">
            {bulkImportPreview.invalid_rows} row(s) need correction.
            No invoices can be imported until all rows are valid.
          </div>
        )}

        <div className="order-bulk-import-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={() => setBulkImportPreview(null)}
            disabled={confirmingImport}
          >
            Clear Preview
          </button>

          <button
            type="button"
            className="primary-button"
            onClick={() => void handleBulkImportConfirm()}
            disabled={
              bulkImportPreview.valid_rows === 0 ||
              bulkImportPreview.invalid_rows > 0 ||
              confirmingImport ||
              previewingImport
            }
          >
            {confirmingImport
              ? "Importing Invoices..."
              : `Confirm Import (${bulkImportPreview.valid_rows})`}
          </button>
        </div>
      </div>
    )}
  </section>
)}

      {loading ? (
        <p className="notice">Loading linked invoices...</p>
      ) : (
        <div className="table-container">
          <table className="invoice-register-table">
            <thead>
              <tr>
                <th>Invoice No.</th>
                <th>Invoice Date</th>
                <th>Entry Date</th>
                <th>PO / Order No.</th>
                <th>Vendor Name</th>
                <th>Budget Category</th>
                <th>Invoice Amount</th>
                <th>Paid to Date</th>
                <th>Balance Due</th>
                <th>Due Date</th>
                <th>Date Sent to Accounts</th>
                <th>Payment Status</th>
                <th>Documents</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {invoices.map((invoice) => {
                const paymentStatus =
                  invoice.payment_status ?? invoice.status ?? "UNPAID";

                const budgetCategory = invoice.budget_type
                  ? `${invoice.budget_name || ""} (${invoice.budget_type})`
                  : invoice.budget_name || "—";

                const documentUploaded = hasInvoiceDocument(invoice);
                const isUploading = uploadingInvoiceId === invoice.id;
                const menuOpen = openDocumentMenuId === invoice.id;

                return (
                  <tr key={invoice.id}>
                    <td>{invoice.invoice_number}</td>
                    <td>{formatDate(invoice.invoice_date)}</td>
                    <td>{formatDate(invoice.entry_date)}</td>
                    <td>{invoice.order_number || order.order_number}</td>
                    <td>
                      {invoice.vendor_name ||
                        invoice.party_name ||
                        order.party_name ||
                        `Party #${invoice.party_id}`}
                    </td>
                    <td>{budgetCategory}</td>
                    <td>{formatCurrency(invoice.amount)}</td>
                    <td>{formatCurrency(invoice.total_paid)}</td>
                    <td>
                      {formatCurrency(
                        invoice.balance_due ??
                          Number(invoice.amount || 0) -
                            Number(invoice.total_paid || 0),
                      )}
                    </td>
                    <td>{formatDate(invoice.due_date)}</td>

                    <td>
                      <div className="invoice-date-account-control">
                        <input
                          type="date"
                          aria-label={`Date sent to Accounts for ${invoice.invoice_number}`}
                          value={dateDrafts[invoice.id] ?? ""}
                          onChange={(event) =>
                            setDateDrafts((current) => ({
                              ...current,
                              [invoice.id]: event.target.value,
                            }))
                          }
                        />

                        <div className="orders-row-actions">
                          <button
                            type="button"
                            className="orders-edit-button"
                            disabled={savingDateId === invoice.id}
                            onClick={() => void handleUpdateDateSent(invoice)}
                          >
                            {savingDateId === invoice.id ? "Saving..." : "Save"}
                          </button>

                          <button
                            type="button"
                            className="orders-secondary-button"
                            disabled={
                              savingDateId === invoice.id ||
                              !invoice.date_sent_to_accounts
                            }
                            onClick={() =>
                              void handleUpdateDateSent(invoice, true)
                            }
                          >
                            Clear
                          </button>
                        </div>
                      </div>
                    </td>

                    <td>
                      <span
                        className={`status-badge status-${paymentStatus
                          .toLowerCase()
                          .replace(/_/g, "-")}`}
                      >
                        {paymentStatus.replace(/_/g, " ")}
                      </span>
                    </td>

                    <td>
                      <div className="invoice-document-menu">
                        <button
                          type="button"
                          className="invoice-document-trigger"
                          aria-expanded={menuOpen}
                          onClick={() =>
                            setOpenDocumentMenuId(
                              menuOpen ? null : invoice.id,
                            )
                          }
                        >
                          Documents
                          <span className="invoice-document-chevron">▾</span>
                        </button>

                        <span
                          className={`invoice-document-status ${
                            documentUploaded ? "is-uploaded" : "is-missing"
                          }`}
                        >
                          {documentUploaded ? "Uploaded" : "Not uploaded"}
                        </span>

                        {menuOpen && (
                          <div className="invoice-document-dropdown">
                            {documentUploaded && (
                              <button
                                type="button"
                                className="invoice-document-menu-item"
                                onClick={() =>
                                  void handleInvoiceDocumentView(invoice)
                                }
                              >
                                View invoice copy
                              </button>
                            )}

                            <label
                              className="invoice-document-menu-item invoice-document-upload-option"
                              htmlFor={`invoice-copy-${invoice.id}`}
                            >
                              {isUploading
                                ? "Uploading..."
                                : documentUploaded
                                  ? "Replace invoice copy"
                                  : "Upload invoice copy"}
                              <input
                                id={`invoice-copy-${invoice.id}`}
                                type="file"
                                accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                                disabled={isUploading}
                                onChange={(event) =>
                                  void handleInvoiceDocumentUpload(
                                    invoice,
                                    event,
                                  )
                                }
                              />
                            </label>
                          </div>
                        )}
                      </div>
                    </td>

                    <td>
                      <div className="orders-row-actions">
                        <button
                          type="button"
                          className="orders-edit-button"
                          onClick={() => onEditInvoice(invoice)}
                        >
                          Edit
                        </button>

                        <button
                          type="button"
                          className="orders-delete-button"
                          disabled={deletingId === invoice.id}
                          onClick={() => void handleDeleteInvoice(invoice)}
                        >
                          {deletingId === invoice.id ? "Deleting..." : "Delete"}
                        </button>

                        {onPaymentDetails && (
                          <button
                            type="button"
                            className="orders-secondary-button"
                            onClick={() => onPaymentDetails(invoice)}
                          >
                            Update Payment Details
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}

              {invoices.length === 0 && (
                <tr>
                  <td colSpan={14} className="orders-empty">
                    No invoices have been recorded for this order yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default OrderInvoicesPage;
