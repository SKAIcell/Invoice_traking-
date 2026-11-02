
import { useEffect, useState } from "react";
import "../styles/VendorsPage.css";

type Vendor = {
  id: number;
  party_type: string;
  code: string;
  name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  is_active: boolean;
  created_at: string;
};

type VendorsPageProps = {
  onVendorSelect: (vendorId: number, vendorName: string) => void;
};

const API_URL = "/api/parties";

export default function VendorsPage({
  onVendorSelect,
}: VendorsPageProps) {
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    async function loadVendors() {
      setLoading(true);
      setError("");

      try {
        const token = sessionStorage.getItem("access_token");

        const params = new URLSearchParams({
          party_type: "VENDOR",
          limit: "100",
        });

        if (search.trim()) {
          params.set("q", search.trim());
        }

        if (statusFilter !== "ALL") {
          params.set(
            "is_active",
            statusFilter === "ACTIVE" ? "true" : "false",
          );
        }

        const response = await fetch(
          `${API_URL}?${params.toString()}`,
          {
            headers: token
              ? { Authorization: `Bearer ${token}` }
              : {},
            signal: controller.signal,
          },
        );

        if (response.status === 401) {
          throw new Error(
            "Your session may have expired. Please log in again.",
          );
        }

        if (!response.ok) {
          throw new Error("Unable to load vendor records.");
        }

        const data: Vendor[] = await response.json();
        setVendors(data);
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }

        setError(
          err instanceof Error
            ? err.message
            : "Something went wrong.",
        );
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    const timeout = window.setTimeout(loadVendors, 250);

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [search, statusFilter]);

  const activeCount = vendors.filter(
    (vendor) => vendor.is_active,
  ).length;

  const inactiveCount = vendors.filter(
    (vendor) => !vendor.is_active,
  ).length;

  return (
    <section className="vendors-page">
      <div className="vendors-page-header">
        <div>
          <p className="vendors-eyebrow">FINANCE OPERATIONS</p>
          <h1>Vendor Management</h1>
          <p className="vendors-subtitle">
            View and search your registered vendor records.
            Select a vendor to view its orders.
          </p>
        </div>

        <button
          className="vendors-refresh-button"
          type="button"
          onClick={() => {
            setSearch((current) => current);
            window.location.reload();
          }}
        >
          Refresh records
        </button>
      </div>

      <div className="vendors-summary-grid">
        <article className="vendors-summary-card">
          <span className="vendors-summary-label">
            Records displayed
          </span>
          <strong>{vendors.length}</strong>
          <span className="vendors-summary-note">
            Matching your filters
          </span>
        </article>

        <article className="vendors-summary-card">
          <span className="vendors-summary-label">
            Active vendors
          </span>
          <strong>{activeCount}</strong>
          <span className="vendors-summary-note">
            Currently displayed
          </span>
        </article>

        <article className="vendors-summary-card">
          <span className="vendors-summary-label">
            Inactive vendors
          </span>
          <strong>{inactiveCount}</strong>
          <span className="vendors-summary-note">
            Currently displayed
          </span>
        </article>
      </div>

      <div className="vendors-register">
        <div className="vendors-register-heading">
          <div>
            <h2>Vendor Register</h2>
            <p>
              Vendor codes, contact information and account status
            </p>
          </div>

          <span className="vendors-record-count">
            {vendors.length}{" "}
            {vendors.length === 1 ? "record" : "records"}
          </span>
        </div>

        <div className="vendors-toolbar">
          <div className="vendors-search">
            <span aria-hidden="true">⌕</span>

            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search name, vendor code, email or phone..."
              aria-label="Search vendors"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value)
            }
            aria-label="Filter vendor status"
          >
            <option value="ALL">All statuses</option>
            <option value="ACTIVE">Active only</option>
            <option value="INACTIVE">Inactive only</option>
          </select>
        </div>

        {error && (
          <div className="vendors-error" role="alert">
            <p>{error}</p>
            <button
              type="button"
              onClick={() => window.location.reload()}
            >
              Retry
            </button>
          </div>
        )}

        {loading ? (
          <div className="vendors-state">
            Loading vendor records...
          </div>
        ) : !error && vendors.length === 0 ? (
          <div className="vendors-state">
            <strong>No vendors found</strong>
            <p>
              {search
                ? "Try another search term or change the status filter."
                : "No vendor records are currently available."}
            </p>
          </div>
        ) : !error ? (
          <div className="vendors-table-wrapper">
            <table className="vendors-table">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Vendor Code</th>
                  <th>Contact Details</th>
                  <th>Address</th>
                  <th>Status</th>
                </tr>
              </thead>

              <tbody>
                {vendors.map((vendor) => (
                  <tr key={vendor.id}>
                    <td>
                      <div className="vendor-name-cell">
                        <span
                          className="vendor-avatar"
                          aria-hidden="true"
                        >
                          {vendor.name.trim().charAt(0).toUpperCase() || "V"}
                        </span>

                        <div>
                          <button
                            type="button"
                            className="vendor-name-button"
                            onClick={() =>
                              onVendorSelect(vendor.id, vendor.name)
                            }
                            title={`View orders for ${vendor.name}`}
                          >
                            {vendor.name}
                          </button>

                          <span>Vendor ID: {vendor.id}</span>
                        </div>
                      </div>
                    </td>

                    <td>
                      <span className="vendor-code">
                        {vendor.code}
                      </span>
                    </td>

                    <td>
                      <div className="vendor-contact-cell">
                        <span>{vendor.email || "—"}</span>
                        <span>{vendor.phone || "—"}</span>
                      </div>
                    </td>

                    <td className="vendor-address">
                      {vendor.address || "—"}
                    </td>

                    <td>
                      <span
                        className={`vendor-status ${
                          vendor.is_active
                            ? "is-active"
                            : "is-inactive"
                        }`}
                      >
                        <span className="vendor-status-dot" />
                        {vendor.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        <div className="vendors-register-footer">
          <span>
            Skipper Limited · Internal Finance Operations
          </span>
          <span>Showing up to 100 records</span>
        </div>
      </div>
    </section>
  );
}
