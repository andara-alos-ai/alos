"use client";

import { useState, useMemo, type ReactNode } from "react";

export interface Column<T> {
  header: string;
  accessorKey?: keyof T;
  cell?: (item: T) => ReactNode;
  className?: string;
}

export interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  keyExtractor: (item: T) => string;
  searchPlaceholder?: string;
  searchFilter?: (item: T, query: string) => boolean;
  onRowClick?: (item: T) => void;
  emptyTitle?: string;
  emptyDescription?: string;
  actions?: ReactNode;
  className?: string;
}

export function DataTable<T>({
  data,
  columns,
  keyExtractor,
  searchPlaceholder = "Cari data...",
  searchFilter,
  onRowClick,
  emptyTitle = "Belum Ada Data",
  emptyDescription = "Tidak ada rekaman data yang sesuai.",
  actions,
  className = "",
}: DataTableProps<T>) {
  const [searchQuery, setSearchQuery] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const filteredData = useMemo(() => {
    if (!searchQuery.trim() || !searchFilter) return data;
    const q = searchQuery.toLowerCase().trim();
    return data.filter((item) => searchFilter(item, q));
  }, [data, searchQuery, searchFilter]);

  const totalPages = Math.ceil(filteredData.length / pageSize) || 1;
  const currentPageData = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredData.slice(start, start + pageSize);
  }, [filteredData, page, pageSize]);

  return (
    <div className={`dataTableWrapper ${className}`}>
      {/* Top Search & Actions Bar */}
      {(searchFilter || actions) && (
        <div className="dataTableControls">
          {searchFilter ? (
            <input
              className="dataTableSearchInput"
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(1);
              }}
              placeholder={searchPlaceholder}
              type="search"
              value={searchQuery}
            />
          ) : <div />}

          {actions && <div>{actions}</div>}
        </div>
      )}

      {/* Table Container */}
      <div className="dataTablePanel">
        {filteredData.length === 0 ? (
          <div className="statePanel" style={{ border: "none" }}>
            <strong>{emptyTitle}</strong>
            <p>{emptyDescription}</p>
          </div>
        ) : (
          <table className="dataTable">
            <thead>
              <tr>
                {columns.map((col, idx) => (
                  <th className={`dataTableTh ${col.className || ""}`} key={idx}>
                    {col.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {currentPageData.map((item) => {
                const key = keyExtractor(item);
                const isClickable = Boolean(onRowClick);
                return (
                  <tr
                    className={`dataTableRow ${isClickable ? "clickable" : ""}`}
                    key={key}
                    onClick={() => onRowClick?.(item)}
                  >
                    {columns.map((col, idx) => (
                      <td className={`dataTableTd ${col.className || ""}`} key={idx}>
                        {col.cell
                          ? col.cell(item)
                          : col.accessorKey
                          ? String(item[col.accessorKey] ?? "-")
                          : "-"}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {/* Pagination Bar */}
        {filteredData.length > pageSize && (
          <div className="dataTablePagination">
            <span>
              Menampilkan {(page - 1) * pageSize + 1}–
              {Math.min(page * pageSize, filteredData.length)} dari {filteredData.length} data
            </span>
            <div style={{ display: "flex", gap: "6px" }}>
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                type="button"
              >
                ← Sebelumnya
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                type="button"
              >
                Berikutnya →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
