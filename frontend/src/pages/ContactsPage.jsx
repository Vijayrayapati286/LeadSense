import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  FiArrowDown,
  FiArrowUp,
  FiBriefcase,
  FiCheck,
  FiCheckCircle,
  FiChevronDown,
  FiFilter,
  FiMapPin,
  FiMoreVertical,
  FiPlus,
  FiSearch,
  FiSliders,
  FiUsers,
  FiX,
} from 'react-icons/fi';
import IcpFiltersPanel, { EMPTY_ICP_FILTERS, FILTER_LABELS } from '../components/icp/IcpFiltersPanel';
import IcpRecordDetail from '../components/icp/IcpRecordDetail';
import AddContactModal from '../components/icp/AddContactModal';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Pagination from '../components/ui/Pagination';
import { useToast } from '../hooks/useToast';
import { icpService } from '../services/services';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { debounce } from '../utils/helpers';

import { getDefaultPageSize } from '../utils/workspaceDefaults';

const PAGE_SIZE = getDefaultPageSize(10);

const SORT_OPTIONS = [
  { id: 'name', label: 'Name' },
  { id: 'company_name', label: 'Company' },
  { id: 'verified_at', label: 'Date verified' },
  { id: 'created_at', label: 'Date added' },
];

function DatabaseMetric({ label, value, hint, icon: Icon, tone = 'blue', action }) {
  const tones = {
    blue: { value: 'text-slate-950', icon: 'bg-blue-50 text-blue-600' },
    green: { value: 'text-emerald-700', icon: 'bg-emerald-50 text-emerald-600' },
    violet: { value: 'text-slate-950', icon: 'bg-violet-50 text-violet-600' },
  };
  const palette = tones[tone] || tones.blue;
  return (
    <div className="flex min-h-[96px] items-center justify-between rounded-xl border border-slate-200/80 bg-white px-5 py-4 shadow-sm">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</p>
        <p className={`mt-1 text-2xl font-bold tabular-nums ${palette.value}`}>{value}</p>
        {action ? (
          <button type="button" onClick={action} className="mt-0.5 text-xs font-medium text-primary-600 hover:text-primary-700">
            Clear all
          </button>
        ) : (
          <p className="mt-0.5 text-xs text-slate-500">{hint}</p>
        )}
      </div>
      {Icon ? (
        <span className={`flex h-10 w-10 items-center justify-center rounded-lg ${palette.icon}`}>
          <Icon size={20} />
        </span>
      ) : null}
    </div>
  );
}

function contactType(row) {
  return row.industry || (Array.isArray(row.tags) && row.tags[0]) || '—';
}

function initials(name) {
  return (name || '?')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase();
}

const AVATAR_STYLES = [
  'bg-blue-50 text-blue-700',
  'bg-emerald-50 text-emerald-700',
  'bg-amber-50 text-amber-700',
  'bg-violet-50 text-violet-700',
  'bg-rose-50 text-rose-700',
];

function avatarStyle(row) {
  const seed = String(row.name || row.id || '');
  const index = [...seed].reduce((sum, char) => sum + char.charCodeAt(0), 0) % AVATAR_STYLES.length;
  return AVATAR_STYLES[index];
}

function SortableHeading({ children, align = 'left' }) {
  return (
    <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'justify-end' : ''}`}>
      {children}
      <span className="text-[9px] text-slate-400">↕</span>
    </span>
  );
}

export default function ContactsPage() {
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const companyFromUrl = searchParams.get('company') || '';

  const [moreOpen, setMoreOpen] = useState(false);
  const [draftFilters, setDraftFilters] = useState({ ...EMPTY_ICP_FILTERS, company: companyFromUrl });
  const [appliedFilters, setAppliedFilters] = useState({ ...EMPTY_ICP_FILTERS, company: companyFromUrl });
  const [sortBy, setSortBy] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [companyInput, setCompanyInput] = useState(companyFromUrl);
  const [page, setPage] = useState(1);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  useEffect(() => {
    if (companyFromUrl) {
      setCompanyInput(companyFromUrl);
      setDraftFilters((prev) => ({ ...prev, company: companyFromUrl }));
      setAppliedFilters((prev) => ({ ...prev, company: companyFromUrl }));
      setPage(1);
    }
  }, [companyFromUrl]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        page,
        limit: PAGE_SIZE,
        sort_by: sortBy,
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
      toast.error(err?.response?.data?.detail || 'Failed to load contacts');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, sortBy, sortOrder, search, appliedFilters]);

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

  const debouncedCompany = useCallback(
    debounce((val) => {
      setAppliedFilters((prev) => ({ ...prev, company: val.trim() }));
      setDraftFilters((prev) => ({ ...prev, company: val.trim() }));
      setPage(1);
      if (val.trim()) {
        setSearchParams({ company: val.trim() });
      } else {
        setSearchParams({});
      }
    }, 400),
    [],
  );

  function handleSortByChange(nextSortBy) {
    setSortBy(nextSortBy);
    setPage(1);
    if (nextSortBy === 'verified_at' || nextSortBy === 'created_at') {
      setSortOrder('desc');
    } else {
      setSortOrder('asc');
    }
  }

  function toggleSortOrder() {
    setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    setPage(1);
  }

  useEffect(() => {
    if (!total) return;
    const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
    setPage((prev) => (prev > lastPage ? lastPage : prev));
  }, [total]);

  async function handleDelete(id) {
    try {
      await icpService.remove(id);
      toast.success('Contact deleted');
      if (selected?.id === id) setSelected(null);
      const remaining = total - 1;
      const lastPage = Math.max(1, Math.ceil(remaining / PAGE_SIZE));
      if (page > lastPage) setPage(lastPage);
      else load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Delete failed');
    }
  }

  function applyFilters() {
    setAppliedFilters({ ...draftFilters });
    setCompanyInput(draftFilters.company || '');
    setPage(1);
    setMoreOpen(false);
    if (draftFilters.company) {
      setSearchParams({ company: draftFilters.company });
    } else {
      setSearchParams({});
    }
  }

  function clearFilters() {
    setDraftFilters({ ...EMPTY_ICP_FILTERS });
    setAppliedFilters({ ...EMPTY_ICP_FILTERS });
    setCompanyInput('');
    setPage(1);
    setSearchParams({});
  }

  function removeFilter(key) {
    const next = { ...appliedFilters, [key]: '' };
    setAppliedFilters(next);
    setDraftFilters(next);
    if (key === 'company') setCompanyInput('');
    setPage(1);
    if (key === 'company') setSearchParams({});
  }

  const advancedFilterCount = Object.entries(appliedFilters).filter(
    ([key, value]) => value && key !== 'company',
  ).length;
  const activeFilterEntries = Object.entries(appliedFilters).filter(([, value]) => value);
  const sortLabel = SORT_OPTIONS.find((o) => o.id === sortBy)?.label || 'Name';
  const activeCount = items.filter((row) => ['active', 'verified'].includes((row.icp_status || '').toLowerCase())).length;
  const showInitialSpinner = loading && items.length === 0;

  return (
    <div className="mx-auto flex h-[calc(100vh-3rem)] min-h-[560px] w-full max-w-[1440px] flex-col lg:h-[calc(100vh-4rem)]">
      <div className="flex shrink-0 flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-primary-600">ICP Database</p>
            <h1 className="mt-0.5 text-2xl font-bold tracking-tight text-slate-950">Contacts</h1>
            <p className="mt-1 line-clamp-1 text-sm text-slate-500 sm:max-w-2xl">
              People at your target accounts — name, designation, email, and location.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setAddOpen(true)}
            className="btn-primary inline-flex min-h-10 shrink-0 items-center gap-2 px-4 py-2 text-sm shadow-lg shadow-primary-200/60"
          >
            <FiPlus size={16} /> Add contact
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <DatabaseMetric
            label="Total contacts"
            value={(total || 0).toLocaleString()}
            hint="In database"
            icon={FiUsers}
          />
          <DatabaseMetric
            label="Active this page"
            value={activeCount}
            hint="This page"
            icon={FiCheckCircle}
            tone="green"
          />
          <DatabaseMetric
            label="Filters applied"
            value={activeFilterEntries.length}
            hint="No filters"
            icon={FiFilter}
            tone="violet"
            action={activeFilterEntries.length ? clearFilters : undefined}
          />
        </div>

        <div className="surface-card flex flex-col gap-3 p-3">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
            <label className="relative min-w-0 flex-[1.15]">
              <FiSearch
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                size={15}
              />
              <input
                type="search"
                className="control w-full pl-9 text-sm"
                value={searchInput}
                placeholder="Search by name, email or designation..."
                onChange={(e) => {
                  setSearchInput(e.target.value);
                  debouncedSearch(e.target.value);
                }}
              />
            </label>
            <label className="relative min-w-0 flex-1">
              <FiBriefcase
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                size={14}
              />
              <input
                type="text"
                className="control w-full pl-9 text-sm"
                placeholder="Filter by company..."
                value={companyInput}
                onChange={(e) => {
                  setCompanyInput(e.target.value);
                  debouncedCompany(e.target.value);
                }}
              />
            </label>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <span className="hidden text-xs font-medium text-slate-500 xl:inline">Sort by:</span>
              <div className="relative">
                <select
                  className="control min-h-9 appearance-none pr-8 text-xs font-medium"
                  value={sortBy}
                  onChange={(e) => handleSortByChange(e.target.value)}
                  aria-label="Sort by"
                >
                  {SORT_OPTIONS.map((opt) => (
                    <option key={opt.id} value={opt.id}>
                      {opt.label} {opt.id === 'name' ? '(A–Z)' : ''}
                    </option>
                  ))}
                </select>
                <FiChevronDown
                  className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400"
                  size={13}
                />
              </div>
              <button
                type="button"
                onClick={toggleSortOrder}
                className="inline-flex min-h-9 items-center justify-center rounded-lg border border-slate-200 bg-white px-2.5 text-slate-600 hover:bg-slate-50"
                title={`${sortLabel} ${sortOrder === 'asc' ? 'ascending' : 'descending'}`}
                aria-label={`Toggle ${sortLabel} sort direction`}
              >
                {sortOrder === 'asc' ? <FiArrowUp size={15} /> : <FiArrowDown size={15} />}
              </button>
              <button
                type="button"
                onClick={() => setMoreOpen((open) => !open)}
                className={`inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                  moreOpen || advancedFilterCount > 0
                    ? 'border-primary-300 bg-primary-50 text-primary-800'
                    : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                }`}
              >
                <FiSliders size={14} />
                More filters
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-primary-600">
                  {advancedFilterCount}
                </span>
              </button>
            </div>
          </div>
        </div>

        {activeFilterEntries.length ? (
          <div className="flex flex-wrap items-center gap-2">
            {activeFilterEntries.map(([key, value]) => (
              <button
                key={key}
                type="button"
                onClick={() => removeFilter(key)}
                className="inline-flex items-center gap-1.5 rounded-full border border-primary-200 bg-primary-50 px-2.5 py-1 text-xs font-medium text-primary-700"
              >
                {FILTER_LABELS[key] || key}: {value} <FiX size={12} />
              </button>
            ))}
          </div>
        ) : null}

        <IcpFiltersPanel
          open={moreOpen}
          variant="advanced"
          filters={draftFilters}
          onChange={setDraftFilters}
          onApply={applyFilters}
          onClear={clearFilters}
        />
      </div>

      <div className="surface-card mt-4 flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="min-w-[940px] w-full table-fixed text-sm">
            <thead className="sticky top-0 z-[1] border-b border-slate-200 bg-slate-50/95">
              <tr className="text-left text-[10px] font-bold uppercase tracking-[0.07em] text-slate-500">
                <th className="w-[15%] px-4 py-3"><SortableHeading>Contact name</SortableHeading></th>
                <th className="w-[14%] px-4 py-3"><SortableHeading>Account</SortableHeading></th>
                <th className="w-[17%] px-4 py-3"><SortableHeading>Designation</SortableHeading></th>
                <th className="w-[19%] px-4 py-3"><SortableHeading>Location</SortableHeading></th>
                <th className="w-[12%] px-4 py-3">Email</th>
                <th className="w-[9%] px-4 py-3"><SortableHeading>Type</SortableHeading></th>
                <th className="w-[9%] px-4 py-3"><SortableHeading>Status</SortableHeading></th>
                <th className="w-[5%] px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white">
              {showInitialSpinner ? (
                <tr className="[&>td]:border-b [&>td]:border-slate-200"><td colSpan={8} className="py-16 text-center"><LoadingSpinner /></td></tr>
              ) : items.length === 0 ? (
                <tr className="[&>td]:border-b [&>td]:border-slate-200">
                  <td colSpan={8} className="py-16 text-center text-gray-500">
                    No contacts yet. Verify extracted profiles or add one manually.
                  </td>
                </tr>
              ) : (
                items.map((row) => (
                  <tr
                    key={row.id}
                    onClick={() => setSelected(row)}
                    className="group cursor-pointer transition-colors hover:bg-primary-50/30 [&>td]:border-b [&>td]:border-slate-200"
                  >
                    <td className="px-4 py-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-bold ${avatarStyle(row)}`}>
                          {initials(row.name)}
                        </span>
                        <span className="truncate text-xs font-semibold text-primary-700">{row.name || '—'}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex min-w-0 items-start gap-2">
                        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-slate-50 text-slate-400">
                          <FiBriefcase size={13} />
                        </span>
                        <div className="min-w-0">
                          <p className="truncate text-xs font-medium text-slate-700">{row.company_name || '—'}</p>
                          <p className="truncate text-[10px] text-slate-400">{row.industry || ''}</p>
                        </div>
                      </div>
                    </td>
                    <td className="truncate px-4 py-3 text-xs text-slate-600">{row.designation || '—'}</td>
                    <td className="px-4 py-3 text-xs text-slate-600">
                      {row.location ? (
                        <span className="inline-flex items-start gap-1.5 leading-relaxed">
                          <FiMapPin className="mt-0.5 shrink-0 text-slate-500" size={12} />
                          <span className="line-clamp-2">{row.location}</span>
                        </span>
                      ) : '—'}
                    </td>
                    <td className="truncate px-4 py-3 text-xs text-slate-600">{row.email || '—'}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex max-w-full truncate rounded-md bg-blue-50 px-2 py-1 text-[10px] font-semibold capitalize text-blue-700">
                        {contactType(row)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold capitalize text-emerald-700">
                        <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-50">
                          <FiCheck size={10} />
                        </span>
                        {row.icp_status || 'Active'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteTarget(row);
                        }}
                        className="rounded-lg border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50 hover:text-slate-800"
                        aria-label={`Actions for ${row.name || 'contact'}`}
                        title="Delete contact"
                      >
                        <FiMoreVertical size={14} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {total > 0 ? (
          <div className="shrink-0 border-t border-slate-100 px-2">
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

      <AddContactModal
        isOpen={addOpen}
        onClose={() => setAddOpen(false)}
        defaultCompany={companyFromUrl}
        onCreated={() => load()}
      />

      <ConfirmDialog
        isOpen={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => handleDelete(deleteTarget?.id)}
        title="Delete contact?"
        message={`This will permanently remove ${deleteTarget?.name || 'this contact'}.`}
        confirmText="Delete"
      />
    </div>
  );
}
