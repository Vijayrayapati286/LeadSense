import { useCallback, useEffect, useState } from 'react';
import {
  FiArrowDown,
  FiArrowUp,
  FiCheck,
  FiDatabase,
  FiFilter,
  FiMapPin,
  FiPlus,
  FiTarget,
  FiTrash2,
  FiUsers,
  FiX,
} from 'react-icons/fi';
import IcpFiltersPanel, { EMPTY_ICP_FILTERS, FILTER_LABELS } from '../components/icp/IcpFiltersPanel';
import IcpRecordDetail from '../components/icp/IcpRecordDetail';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Modal from '../components/ui/Modal';
import Pagination from '../components/ui/Pagination';
import SearchInput from '../components/ui/SearchInput';
import { useToast } from '../hooks/useToast';
import { icpService } from '../services/services';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { EmptyState, WorkspaceHeader } from '../components/ui/GrowthWorkspace';
import { debounce } from '../utils/helpers';

const PAGE_SIZE = 5;

function DatabaseMetric({ label, value, hint, icon: Icon, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-50 text-slate-700 ring-slate-200',
    green: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
    blue: 'bg-primary-50 text-primary-700 ring-primary-100',
  };

  return (
    <div className="flex min-h-[104px] items-center gap-4 rounded-2xl border border-slate-200/80 bg-white px-5 py-4 shadow-sm transition duration-200 hover:border-slate-300 hover:shadow-md">
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ring-1 ${tones[tone]}`}>
        <Icon size={18} />
      </span>
      <div className="min-w-0">
        <p className="truncate text-[11px] font-bold uppercase tracking-[0.14em] text-slate-400">{label}</p>
        <p className="mt-0.5 text-2xl font-bold leading-7 tracking-tight text-slate-950">{value}</p>
        <p className="mt-0.5 truncate text-xs text-slate-500">{hint}</p>
      </div>
    </div>
  );
}

export default function IcpDatabasePage() {
  const toast = useToast();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [draftFilters, setDraftFilters] = useState({ ...EMPTY_ICP_FILTERS });
  const [appliedFilters, setAppliedFilters] = useState({ ...EMPTY_ICP_FILTERS });
  const [sortOrder, setSortOrder] = useState('asc');
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState({ name: '', company_name: '', designation: '', linkedin_url: '' });
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        page,
        limit: PAGE_SIZE,
        sort_by: 'name',
        sort_order: sortOrder,
        search: search || undefined,
        industry: appliedFilters.industry || undefined,
        company: appliedFilters.company || undefined,
        company_size: appliedFilters.company_size || undefined,
        designation: appliedFilters.designation || undefined,
        location: appliedFilters.location || undefined,
        icp_status: appliedFilters.icp_status || undefined,
        verified_from: appliedFilters.date_from || undefined,
        verified_to: appliedFilters.date_to || undefined,
      };
      const data = await icpService.list(params);
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load ICP Database');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, sortOrder, search, appliedFilters]);

  useEffect(() => {
    load();
  }, [load]);

  const debouncedSearch = useCallback(
    debounce((val) => {
      setSearch(val);
      setPage(1);
    }, 400),
    [],
  );

  // Only clamp when filters shrink the result set — not on every render.
  useEffect(() => {
    if (!total) return;
    const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
    setPage((prev) => (prev > lastPage ? lastPage : prev));
  }, [total]);

  async function handleAdd() {
    if (!addForm.name?.trim() && !addForm.linkedin_url?.trim()) {
      toast.error('Name or LinkedIn URL is required');
      return;
    }
    setSaving(true);
    try {
      await icpService.create(addForm);
      toast.success('ICP record created');
      setAddOpen(false);
      setAddForm({ name: '', company_name: '', designation: '', linkedin_url: '' });
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to create record');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    try {
      await icpService.remove(id);
      toast.success('Record deleted');
      if (selected?.id === id) setSelected(null);
      const remaining = total - 1;
      const lastPage = Math.max(1, Math.ceil(remaining / PAGE_SIZE));
      if (page > lastPage) setPage(lastPage);
      else load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Delete failed');
    }
  }

  function openRecord(row) {
    setSelected(row);
  }

  function applyFilters() {
    setAppliedFilters({ ...draftFilters });
    setPage(1);
    setFiltersOpen(false);
  }

  function clearFilters() {
    setDraftFilters({ ...EMPTY_ICP_FILTERS });
    setAppliedFilters({ ...EMPTY_ICP_FILTERS });
    setPage(1);
  }

  function removeFilter(key) {
    const next = { ...appliedFilters, [key]: '' };
    setAppliedFilters(next);
    setDraftFilters(next);
    setPage(1);
  }

  function toggleSort() {
    setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    setPage(1);
  }

  const activeFilterEntries = Object.entries(appliedFilters).filter(([, value]) => value);
  const verifiedCount = items.filter((row) => (row.icp_status || 'verified').toLowerCase() === 'verified').length;
  const showInitialSpinner = loading && items.length === 0;

  return (
    <div className="mx-auto flex h-[calc(100vh-3rem)] min-h-[560px] w-full max-w-[1440px] flex-col lg:h-[calc(100vh-4rem)]">
      <div className="flex shrink-0 flex-col gap-4">
        <WorkspaceHeader
          eyebrow="Audience intelligence"
          title="Your ideal customer database"
          description="A trusted, filterable view of every verified prospect. Inspect buying context and connect the right people to the right offering."
          actions={
            <button type="button" onClick={() => setAddOpen(true)} className="btn-primary inline-flex items-center gap-2">
              <FiPlus size={16} /> Add record
            </button>
          }
        />

        <div className="grid gap-3 sm:grid-cols-3">
          <DatabaseMetric label="Total records" value={(total || 0).toLocaleString()} hint="In your database" icon={FiDatabase} />
          <DatabaseMetric label="Verified" value={verifiedCount} hint="On this page" tone="green" icon={FiCheck} />
          <DatabaseMetric label="Active filters" value={activeFilterEntries.length} hint="Narrowing results" tone="blue" icon={FiTarget} />
        </div>

        <div className="surface-card flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:p-4">
          <SearchInput
            className="flex-1 min-w-0"
            value={searchInput}
            placeholder="Search company, person, designation…"
            onChange={(val) => {
              setSearchInput(val);
              debouncedSearch(val);
            }}
          />
          <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setFiltersOpen((o) => !o)}
            aria-expanded={filtersOpen}
            className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold transition ${
              filtersOpen
                ? 'border-primary-300 bg-primary-50 text-primary-800 shadow-sm'
                : 'border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-50'
            }`}
          >
            <FiFilter size={16} />
            Filters
            {activeFilterEntries.length > 0 ? (
              <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary-600 px-1 text-[10px] font-bold text-white">
                {activeFilterEntries.length}
              </span>
            ) : null}
          </button>
          <button
            type="button"
            onClick={toggleSort}
            className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-400 hover:bg-slate-50"
            aria-label={`Sort by name ${sortOrder === 'asc' ? 'A to Z' : 'Z to A'}`}
          >
            Name {sortOrder === 'asc' ? <FiArrowUp size={16} /> : <FiArrowDown size={16} />}
            <span className="text-xs font-normal text-slate-500">{sortOrder === 'asc' ? 'A → Z' : 'Z → A'}</span>
          </button>
          </div>
        </div>

        {activeFilterEntries.length ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Filtered by</span>
            {activeFilterEntries.map(([key, value]) => (
              <button
                key={key}
                type="button"
                onClick={() => removeFilter(key)}
                className="inline-flex items-center gap-1.5 rounded-full border border-primary-200 bg-primary-50 px-2.5 py-1 text-xs font-medium text-primary-700"
              >
                {FILTER_LABELS[key] || key.replaceAll('_', ' ')}: {value} <FiX size={12} />
              </button>
            ))}
          </div>
        ) : null}

        <IcpFiltersPanel
          open={filtersOpen}
          filters={draftFilters}
          onChange={setDraftFilters}
          onApply={applyFilters}
          onClear={clearFilters}
        />
      </div>

      <div className="surface-card mt-4 flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="relative min-h-0 flex-1 overflow-hidden">
          {loading && items.length > 0 ? (
            <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center pt-3">
              <span className="rounded-full bg-white/90 px-3 py-1 text-xs font-medium text-slate-500 shadow-sm ring-1 ring-slate-200">
                Updating…
              </span>
            </div>
          ) : null}
          <div className="hidden h-full overflow-x-auto overflow-y-auto md:block">
            <table className="min-w-[900px] w-full table-fixed text-sm">
              <thead className="sticky top-0 z-[1] border-b border-slate-200 bg-slate-50/95 backdrop-blur-sm">
                <tr className="text-left text-[11px] font-bold uppercase tracking-[0.06em] text-slate-500">
                  <th className="w-[13%] px-4 py-3">
                    <button
                      type="button"
                      onClick={toggleSort}
                      className="inline-flex items-center gap-1 hover:text-primary-700"
                    >
                      Name
                      {sortOrder === 'asc' ? <FiArrowUp size={12} /> : <FiArrowDown size={12} />}
                    </button>
                  </th>
                  <th className="w-[22%] px-4 py-3">Company</th>
                  <th className="w-[38%] px-4 py-3">Designation</th>
                  <th className="w-[10%] px-4 py-3">Industry</th>
                  <th className="w-[11%] px-4 py-3">Status</th>
                  <th className="w-[6%] px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className={`divide-y divide-slate-100 bg-white ${loading && items.length > 0 ? 'opacity-60' : ''}`}>
                {showInitialSpinner ? (
                  <tr>
                    <td colSpan={6} className="py-16 text-center">
                      <LoadingSpinner />
                    </td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-16 text-center text-gray-500">
                      No ICP records yet. Verify extracted profiles to populate this database.
                    </td>
                  </tr>
                ) : (
                  items.map((row) => (
                    <tr
                      key={row.id}
                      onClick={() => openRecord(row)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          openRecord(row);
                        }
                      }}
                      tabIndex={0}
                      className="group cursor-pointer outline-none transition-colors hover:bg-primary-50/40 focus:bg-primary-50 focus:ring-2 focus:ring-inset focus:ring-primary-400"
                    >
                      <td className="px-4 py-3.5 font-semibold text-slate-900">
                        <span className="block truncate" title={row.name || undefined}>{row.name || '—'}</span>
                      </td>
                      <td className="px-4 py-3.5 text-slate-600">
                        <span className="block truncate" title={row.company_name || undefined}>{row.company_name || '—'}</span>
                      </td>
                      <td className="px-4 py-3.5 text-slate-600">
                        <span className="block truncate" title={row.designation || undefined}>{row.designation || '—'}</span>
                      </td>
                      <td className="px-4 py-3.5 text-slate-600">
                        <span className="block truncate capitalize">{row.industry || '—'}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 text-xs font-medium ${
                          (row.icp_status || 'verified').toLowerCase() === 'verified' ? 'text-green-700' : 'text-amber-700'
                        }`}>
                          <FiCheck size={13} strokeWidth={2.5} />
                          <span className="capitalize">{row.icp_status || 'Verified'}</span>
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteTarget(row);
                          }}
                          className="rounded-lg p-2 text-slate-300 opacity-70 transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100 focus:opacity-100"
                          aria-label={`Delete ${row.name || 'record'}`}
                        >
                          <FiTrash2 size={15} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {!showInitialSpinner && items.length > 0 ? (
            <div className={`divide-y divide-slate-100 overflow-y-auto md:hidden ${loading ? 'opacity-60' : ''}`}>
              {items.map((row, index) => (
                <button
                  type="button"
                  key={row.id}
                  onClick={() => openRecord(row)}
                  className="stagger-item flex w-full items-start gap-3 p-4 text-left hover:bg-slate-50"
                  style={{ '--item-index': index }}
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 font-semibold text-primary-700">
                    {(row.name || '?').slice(0, 1).toUpperCase()}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-slate-900">{row.name || 'Unnamed contact'}</span>
                    <span className="mt-0.5 block truncate text-xs text-slate-500">{row.designation || 'Role not set'} · {row.company_name || 'Company not set'}</span>
                    {row.location ? <span className="mt-2 flex items-center gap-1 text-xs text-slate-400"><FiMapPin size={12} /> {row.location}</span> : null}
                  </span>
                  <span className="rounded-full bg-emerald-50 px-2 py-1 text-[11px] font-semibold text-emerald-700">{row.icp_status || 'Verified'}</span>
                </button>
              ))}
            </div>
          ) : null}
          {!showInitialSpinner && items.length === 0 ? (
            <div className="p-5 md:hidden"><EmptyState title="No ICP records found" description="Verify extracted profiles or adjust your filters." icon={FiUsers} /></div>
          ) : null}
        </div>
        {total > 0 ? (
          <div className="shrink-0 border-t border-slate-100 px-2 sm:px-3">
            <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
          </div>
        ) : null}
      </div>

      <IcpRecordDetail
        record={selected}
        isOpen={Boolean(selected)}
        onClose={() => setSelected(null)}
        onSaved={(updated) => {
          setSelected(updated);
          load();
        }}
      />

      <Modal isOpen={addOpen} onClose={() => setAddOpen(false)} title="Add ICP Record" size="md">
        <div className="space-y-3">
          {[
            ['name', 'Name'],
            ['company_name', 'Company'],
            ['designation', 'Designation'],
            ['linkedin_url', 'LinkedIn URL'],
          ].map(([key, label]) => (
            <label key={key} className="block">
              <span className="text-xs font-medium text-gray-500">{label}</span>
              <input
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                value={addForm[key] || ''}
                onChange={(e) => setAddForm((prev) => ({ ...prev, [key]: e.target.value }))}
              />
            </label>
          ))}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setAddOpen(false)}
              className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={handleAdd}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => handleDelete(deleteTarget?.id)}
        title="Delete ICP record?"
        message={`This will permanently remove ${deleteTarget?.name || 'this record'} from the ICP database.`}
        confirmText="Delete record"
      />
    </div>
  );
}
