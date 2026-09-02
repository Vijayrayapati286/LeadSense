import { useCallback, useEffect, useState } from 'react';
import {
  FiArrowDown,
  FiArrowUp,
  FiBriefcase,
  FiDatabase,
  FiMapPin,
  FiPlus,
  FiUsers,
} from 'react-icons/fi';
import AccountDetailPanel from '../components/icp/AccountDetailPanel';
import AddAccountModal from '../components/icp/AddAccountModal';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Pagination from '../components/ui/Pagination';
import SearchInput from '../components/ui/SearchInput';
import { useToast } from '../hooks/useToast';
import { icpService } from '../services/services';
import { MetricCard, WorkspaceHeader } from '../components/ui/GrowthWorkspace';
import { debounce } from '../utils/helpers';

import { getDefaultPageSize } from '../utils/workspaceDefaults';

const PAGE_SIZE = getDefaultPageSize(4);
const ROW_HEIGHT_CLASS = 'h-[3.25rem]';

function accountType(row) {
  return row.company_size || row.industry || '—';
}

export default function AccountsPage() {
  const toast = useToast();
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [industryFilter, setIndustryFilter] = useState('');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [sortOrder, setSortOrder] = useState('asc');
  const [selected, setSelected] = useState(null);
  const [addOpen, setAddOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await icpService.listAccounts({
        page,
        page_size: PAGE_SIZE,
        search: search || undefined,
        industry: industryFilter || undefined,
      });
      const sorted = [...(data.items || [])].sort((a, b) => {
        const av = (a.company_name || '').toLowerCase();
        const bv = (b.company_name || '').toLowerCase();
        return sortOrder === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      });
      setItems(sorted);
      setTotal(data.total || 0);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load accounts');
    } finally {
      setLoading(false);
    }
  }, [page, search, industryFilter, sortOrder, toast]);

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

  const showSpinner = loading && items.length === 0;
  const contactTotal = items.reduce((sum, row) => sum + (row.contact_count || 0), 0);

  return (
    <div className="mx-auto flex h-[calc(100vh-3rem)] min-h-[560px] w-full max-w-[1440px] flex-col lg:h-[calc(100vh-4rem)]">
      <div className="flex shrink-0 flex-col gap-4">
        <WorkspaceHeader
          eyebrow="ICP Database"
          title="Accounts"
          description="Companies grouped from your verified contacts. Each account shows how many people you have on file."
          actions={
            <button type="button" onClick={() => setAddOpen(true)} className="btn-primary inline-flex items-center gap-2">
              <FiPlus size={16} /> Add account
            </button>
          }
        />

        <div className="grid gap-2.5 sm:grid-cols-3">
          <MetricCard label="Total accounts" value={(total || 0).toLocaleString()} hint="In database" icon={FiBriefcase} />
          <MetricCard label="Contacts linked" value={contactTotal.toLocaleString()} hint="Across this page" tone="green" icon={FiUsers} />
          <MetricCard label="On this page" value={items.length.toLocaleString()} hint="Current results" icon={FiDatabase} />
        </div>

        <div className="surface-card flex flex-col gap-2.5 p-3 sm:flex-row sm:items-center sm:p-3.5">
          <SearchInput
            className="flex-1 min-w-0"
            value={searchInput}
            placeholder="Account name, industry, location…"
            onChange={(val) => {
              setSearchInput(val);
              debouncedSearch(val);
            }}
          />
          <input
            className="input-field max-w-[180px]"
            placeholder="Industry filter"
            value={industryFilter}
            onChange={(e) => {
              setIndustryFilter(e.target.value);
              setPage(1);
            }}
          />
          <button
            type="button"
            onClick={() => setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'))}
            className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700"
          >
            Name {sortOrder === 'asc' ? <FiArrowUp size={16} /> : <FiArrowDown size={16} />}
          </button>
        </div>
      </div>

      <div className="surface-card mt-3 flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="min-w-[800px] w-full text-sm table-fixed">
            <thead className="sticky top-0 z-[1] border-b border-slate-200 bg-slate-50/95">
              <tr className={`text-left text-[11px] font-bold uppercase tracking-[0.06em] text-slate-500 ${ROW_HEIGHT_CLASS}`}>
                <th className="w-[32%] px-4 py-2">Account Name</th>
                <th className="w-[16%] px-4 py-2">Type</th>
                <th className="w-[22%] px-4 py-2">Location</th>
                <th className="w-[14%] px-4 py-2">Contacts</th>
                <th className="w-[16%] px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="bg-white">
              {showSpinner ? (
                <tr className="[&>td]:border-b [&>td]:border-slate-200">
                  <td colSpan={5} className="py-12 text-center"><LoadingSpinner /></td>
                </tr>
              ) : items.length === 0 ? (
                <tr className="[&>td]:border-b [&>td]:border-slate-200">
                  <td colSpan={5} className="py-12 text-center text-gray-500">
                    No accounts yet. Click <strong>Add account</strong> or add contacts with a company name.
                  </td>
                </tr>
              ) : (
                items.map((row) => (
                  <tr
                    key={row.company_name}
                    onClick={() => setSelected(row)}
                    className={`cursor-pointer hover:bg-primary-50/40 [&>td]:border-b [&>td]:border-slate-200 ${ROW_HEIGHT_CLASS}`}
                  >
                    <td className="px-4 py-2 align-middle">
                      <span className="block truncate font-semibold text-primary-700">
                        {row.company_name}
                      </span>
                      {row.company_website ? (
                        <span className="block truncate text-xs text-slate-400">{row.company_website}</span>
                      ) : null}
                    </td>
                    <td className="px-4 py-2 align-middle text-slate-600 capitalize truncate">{accountType(row)}</td>
                    <td className="px-4 py-2 align-middle text-slate-600 truncate">
                      {row.location ? (
                        <span className="inline-flex max-w-full items-center gap-1 truncate"><FiMapPin size={12} className="shrink-0" /> <span className="truncate">{row.location}</span></span>
                      ) : '—'}
                    </td>
                    <td className="px-4 py-2 align-middle text-slate-600">
                      <span className="inline-flex items-center gap-1"><FiUsers size={13} /> {row.contact_count}</span>
                    </td>
                    <td className="px-4 py-2 align-middle">
                      <span className="inline-flex rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
                        Active
                      </span>
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

      <AccountDetailPanel
        account={selected}
        isOpen={Boolean(selected)}
        onClose={() => setSelected(null)}
      />

      <AddAccountModal
        isOpen={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={() => {
          if (page !== 1) setPage(1);
          else load();
        }}
      />
    </div>
  );
}
