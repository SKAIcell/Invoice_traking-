import { useEffect, useMemo, useState, type FormEvent } from "react";

type Order = {
  id: number;
  order_type: "PO" | "SO";
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

type Vendor = {
  id: number;
  party_type: "VENDOR" | "CUSTOMER";
  code: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  is_active: boolean;
};

type Budget = {
  id: number;
  name: string;
  financial_year: string;
  budget_type: "OPEX" | "CAPEX";
  planned_amount: string | number;
  approved_amount: string | number;
};

type OrderImportRow = {
  excel_row: number;
  order_type: "PO" | "SO";
  order_number: string;
  vendor_code: string;
  budget_name: string;
  financial_year: string;
  order_date: string;
  order_period?: string | null;
  location?: string | null;
  amount: string;
  description?: string | null;
  errors: string[];
  is_valid: boolean;
  vendor_id?: number | null;
  budget_id?: number | null;
};

type OrderImportPreview = {
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  rows: OrderImportRow[];
};

type OrderImportResult = {
  message: string;
  created_count: number;
  created_order_ids: number[];
};

type OrderCategoryFilter = "ALL" | "OPEX" | "CAPEX";

type OrderForm = {
  order_type: "PO" | "SO";
  order_number: string;
  party_id: string;
  budget_id: string;
  order_date: string;
  order_period: string;
  location: string;
  amount: string;
  status: string;
  description: string;
};

type VendorForm = {
  code: string;
  name: string;
  email: string;
  phone: string;
  address: string;
};

type ApiError = {
  detail?: string | { message?: string } | { msg?: string }[];
};

type Props = {
  onOpenOrder: (order: Order) => void;
  initialVendorId?: number | null;
  initialVendorName?: string;
  initialCategoryFilter?: OrderCategoryFilter;
};

type DocumentType = "order-copy" | "approval";

const FINANCIAL_YEAR = "2026-2027";

const OFFICIAL_LOCATIONS = [
  "TIRUMALA",
  "Loudon Street",
  "SALTLAKE",
  "CAMAC STREET",
  "AHMEDABAD",
  "OUTRAM STREET",
  "DELHI",
  "GUWAHATI",
  "BCTL",
  "Jangalpur",
  "LANE10",
  "ULUBERIA",
  "Ghoraghata",
  "Khalna",
] as const;

const OTHER_LOCATION = "Others";

const emptyForm: OrderForm = {
  order_type: "PO",
  order_number: "",
  party_id: "",
  budget_id: "",
  order_date: new Date().toISOString().slice(0, 10),
  order_period: "",
  location: "",
  amount: "",
  status: "DRAFT",
  description: "",
};

const emptyVendorForm: VendorForm = {
  code: "",
  name: "",
  email: "",
  phone: "",
  address: "",
};

function getToken(): string | null {
  return sessionStorage.getItem("access_token");
}

function getErrorMessage(data: ApiError, fallback: string): string {
  if (typeof data.detail === "string") return data.detail;

  if (
    data.detail &&
    !Array.isArray(data.detail) &&
    typeof data.detail.message === "string"
  ) {
    return data.detail.message;
  }

  if (Array.isArray(data.detail)) {
    return data.detail.map((item) => item.msg ?? "Invalid input").join(", ");
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

function money(value: string | number): string {
  return Number(value || 0).toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  });
}

function orderTypeLabel(type: string): string {
  if (type === "PO") return "Purchase Order";
  if (type === "SO") return "Service Order";
  return type;
}

function expectedBudgetType(orderType: "PO" | "SO"): "CAPEX" | "OPEX" {
  return orderType === "PO" ? "CAPEX" : "OPEX";
}

function expectedAccountType(_orderType: "PO" | "SO"): "VENDOR" {
  return "VENDOR";
}

function isOfficialLocation(location: string): boolean {
  return (OFFICIAL_LOCATIONS as readonly string[]).includes(location);
}

function validateDocument(
  file: File,
  documentType: DocumentType,
): string | null {
  const allowedExtensions =
    documentType === "order-copy"
      ? [".pdf", ".jpg", ".jpeg", ".png"]
      : [".pdf", ".jpg", ".jpeg"];

  const extension = file.name
    .slice(file.name.lastIndexOf("."))
    .toLowerCase();

  if (!allowedExtensions.includes(extension)) {
    return documentType === "order-copy"
      ? "Order Copy must be a PDF, JPG, JPEG or PNG file."
      : "Approval Copy must be a PDF, JPG or JPEG file.";
  }

  if (file.size > 10 * 1024 * 1024) {
    return "File size must not exceed 10 MB.";
  }

  return null;
}

export default function OrdersPage({
  onOpenOrder,
  initialVendorId = null,
  initialVendorName = "",
  initialCategoryFilter = "ALL",
}: Props) {
  const [orders, setOrders] = useState<Order[]>([]);
  const [importFile, setImportFile] = useState<File | null>(null);
const [importPreview, setImportPreview] =
  useState<OrderImportPreview | null>(null);
const [showImport, setShowImport] = useState(false);
const [importLoading, setImportLoading] = useState(false);
const [importConfirming, setImportConfirming] = useState(false);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [form, setForm] = useState<OrderForm>(emptyForm);
  const [vendorForm, setVendorForm] = useState<VendorForm>(emptyVendorForm);

  const [locationChoice, setLocationChoice] = useState("");
  const [categoryFilter, setCategoryFilter] =
    useState<OrderCategoryFilter>(initialCategoryFilter);

  const [showForm, setShowForm] = useState(false);
  const [showVendorForm, setShowVendorForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingVendor, setSavingVendor] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [editingOrderId, setEditingOrderId] = useState<number | null>(null);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState(initialVendorName);

  const [documentBusy, setDocumentBusy] = useState<string | null>(null);
  const [openDocumentMenuId, setOpenDocumentMenuId] = useState<number | null>(
    null,
  );

  const [orderCopyFile, setOrderCopyFile] = useState<File | null>(null);
  const [approvalFile, setApprovalFile] = useState<File | null>(null);
  const [uploadedDocumentIds, setUploadedDocumentIds] = useState<
    Record<number, { orderCopy?: boolean; approval?: boolean }>
  >({});

  useEffect(() => {
    setCategoryFilter(initialCategoryFilter);
  }, [initialCategoryFilter]);

  useEffect(() => {
    setSearch(initialVendorName);
  }, [initialVendorName]);

  async function loadOrders() {
    setLoading(true);
    setError("");

    try {
      const response = await fetch("/api/orders", {
        headers: { Authorization: `Bearer ${getToken()}` },
      });

      const data = await readResponse(response);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data as ApiError, "Unable to load orders."),
        );
      }

      const orderList: Order[] = Array.isArray(data)
        ? (data as Order[])
        : typeof data === "object" &&
            data !== null &&
            "items" in data &&
            Array.isArray(data.items)
          ? (data.items as Order[])
          : [];

      setOrders(orderList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load orders.");
    } finally {
      setLoading(false);
    }
  }

  async function loadOptions() {
    setLoadingOptions(true);

    try {
      const headers = { Authorization: `Bearer ${getToken()}` };

      const [vendorsResponse, budgetsResponse] = await Promise.all([
        fetch(
          "/api/parties?party_type=VENDOR&is_active=true&limit=100&offset=0",
          { headers },
        ),
        fetch(`/api/budgets?financial_year=${FINANCIAL_YEAR}`, { headers }),
      ]);

      const [vendorsData, budgetsData] = await Promise.all([
        readResponse(vendorsResponse),
        readResponse(budgetsResponse),
      ]);

      if (!vendorsResponse.ok) {
        throw new Error(
          getErrorMessage(vendorsData as ApiError, "Unable to load vendors."),
        );
      }

      if (!budgetsResponse.ok) {
        throw new Error(
          getErrorMessage(budgetsData as ApiError, "Unable to load budgets."),
        );
      }

      setVendors(Array.isArray(vendorsData) ? (vendorsData as Vendor[]) : []);
      setBudgets(Array.isArray(budgetsData) ? (budgetsData as Budget[]) : []);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load vendor and budget options.",
      );
    } finally {
      setLoadingOptions(false);
    }
  }

  useEffect(() => {
    void loadOrders();
    void loadOptions();
  }, []);

  function updateField<K extends keyof OrderForm>(
    field: K,
    value: OrderForm[K],
  ) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function handleLocationChange(value: string) {
    setLocationChoice(value);

    if (value === OTHER_LOCATION) {
      setForm((current) => ({
        ...current,
        location: isOfficialLocation(current.location) ? "" : current.location,
      }));
      return;
    }

    updateField("location", value);
  }

  function resetForm() {
    setForm(emptyForm);
    setVendorForm(emptyVendorForm);
    setLocationChoice("");
    setEditingOrderId(null);
    setShowVendorForm(false);
    setShowForm(false);
    setOrderCopyFile(null);
    setApprovalFile(null);
  }

  function startCreate() {
    if (showForm && editingOrderId === null) {
      resetForm();
      return;
    }

    resetForm();
    setShowForm(true);
    setError("");
    setSuccess("");
  }

  function startEdit(order: Order) {
    setEditingOrderId(order.id);

    const savedLocation = order.location ?? "";

    setLocationChoice(
      savedLocation
        ? isOfficialLocation(savedLocation)
          ? savedLocation
          : OTHER_LOCATION
        : "",
    );

    setForm({
      order_type: order.order_type,
      order_number: order.order_number,
      party_id: String(order.party_id),
      budget_id: order.budget_id == null ? "" : String(order.budget_id),
      order_date: String(order.order_date).slice(0, 10),
      order_period: order.order_period ?? "",
      location: savedLocation,
      amount: String(order.amount),
      status: order.status,
      description: order.description ?? "",
    });

    setOrderCopyFile(null);
    setApprovalFile(null);
    setVendorForm(emptyVendorForm);
    setShowVendorForm(false);
    setShowForm(true);
    setError("");
    setSuccess("");

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleCreateVendor() {
    setError("");
    setSuccess("");

    const code = vendorForm.code.trim().toUpperCase();
    const name = vendorForm.name.trim();

    if (!code || !name) {
      setError("Vendor code and vendor name are required.");
      return;
    }

    setSavingVendor(true);

    try {
      const response = await fetch("/api/parties", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          party_type: "VENDOR",
          code,
          name,
          email: vendorForm.email.trim() || null,
          phone: vendorForm.phone.trim() || null,
          address: vendorForm.address.trim() || null,
        }),
      });

      const data = await readResponse(response);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data as ApiError, "Unable to create vendor."),
        );
      }

      const newVendor = data as Vendor;

      setVendors((current) => [
        ...current.filter((vendor) => vendor.id !== newVendor.id),
        newVendor,
      ]);

      setForm((current) => ({
        ...current,
        party_id: String(newVendor.id),
      }));

      setVendorForm(emptyVendorForm);
      setShowVendorForm(false);
      setSuccess(`Vendor "${newVendor.name}" created and selected.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create vendor.");
    } finally {
      setSavingVendor(false);
    }
  }

  async function uploadDocument(
    orderId: number,
    documentType: DocumentType,
    file: File,
  ): Promise<void> {
    const validationError = validateDocument(file, documentType);

    if (validationError) {
      throw new Error(validationError);
    }

    const key = `${orderId}-${documentType}`;
    setDocumentBusy(key);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(
        `/api/orders/${orderId}/${documentType}`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${getToken()}`,
          },
          body: formData,
        },
      );

      const data = await readResponse(response);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data as ApiError, "Unable to upload document."),
        );
      }

      setUploadedDocumentIds((current) => ({
        ...current,
        [orderId]: {
          ...current[orderId],
          ...(documentType === "order-copy"
            ? { orderCopy: true }
            : { approval: true }),
        },
      }));
    } finally {
      setDocumentBusy(null);
    }
  }

  function resetImport() {
  setImportFile(null);
  setImportPreview(null);
}

async function handleImportPreview() {
  setError("");
  setSuccess("");

  if (!importFile) {
    setError("Select an Excel file first.");
    return;
  }

  if (!importFile.name.toLowerCase().endsWith(".xlsx")) {
    setError("Please select an Excel .xlsx file.");
    return;
  }

  if (importFile.size > 10 * 1024 * 1024) {
    setError("Excel file must be 10 MB or smaller.");
    return;
  }

  setImportLoading(true);
  setImportPreview(null);

  try {
    const formData = new FormData();
    formData.append("file", importFile);

    const response = await fetch("/api/orders/import/preview", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${getToken()}`,
      },
      body: formData,
    });

    const data = await readResponse(response);

    if (!response.ok) {
      throw new Error(
        getErrorMessage(data as ApiError, "Unable to preview Excel file."),
      );
    }

    const preview = data as OrderImportPreview;
    setImportPreview(preview);

    if (preview.invalid_rows > 0) {
      setError(
        `${preview.invalid_rows} row(s) need correction. Only a completely valid preview can be imported.`,
      );
    } else if (preview.valid_rows > 0) {
      setSuccess(
        `Preview complete. All ${preview.valid_rows} order(s) passed validation.`,
      );
    } else {
      setError("The Excel file does not contain any importable order rows.");
    }
  } catch (err) {
    setError(
      err instanceof Error ? err.message : "Unable to preview Excel file.",
    );
  } finally {
    setImportLoading(false);
  }
}

async function handleConfirmImport() {
  if (
    !importPreview ||
    importPreview.valid_rows === 0 ||
    importPreview.invalid_rows > 0
  ) {
    setError("Please correct all invalid rows before importing.");
    return;
  }

  const confirmed = window.confirm(
    `Import ${importPreview.valid_rows} orders into the Order Register? This will create actual database records.`,
  );

  if (!confirmed) return;

  setImportConfirming(true);
  setError("");
  setSuccess("");

  try {
    const response = await fetch("/api/orders/import/confirm", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify(importPreview.rows),
    });

    const data = await readResponse(response);

    if (!response.ok) {
      throw new Error(
        getErrorMessage(data as ApiError, "Unable to import orders."),
      );
    }

    const result = data as OrderImportResult;

    resetImport();
    setShowImport(false);

    await loadOrders();

    setSuccess(
      `${result.created_count} order(s) imported successfully. Order IDs: ${result.created_order_ids.join(", ")}.`,
    );
  } catch (err) {
    setError(
      err instanceof Error ? err.message : "Unable to import orders.",
    );
  } finally {
    setImportConfirming(false);
  }
}

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (!form.party_id || Number(form.party_id) <= 0) {
      setError("Select a vendor.");
      return;
    }

    if (!form.budget_id || Number(form.budget_id) <= 0) {
      setError(`Select a ${expectedBudgetType(form.order_type)} budget.`);
      return;
    }

    const selectedAccount = vendors.find(
      (vendor) =>
        vendor.id === Number(form.party_id) &&
        vendor.party_type === expectedAccountType(form.order_type),
    );

    if (!selectedAccount) {
      setError(
        `Select a valid vendor for this ${orderTypeLabel(form.order_type)}.`,
      );
      return;
    }

    const selectedBudget = budgets.find(
      (budget) => budget.id === Number(form.budget_id),
    );

    if (!selectedBudget) {
      setError("The selected budget could not be found. Refresh and try again.");
      return;
    }

    const requiredType = expectedBudgetType(form.order_type);

    if (selectedBudget.budget_type !== requiredType) {
      setError(`${form.order_type} orders must use a ${requiredType} budget.`);
      return;
    }

    if (selectedBudget.financial_year !== FINANCIAL_YEAR) {
      setError(`Select a budget for financial year ${FINANCIAL_YEAR}.`);
      return;
    }

    if (!form.amount || Number(form.amount) <= 0) {
      setError("Order amount must be greater than zero.");
      return;
    }

    if (!form.order_number.trim()) {
      setError("Order number is required.");
      return;
    }

    if (!form.order_date) {
      setError("Order date is required.");
      return;
    }

    if (locationChoice === OTHER_LOCATION && !form.location.trim()) {
      setError("Enter a location when selecting Others.");
      return;
    }

    if (orderCopyFile) {
      const fileError = validateDocument(orderCopyFile, "order-copy");
      if (fileError) {
        setError(fileError);
        return;
      }
    }

    if (approvalFile) {
      const fileError = validateDocument(approvalFile, "approval");
      if (fileError) {
        setError(fileError);
        return;
      }
    }

    const isEditing = editingOrderId !== null;

    const payload = {
      order_type: form.order_type,
      order_number: form.order_number.trim(),
      financial_year: FINANCIAL_YEAR,
      party_id: Number(form.party_id),
      budget_id: Number(form.budget_id),
      order_date: form.order_date,
      order_period: form.order_period.trim() || null,
      location: form.location.trim() || null,
      amount: Number(form.amount),
      description: form.description.trim() || null,
    };

    setSaving(true);

    try {
      const response = await fetch(
        isEditing ? `/api/orders/${editingOrderId}` : "/api/orders",
        {
          method: isEditing ? "PUT" : "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken()}`,
          },
          body: JSON.stringify(payload),
        },
      );

      const data = await readResponse(response);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(
            data as ApiError,
            isEditing ? "Unable to update order." : "Unable to create order.",
          ),
        );
      }

      const savedOrder = data as Order;
      const orderId = isEditing ? editingOrderId! : savedOrder.id;

      if (!orderId) {
        throw new Error(
          "The order was saved, but its ID was not returned. Refresh the order register before uploading documents.",
        );
      }

      const uploadErrors: string[] = [];

      if (orderCopyFile) {
        try {
          await uploadDocument(orderId, "order-copy", orderCopyFile);
        } catch (err) {
          uploadErrors.push(
            `Order Copy: ${
              err instanceof Error ? err.message : "Upload failed."
            }`,
          );
        }
      }

      if (approvalFile) {
        try {
          await uploadDocument(orderId, "approval", approvalFile);
        } catch (err) {
          uploadErrors.push(
            `Approval Copy: ${
              err instanceof Error ? err.message : "Upload failed."
            }`,
          );
        }
      }

      resetForm();
      await loadOrders();

      if (uploadErrors.length > 0) {
        setError(
          `Order ${isEditing ? "updated" : "created"} successfully, but one or more documents could not be uploaded. You can upload them from the Documents menu in the register. ${uploadErrors.join(" ")}`,
        );
      } else if (orderCopyFile || approvalFile) {
        setSuccess(
          `Order ${isEditing ? "updated" : "created"} and documents uploaded successfully.`,
        );
      } else {
        setSuccess(
          isEditing
            ? "Order updated successfully."
            : "Order created successfully.",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save the order.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteOrder(order: Order) {
    const confirmed = window.confirm(
      `Delete order "${order.order_number}"? This action cannot be undone.`,
    );

    if (!confirmed) return;

    setDeletingId(order.id);
    setError("");
    setSuccess("");

    try {
      const response = await fetch(`/api/orders/${order.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${getToken()}` },
      });

      const data = await readResponse(response);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data as ApiError, "Unable to delete order."),
        );
      }

      setSuccess(`Order ${order.order_number} deleted successfully.`);

      if (editingOrderId === order.id) {
        resetForm();
      }

      await loadOrders();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete order.");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleDocumentUpload(
    orderId: number,
    documentType: DocumentType,
    file: File,
  ) {
    setError("");
    setSuccess("");

    try {
      await uploadDocument(orderId, documentType, file);

      setSuccess(
        `${documentType === "order-copy" ? "Order Copy" : "Approval Copy"} uploaded successfully.`,
      );
      setOpenDocumentMenuId(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to upload document.",
      );
    }
  }

  async function handleDocumentView(
    orderId: number,
    documentType: DocumentType,
  ) {
    setError("");
    setSuccess("");

    const previewWindow = window.open("about:blank", "_blank");

    if (!previewWindow) {
      setError("Please allow pop-ups to view the document.");
      return;
    }

    const key = `${orderId}-${documentType}`;
    setDocumentBusy(key);

    try {
      const response = await fetch(
        `/api/orders/${orderId}/${documentType}`,
        {
          headers: {
            Authorization: `Bearer ${getToken()}`,
          },
        },
      );

      if (!response.ok) {
        const data = await readResponse(response);
        throw new Error(
          getErrorMessage(data as ApiError, "Document not found."),
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

      setOpenDocumentMenuId(null);
    } catch (err) {
      previewWindow.close();
      setError(
        err instanceof Error ? err.message : "Unable to view document.",
      );
    } finally {
      setDocumentBusy(null);
    }
  }

  function hasDocument(order: Order, documentType: DocumentType): boolean {
    const uploaded = uploadedDocumentIds[order.id];

    if (documentType === "order-copy") {
      return Boolean(order.order_file_path || uploaded?.orderCopy);
    }

    return Boolean(order.approval_file_path || uploaded?.approval);
  }

  const requiredBudgetType = expectedBudgetType(form.order_type);
  const requiredAccountType = expectedAccountType(form.order_type);

  const availableVendors = useMemo(
    () =>
      vendors.filter(
        (vendor) =>
          vendor.party_type === requiredAccountType &&
          (vendor.is_active || String(vendor.id) === form.party_id),
      ),
    [vendors, requiredAccountType, form.party_id],
  );

  const vendorById = useMemo(
    () => new Map(vendors.map((vendor) => [vendor.id, vendor])),
    [vendors],
  );

  const budgetById = useMemo(
    () => new Map(budgets.map((budget) => [budget.id, budget])),
    [budgets],
  );

  const availableBudgets = useMemo(
    () =>
      budgets.filter(
        (budget) =>
          budget.budget_type === requiredBudgetType &&
          budget.financial_year === FINANCIAL_YEAR,
      ),
    [budgets, requiredBudgetType],
  );

  const filteredOrders = orders.filter((order) => {
    if (initialVendorId !== null && order.party_id !== initialVendorId) {
      return false;
    }

    if (categoryFilter === "OPEX" && order.order_type !== "SO") {
      return false;
    }

    if (categoryFilter === "CAPEX" && order.order_type !== "PO") {
      return false;
    }

    const query = search.trim().toLowerCase();
    const vendor = vendorById.get(order.party_id);
    const budget =
      order.budget_id == null ? undefined : budgetById.get(order.budget_id);

    return (
      order.order_number.toLowerCase().includes(query) ||
      String(order.party_id).includes(query) ||
      (vendor?.name.toLowerCase().includes(query) ?? false) ||
      (vendor?.code.toLowerCase().includes(query) ?? false) ||
      String(order.budget_id ?? "").includes(query) ||
      (budget?.name.toLowerCase().includes(query) ?? false) ||
      (order.order_period?.toLowerCase().includes(query) ?? false) ||
      (order.location?.toLowerCase().includes(query) ?? false) ||
      orderTypeLabel(order.order_type).toLowerCase().includes(query) ||
      order.order_type.toLowerCase().includes(query) ||
      order.status.toLowerCase().includes(query)
    );
  });

  const visibleTotalAmount = filteredOrders.reduce(
    (total, order) => total + Number(order.amount || 0),
    0,
  );

  const visiblePurchaseOrderCount = filteredOrders.filter(
    (order) => order.order_type === "PO",
  ).length;

  const visibleServiceOrderCount = filteredOrders.filter(
    (order) => order.order_type === "SO",
  ).length;

  return (
    <section className="orders-page">
      <div className="orders-heading">
        <div>
          <h1>Orders</h1>
          <p>
            {initialVendorId !== null
              ? `Purchase and service orders for ${initialVendorName || "the selected vendor"}.`
              : categoryFilter === "OPEX"
                ? "Review service orders and their OPEX budgets."
                : categoryFilter === "CAPEX"
                  ? "Review purchase orders and their CAPEX budgets."
                  : "Manage purchase orders, service orders, vendors and budgets."}
          </p>
        </div>

        <div className="orders-heading-actions">
  <button
    type="button"
    className="orders-secondary-button"
    onClick={() => {
      setShowImport((current) => !current);
      resetImport();
      setError("");
      setSuccess("");
    }}
  >
    {showImport ? "Close Bulk Import" : "Bulk Import Excel"}
  </button>

  <button
    type="button"
    className="orders-primary-button"
    onClick={startCreate}
  >
    {showForm && editingOrderId === null ? "Close Form" : "+ Create Order"}
  </button>
</div>
      </div>

      {initialVendorId !== null && (
        <div className="orders-alert" role="status">
          Showing orders for{" "}
          <strong>{initialVendorName || `vendor ID ${initialVendorId}`}</strong>.
          The vendor filter is active.
        </div>
      )}

      {error && (
        <div className="orders-alert orders-alert-error" role="alert">
          {error}
        </div>
      )}

      {success && (
        <div className="orders-alert orders-alert-success" role="status">
          {success}
        </div>
      )}


      {showImport && (
  <div className="orders-import-panel">
    <div className="orders-import-heading">
      <div>
        <h2>Bulk Import Orders</h2>
        <p>
          Upload an Excel workbook to validate and import multiple
          purchase and service orders.
        </p>
      </div>
    </div>

    <div className="orders-import-upload">
      <label>
        Select Excel Workbook (.xlsx)
        <input
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          disabled={importLoading || importConfirming}
          onChange={(event) => {
            setImportFile(event.currentTarget.files?.[0] ?? null);
            setImportPreview(null);
            setError("");
            setSuccess("");
          }}
        />
      </label>

      {importFile && (
        <p className="orders-import-file">
          Selected file: <strong>{importFile.name}</strong>
        </p>
      )}

      <div className="orders-form-actions">
        <button
          type="button"
          className="orders-secondary-button"
          onClick={resetImport}
          disabled={importLoading || importConfirming}
        >
          Clear
        </button>

        <button
          type="button"
          className="orders-primary-button"
          onClick={() => void handleImportPreview()}
          disabled={!importFile || importLoading || importConfirming}
        >
          {importLoading ? "Validating..." : "Preview Excel"}
        </button>
      </div>
    </div>

    {importPreview && (
      <div className="orders-import-results">
        <h3>Import Preview</h3>

        <div className="orders-import-summary">
          <div>
            <span>Total Rows</span>
            <strong>{importPreview.total_rows}</strong>
          </div>

          <div>
            <span>Valid Rows</span>
            <strong>{importPreview.valid_rows}</strong>
          </div>

          <div>
            <span>Invalid Rows</span>
            <strong>{importPreview.invalid_rows}</strong>
          </div>
        </div>

        <div className="orders-table-wrapper">
          <table className="orders-table orders-import-table">
            <thead>
              <tr>
                <th>Excel Row</th>
                <th>Order No.</th>
                <th>Type</th>
                <th>Vendor Code</th>
                <th>Budget</th>
                <th>Order Date</th>
                <th>Amount</th>
                <th>Validation</th>
              </tr>
            </thead>

            <tbody>
              {importPreview.rows.map((row) => (
                <tr key={row.excel_row}>
                  <td>{row.excel_row}</td>
                  <td>{row.order_number}</td>
                  <td>{row.order_type}</td>
                  <td>{row.vendor_code}</td>
                  <td>{row.budget_name}</td>
                  <td>{row.order_date}</td>
                  <td>{money(row.amount)}</td>
                  <td>
                    <span
                      className={`orders-import-status ${
                        row.is_valid ? "valid" : "invalid"
                      }`}
                    >
                      {row.is_valid ? "Valid" : "Invalid"}
                    </span>

                    {row.errors.length > 0 && (
                      <ul className="orders-import-errors">
                        {row.errors.map((message, index) => (
                          <li key={index}>{message}</li>
                        ))}
                      </ul>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="orders-form-actions">
          <button
            type="button"
            className="orders-secondary-button"
            onClick={resetImport}
            disabled={importConfirming}
          >
            Clear Preview
          </button>

          <button
            type="button"
            className="orders-primary-button"
            onClick={() => void handleConfirmImport()}
            disabled={
              importPreview.valid_rows === 0 ||
              importPreview.invalid_rows > 0 ||
              importConfirming
            }
          >
            {importConfirming
              ? "Importing Orders..."
              : `Confirm Import (${importPreview.valid_rows})`}
          </button>
        </div>

        {importPreview.invalid_rows > 0 && (
          <p className="orders-import-warning">
            Correct the invalid rows in your Excel file and upload it again.
            Import is disabled until every row passes validation.
          </p>
        )}
      </div>
    )}
  </div>
)}

      <div className="orders-summary">
        <article className="orders-summary-card">
          <span>
            {categoryFilter === "ALL"
              ? initialVendorId !== null
                ? "Vendor Orders"
                : "Total Orders"
              : categoryFilter === "OPEX"
                ? "Service Orders"
                : "Purchase Orders"}
          </span>
          <strong>{filteredOrders.length}</strong>
        </article>

        <article className="orders-summary-card">
          <span>Visible Order Value</span>
          <strong>{money(visibleTotalAmount)}</strong>
        </article>

        <article className="orders-summary-card">
          <span>Purchase Orders</span>
          <strong>{visiblePurchaseOrderCount}</strong>
        </article>

        <article className="orders-summary-card">
          <span>Service Orders</span>
          <strong>{visibleServiceOrderCount}</strong>
        </article>
      </div>

      <div className="orders-list-card">
        <div className="orders-list-heading">
          <div>
            <h2>Order Register</h2>
            <p>Choose a category, then search within the matching orders.</p>
          </div>

          <div className="orders-register-controls">
            <div
              className="orders-category-filters"
              role="group"
              aria-label="Filter orders by budget category"
            >
              {(["ALL", "OPEX", "CAPEX"] as const).map((category) => (
                <button
                  key={category}
                  type="button"
                  className={`orders-category-filter ${categoryFilter === category ? "active" : ""}`}
                  aria-pressed={categoryFilter === category}
                  onClick={() => setCategoryFilter(category)}
                >
                  {category === "ALL" ? "All" : category}
                </button>
              ))}
            </div>

            <input
              className="orders-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search order, vendor, budget, status..."
              aria-label="Search orders"
            />
          </div>
        </div>

        {loading ? (
          <p className="orders-empty">Loading orders...</p>
        ) : (
          <div className="orders-table-wrapper">
            <table className="orders-table">
              <thead>
                <tr>
                  <th>Order No.</th>
                  <th>Type</th>
                  <th>Vendor</th>
                  <th>Budget</th>
                  <th>Order Date</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>

              <tbody>
                {filteredOrders.map((order) => {
                  const account =
                    vendorById.get(order.party_id) ??
                    (order.party_name
                      ? {
                          id: order.party_id,
                          name: order.party_name,
                          code: "",
                          party_type: "VENDOR" as const,
                          is_active: true,
                        }
                      : undefined);

                  const budget =
                    order.budget_id == null
                      ? undefined
                      : budgetById.get(order.budget_id);

                  const orderCopyUploaded = hasDocument(order, "order-copy");
                  const approvalUploaded = hasDocument(order, "approval");

                  return (
                    <tr key={order.id}>
                      <td>
                        <button
                          type="button"
                          className="orders-order-number-button"
                          onClick={() => onOpenOrder(order)}
                          title={`View invoices for ${order.order_number}`}
                        >
                          {order.order_number}
                        </button>
                      </td>

                      <td>
                        <span className="orders-type-badge">
                          {orderTypeLabel(order.order_type)}
                        </span>
                      </td>

                      <td>
                        {account ? (
                          <span title={account.code || account.name}>
                            {account.name}
                            {account.code && (
                              <small className="orders-party-code">
                                {account.code}
                              </small>
                            )}
                          </span>
                        ) : (
                          `Vendor ID ${order.party_id}`
                        )}
                      </td>

                      <td>
                        {budget?.name ??
                          order.budget_name ??
                          order.budget_id ??
                          "—"}
                      </td>

                      <td>{String(order.order_date).slice(0, 10)}</td>
                      <td>{money(order.amount)}</td>

                      <td>
                        <span className="orders-status-badge">
                          {order.status}
                        </span>
                      </td>

                      <td>
                        <div className="orders-row-actions">
                          <button
                            type="button"
                            className="orders-edit-button"
                            onClick={() => startEdit(order)}
                          >
                            Edit
                          </button>

                          <button
                            type="button"
                            className="orders-delete-button"
                            disabled={deletingId === order.id}
                            onClick={() => void handleDeleteOrder(order)}
                          >
                            {deletingId === order.id ? "Deleting..." : "Delete"}
                          </button>

                          <div className="orders-document-menu">
                            <button
                              type="button"
                              className="orders-document-trigger"
                              aria-expanded={openDocumentMenuId === order.id}
                              onClick={() =>
                                setOpenDocumentMenuId((current) =>
                                  current === order.id ? null : order.id,
                                )
                              }
                            >
                              Documents
                              <span className="orders-document-chevron">▾</span>
                            </button>

                            {openDocumentMenuId === order.id && (
                              <div className="orders-document-dropdown">
                                <div className="orders-document-item">
                                  <div className="orders-document-item-heading">
                                    <strong>Order Copy</strong>
                                    <span
                                      className={`orders-document-status ${orderCopyUploaded ? "uploaded" : "missing"}`}
                                    >
                                      {orderCopyUploaded
                                        ? "Uploaded"
                                        : "Not uploaded"}
                                    </span>
                                  </div>

                                  {orderCopyUploaded && (
                                    <button
                                      type="button"
                                      onClick={() =>
                                        void handleDocumentView(
                                          order.id,
                                          "order-copy",
                                        )
                                      }
                                      disabled={documentBusy !== null}
                                    >
                                      {documentBusy ===
                                      `${order.id}-order-copy`
                                        ? "Opening..."
                                        : "View Order Copy"}
                                    </button>
                                  )}

                                  <label className="orders-document-upload-option">
                                    {orderCopyUploaded
                                      ? "Replace Order Copy"
                                      : "Upload Order Copy"}
                                    <input
                                      type="file"
                                      accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                                      hidden
                                      disabled={documentBusy !== null}
                                      onChange={(event) => {
                                        const file =
                                          event.currentTarget.files?.[0];

                                        if (file) {
                                          void handleDocumentUpload(
                                            order.id,
                                            "order-copy",
                                            file,
                                          );
                                        }

                                        event.currentTarget.value = "";
                                      }}
                                    />
                                  </label>
                                </div>

                                <div className="orders-document-divider" />

                                <div className="orders-document-item">
                                  <div className="orders-document-item-heading">
                                    <strong>Approval Copy</strong>
                                    <span
                                      className={`orders-document-status ${approvalUploaded ? "uploaded" : "missing"}`}
                                    >
                                      {approvalUploaded
                                        ? "Uploaded"
                                        : "Not uploaded"}
                                    </span>
                                  </div>

                                  {approvalUploaded && (
                                    <button
                                      type="button"
                                      onClick={() =>
                                        void handleDocumentView(
                                          order.id,
                                          "approval",
                                        )
                                      }
                                      disabled={documentBusy !== null}
                                    >
                                      {documentBusy === `${order.id}-approval`
                                        ? "Opening..."
                                        : "View Approval Copy"}
                                    </button>
                                  )}

                                  <label className="orders-document-upload-option">
                                    {approvalUploaded
                                      ? "Replace Approval Copy"
                                      : "Upload Approval Copy"}
                                    <input
                                      type="file"
                                      accept=".pdf,.jpg,.jpeg,application/pdf,image/jpeg"
                                      hidden
                                      disabled={documentBusy !== null}
                                      onChange={(event) => {
                                        const file =
                                          event.currentTarget.files?.[0];

                                        if (file) {
                                          void handleDocumentUpload(
                                            order.id,
                                            "approval",
                                            file,
                                          );
                                        }

                                        event.currentTarget.value = "";
                                      }}
                                    />
                                  </label>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  );
                })}

                {filteredOrders.length === 0 && (
                  <tr>
                    <td colSpan={8} className="orders-empty">
                      {search ||
                      initialVendorId !== null ||
                      categoryFilter !== "ALL"
                        ? "No orders match the selected category, vendor and search."
                        : "No orders found. Create your first order."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showForm && (
        <form className="orders-form" onSubmit={handleSubmit}>
          <h2>{editingOrderId !== null ? "Edit Order" : "Create Order"}</h2>

          <div className="orders-form-grid">
            <label>
              Order Type *
              <select
                required
                value={form.order_type}
                onChange={(event) => {
                  const value = event.target.value as "PO" | "SO";

                  setForm((current) => ({
                    ...current,
                    order_type: value,
                    party_id: "",
                    budget_id: "",
                  }));

                  setShowVendorForm(false);
                  setVendorForm(emptyVendorForm);
                  setError("");
                  setSuccess("");
                }}
              >
                <option value="PO">Purchase Order (PO)</option>
                <option value="SO">Service Order (SO)</option>
              </select>
            </label>

            <label>
              Order Number *
              <input
                required
                maxLength={64}
                value={form.order_number}
                onChange={(event) =>
                  updateField("order_number", event.target.value)
                }
                placeholder="e.g. PO-2026-001"
              />
            </label>

            <label>
              Vendor *
              <select
                required
                value={form.party_id}
                onChange={(event) =>
                  updateField("party_id", event.target.value)
                }
                disabled={loadingOptions}
              >
                <option value="">
                  {loadingOptions ? "Loading vendors..." : "Select Vendor"}
                </option>

                {availableVendors.map((vendor) => (
                  <option key={vendor.id} value={vendor.id}>
                    {vendor.code} — {vendor.name}
                  </option>
                ))}
              </select>

              <button
                type="button"
                className="orders-secondary-button"
                onClick={() => {
                  setShowVendorForm((current) => !current);
                  setVendorForm(emptyVendorForm);
                  setError("");
                }}
                disabled={loadingOptions || saving || savingVendor}
              >
                {showVendorForm ? "Cancel Add Vendor" : "+ Add New Vendor"}
              </button>

              {!loadingOptions && availableVendors.length === 0 && (
                <small>
                  No active vendors found. Use Add New Vendor to create one.
                </small>
              )}
            </label>

            <label>
              {requiredBudgetType} Budget *
              <select
                required
                value={form.budget_id}
                onChange={(event) =>
                  updateField("budget_id", event.target.value)
                }
                disabled={loadingOptions}
              >
                <option value="">
                  {loadingOptions
                    ? "Loading budgets..."
                    : `Select ${requiredBudgetType} budget`}
                </option>

                {availableBudgets.map((budget) => (
                  <option key={budget.id} value={budget.id}>
                    {budget.name} · {budget.financial_year} · Approved{" "}
                    {money(budget.approved_amount)}
                  </option>
                ))}
              </select>

              {!loadingOptions && availableBudgets.length === 0 && (
                <small>
                  No {requiredBudgetType} budgets found for FY {FINANCIAL_YEAR}.
                  Create a matching budget first.
                </small>
              )}
            </label>

            <label>
              Financial Year
              <input value={FINANCIAL_YEAR} readOnly />
            </label>

            <label>
              Order Date *
              <input
                required
                type="date"
                value={form.order_date}
                onChange={(event) =>
                  updateField("order_date", event.target.value)
                }
              />
            </label>

            <label>
              Order Period
              <input
                maxLength={100}
                value={form.order_period}
                onChange={(event) =>
                  updateField("order_period", event.target.value)
                }
                placeholder="e.g. September–November 2026"
              />
            </label>

            <label>
              Location
              <select
                value={locationChoice}
                onChange={(event) => handleLocationChange(event.target.value)}
              >
                <option value="">Select location</option>
                {OFFICIAL_LOCATIONS.map((location) => (
                  <option key={location} value={location}>
                    {location}
                  </option>
                ))}
                <option value={OTHER_LOCATION}>Others</option>
              </select>
            </label>

            {locationChoice === OTHER_LOCATION && (
              <label>
                Enter Location *
                <input
                  required
                  maxLength={200}
                  value={isOfficialLocation(form.location) ? "" : form.location}
                  onChange={(event) =>
                    updateField("location", event.target.value)
                  }
                  placeholder="Type the location"
                />
                <small>
                  Enter the location manually. This value will be saved with the
                  order.
                </small>
              </label>
            )}

            <label>
              Order Amount (₹) *
              <input
                required
                type="number"
                min="0.01"
                step="0.01"
                value={form.amount}
                onChange={(event) => updateField("amount", event.target.value)}
                placeholder="0.00"
              />
            </label>

            <label>
              Description
              <textarea
                rows={3}
                maxLength={1000}
                value={form.description}
                onChange={(event) =>
                  updateField("description", event.target.value)
                }
                placeholder="Optional order details"
              />
            </label>
          </div>

          <div className="orders-document-upload-section">
            <div>
              <h3>Order Documents</h3>
              <p>
                Attach the order and approval documents now, or upload them
                later from the Order Register.
              </p>
            </div>

            <div className="orders-document-upload-grid">
              <label className="orders-form-document-field">
                <span>Order Copy</span>
                <small>PDF, JPG, JPEG or PNG · Maximum 10 MB</small>
                <input
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                  onChange={(event) => {
                    const file = event.currentTarget.files?.[0] ?? null;

                    if (file) {
                      const validationError = validateDocument(
                        file,
                        "order-copy",
                      );

                      if (validationError) {
                        setError(validationError);
                        event.currentTarget.value = "";
                        return;
                      }
                    }

                    setError("");
                    setOrderCopyFile(file);
                  }}
                  disabled={saving}
                />
                {orderCopyFile && (
                  <span className="orders-selected-document">
                    Selected: {orderCopyFile.name}
                    <button
                      type="button"
                      onClick={() => setOrderCopyFile(null)}
                      disabled={saving}
                    >
                      Remove
                    </button>
                  </span>
                )}
              </label>

              <label className="orders-form-document-field">
                <span>Approval Copy</span>
                <small>PDF, JPG or JPEG · Maximum 10 MB</small>
                <input
                  type="file"
                  accept=".pdf,.jpg,.jpeg,application/pdf,image/jpeg"
                  onChange={(event) => {
                    const file = event.currentTarget.files?.[0] ?? null;

                    if (file) {
                      const validationError = validateDocument(
                        file,
                        "approval",
                      );

                      if (validationError) {
                        setError(validationError);
                        event.currentTarget.value = "";
                        return;
                      }
                    }

                    setError("");
                    setApprovalFile(file);
                  }}
                  disabled={saving}
                />
                {approvalFile && (
                  <span className="orders-selected-document">
                    Selected: {approvalFile.name}
                    <button
                      type="button"
                      onClick={() => setApprovalFile(null)}
                      disabled={saving}
                    >
                      Remove
                    </button>
                  </span>
                )}
              </label>
            </div>
          </div>

          {showVendorForm && (
            <div className="orders-inline-vendor">
              <h3>Add New Vendor</h3>
              <p>
                The vendor will be created as a vendor and selected automatically
                for this order.
              </p>

              <div className="orders-form-grid">
                <label>
                  Vendor Code *
                  <input
                    required
                    maxLength={50}
                    value={vendorForm.code}
                    onChange={(event) =>
                      setVendorForm((current) => ({
                        ...current,
                        code: event.target.value.toUpperCase(),
                      }))
                    }
                    placeholder="e.g. VEN-001"
                  />
                </label>

                <label>
                  Vendor Name *
                  <input
                    required
                    maxLength={200}
                    value={vendorForm.name}
                    onChange={(event) =>
                      setVendorForm((current) => ({
                        ...current,
                        name: event.target.value,
                      }))
                    }
                    placeholder="Enter registered vendor name"
                  />
                </label>

                <label>
                  Email
                  <input
                    type="email"
                    maxLength={254}
                    value={vendorForm.email}
                    onChange={(event) =>
                      setVendorForm((current) => ({
                        ...current,
                        email: event.target.value,
                      }))
                    }
                    placeholder="vendor@example.com"
                  />
                </label>

                <label>
                  Phone
                  <input
                    maxLength={30}
                    value={vendorForm.phone}
                    onChange={(event) =>
                      setVendorForm((current) => ({
                        ...current,
                        phone: event.target.value,
                      }))
                    }
                    placeholder="Contact number"
                  />
                </label>

                <label className="orders-description-field">
                  Address
                  <textarea
                    rows={2}
                    maxLength={500}
                    value={vendorForm.address}
                    onChange={(event) =>
                      setVendorForm((current) => ({
                        ...current,
                        address: event.target.value,
                      }))
                    }
                    placeholder="Optional vendor address"
                  />
                </label>
              </div>

              <div className="orders-form-actions">
                <button
                  type="button"
                  className="orders-secondary-button"
                  onClick={() => {
                    setShowVendorForm(false);
                    setVendorForm(emptyVendorForm);
                  }}
                  disabled={savingVendor}
                >
                  Cancel
                </button>

                <button
                  type="button"
                  className="orders-primary-button"
                  onClick={() => void handleCreateVendor()}
                  disabled={savingVendor || saving || loadingOptions}
                >
                  {savingVendor ? "Creating..." : "Save Vendor"}
                </button>
              </div>
            </div>
          )}

          <div className="orders-form-actions">
            <button
              type="button"
              className="orders-secondary-button"
              onClick={resetForm}
              disabled={saving || savingVendor}
            >
              Cancel
            </button>

            <button
              type="submit"
              className="orders-primary-button"
              disabled={saving || savingVendor || loadingOptions}
            >
              {saving
                ? "Saving..."
                : editingOrderId !== null
                  ? "Update Order"
                  : "Save Order"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}