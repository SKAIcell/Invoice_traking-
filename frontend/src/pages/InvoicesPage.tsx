
import { useEffect, useState, type FormEvent } from "react";
import "../styles/invoices.css";
import "../styles/invoice-approvals.css";

type OrderOption = {
  id: number;
  order_type: string;
  order_number: string;
  party_id: number;
  party_name?: string | null;
  financial_year: string;
  status: string;
};

export type Invoice = {
  id: number;
  invoice_type: string;
  invoice_number: string;
  order_id: number;
  party_id: number;
  financial_year: string;
  invoice_date: string;
  due_date: string;
  amount: string | number;
  status: string;
  description?: string | null;
  period?: string | null;
  location?: string | null;
  remarks?: string | null;
  vendor_name?: string | null;
  order_number?: string | null;
  payment_status?: string;
  invoice_file_path?: string | null;
};

export type InvoiceRegisterRow = {
  id: number;
  invoice_type: string;
  invoice_number: string;
  invoice_date: string;
  entry_date: string;
  order_id: number;
  order_number: string;
  party_id: number;
  party_name: string;
  financial_year: string;
  budget_name: string;
  budget_type: string;
  amount: string | number;
  total_paid: string | number;
  balance_due: string | number;
  due_date: string;
  date_sent_to_accounts: string | null;
  payment_status: string;
};

type ApprovalInvoiceData = {
  invoice_number?: string;
  invoice_type?: string;
  invoice_date?: string;
  due_date?: string;
  amount?: string | number;
  party_id?: number;
  order_id?: number;
  financial_year?: string;
  description?: string | null;
};

type ApprovalRequest = {
  id: number;
  order_id: number;
  order_number: string;
  request_type: "MANUAL" | "BULK";
  status: "PENDING" | "APPROVED" | "REJECTED";
  invoice_count: number;
  invoice_data: ApprovalInvoiceData[];
  requested_by: string;
  requested_at: string;
  decided_by?: string | null;
  decided_at?: string | null;
  remarks?: string | null;
  result_invoice_ids: number[];
};

type InvoiceForm = {
  invoice_type: "PURCHASE" | "SERVICE";
  invoice_number: string;
  order_id: string;
  party_id: string;
  financial_year: string;
  invoice_date: string;
  due_date: string;
  amount: string;
  period: string;
  location: string;
  remarks: string;
  description: string;
};

const initialForm: InvoiceForm = {
  invoice_type: "PURCHASE",
  invoice_number: "",
  order_id: "",
  party_id: "",
  financial_year: "2026-2027",
  invoice_date: "",
  due_date: "",
  amount: "",
  period: "",
  location: "",
  remarks: "",
  description: "",
};

function getErrorMessage(data: any, fallback: string): string {
  const detail = data?.detail;

  if (typeof detail === "string") return detail;

  if (detail && typeof detail.message === "string") {
    return detail.message;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item: { msg?: string }) => item.msg ?? "Invalid input")
      .join(", ");
  }

  return fallback;
}

function validateInvoiceFile(file: File): string | null {
  const allowedExtensions = [".pdf", ".jpg", ".jpeg", ".png"];
  const extension = file.name
    .slice(file.name.lastIndexOf("."))
    .toLowerCase();

  if (!allowedExtensions.includes(extension)) {
    return "Only PDF, JPG, JPEG and PNG files are allowed.";
  }

  if (file.size > 10 * 1024 * 1024) {
    return "File size must not exceed 10 MB.";
  }

  return null;
}

function formatDate(value?: string | null): string {
  return value ? value.slice(0, 10) : "—";
}

function formatDateTime(value?: string | null): string {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value.slice(0, 16).replace("T", " ");
  }

  return date.toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function formatCurrency(
  value: string | number | null | undefined,
): string {
  return Number(value ?? 0).toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  });
}

type OrderContext = {
  id: number;
  order_type: string;
  order_number: string;
  party_id: number;
  party_name?: string | null;
  financial_year?: string;
};

type InvoicesPageProps = {
  orderContext?: OrderContext;
  onBackToOrder?: () => void;
  initialInvoiceToEdit?: Invoice | null;
  onPaymentDetails?: (invoice: InvoiceRegisterRow) => void;
};

export default function InvoicesPage({
  orderContext,
  onBackToOrder,
  initialInvoiceToEdit = null,
  onPaymentDetails,
}: InvoicesPageProps) {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [registerRows, setRegisterRows] = useState<InvoiceRegisterRow[]>([]);
  const [orders, setOrders] = useState<OrderOption[]>([]);
  const [, setLoading] = useState(true);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!success) return;

    const timer = window.setTimeout(() => {
      setSuccess("");
    }, 6000);

    return () => window.clearTimeout(timer);
  }, [success]);

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<
    "ALL" | "OPEX" | "CAPEX"
  >("ALL");

  // Approval request state
  const [approvalRequests, setApprovalRequests] = useState<
    ApprovalRequest[]
  >([]);
  const [approvalLoading, setApprovalLoading] = useState(true);
  const [approvalSearch, setApprovalSearch] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [editingInvoiceId, setEditingInvoiceId] = useState<number | null>(
    null,
  );

  const [form, setForm] = useState<InvoiceForm>(initialForm);
  const [invoiceFile, setInvoiceFile] = useState<File | null>(null);

  const [dateDrafts, setDateDrafts] = useState<Record<number, string>>({});
  const [savingDateId, setSavingDateId] = useState<number | null>(null);
  const [documentBusyId, setDocumentBusyId] = useState<number | null>(null);
  const [openDocumentMenuId, setOpenDocumentMenuId] = useState<number | null>(
    null,
  );

  const [uploadedDocumentIds, setUploadedDocumentIds] = useState<number[]>(
    [],
  );

  const selectedOrder = orders.find(
    (order) => String(order.id) === form.order_id,
  );

  const displayedPartyName =
    orderContext?.party_name || selectedOrder?.party_name || "";

  async function loadInvoices() {
    try {
      setError("");

      const token = sessionStorage.getItem("access_token");
      const response = await fetch("/api/invoices", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(
          getErrorMessage(
            data,
            `Unable to load invoices (${response.status}).`,
          ),
        );
      }

      const data: Invoice[] = await response.json();
      setInvoices(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load invoices.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadInvoiceRegister() {
    try {
      const token = sessionStorage.getItem("access_token");

      const response = await fetch("/api/invoices/register", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(
          getErrorMessage(
            data,
            `Unable to load invoice register (${response.status}).`,
          ),
        );
      }

      const data: InvoiceRegisterRow[] = await response.json();
      setRegisterRows(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load invoice register.",
      );
    }
  }

  async function loadOrders() {
    try {
      const token = sessionStorage.getItem("access_token");
      const response = await fetch("/api/orders", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(
          getErrorMessage(data, `Unable to load orders (${response.status}).`),
        );
      }

      const data: OrderOption[] = await response.json();
      setOrders(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load orders.",
      );
    }
  }

  async function loadApprovalRequests() {
    setApprovalLoading(true);

    try {
      const token = sessionStorage.getItem("access_token");

      const response = await fetch("/api/invoice-approvals/requests", {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);

        throw new Error(
          getErrorMessage(
            data,
            `Unable to load approval requests (${response.status}).`,
          ),
        );
      }

      const data: ApprovalRequest[] = await response.json();

      setApprovalRequests(
        Array.isArray(data)
          ? data.map((request) => ({
              ...request,
              invoice_data: Array.isArray(request.invoice_data)
                ? request.invoice_data
                : [],
              result_invoice_ids: Array.isArray(request.result_invoice_ids)
                ? request.result_invoice_ids
                : [],
            }))
          : [],
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load invoice approval requests.",
      );
    } finally {
      setApprovalLoading(false);
    }
  }

  async function refreshInvoiceData() {
    setError("");

    await Promise.all([
      loadInvoices(),
      loadInvoiceRegister(),
      loadOrders(),
      loadApprovalRequests(),
    ]);
  }

  useEffect(() => {
    void loadInvoices();
    void loadInvoiceRegister();
    void loadOrders();
    void loadApprovalRequests();
  }, []);

  useEffect(() => {
    if (!orderContext) {
      setShowForm(false);
      setEditingInvoiceId(null);
      return;
    }

    setError("");
    setSuccess("");

    if (initialInvoiceToEdit) {
      startEdit(initialInvoiceToEdit);
      return;
    }

    setForm({
      ...initialForm,
      invoice_type:
        orderContext.order_type === "PO" ? "PURCHASE" : "SERVICE",
      order_id: String(orderContext.id),
      party_id: String(orderContext.party_id),
      financial_year:
        orderContext.financial_year ?? initialForm.financial_year,
    });

    setInvoiceFile(null);
    setEditingInvoiceId(null);
    setShowForm(true);
  }, [orderContext?.id, initialInvoiceToEdit?.id]);

  function updateField(field: keyof InvoiceForm, value: string) {
    setForm((previous) => ({
      ...previous,
      [field]: value,
    }));
  }

  function resetForm() {
    setForm(initialForm);
    setInvoiceFile(null);
    setEditingInvoiceId(null);
    setShowForm(false);
  }

  function leaveOrderEditor() {
    if (orderContext && onBackToOrder) {
      onBackToOrder();
      return true;
    }

    return false;
  }

  function startEdit(invoice: Invoice) {
    setForm({
      invoice_type: invoice.invoice_type as "PURCHASE" | "SERVICE",
      invoice_number: invoice.invoice_number,
      order_id: String(invoice.order_id),
      party_id: String(invoice.party_id),
      financial_year: invoice.financial_year,
      invoice_date: String(invoice.invoice_date).slice(0, 10),
      due_date: String(invoice.due_date).slice(0, 10),
      amount: String(invoice.amount),
      period: invoice.period ?? "",
      location: invoice.location ?? "",
      remarks: invoice.remarks ?? "",
      description: invoice.description ?? "",
    });

    setInvoiceFile(null);
    setEditingInvoiceId(invoice.id);
    setShowForm(true);
    setError("");
    setSuccess("");

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function uploadInvoiceDocument(
    invoiceId: number,
    file: File,
  ): Promise<void> {
    const validationError = validateInvoiceFile(file);

    if (validationError) {
      throw new Error(validationError);
    }

    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(
      `/api/invoices/${invoiceId}/invoice-copy`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${sessionStorage.getItem("access_token")}`,
        },
        body: formData,
      },
    );

    const data = await response.json().catch(() => null);

    if (!response.ok) {
      throw new Error(
        getErrorMessage(data, "Invoice saved, but its document upload failed."),
      );
    }

    setUploadedDocumentIds((previous) =>
      previous.includes(invoiceId) ? previous : [...previous, invoiceId],
    );
  }

  async function handleSubmitInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");

    const isEditing = editingInvoiceId !== null;

    if (!orderContext && !isEditing) {
      setError(
        "New invoices can only be created from an order's invoice page.",
      );
      return;
    }

    if (!form.invoice_number.trim()) {
      setError("Enter an invoice number.");
      return;
    }

    if (!form.invoice_date || !form.due_date) {
      setError("Enter both the invoice date and due date.");
      return;
    }

    if (form.due_date < form.invoice_date) {
      setError("Due date cannot be before invoice date.");
      return;
    }

    if (!Number.isFinite(Number(form.amount)) || Number(form.amount) <= 0) {
      setError("Invoice amount must be greater than zero.");
      return;
    }

    if (!form.order_id || !form.party_id) {
      setError("Select an order and its associated party.");
      return;
    }

    // New invoices must include a copy for IT Head approval.
    if (!isEditing && !invoiceFile) {
      setError(
        "Please attach the invoice copy before submitting it for IT Head approval.",
      );
      return;
    }

    if (invoiceFile) {
      const validationError = validateInvoiceFile(invoiceFile);

      if (validationError) {
        setError(validationError);
        return;
      }
    }

    const partyId = orderContext
      ? orderContext.party_id
      : Number(form.party_id);

    setSaving(true);

    try {
      const token = sessionStorage.getItem("access_token");

      const payload = {
        invoice_type: form.invoice_type,
        invoice_number: form.invoice_number.trim(),
        order_id: Number(form.order_id),
        party_id: partyId,
        financial_year: form.financial_year.trim(),
        invoice_date: form.invoice_date,
        due_date: form.due_date,
        amount: Number(form.amount),
        period: form.period.trim() || null,
        location: form.location.trim() || null,
        remarks: form.remarks.trim() || null,
        description: form.description.trim() || null,
      };

      let response: Response;

      if (isEditing) {
        // Existing invoices continue using the normal update endpoint.
        response = await fetch(`/api/invoices/${editingInvoiceId}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(payload),
        });
      } else {
        // New invoices go through IT Head approval.
        const formData = new FormData();

        formData.append("payload_json", JSON.stringify(payload));
        formData.append("invoice_copy", invoiceFile!);

        response = await fetch("/api/invoice-approvals/manual", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
          },
          body: formData,
        });
      }

      const responseData = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(
            responseData,
            `Unable to ${isEditing ? "update" : "submit"} invoice (${response.status}).`,
          ),
        );
      }

      if (!isEditing) {
        setSuccess(
          "Invoice approval request sent to IT Head successfully. Your request is awaiting approval.",
        );

        resetForm();

        await loadApprovalRequests();

        return;
      }

      const savedInvoiceId = editingInvoiceId;

      if (!savedInvoiceId) {
        throw new Error(
          "Invoice was updated, but its invoice ID could not be identified.",
        );
      }

      let documentUploadFailed = false;

      // Invoice copy upload remains optional for existing invoice edits.
      if (invoiceFile) {
        try {
          await uploadInvoiceDocument(savedInvoiceId, invoiceFile);
        } catch (uploadError) {
          documentUploadFailed = true;
          setError(
            uploadError instanceof Error
              ? `Invoice updated successfully, but document upload failed: ${uploadError.message}`
              : "Invoice updated successfully, but document upload failed.",
          );
        }
      }

      resetForm();

      if (!documentUploadFailed) {
        setSuccess("Invoice updated successfully.");
      }

      setLoading(true);

      await loadInvoices();
      await loadInvoiceRegister();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to save invoice.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteInvoice(invoice: Invoice) {
    const confirmed = window.confirm(
      `Delete invoice "${invoice.invoice_number}"?\n\nThis action cannot be undone.`,
    );

    if (!confirmed) return;

    setError("");
    setSuccess("");
    setDeletingId(invoice.id);

    try {
      const token = sessionStorage.getItem("access_token");

      const response = await fetch(`/api/invoices/${invoice.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);

        throw new Error(
          getErrorMessage(
            data,
            `Unable to delete invoice (${response.status}).`,
          ),
        );
      }

      if (editingInvoiceId === invoice.id) resetForm();

      setUploadedDocumentIds((previous) =>
        previous.filter((id) => id !== invoice.id),
      );

      setSuccess(`Invoice "${invoice.invoice_number}" deleted successfully.`);

      setLoading(true);

      await loadInvoices();
      await loadInvoiceRegister();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to delete invoice.",
      );
    } finally {
      setDeletingId(null);
    }
  }

  async function handleInvoiceCopyUpload(invoiceId: number, file: File) {
    setError("");
    setSuccess("");
    setDocumentBusyId(invoiceId);

    try {
      await uploadInvoiceDocument(invoiceId, file);
      setSuccess("Invoice copy uploaded successfully.");
      setOpenDocumentMenuId(null);
      await loadInvoices();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to upload invoice copy.",
      );
    } finally {
      setDocumentBusyId(null);
    }
  }

  async function handleInvoiceCopyView(invoiceId: number) {
    setError("");

    const previewWindow = window.open("about:blank", "_blank");

    if (!previewWindow) {
      setError("Please allow pop-ups to view the invoice copy.");
      return;
    }

    setDocumentBusyId(invoiceId);

    try {
      const response = await fetch(
        `/api/invoices/${invoiceId}/invoice-copy`,
        {
          headers: {
            Authorization: `Bearer ${sessionStorage.getItem("access_token")}`,
          },
        },
      );

      if (!response.ok) {
        const data = await response.json().catch(() => null);

        throw new Error(
          getErrorMessage(data, "Invoice copy not found."),
        );
      }

      const blob = await response.blob();
      const fileUrl = URL.createObjectURL(blob);

      previewWindow.location.href = fileUrl;

      previewWindow.addEventListener(
        "unload",
        () => URL.revokeObjectURL(fileUrl),
        { once: true },
      );
    } catch (err) {
      previewWindow.close();

      setError(
        err instanceof Error ? err.message : "Unable to view invoice copy.",
      );
    } finally {
      setDocumentBusyId(null);
    }
  }

  async function handleUpdateDateSent(
    row: InvoiceRegisterRow,
    clear = false,
  ) {
    setError("");
    setSuccess("");

    const dateValue = clear
      ? ""
      : dateDrafts[row.id] ?? row.date_sent_to_accounts ?? "";

    setSavingDateId(row.id);

    try {
      const token = sessionStorage.getItem("access_token");

      const response = await fetch(
        `/api/invoices/${row.id}/date-sent-to-accounts`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            date_sent_to_accounts: dateValue || null,
          }),
        },
      );

      if (!response.ok) {
        const data = await response.json().catch(() => null);

        throw new Error(
          getErrorMessage(data, `Unable to update date (${response.status}).`),
        );
      }

      await loadInvoiceRegister();

      setDateDrafts((previous) => {
        const updated = { ...previous };
        delete updated[row.id];
        return updated;
      });

      setSuccess(
        dateValue
          ? `Date sent to Accounts updated for ${row.invoice_number}.`
          : `Date sent to Accounts cleared for ${row.invoice_number}.`,
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to update date sent to Accounts.",
      );
    } finally {
      setSavingDateId(null);
    }
  }

  const filteredRegisterRows = registerRows.filter((row) => {
    const query = search.trim().toLowerCase();

    const matchesSearch =
      row.invoice_number.toLowerCase().includes(query) ||
      row.order_number.toLowerCase().includes(query) ||
      row.party_name.toLowerCase().includes(query) ||
      row.payment_status.toLowerCase().includes(query) ||
      row.invoice_type.toLowerCase().includes(query) ||
      row.budget_name.toLowerCase().includes(query) ||
      row.budget_type.toLowerCase().includes(query);

    const matchesCategory =
      categoryFilter === "ALL" || row.budget_type === categoryFilter;

    return matchesSearch && matchesCategory;
  });

  const totalAmount = invoices.reduce(
    (total, invoice) => total + Number(invoice.amount),
    0,
  );

  const purchaseCount = invoices.filter(
    (invoice) => invoice.invoice_type === "PURCHASE",
  ).length;

  const salesCount = invoices.filter(
    (invoice) => invoice.invoice_type === "SERVICE",
  ).length;

  function hasInvoiceDocument(invoiceId: number): boolean {
    const invoice = invoices.find((item) => item.id === invoiceId);

    return Boolean(
      invoice?.invoice_file_path || uploadedDocumentIds.includes(invoiceId),
    );
  }

  function statusClass(status: string) {
    return `status-badge status-${(status || "UNPAID")
      .toLowerCase()
      .replace(/_/g, "-")}`;
  }

  // Show only pending approval requests.
  const filteredApprovalRequests = approvalRequests.filter((request) => {
    if (request.status !== "PENDING") return false;

    const query = approvalSearch.trim().toLowerCase();

    if (!query) return true;

    const requestOrder = orders.find(
      (order) => order.id === request.order_id,
    );

    const invoiceMatches = (request.invoice_data ?? []).some(
      (invoice) =>
        (invoice.invoice_number ?? "").toLowerCase().includes(query) ||
        (invoice.invoice_type ?? "").toLowerCase().includes(query) ||
        String(invoice.amount ?? "").toLowerCase().includes(query),
    );

    return (
      String(request.id).includes(query) ||
      String(request.order_id).includes(query) ||
      (request.order_number ?? "").toLowerCase().includes(query) ||
      (requestOrder?.order_number ?? "").toLowerCase().includes(query) ||
      (requestOrder?.party_name ?? "").toLowerCase().includes(query) ||
      (request.requested_by ?? "").toLowerCase().includes(query) ||
      request.request_type.toLowerCase().includes(query) ||
      invoiceMatches
    );
  });

  const pendingRequests = filteredApprovalRequests;

  function renderApprovalTable(
    title: string,
    description: string,
    requests: ApprovalRequest[],
  ) {
    const invoiceRows = requests.flatMap((request) => {
      const requestInvoices =
        request.invoice_data?.length > 0
          ? request.invoice_data
          : [{}];

      return requestInvoices.map((invoice, index) => ({
        request,
        invoice,
        index,
      }));
    });

    return (
      <div className="invoice-approval-section">
        <div className="invoice-approval-section-header">
          <div>
            <h4>{title}</h4>
            <p>{description}</p>
          </div>

          <span className="invoice-approval-count invoice-approval-count-pending">
            {requests.length}
          </span>
        </div>

        <div className="invoice-approval-table-wrapper">
          <table className="invoice-approval-table">
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Invoice No.</th>
                <th>Invoice Date</th>
                <th>Order No.</th>
                <th>Vendor</th>
                <th>Amount</th>
                <th>Request Type</th>
                <th>Submitted By</th>
                <th>Submitted On</th>
              </tr>
            </thead>

            <tbody>
              {approvalLoading ? (
                <tr>
                  <td colSpan={9} className="invoice-empty-state">
                    Loading approval requests...
                  </td>
                </tr>
              ) : invoiceRows.length === 0 ? (
                <tr>
                  <td colSpan={9} className="invoice-empty-state">
                    {approvalSearch.trim()
                      ? "No pending approval requests match your search."
                      : "No pending approval requests found."}
                  </td>
                </tr>
              ) : (
                invoiceRows.map(({ request, invoice, index }) => {
                  const relatedOrder = orders.find(
                    (order) => order.id === request.order_id,
                  );

                  const vendorName =
                    relatedOrder?.party_name ||
                    (invoice.party_id
                      ? `Vendor #${invoice.party_id}`
                      : "—");

                  return (
                    <tr key={`${request.id}-${index}`}>
                      <td>
                        <strong>#{request.id}</strong>
                      </td>

                      <td>
                        <strong>{invoice.invoice_number || "—"}</strong>

                        {request.invoice_count > 1 && (
                          <small className="invoice-approval-batch-label">
                            Invoice {index + 1} of {request.invoice_count}
                          </small>
                        )}
                      </td>

                      <td>{formatDate(invoice.invoice_date)}</td>

                      <td>
                        {request.order_number ||
                          relatedOrder?.order_number ||
                          `Order #${request.order_id}`}
                      </td>

                      <td>{vendorName}</td>

                      <td>
                        {invoice.amount !== undefined
                          ? formatCurrency(invoice.amount)
                          : "—"}
                      </td>

                      <td>
                        <span className="invoice-approval-type">
                          {request.request_type}
                        </span>
                      </td>

                      <td>{request.requested_by || "—"}</td>

                      <td>{formatDateTime(request.requested_at)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <section className="page-content">
      <div className="invoice-page-header">
        <div>
          <p className="eyebrow">FINANCE OPERATIONS</p>

          <h2>
            {orderContext
              ? `Invoice ${editingInvoiceId !== null ? "Details" : "Entry"} — ${orderContext.order_number}`
              : "Invoices"}
          </h2>

          <p className="page-description">
            {orderContext
              ? editingInvoiceId !== null
                ? `Update the invoice associated with order ${orderContext.order_number}.`
                : `Submit an invoice linked to order ${orderContext.order_number} for IT Head approval.`
              : "View pending approval requests and manage the official vendor invoice register."}
          </p>
        </div>

        {orderContext && (
          <button
            type="button"
            className="invoice-primary-button"
            onClick={() => onBackToOrder?.()}
          >
            Back to Order
          </button>
        )}
      </div>

      {success && (
        <div className="notice" role="status">
          {success}
        </div>
      )}

      {error && (
        <div className="error-message" role="alert">
          {error}
        </div>
      )}

      {showForm && (orderContext || editingInvoiceId !== null) && (
        <div className="invoice-form-panel">
          <h3 className="invoice-form-heading">
            {editingInvoiceId !== null
              ? "Edit Invoice"
              : "Submit Invoice for Approval"}
          </h3>

          <p className="invoice-form-description">
            {orderContext
              ? editingInvoiceId !== null
                ? `Update the invoice associated with order ${orderContext.order_number}.`
                : "This invoice will be sent to the IT Head for approval. It will not enter the official Invoice Register until approved."
              : "Update the details of this existing invoice."}
          </p>

          <form className="invoice-form" onSubmit={handleSubmitInvoice}>
            <div className="invoice-form-field">
              <label htmlFor="invoice-type">Invoice Type *</label>
              <select
                id="invoice-type"
                value={form.invoice_type}
                onChange={(event) =>
                  updateField(
                    "invoice_type",
                    event.target.value as "PURCHASE" | "SERVICE",
                  )
                }
                disabled={Boolean(orderContext) || saving}
                required
              >
                <option value="PURCHASE">Purchase</option>
                <option value="SERVICE">Sales</option>
              </select>
            </div>

            <div className="invoice-form-field">
              <label htmlFor="invoice-number">Invoice Number *</label>
              <input
                id="invoice-number"
                value={form.invoice_number}
                onChange={(event) =>
                  updateField("invoice_number", event.target.value)
                }
                maxLength={100}
                disabled={saving}
                required
              />
            </div>

            <div className="invoice-form-field">
              <label htmlFor="invoice-order">Order *</label>
              <select
                id="invoice-order"
                value={form.order_id}
                onChange={(event) => {
                  const selected = orders.find(
                    (order) => String(order.id) === event.target.value,
                  );

                  setForm((previous) => ({
                    ...previous,
                    order_id: event.target.value,
                    party_id: selected ? String(selected.party_id) : "",
                    invoice_type:
                      selected?.order_type === "SO" ? "SERVICE" : "PURCHASE",
                    financial_year:
                      selected?.financial_year ?? previous.financial_year,
                  }));
                }}
                disabled={Boolean(orderContext) || saving}
                required
              >
                <option value="">Select an order</option>

                {orders
                  .filter((order) => order.status !== "CANCELLED")
                  .map((order) => (
                    <option key={order.id} value={String(order.id)}>
                      {order.order_number} — {order.order_type}
                    </option>
                  ))}
              </select>
            </div>

            <div className="invoice-form-field">
              <label htmlFor="invoice-party-name">Vendor Name *</label>

              <input
                id="invoice-party-name"
                value={displayedPartyName}
                placeholder={
                  form.order_id
                    ? "Loading vendor name..."
                    : "Select an order first"
                }
                readOnly
                aria-readonly="true"
                className="invoice-readonly-field"
                required
              />

              <input type="hidden" name="party_id" value={form.party_id} />

              <small>
                The vendor is linked to the selected order and cannot be changed
                here.
              </small>
            </div>

            <div className="invoice-form-field">
              <label htmlFor="invoice-year">Financial Year *</label>
              <input
                id="invoice-year"
                value={form.financial_year}
                onChange={(event) =>
                  updateField("financial_year", event.target.value)
                }
                pattern="[0-9]{4}-[0-9]{4}"
                maxLength={9}
                title="Enter the financial year as YYYY-YYYY"
                disabled={saving}
                required
              />
            </div>

            <div className="invoice-form-field">
              <label htmlFor="invoice-amount">Amount (INR) *</label>
              <input
                id="invoice-amount"
                type="number"
                min="0.01"
                step="0.01"
                value={form.amount}
                onChange={(event) =>
                  updateField("amount", event.target.value)
                }
                disabled={saving}
                required
              />
            </div>

            <div className="invoice-form-field">
              <label htmlFor="invoice-date">Invoice Date *</label>
              <input
                id="invoice-date"
                type="date"
                value={form.invoice_date}
                onChange={(event) =>
                  updateField("invoice_date", event.target.value)
                }
                disabled={saving}
                required
              />
            </div>

            <div className="invoice-form-field">
              <label htmlFor="invoice-due-date">Due Date *</label>
              <input
                id="invoice-due-date"
                type="date"
                min={form.invoice_date || undefined}
                value={form.due_date}
                onChange={(event) =>
                  updateField("due_date", event.target.value)
                }
                disabled={saving}
                required
              />
            </div>

            <div className="invoice-form-field">
              <label htmlFor="invoice-period">Period</label>
              <input
                id="invoice-period"
                value={form.period}
                onChange={(event) =>
                  updateField("period", event.target.value)
                }
                maxLength={100}
                placeholder="e.g. September–November 2026"
                disabled={saving}
              />
            </div>

            <div className="invoice-form-field">
              <label htmlFor="invoice-location">Location</label>
              <input
                id="invoice-location"
                value={form.location}
                onChange={(event) =>
                  updateField("location", event.target.value)
                }
                maxLength={200}
                placeholder="e.g. Kolkata site"
                disabled={saving}
              />
            </div>

            <div className="invoice-form-field full-width">
              <label htmlFor="invoice-remarks">Remarks</label>
              <textarea
                id="invoice-remarks"
                value={form.remarks}
                onChange={(event) =>
                  updateField("remarks", event.target.value)
                }
                rows={3}
                disabled={saving}
              />
            </div>

            <div className="invoice-form-field full-width">
              <label htmlFor="invoice-description">Description</label>
              <textarea
                id="invoice-description"
                value={form.description}
                onChange={(event) =>
                  updateField("description", event.target.value)
                }
                rows={3}
                disabled={saving}
              />
            </div>

            <div className="invoice-form-field full-width">
              <label htmlFor="invoice-document">
                Invoice Copy {editingInvoiceId === null ? "*" : ""}
              </label>

              <input
                id="invoice-document"
                type="file"
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={(event) =>
                  setInvoiceFile(event.target.files?.[0] ?? null)
                }
                disabled={saving}
                required={editingInvoiceId === null}
              />

              <small>
                {editingInvoiceId === null
                  ? "Required for IT Head approval. "
                  : "Optional when editing an existing invoice. "}
                Supported formats: PDF, PNG, JPG, JPEG. Maximum file size: 10
                MB.
              </small>

              {invoiceFile && (
                <p className="invoice-selected-file">
                  Selected: {invoiceFile.name}
                </p>
              )}
            </div>

            {editingInvoiceId === null && (
              <div className="invoice-form-field full-width">
                <div className="invoice-approval-notice">
                  <strong>Approval workflow</strong>
                  <p>
                    Your invoice and its supporting copy will be sent to the IT
                    Head for review. The invoice will enter the official
                    Invoice Register only after approval.
                  </p>
                </div>
              </div>
            )}

            <div className="invoice-form-actions full-width">
              <button
                type="button"
                className="invoice-secondary-button"
                onClick={leaveOrderEditor}
                disabled={saving}
              >
                Cancel
              </button>

              <button
                type="submit"
                className="invoice-primary-button"
                disabled={saving}
              >
                {saving
                  ? editingInvoiceId !== null
                    ? "Updating..."
                    : "Submitting for Approval..."
                  : editingInvoiceId !== null
                    ? "Update Invoice"
                    : "Submit for IT Head Approval"}
              </button>
            </div>
          </form>
        </div>
      )}

      {!orderContext && (
        <>
          {/* Pending invoice approval requests */}
          <div className="invoice-approvals-panel">
            <div className="invoice-approvals-header">
              <div>
                <p className="eyebrow">WORKFLOW MANAGEMENT</p>
                <h3>Pending Approval Requests</h3>
                <p>
                  Track invoices awaiting review and approval by the IT Head.
                </p>
              </div>

              <button
                type="button"
                className="invoice-secondary-button"
                onClick={() => void refreshInvoiceData()}
                disabled={approvalLoading}
              >
                {approvalLoading ? "Refreshing..." : "Refresh"}
              </button>
            </div>

            <div className="invoice-approval-toolbar">
              <div className="invoice-approval-search-group">
                <label
                  htmlFor="approval-request-search"
                  className="invoice-approval-search-label"
                >
                  Search Pending Requests
                </label>

                <input
                  id="approval-request-search"
                  type="text"
                  className="invoice-approval-search"
                  placeholder="Search by request ID, invoice, vendor..."
                  value={approvalSearch}
                  onChange={(event) => setApprovalSearch(event.target.value)}
                />
              </div>
            </div>

            {renderApprovalTable(
              "Pending Approval Requests",
              "Invoices awaiting an IT Head decision.",
              pendingRequests,
            )}
          </div>

          {/* Official invoice register */}
          <div className="invoice-register-summary">
            <div className="invoice-summary-card">
              <span>Total Invoices</span>
              <strong>{filteredRegisterRows.length}</strong>
            </div>

            <div className="invoice-summary-card">
              <span>Purchase Invoices</span>
              <strong>{purchaseCount}</strong>
            </div>

            <div className="invoice-summary-card">
              <span>Sales Invoices</span>
              <strong>{salesCount}</strong>
            </div>

            <div className="invoice-summary-card">
              <span>Total Recorded Amount</span>
              <strong>{formatCurrency(totalAmount)}</strong>
            </div>
          </div>

          <div className="invoice-register-panel">
            <div className="invoice-register-header">
              <div>
                <h3>Official Invoice Register</h3>
                <p>
                  Search, review and manage invoices recorded in the system
                  after approval.
                </p>
              </div>
            </div>

            <div className="invoice-register-toolbar">
              <div className="invoice-register-filters">
                <button
                  type="button"
                  className={
                    categoryFilter === "ALL"
                      ? "invoice-filter-button active"
                      : "invoice-filter-button"
                  }
                  onClick={() => setCategoryFilter("ALL")}
                >
                  All
                </button>

                <button
                  type="button"
                  className={
                    categoryFilter === "OPEX"
                      ? "invoice-filter-button active"
                      : "invoice-filter-button"
                  }
                  onClick={() => setCategoryFilter("OPEX")}
                >
                  OPEX
                </button>

                <button
                  type="button"
                  className={
                    categoryFilter === "CAPEX"
                      ? "invoice-filter-button active"
                      : "invoice-filter-button"
                  }
                  onClick={() => setCategoryFilter("CAPEX")}
                >
                  CAPEX
                </button>
              </div>

              <div className="invoice-register-search">
                <input
                  type="search"
                  placeholder="Search invoice, PO, vendor..."
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
            </div>

            <div className="invoice-register-result-count">
              Showing {filteredRegisterRows.length} invoice
              {filteredRegisterRows.length !== 1 ? "s" : ""}
            </div>

            <div className="invoice-register-table-wrapper">
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
                  {filteredRegisterRows.length === 0 ? (
                    <tr>
                      <td colSpan={14} className="invoice-empty-state">
                        No invoices found matching your search.
                      </td>
                    </tr>
                  ) : (
                    filteredRegisterRows.map((row) => {
                      const invoice = invoices.find(
                        (item) => item.id === row.id,
                      );

                      const hasDocument = hasInvoiceDocument(row.id);
                      const isDocumentBusy = documentBusyId === row.id;
                      const isDateSaving = savingDateId === row.id;

                      const dateValue =
                        dateDrafts[row.id] ??
                        row.date_sent_to_accounts?.slice(0, 10) ??
                        "";

                      return (
                        <tr key={row.id}>
                          <td>
                            <strong>{row.invoice_number}</strong>
                          </td>

                          <td>{formatDate(row.invoice_date)}</td>

                          <td>{formatDate(row.entry_date)}</td>

                          <td>{row.order_number || "—"}</td>

                          <td>
                            {invoice?.vendor_name ||
                              row.party_name ||
                              `Vendor #${row.party_id}`}
                          </td>

                          <td>
                            {row.budget_name
                              ? `${row.budget_name}${
                                  row.budget_type
                                    ? ` (${row.budget_type})`
                                    : ""
                                }`
                              : row.budget_type || "—"}
                          </td>

                          <td>{formatCurrency(row.amount)}</td>

                          <td>{formatCurrency(row.total_paid)}</td>

                          <td>
                            {formatCurrency(
                              row.balance_due ?? row.amount,
                            )}
                          </td>

                          <td>{formatDate(row.due_date)}</td>

                          <td>
                            <div className="invoice-date-sent-action">
                              <input
                                type="date"
                                value={dateValue}
                                onChange={(event) =>
                                  setDateDrafts((previous) => ({
                                    ...previous,
                                    [row.id]: event.target.value,
                                  }))
                                }
                                disabled={isDateSaving}
                                aria-label={`Date sent to Accounts for ${row.invoice_number}`}
                              />

                              <div className="invoice-date-sent-buttons">
                                <button
                                  type="button"
                                  onClick={() =>
                                    void handleUpdateDateSent(row)
                                  }
                                  disabled={isDateSaving}
                                >
                                  {isDateSaving ? "Saving..." : "Save"}
                                </button>

                                <button
                                  type="button"
                                  onClick={() =>
                                    void handleUpdateDateSent(row, true)
                                  }
                                  disabled={
                                    isDateSaving ||
                                    !row.date_sent_to_accounts
                                  }
                                >
                                  Clear
                                </button>
                              </div>
                            </div>
                          </td>

                          <td>
                            <span className={statusClass(row.payment_status)}>
                              {row.payment_status || "UNPAID"}
                            </span>
                          </td>

                          <td>
                            <div className="invoice-document-menu">
                              <button
                                type="button"
                                className="invoice-document-trigger"
                                onClick={() =>
                                  setOpenDocumentMenuId((previous) =>
                                    previous === row.id ? null : row.id,
                                  )
                                }
                                disabled={isDocumentBusy}
                              >
                                Documents
                                <span className="invoice-document-chevron">
                                  {openDocumentMenuId === row.id ? "▲" : "▼"}
                                </span>
                              </button>

                              <span
                                className={`invoice-document-status ${
                                  hasDocument
                                    ? "is-uploaded"
                                    : "is-missing"
                                }`}
                              >
                                {hasDocument ? "Uploaded" : "Not uploaded"}
                              </span>

                              {openDocumentMenuId === row.id && (
                                <div className="invoice-document-dropdown">
                                  {hasDocument && (
                                    <button
                                      type="button"
                                      className="invoice-document-menu-item"
                                      onClick={() => {
                                        setOpenDocumentMenuId(null);
                                        void handleInvoiceCopyView(row.id);
                                      }}
                                      disabled={isDocumentBusy}
                                    >
                                      View invoice copy
                                    </button>
                                  )}

                                  <label className="invoice-document-menu-item invoice-document-upload-option">
                                    {isDocumentBusy
                                      ? "Uploading..."
                                      : hasDocument
                                        ? "Replace invoice copy"
                                        : "Upload invoice copy"}

                                    <input
                                      type="file"
                                      accept=".pdf,.png,.jpg,.jpeg"
                                      disabled={isDocumentBusy}
                                      onChange={(event) => {
                                        const file =
                                          event.target.files?.[0];

                                        if (file) {
                                          void handleInvoiceCopyUpload(
                                            row.id,
                                            file,
                                          );
                                        }

                                        event.target.value = "";
                                      }}
                                    />
                                  </label>
                                </div>
                              )}
                            </div>
                          </td>

                          <td>
                            <div className="invoice-row-actions">
                              <button
                                type="button"
                                onClick={() => {
                                  if (invoice) {
                                    startEdit(invoice);
                                  }
                                }}
                                disabled={!invoice}
                              >
                                Edit
                              </button>

                              <button
                                type="button"
                                className="invoice-delete-button"
                                onClick={() => {
                                  if (invoice) {
                                    void handleDeleteInvoice(invoice);
                                  }
                                }}
                                disabled={!invoice || deletingId === row.id}
                              >
                                {deletingId === row.id
                                  ? "Deleting..."
                                  : "Delete"}
                              </button>

                              <button
                                type="button"
                                onClick={() => onPaymentDetails?.(row)}
                                disabled={!onPaymentDetails}
                              >
                                Update Payment Details
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
