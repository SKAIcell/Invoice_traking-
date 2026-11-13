
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ChangeEvent,
} from "react";

type BudgetType = "OPEX" | "CAPEX";
type RequestStatus = "PENDING" | "APPROVED" | "REJECTED";
type RequestType = "CREATE" | "UPDATE";
type RequestMode = "CAPEX" | "OPEX";

type Budget = {
  id: number;
  name: string;
  financial_year: string;
  budget_type: BudgetType;
  planned_amount: string | number;
  approved_amount: string | number;
  has_approval_copy: boolean;
  created_at: string;
};

type BudgetApprovalRequest = {
  id: number;
  budget_id: number | null;
  request_type: RequestType;
  status: RequestStatus;
  name: string;
  financial_year: string;
  budget_type: BudgetType;
  planned_amount: string | number;
  approved_amount: string | number | null;
  has_approval_copy?: boolean;
  requested_by_id: number;
  decided_by_id: number | null;
  requested_at: string;
  decided_at: string | null;
  remarks: string | null;
};

type Subcategory = {
  id: number;
  budget_id: number;
  name: string;
  planned_amount: string | number;
  approved_amount: string | number;
  has_approval_copy: boolean;
  created_at: string;
};

type SubcategoryRequest = {
  id: number;
  budget_id: number;
  subcategory_id: number | null;
  request_type: RequestType;
  status: RequestStatus;
  name: string;
  planned_amount: string | number;
  approved_amount: string | number | null;
  has_approval_copy?: boolean;
  requested_by_id: number;
  decided_by_id: number | null;
  requested_at: string;
  decided_at: string | null;
  remarks: string | null;
};

const OPEX_CATEGORIES = [
  "AMC & IT CONSUMABLES",
  "APPLICATION SUBSCRIPTION SUPPORT",
  "INFRASTRUCTURE MANAGED SERVICES & CLOUD",
  "NETWORK CONNECTIVITY",
] as const;

const OPEX_SUBCATEGORIES: Record<string, string[]> = {
  "APPLICATION SUBSCRIPTION SUPPORT": [
    "Civil 3D 2026 Autodesk Software",
    "Creative Cloud Pro team, Illustrator, Photoshop, Studio (Adobe)",
    "Creative Cloud Pro for Branding department (Adobe)",
    "Shutterstock (50 image Downloads per mon)",
    "Autocad",
    "PLS software",
    "Light House",
    "Solidworks Professional Service",
    "Infobip India",
    "Prowess Selling (KloudQ)",
    "Arokia IT",
    "Almond AI (Loyalty Application)",
    "Network Security(PWC/ISOAH Security Services) & Audit",
    "Activ Track",
    "Emsphere Enterprise CLMS 5.0 including mobile application",
    "Tekla Design Software",
    "Sasco license + AMC",
    "Zoom License(Loudon & Tirumala)",
    "Fortiget- ZTNA+ Forti Manager",
    "Patch Management",
  ],
  "INFRASTRUCTURE MANAGED SERVICES & CLOUD": [
    "Microsoft O365",
    "Azure Landscape",
    "NTT Global Data Centers and Cloud",
    "NTT COMMUNICATIONS INDIA NETWORK",
    "AWS Server hosting & maintenance",
    "SERVICEFORCE.COM INDIA PRIVATE LTD",
    "SGN SOFTWARE PVT LTD",
    "PriceWaterhouseCoopers Private-ECC AMS",
    "ITSM & ITAM Tool",
    "SAP INDIA",
    "Firewall Support & subscription license",
    "Managed Network support",
    "Vishnu Solution-Call center",
    "Google Server hosting & maintenance",
    "SAP S4 Hana consultant support",
    "Kaspersky EDR",
    "User Backup solution",
    "Server Backup",
    "MDM",
    "Newsletter Service",
  ],
  "AMC & IT CONSUMABLES": [
    "IT Equipments AMC(DT, LT & Residential Engineer)",
    "IT Equipments AMC Server & NAS Drive",
    "IT Equipments AMC cctv",
    "IT Equipments AMC epabx+License procurement",
    "UPS AMC - North, East, South & West",
    "Printer AMC",
    "Door lock & access control including server room camera",
    "AMC-Access Point",
    "UPS AMC - North East",
    "Biomatrics & Access control rental",
    "Emsphere Enterprise-AMC of 50 devices",
    "Printer(Shaprp) rental",
    "Printer- Sharp-TG",
    "Printer(Canon) rental",
    "Printer-Canon-TG",
    "IT Consumables",
  ],
  "NETWORK CONNECTIVITY": [
    "Meghbala Cable",
    "Vodafone",
    "Tata Teleservices",
    "Bharti Airtel",
    "Reliance Jio",
    "Elyzium",
    "BSNL",
    "GTPL",
  ],
};

const MAX_APPROVAL_COPY_SIZE = 10 * 1024 * 1024;

const ALLOWED_APPROVAL_COPY_EXTENSIONS = [
  ".pdf",
  ".jpg",
  ".jpeg",
  ".png",
];

function getCurrentFinancialYear() {
  const now = new Date();
  const year = now.getFullYear();
  const startYear = now.getMonth() >= 3 ? year : year - 1;
  return `${startYear}-${startYear + 1}`;
}

function amount(value: string | number | null | undefined) {
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

function formatDate(value: string | null | undefined) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function isOpexCategory(name: string) {
  return OPEX_CATEGORIES.includes(
    name as (typeof OPEX_CATEGORIES)[number]
  );
}

function validateFinancialYear(year: string) {
  if (!/^\d{4}-\d{4}$/.test(year)) {
    return "Enter a valid financial year, for example 2026-2027.";
  }

  const [start, end] = year.split("-").map(Number);

  if (end !== start + 1) {
    return "Financial year must be consecutive, for example 2026-2027.";
  }

  return "";
}

function validateApprovalCopy(file: File): string {
  const extension = file.name
    .substring(file.name.lastIndexOf("."))
    .toLowerCase();

  if (!ALLOWED_APPROVAL_COPY_EXTENSIONS.includes(extension)) {
    return "Only PDF, JPG, JPEG and PNG files are allowed.";
  }

  if (file.size === 0) {
    return "The selected approval copy is empty.";
  }

  if (file.size > MAX_APPROVAL_COPY_SIZE) {
    return "Budget approval copy cannot exceed 10 MB.";
  }

  return "";
}

export default function BudgetsPage() {
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [requests, setRequests] = useState<BudgetApprovalRequest[]>([]);
  const [subcategoryRequests, setSubcategoryRequests] =
    useState<SubcategoryRequest[]>([]);
  const [pendingRequests, setPendingRequests] =
    useState<BudgetApprovalRequest[]>([]);
  const [pendingSubcategoryRequests, setPendingSubcategoryRequests] =
    useState<SubcategoryRequest[]>([]);

  const [selectedCategory, setSelectedCategory] = useState<Budget | null>(null);
  const [subcategories, setSubcategories] = useState<Subcategory[]>([]);
  const [subcategoryLoading, setSubcategoryLoading] = useState(false);

  // Main budget request form
  const [requestMode, setRequestMode] = useState<RequestMode>("CAPEX");
  const [requestYear, setRequestYear] = useState(getCurrentFinancialYear());
  const [capexAmount, setCapexAmount] = useState("");
  const [capexApprovalCopy, setCapexApprovalCopy] =
    useState<File | null>(null);

  // OPEX request form
  const [opexCategoryId, setOpexCategoryId] = useState("");
  const [selectedSubcategory, setSelectedSubcategory] = useState("");
  const [subcategoryAmount, setSubcategoryAmount] = useState("");
  const [customSubcategory, setCustomSubcategory] = useState("");
  const [opexApprovalCopy, setOpexApprovalCopy] =
    useState<File | null>(null);

  // OPEX detail page request form
  const [detailSubcategory, setDetailSubcategory] = useState("");
  const [detailAmount, setDetailAmount] = useState("");
  const [detailCustomSubcategory, setDetailCustomSubcategory] = useState("");
  const [detailApprovalCopy, setDetailApprovalCopy] =
    useState<File | null>(null);

  // Existing subcategory edit state
  const [editingSubcategoryId, setEditingSubcategoryId] =
    useState<number | null>(null);

  const [search, setSearch] = useState("");
  const [yearFilter, setYearFilter] = useState(getCurrentFinancialYear());
  const [typeFilter, setTypeFilter] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const role = sessionStorage.getItem("role")?.toUpperCase() ?? "";
  const isITHead = role === "IT_HEAD";
  const token = sessionStorage.getItem("access_token");

  const authHeaders = useMemo((): Record<string, string> => {
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [token]);

  const loadBudgets = useCallback(async () => {
    const response = await fetch("/api/budgets", {
      headers: authHeaders,
    });

    const data = await response.json().catch(() => null);

    if (!response.ok) {
      throw new Error(getErrorMessage(data, "Unable to load budgets."));
    }

    if (!Array.isArray(data)) {
      throw new Error("Unexpected response received from the budget API.");
    }

    setBudgets(data);
  }, [authHeaders]);

  const loadMyRequests = useCallback(async () => {
    if (isITHead) {
      setRequests([]);
      setSubcategoryRequests([]);
      return;
    }

    const [generalResponse, subcategoryResponse] = await Promise.all([
      fetch("/api/budgets/approval-requests/mine", {
        headers: authHeaders,
      }),
      fetch("/api/budgets/subcategory-approval-requests/mine", {
        headers: authHeaders,
      }),
    ]);

    const [generalData, subcategoryData] = await Promise.all([
      generalResponse.json().catch(() => null),
      subcategoryResponse.json().catch(() => null),
    ]);

    if (!generalResponse.ok) {
      throw new Error(
        getErrorMessage(generalData, "Unable to load your budget requests.")
      );
    }

    if (!subcategoryResponse.ok) {
      throw new Error(
        getErrorMessage(
          subcategoryData,
          "Unable to load your OPEX allocation requests."
        )
      );
    }

    setRequests(Array.isArray(generalData) ? generalData : []);
    setSubcategoryRequests(
      Array.isArray(subcategoryData) ? subcategoryData : []
    );
  }, [authHeaders, isITHead]);

  const loadPendingRequests = useCallback(async () => {
    if (!isITHead) {
      setPendingRequests([]);
      setPendingSubcategoryRequests([]);
      return;
    }

    const [generalResponse, subcategoryResponse] = await Promise.all([
      fetch("/api/budgets/approval-requests/pending", {
        headers: authHeaders,
      }),
      fetch("/api/budgets/subcategory-approval-requests/pending", {
        headers: authHeaders,
      }),
    ]);

    const [generalData, subcategoryData] = await Promise.all([
      generalResponse.json().catch(() => null),
      subcategoryResponse.json().catch(() => null),
    ]);

    if (!generalResponse.ok) {
      throw new Error(
        getErrorMessage(generalData, "Unable to load pending CAPEX requests.")
      );
    }

    if (!subcategoryResponse.ok) {
      throw new Error(
        getErrorMessage(
          subcategoryData,
          "Unable to load pending OPEX allocation requests."
        )
      );
    }

    setPendingRequests(Array.isArray(generalData) ? generalData : []);
    setPendingSubcategoryRequests(
      Array.isArray(subcategoryData) ? subcategoryData : []
    );
  }, [authHeaders, isITHead]);

  const loadPageData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      await Promise.all([
        loadBudgets(),
        loadMyRequests(),
        loadPendingRequests(),
      ]);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load budget data."
      );
    } finally {
      setLoading(false);
    }
  }, [loadBudgets, loadMyRequests, loadPendingRequests]);

  useEffect(() => {
    void loadPageData();
  }, [loadPageData]);

  const financialYears = useMemo(
    () =>
      [
        ...new Set([
          ...budgets.map((budget) => budget.financial_year),
          ...requests.map((request) => request.financial_year),
          ...pendingRequests.map((request) => request.financial_year),
        ]),
      ]
        .filter(Boolean)
        .sort((a, b) => b.localeCompare(a)),
    [budgets, requests, pendingRequests]
  );

  const filteredBudgets = useMemo(() => {
    const term = search.trim().toLowerCase();

    return budgets.filter((budget) => {
      const matchesSearch =
        budget.name.toLowerCase().includes(term) ||
        budget.financial_year.toLowerCase().includes(term);

      const matchesYear =
        !yearFilter || budget.financial_year === yearFilter;

      const matchesType =
        !typeFilter || budget.budget_type === typeFilter;

      return matchesSearch && matchesYear && matchesType;
    });
  }, [budgets, search, yearFilter, typeFilter]);

  const approvedBudgets = useMemo(
    () =>
      filteredBudgets.filter(
        (budget) =>
          Number(budget.approved_amount) > 0 ||
          (budget.budget_type === "OPEX" && isOpexCategory(budget.name))
      ),
    [filteredBudgets]
  );

  const opexParentOptions = useMemo(
    () =>
      budgets.filter(
        (budget) =>
          budget.budget_type === "OPEX" &&
          isOpexCategory(budget.name) &&
          budget.financial_year === requestYear
      ),
    [budgets, requestYear]
  );

  const waitingGeneral = useMemo(
    () =>
      isITHead
        ? pendingRequests
        : requests.filter((request) => request.status === "PENDING"),
    [isITHead, pendingRequests, requests]
  );

  const waitingSubcategory = useMemo(
    () =>
      isITHead
        ? pendingSubcategoryRequests
        : subcategoryRequests.filter(
            (request) => request.status === "PENDING"
          ),
    [isITHead, pendingSubcategoryRequests, subcategoryRequests]
  );

  const totalWaiting = waitingGeneral.length + waitingSubcategory.length;

  function handleApprovalCopyChange(
    event: ChangeEvent<HTMLInputElement>,
    setter: (file: File | null) => void
  ) {
    const input = event.currentTarget;
    const file = input.files?.[0] ?? null;

    if (!file) {
      setter(null);
      return;
    }

    const validationError = validateApprovalCopy(file);

    if (validationError) {
      setter(null);
      setError(validationError);
      input.value = "";
      return;
    }

    setError("");
    setter(file);
  }

  function handleCapexApprovalCopyChange(
    event: ChangeEvent<HTMLInputElement>
  ) {
    handleApprovalCopyChange(event, setCapexApprovalCopy);
  }

  function handleOpexApprovalCopyChange(
    event: ChangeEvent<HTMLInputElement>
  ) {
    handleApprovalCopyChange(event, setOpexApprovalCopy);
  }

  function handleDetailApprovalCopyChange(
    event: ChangeEvent<HTMLInputElement>
  ) {
    handleApprovalCopyChange(event, setDetailApprovalCopy);
  }

  async function openApprovalCopy(
    url: string,
    fallbackMessage: string
  ) {
    const newTab = window.open("about:blank", "_blank");

    if (!newTab) {
      setError(
        "Your browser blocked the approval-copy window. Please allow pop-ups and try again."
      );
      return;
    }

    setError("");

    try {
      const response = await fetch(url, {
        headers: authHeaders,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);

        throw new Error(
          getErrorMessage(data, fallbackMessage)
        );
      }

      const fileBlob = await response.blob();
      const fileUrl = URL.createObjectURL(fileBlob);

      newTab.location.href = fileUrl;

      window.setTimeout(() => {
        URL.revokeObjectURL(fileUrl);
      }, 60000);
    } catch (err) {
      newTab.close();

      setError(
        err instanceof Error ? err.message : fallbackMessage
      );
    }
  }

  async function viewBudgetApprovalCopy(budgetId: number) {
    await openApprovalCopy(
      `/api/budgets/${budgetId}/approval-copy`,
      "Unable to open the budget approval copy."
    );
  }

  async function viewSubcategoryApprovalCopy(subcategoryId: number) {
    await openApprovalCopy(
      `/api/budgets/subcategories/${subcategoryId}/approval-copy`,
      "Unable to open the OPEX approval copy."
    );
  }

  async function openOpexCategory(budget: Budget) {
    setSelectedCategory(budget);
    setSubcategories([]);
    setDetailSubcategory("");
    setDetailCustomSubcategory("");
    setDetailAmount("");
    setDetailApprovalCopy(null);
    setEditingSubcategoryId(null);
    setError("");
    setSuccess("");
    setSubcategoryLoading(true);

    try {
      const response = await fetch(
        `/api/budgets/${budget.id}/subcategories`,
        { headers: authHeaders }
      );

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data, "Unable to load OPEX subcategories.")
        );
      }

      setSubcategories(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load OPEX subcategories."
      );
    } finally {
      setSubcategoryLoading(false);
    }
  }

  function closeOpexCategory() {
    setSelectedCategory(null);
    setSubcategories([]);
    setDetailSubcategory("");
    setDetailCustomSubcategory("");
    setDetailAmount("");
    setDetailApprovalCopy(null);
    setEditingSubcategoryId(null);
    setError("");
    setSuccess("");
  }

  function startEditingSubcategory(subcategory: Subcategory) {
    setEditingSubcategoryId(subcategory.id);
    setDetailSubcategory("");
    setDetailCustomSubcategory("");
    setDetailAmount(String(subcategory.planned_amount));
    setDetailApprovalCopy(null);
    setError("");
    setSuccess("");

    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  }

  function cancelEditingSubcategory() {
    setEditingSubcategoryId(null);
    setDetailSubcategory("");
    setDetailCustomSubcategory("");
    setDetailAmount("");
    setDetailApprovalCopy(null);
    setError("");
    setSuccess("");
  }

  async function submitOpexRequest(
    event: FormEvent<HTMLFormElement>,
    parentBudget: Budget,
    subcategoryValue: string,
    customValue: string,
    plannedValue: string,
    approvalCopy: File | null,
    resetForm: () => void
  ) {
    event.preventDefault();

    const finalName =
      subcategoryValue === "__OTHER__"
        ? customValue.trim()
        : subcategoryValue.trim();

    if (!finalName) {
      setError("Select a subcategory or enter a custom subcategory.");
      return;
    }

    const planned = Number(plannedValue);

    if (!Number.isFinite(planned) || planned <= 0) {
      setError("Planned amount must be greater than zero.");
      return;
    }

    if (approvalCopy) {
      const validationError = validateApprovalCopy(approvalCopy);

      if (validationError) {
        setError(validationError);
        return;
      }
    }

    setSaving(true);
    setError("");
    setSuccess("");

    try {
      const formData = new FormData();

      formData.append("name", finalName);
      formData.append("planned_amount", planned.toFixed(2));

      if (approvalCopy) {
        formData.append("approval_copy", approvalCopy);
      }

      const response = await fetch(
        `/api/budgets/${parentBudget.id}/subcategories/requests`,
        {
          method: "POST",
          headers: {
            ...authHeaders,
          },
          body: formData,
        }
      );

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data, "Unable to submit OPEX allocation request.")
        );
      }

      resetForm();

      setSuccess(
        `OPEX allocation "${finalName}" submitted. IT Head will approve or reject it by email.`
      );

      await loadPageData();

      if (selectedCategory?.id === parentBudget.id) {
        await openOpexCategory(parentBudget);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to submit OPEX allocation request."
      );
    } finally {
      setSaving(false);
    }
  }

  async function submitSubcategoryUpdate(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    if (!selectedCategory || editingSubcategoryId === null) {
      setError("Select an allocation to update.");
      return;
    }

    const planned = Number(detailAmount);

    if (!Number.isFinite(planned) || planned <= 0) {
      setError("Planned amount must be greater than zero.");
      return;
    }

    const originalSubcategory = subcategories.find(
      (subcategory) => subcategory.id === editingSubcategoryId
    );

    if (!originalSubcategory) {
      setError("The selected subcategory allocation could not be found.");
      return;
    }

    if (planned === Number(originalSubcategory.planned_amount)) {
      setError("Enter a different planned amount to submit an update.");
      return;
    }

    setSaving(true);
    setError("");
    setSuccess("");

    try {
      const response = await fetch(
        `/api/budgets/subcategories/${editingSubcategoryId}/requests`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            ...authHeaders,
          },
          body: JSON.stringify({
            planned_amount: planned.toFixed(2),
          }),
        }
      );

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(
            data,
            "Unable to submit subcategory allocation update."
          )
        );
      }

      const editedName = originalSubcategory.name;

      setEditingSubcategoryId(null);
      setDetailAmount("");
      setDetailSubcategory("");
      setDetailCustomSubcategory("");
      setDetailApprovalCopy(null);

      setSuccess(
        `Allocation update for "${editedName}" submitted. IT Head will approve or reject it by email.`
      );

      await loadPageData();
      await openOpexCategory(selectedCategory);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to submit subcategory allocation update."
      );
    } finally {
      setSaving(false);
    }
  }

  async function submitCapexRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const yearError = validateFinancialYear(requestYear);

    if (yearError) {
      setError(yearError);
      return;
    }

    const plannedAmount = Number(capexAmount);

    if (!Number.isFinite(plannedAmount) || plannedAmount <= 0) {
      setError("Planned CAPEX amount must be greater than zero.");
      return;
    }

    if (capexApprovalCopy) {
      const validationError = validateApprovalCopy(capexApprovalCopy);

      if (validationError) {
        setError(validationError);
        return;
      }
    }

    setSaving(true);
    setError("");
    setSuccess("");

    try {
      const formData = new FormData();

      formData.append("name", "CAPEX");
      formData.append("financial_year", requestYear);
      formData.append("budget_type", "CAPEX");
      formData.append("planned_amount", plannedAmount.toFixed(2));

      if (capexApprovalCopy) {
        formData.append("approval_copy", capexApprovalCopy);
      }

      const response = await fetch("/api/budgets", {
        method: "POST",
        headers: authHeaders,
        body: formData,
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(data, "Unable to submit CAPEX request.")
        );
      }

      setCapexAmount("");
      setCapexApprovalCopy(null);

      setSuccess(
        "CAPEX request submitted. IT Head will approve or reject it by email."
      );

      await loadPageData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to submit CAPEX request."
      );
    } finally {
      setSaving(false);
    }
  }

  function renderWaitingTable() {
    if (totalWaiting === 0) {
      return (
        <div className="budgets-empty">
          <strong>No requests waiting for approval</strong>
          <p>New CAPEX and OPEX allocation requests will appear here.</p>
        </div>
      );
    }

    return (
      <div className="budgets-table-wrapper">
        <table className="budgets-table">
          <thead>
            <tr>
              <th>Request</th>
              <th>Budget category</th>
              <th>Subcategory / Request details</th>
              <th>Financial year</th>
              <th>Type</th>
              <th>Planned amount</th>
              <th>Submitted</th>
              <th>Status</th>
            </tr>
          </thead>

          <tbody>
            {waitingGeneral.map((request) => (
              <tr key={`general-${request.id}`}>
                <td>
                  <strong>#{request.id}</strong>
                  <small className="budgets-table-subtitle">
                    CAPEX budget request
                  </small>
                </td>
                <td>{request.name}</td>
                <td>
                  {request.request_type === "CREATE"
                    ? "New CAPEX budget"
                    : "CAPEX budget update"}
                </td>
                <td>{request.financial_year}</td>
                <td>
                  <span className="budgets-type-badge budgets-type-capex">
                    CAPEX
                  </span>
                </td>
                <td className="budgets-money-cell">
                  {amount(request.planned_amount)}
                </td>
                <td>{formatDate(request.requested_at)}</td>
                <td>
                  <span className="budgets-status-badge budgets-status-pending">
                    Pending
                  </span>
                </td>
              </tr>
            ))}

            {waitingSubcategory.map((request) => {
              const parent = budgets.find(
                (budget) => budget.id === request.budget_id
              );

              return (
                <tr key={`subcategory-${request.id}`}>
                  <td>
                    <strong>#{request.id}</strong>
                    <small className="budgets-table-subtitle">
                      OPEX allocation request
                    </small>
                  </td>
                  <td>{parent?.name ?? "OPEX"}</td>
                  <td>
                    <strong>{request.name}</strong>
                    <small className="budgets-table-subtitle">
                      {request.request_type === "CREATE"
                        ? "New subcategory allocation"
                        : "Subcategory allocation update"}
                    </small>
                  </td>
                  <td>{parent?.financial_year ?? "—"}</td>
                  <td>
                    <span className="budgets-type-badge budgets-type-opex">
                      OPEX
                    </span>
                  </td>
                  <td className="budgets-money-cell">
                    {amount(request.planned_amount)}
                  </td>
                  <td>{formatDate(request.requested_at)}</td>
                  <td>
                    <span className="budgets-status-badge budgets-status-pending">
                      Pending
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  if (selectedCategory) {
    const availableSubcategories =
      OPEX_SUBCATEGORIES[selectedCategory.name] ?? [];

    const editingSubcategory = subcategories.find(
      (subcategory) => subcategory.id === editingSubcategoryId
    );

    const editingHasPendingRequest =
      editingSubcategoryId !== null &&
      waitingSubcategory.some(
        (request) =>
          request.budget_id === selectedCategory.id &&
          request.subcategory_id === editingSubcategoryId
      );

    return (
      <main className="budgets-page">
        <header className="budgets-heading">
          <div>
            <p className="budgets-eyebrow">OPEX BUDGET MANAGEMENT</p>
            <h1>{selectedCategory.name}</h1>
            <p className="budgets-subtitle">
              {selectedCategory.financial_year} · Subcategory allocations
            </p>
          </div>

          <button
            type="button"
            className="budgets-secondary-button"
            onClick={closeOpexCategory}
          >
            ← Back to Budget Register
          </button>
        </header>

        {error && (
          <div className="budgets-alert budgets-alert-error" role="alert">
            {error}
          </div>
        )}

        {success && (
          <div className="budgets-alert budgets-alert-success" role="status">
            {success}
          </div>
        )}

        {!isITHead && (
          <section className="budgets-form-card">
            <div className="budgets-section-heading">
              <div>
                <h2>
                  {editingSubcategory
                    ? `Edit allocation: ${editingSubcategory.name}`
                    : "Request subcategory allocation"}
                </h2>
                <p>
                  {editingSubcategory
                    ? "Submit a revised planned amount. The allocation will change only after IT Head approval."
                    : "Select a predefined subcategory or enter a custom one. IT Head approval is required by email."}
                </p>
              </div>
            </div>

            {editingSubcategory ? (
              <form
                className="budgets-form"
                onSubmit={submitSubcategoryUpdate}
              >
                <div className="budgets-form-grid">
                  <label>
                    Subcategory
                    <input
                      value={editingSubcategory.name}
                      readOnly
                    />
                  </label>

                  <label>
                    Current planned amount (₹)
                    <input
                      value={amount(editingSubcategory.planned_amount)}
                      readOnly
                    />
                  </label>

                  <label>
                    New planned amount (₹) <span>*</span>
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={detailAmount}
                      onChange={(event) =>
                        setDetailAmount(event.target.value)
                      }
                      placeholder="Enter revised planned amount"
                      required
                    />
                  </label>
                </div>

                {editingHasPendingRequest && (
                  <div
                    className="budgets-alert budgets-alert-error"
                    role="alert"
                  >
                    There is already a pending approval request for this
                    allocation. Please wait for IT Head's decision before
                    submitting another update.
                  </div>
                )}

                <div className="budgets-form-actions">
                  <button
                    type="submit"
                    className="budgets-primary-button"
                    disabled={saving || editingHasPendingRequest}
                  >
                    {saving
                      ? "Submitting..."
                      : "Submit update for approval"}
                  </button>

                  <button
                    type="button"
                    className="budgets-secondary-button"
                    onClick={cancelEditingSubcategory}
                    disabled={saving}
                  >
                    Cancel edit
                  </button>
                </div>
              </form>
            ) : (
              <form
                className="budgets-form"
                onSubmit={(event) =>
                  void submitOpexRequest(
                    event,
                    selectedCategory,
                    detailSubcategory,
                    detailCustomSubcategory,
                    detailAmount,
                    detailApprovalCopy,
                    () => {
                      setDetailSubcategory("");
                      setDetailCustomSubcategory("");
                      setDetailAmount("");
                      setDetailApprovalCopy(null);
                    }
                  )
                }
              >
                <div className="budgets-form-grid">
                  <label>
                    Subcategory <span>*</span>
                    <select
                      value={detailSubcategory}
                      onChange={(event) =>
                        setDetailSubcategory(event.target.value)
                      }
                      required
                    >
                      <option value="">Select subcategory</option>
                      {availableSubcategories.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                      <option value="__OTHER__">
                        Other — enter custom subcategory
                      </option>
                    </select>
                  </label>

                  {detailSubcategory === "__OTHER__" && (
                    <label>
                      Custom subcategory name <span>*</span>
                      <input
                        value={detailCustomSubcategory}
                        onChange={(event) =>
                          setDetailCustomSubcategory(event.target.value)
                        }
                        maxLength={200}
                        placeholder="Enter subcategory name"
                        required
                      />
                    </label>
                  )}

                  <label>
                    Planned amount (₹) <span>*</span>
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={detailAmount}
                      onChange={(event) => setDetailAmount(event.target.value)}
                      placeholder="Enter planned amount"
                      required
                    />
                  </label>

                  <label>
                    Budget approval copy
                    <input
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                      onChange={handleDetailApprovalCopyChange}
                      disabled={saving}
                    />
                    <small className="budgets-table-subtitle">
                      Optional · PDF, JPG, JPEG or PNG · Maximum 10 MB
                    </small>

                    {detailApprovalCopy && (
                      <div className="budgets-form-actions">
                        <small>Selected: {detailApprovalCopy.name}</small>
                        <button
                          type="button"
                          className="budgets-secondary-button"
                          onClick={() => setDetailApprovalCopy(null)}
                          disabled={saving}
                        >
                          Remove file
                        </button>
                      </div>
                    )}
                  </label>
                </div>

                <div className="budgets-form-actions">
                  <button
                    type="submit"
                    className="budgets-primary-button"
                    disabled={saving}
                  >
                    {saving
                      ? "Submitting..."
                      : "Submit allocation for approval"}
                  </button>
                </div>
              </form>
            )}
          </section>
        )}

        <section className="budgets-list-card">
          <div className="budgets-section-heading">
            <div>
              <h2>Approved subcategory allocations</h2>
              <p>
                Parent approved total:{" "}
                {amount(selectedCategory.approved_amount)}
              </p>
            </div>
          </div>

          {subcategoryLoading ? (
            <div className="budgets-empty">Loading subcategories...</div>
          ) : subcategories.length === 0 ? (
            <div className="budgets-empty">
              <strong>No approved subcategory allocations yet</strong>
              <p>Approved subcategory allocations will appear here.</p>
            </div>
          ) : (
            <div className="budgets-table-wrapper">
              <table className="budgets-table">
                <thead>
                  <tr>
                    <th>Subcategory</th>
                    <th>Planned amount</th>
                    <th>Approved amount</th>
                    <th>Balance</th>
                    <th>Approval copy</th>
                    {!isITHead && <th>Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {subcategories.map((subcategory) => {
                    const hasPendingRequest = waitingSubcategory.some(
                      (request) =>
                        request.budget_id === selectedCategory.id &&
                        request.subcategory_id === subcategory.id
                    );

                    return (
                      <tr key={subcategory.id}>
                        <td>
                          <strong>{subcategory.name}</strong>
                          <small className="budgets-table-subtitle">
                            Allocation #{subcategory.id}
                          </small>
                        </td>
                        <td className="budgets-money-cell">
                          {amount(subcategory.planned_amount)}
                        </td>
                        <td className="budgets-money-cell">
                          {amount(subcategory.approved_amount)}
                        </td>
                        <td className="budgets-money-cell">
                          {amount(
                            Number(subcategory.planned_amount) -
                              Number(subcategory.approved_amount)
                          )}
                        </td>
                        <td>
                          {subcategory.has_approval_copy ? (
                            <button
                              type="button"
                              className="budgets-category-link"
                              onClick={() =>
                                void viewSubcategoryApprovalCopy(
                                  subcategory.id
                                )
                              }
                              title="View OPEX approval copy"
                            >
                              View Approval Copy ↗
                            </button>
                          ) : (
                            <span>—</span>
                          )}
                        </td>

                        {!isITHead && (
                          <td>
                            <button
                              type="button"
                              className="budgets-secondary-button"
                              onClick={() =>
                                startEditingSubcategory(subcategory)
                              }
                              disabled={saving || hasPendingRequest}
                              title={
                                hasPendingRequest
                                  ? "An update request is already pending"
                                  : "Edit planned allocation"
                              }
                            >
                              {hasPendingRequest
                                ? "Pending approval"
                                : "Edit"}
                            </button>
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="budgets-list-card">
          <div className="budgets-section-heading">
            <div>
              <h2>Waiting for approval</h2>
              <p>Pending requests for this OPEX category</p>
            </div>
          </div>

          {waitingSubcategory.filter(
            (request) => request.budget_id === selectedCategory.id
          ).length === 0 ? (
            <div className="budgets-empty">
              No pending subcategory requests for this category.
            </div>
          ) : (
            <div className="budgets-table-wrapper">
              <table className="budgets-table">
                <thead>
                  <tr>
                    <th>Request</th>
                    <th>Subcategory</th>
                    <th>Request type</th>
                    <th>Planned amount</th>
                    <th>Submitted</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {waitingSubcategory
                    .filter(
                      (request) => request.budget_id === selectedCategory.id
                    )
                    .map((request) => (
                      <tr key={request.id}>
                        <td>#{request.id}</td>
                        <td>{request.name}</td>
                        <td>
                          {request.request_type === "UPDATE"
                            ? "Allocation update"
                            : "New allocation"}
                        </td>
                        <td className="budgets-money-cell">
                          {amount(request.planned_amount)}
                        </td>
                        <td>{formatDate(request.requested_at)}</td>
                        <td>
                          <span className="budgets-status-badge budgets-status-pending">
                            Pending
                          </span>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    );
  }

  return (
    <main className="budgets-page">
      <header className="budgets-heading">
        <div>
          <p className="budgets-eyebrow">FINANCIAL MANAGEMENT</p>
          <h1>Budget Register</h1>
          <p className="budgets-subtitle">
            Manage approved budgets and track budget allocation requests.
          </p>
        </div>

        <button
          className="budgets-refresh-button"
          type="button"
          onClick={() => void loadPageData()}
          disabled={loading}
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </header>

      {error && (
        <div className="budgets-alert budgets-alert-error" role="alert">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError("")}
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}

      {success && (
        <div className="budgets-alert budgets-alert-success" role="status">
          <span>{success}</span>
          <button
            type="button"
            onClick={() => setSuccess("")}
            aria-label="Dismiss message"
          >
            ×
          </button>
        </div>
      )}

      <section className="budgets-summary" aria-label="Budget summary">
        <article className="budgets-summary-card">
          <span>Approved budget categories</span>
          <strong>{approvedBudgets.length}</strong>
          <small>Matching register filters</small>
        </article>

        <article className="budgets-summary-card">
          <span>Pending requests</span>
          <strong>{totalWaiting}</strong>
          <small>CAPEX and OPEX allocation requests</small>
        </article>

        <article className="budgets-summary-card">
          <span>Approved CAPEX</span>
          <strong>
            {amount(
              approvedBudgets
                .filter((budget) => budget.budget_type === "CAPEX")
                .reduce(
                  (sum, budget) => sum + Number(budget.approved_amount),
                  0
                )
            )}
          </strong>
          <small>Approved capital expenditure</small>
        </article>

        <article className="budgets-summary-card">
          <span>Approved OPEX</span>
          <strong>
            {amount(
              approvedBudgets
                .filter((budget) => budget.budget_type === "OPEX")
                .reduce(
                  (sum, budget) => sum + Number(budget.approved_amount),
                  0
                )
            )}
          </strong>
          <small>Approved operating expenditure</small>
        </article>
      </section>

      {/* CAPEX / OPEX request selector and form */}
      {!isITHead && (
        <section className="budgets-form-card">
          <div className="budgets-section-heading">
            <div>
              <h2>Submit Budget Request</h2>
              <p>
                Submit a CAPEX budget request or request an allocation under an
                existing OPEX category.
              </p>
            </div>
          </div>

          <div className="budgets-filters">
            <label>
              Request type
              <select
                value={requestMode}
                onChange={(event) => {
                  setRequestMode(event.target.value as RequestMode);
                  setError("");
                  setSuccess("");
                }}
              >
                <option value="CAPEX">CAPEX — General budget request</option>
                <option value="OPEX">OPEX — Subcategory allocation</option>
              </select>
            </label>
          </div>

          {requestMode === "CAPEX" ? (
            <form className="budgets-form" onSubmit={submitCapexRequest}>
              <div className="budgets-form-grid">
                <label>
                  Financial year <span>*</span>
                  <input
                    value={requestYear}
                    onChange={(event) => setRequestYear(event.target.value)}
                    placeholder="2026-2027"
                    required
                  />
                </label>

                <label>
                  Planned CAPEX amount (₹) <span>*</span>
                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={capexAmount}
                    onChange={(event) => setCapexAmount(event.target.value)}
                    placeholder="Enter planned amount"
                    required
                  />
                </label>

                <label>
                  Budget approval copy
                  <input
                    key={capexApprovalCopy?.name ?? "empty"}
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                    onChange={handleCapexApprovalCopyChange}
                  />
                  <small className="budgets-table-subtitle">
                    Optional · PDF, JPG, JPEG or PNG · Maximum 10 MB
                  </small>

                  {capexApprovalCopy && (
                    <div className="budgets-form-actions">
                      <small>
                        Selected: {capexApprovalCopy.name}
                      </small>
                      <button
                        type="button"
                        className="budgets-secondary-button"
                        onClick={() => setCapexApprovalCopy(null)}
                        disabled={saving}
                      >
                        Remove file
                      </button>
                    </div>
                  )}
                </label>
              </div>

              <div className="budgets-form-actions">
                <button
                  type="submit"
                  className="budgets-primary-button"
                  disabled={saving}
                >
                  {saving ? "Submitting..." : "Submit CAPEX for approval"}
                </button>
              </div>
            </form>
          ) : (
            <form
              className="budgets-form"
              onSubmit={(event) => {
                const parent = opexParentOptions.find(
                  (budget) => String(budget.id) === opexCategoryId
                );

                if (!parent) {
                  event.preventDefault();
                  setError("Select an OPEX category.");
                  return;
                }

                void submitOpexRequest(
                  event,
                  parent,
                  selectedSubcategory,
                  customSubcategory,
                  subcategoryAmount,
                  opexApprovalCopy,
                  () => {
                    setSelectedSubcategory("");
                    setCustomSubcategory("");
                    setSubcategoryAmount("");
                    setOpexCategoryId("");
                    setOpexApprovalCopy(null);
                  }
                );
              }}
            >
              <div className="budgets-form-grid">
                <label>
                  Financial year <span>*</span>
                  <input
                    value={requestYear}
                    onChange={(event) => {
                      setRequestYear(event.target.value);
                      setOpexCategoryId("");
                      setSelectedSubcategory("");
                      setCustomSubcategory("");
                      setOpexApprovalCopy(null);
                    }}
                    placeholder="2026-2027"
                    required
                  />
                </label>

                <label>
                  OPEX category <span>*</span>
                  <select
                    value={opexCategoryId}
                    onChange={(event) => {
                      setOpexCategoryId(event.target.value);
                      setSelectedSubcategory("");
                      setCustomSubcategory("");
                    }}
                    required
                  >
                    <option value="">Select OPEX category</option>
                    {opexParentOptions.map((budget) => (
                      <option key={budget.id} value={String(budget.id)}>
                        {budget.name}
                      </option>
                    ))}
                  </select>

                  {opexParentOptions.length === 0 && (
                    <small className="budgets-table-subtitle">
                      No OPEX categories found for this financial year. Please
                      refresh or contact Finance Operations.
                    </small>
                  )}
                </label>

                <label>
                  Subcategory <span>*</span>
                  <select
                    value={selectedSubcategory}
                    onChange={(event) =>
                      setSelectedSubcategory(event.target.value)
                    }
                    required
                    disabled={!opexCategoryId}
                  >
                    <option value="">Select subcategory</option>
                    {OPEX_SUBCATEGORIES[
                      opexParentOptions.find(
                        (budget) => String(budget.id) === opexCategoryId
                      )?.name ?? ""
                    ]?.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                    <option value="__OTHER__">
                      Other — enter custom subcategory
                    </option>
                  </select>
                </label>

                {selectedSubcategory === "__OTHER__" && (
                  <label>
                    Custom subcategory name <span>*</span>
                    <input
                      value={customSubcategory}
                      onChange={(event) =>
                        setCustomSubcategory(event.target.value)
                      }
                      maxLength={200}
                      placeholder="Enter subcategory name"
                      required
                    />
                  </label>
                )}

                <label>
                  Planned OPEX allocation (₹) <span>*</span>
                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={subcategoryAmount}
                    onChange={(event) =>
                      setSubcategoryAmount(event.target.value)
                    }
                    placeholder="Enter planned amount"
                    required
                  />
                </label>

                <label>
                  Budget approval copy
                  <input
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                    onChange={handleOpexApprovalCopyChange}
                    disabled={saving}
                  />
                  <small className="budgets-table-subtitle">
                    Optional · PDF, JPG, JPEG or PNG · Maximum 10 MB
                  </small>

                  {opexApprovalCopy && (
                    <div className="budgets-form-actions">
                      <small>Selected: {opexApprovalCopy.name}</small>
                      <button
                        type="button"
                        className="budgets-secondary-button"
                        onClick={() => setOpexApprovalCopy(null)}
                        disabled={saving}
                      >
                        Remove file
                      </button>
                    </div>
                  )}
                </label>
              </div>

              <div className="budgets-form-actions">
                <button
                  type="submit"
                  className="budgets-primary-button"
                  disabled={saving || opexParentOptions.length === 0}
                >
                  {saving
                    ? "Submitting..."
                    : "Submit OPEX allocation for approval"}
                </button>
              </div>
            </form>
          )}
        </section>
      )}

      {/* Register filters */}
      <section className="budgets-list-card">
        <div className="budgets-section-heading">
          <div>
            <h2>Register filters</h2>
            <p>
              Filter approved budget categories by name, financial year and type.
            </p>
          </div>
        </div>

        <div className="budgets-filters">
          <label className="budgets-search-field">
            Search category
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search budget categories..."
            />
          </label>

          <label>
            Financial year
            <select
              value={yearFilter}
              onChange={(event) => setYearFilter(event.target.value)}
            >
              <option value="">All financial years</option>
              {financialYears.map((year) => (
                <option key={year} value={year}>
                  {year}
                </option>
              ))}
            </select>
          </label>

          <label>
            Budget type
            <select
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value)}
            >
              <option value="">All types</option>
              <option value="OPEX">OPEX</option>
              <option value="CAPEX">CAPEX</option>
            </select>
          </label>

          <button
            type="button"
            className="budgets-secondary-button"
            onClick={() => {
              setSearch("");
              setYearFilter("");
              setTypeFilter("");
            }}
          >
            Clear filters
          </button>
        </div>
      </section>

      {/* TABLE 1: Approved Budget Register */}
      <section className="budgets-list-card">
        <div className="budgets-section-heading budgets-list-heading">
          <div>
            <h2>Approved Budget Register</h2>
            <p>
              {approvedBudgets.length} approved budget category/categories
            </p>
          </div>
        </div>

        {loading ? (
          <div className="budgets-empty">Loading budgets...</div>
        ) : approvedBudgets.length === 0 ? (
          <div className="budgets-empty">
            <strong>No approved budgets found</strong>
            <p>Approved budgets will appear here.</p>
          </div>
        ) : (
          <div className="budgets-table-wrapper">
            <table className="budgets-table">
              <thead>
                <tr>
                  <th>Budget category</th>
                  <th>Financial year</th>
                  <th>Type</th>
                  <th>Planned amount</th>
                  <th>Approved amount</th>
                  <th>Balance</th>
                </tr>
              </thead>

              <tbody>
                {approvedBudgets.map((budget) => {
                  const planned = Number(budget.planned_amount) || 0;
                  const approved = Number(budget.approved_amount) || 0;
                  const clickableOpex =
                    budget.budget_type === "OPEX" &&
                    isOpexCategory(budget.name);

                  return (
                    <tr key={budget.id}>
                      <td>
                        <div className="budgets-name-cell">
                          {clickableOpex ? (
                            <button
                              type="button"
                              className="budgets-category-link"
                              onClick={() => void openOpexCategory(budget)}
                              title="View OPEX subcategory allocations"
                            >
                              {budget.name}
                              <span aria-hidden="true"> ↗</span>
                            </button>
                          ) : (
                            <strong>{budget.name}</strong>
                          )}

                          <small>Budget #{budget.id}</small>

                          {budget.has_approval_copy && (
                            <button
                              type="button"
                              className="budgets-category-link"
                              onClick={() =>
                                void viewBudgetApprovalCopy(budget.id)
                              }
                              title="View budget approval copy"
                            >
                              View Approval Copy ↗
                            </button>
                          )}
                        </div>
                      </td>

                      <td>{budget.financial_year}</td>

                      <td>
                        <span
                          className={`budgets-type-badge budgets-type-${budget.budget_type.toLowerCase()}`}
                        >
                          {budget.budget_type}
                        </span>
                      </td>

                      <td className="budgets-money-cell">{amount(planned)}</td>
                      <td className="budgets-money-cell">{amount(approved)}</td>
                      <td className="budgets-money-cell">
                        {amount(planned - approved)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* TABLE 2: Combined Waiting for Approval */}
      <section className="budgets-list-card budgets-request-section">
        <div className="budgets-section-heading budgets-list-heading">
          <div>
            <h2>Waiting for Approval</h2>
            <p>
              {totalWaiting} pending CAPEX and OPEX allocation request(s)
            </p>
          </div>
        </div>

        {loading ? (
          <div className="budgets-empty">Loading requests...</div>
        ) : (
          renderWaitingTable()
        )}
      </section>
    </main>
  );
}
