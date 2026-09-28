import { useEffect, useState, useCallback, Fragment } from 'react';
import { FiActivity, FiCheckCircle, FiChevronDown, FiChevronRight, FiFilter, FiMail } from 'react-icons/fi';
import { logService, userService, campaignService, recipientGroupService } from '../services/services';
import { useToast } from '../hooks/useToast';
import SearchInput from '../components/ui/SearchInput';
import Pagination from '../components/ui/Pagination';
import StatusBadge from '../components/ui/StatusBadge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import PageShell from '../components/ui/PageShell';
import { MetricCard } from '../components/ui/GrowthWorkspace';
import { formatDateTime, debounce } from '../utils/helpers';

const EMPTY_FILTERS = { userId: '', campaignId: '', groupId: '', dateFrom: '', dateTo: '' };

function LogDetailCells({ log, indent = false }) {
  return (
    <>
      <td className={`px-6 py-3 text-gray-600 ${indent ? 'pl-12' : ''}`}>
        {log.campaign_name || `Campaign #${log.campaign_id}`}
      </td>
      <td className="px-6 py-3 text-gray-600">
        {log.sender_name || <span className="text-gray-400">—</span>}
        {log.sender_email && <p className="text-xs text-gray-400">{log.sender_email}</p>}
      </td>
      <td className="px-6 py-3 text-gray-600 whitespace-nowrap">{formatDateTime(log.sent_at)}</td>
      <td className="px-6 py-3"><StatusBadge status={log.status} /></td>
      <td className="px-6 py-3 text-gray-500 text-xs max-w-xs truncate">{log.error_message || '—'}</td>
    </>
  );
}

export default function EmailLogsPage() {
  const [logs, setLogs] = useState([]);
  const [groups, setGroups] = useState([]);
  const [grouped, setGrouped] = useState(false);
  const [total, setTotal] = useState(0);
  const [verifiedTotal, setVerifiedTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [expandedEmails, setExpandedEmails] = useState(() => new Set());
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [users, setUsers] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [groupsFilter, setGroupsFilter] = useState([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();
  const pageSize = 10;

  useEffect(() => {
    userService.getAll().then(({ data }) => setUsers(data)).catch(() => {});
    campaignService.getAll().then(({ data }) => setCampaigns(data)).catch(() => {});
    recipientGroupService.getAll().then(({ data }) => setGroupsFilter(data)).catch(() => {});
  }, []);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await logService.getAll({
        page,
        page_size: pageSize,
        search,
        status: statusFilter,
        verified_only: verifiedOnly || undefined,
        user_id: filters.userId || undefined,
        campaign_id: filters.campaignId || undefined,
        group_id: filters.groupId || undefined,
        date_from: filters.dateFrom || undefined,
        date_to: filters.dateTo || undefined,
      });
      const isGrouped = Boolean(data.grouped);
      setGrouped(isGrouped);
      setGroups(data.groups || []);
      setLogs(data.items || []);
      setTotal(data.total);
      setVerifiedTotal(data.verified_total ?? 0);
      if (!isGrouped) setExpandedEmails(new Set());
    } catch {
      toast.error('Failed to load email logs');
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter, verifiedOnly, filters, toast]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const debouncedSearch = useCallback(debounce((val) => { setSearch(val); setPage(1); }, 400), []);

  const updateFilter = (field, value) => {
    setFilters((prev) => ({ ...prev, [field]: value }));
    setPage(1);
  };
  const clearFilters = () => {
    setFilters(EMPTY_FILTERS);
    setStatusFilter('');
    setVerifiedOnly(false);
    setExpandedEmails(new Set());
    setPage(1);
  };
  const showAllEmails = () => {
    setVerifiedOnly(false);
    setExpandedEmails(new Set());
    setPage(1);
  };
  const toggleVerifiedOnly = () => {
    setVerifiedOnly((prev) => !prev);
    setExpandedEmails(new Set());
    setPage(1);
  };
  const toggleExpanded = (groupKey) => {
    const key = (groupKey || '').toLowerCase();
    setExpandedEmails((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  const filterCount = (statusFilter ? 1 : 0) + (verifiedOnly ? 1 : 0) + Object.values(filters).filter(Boolean).length;
  const hasActiveFilters = filterCount > 0;
  const rowCount = grouped ? groups.length : logs.length;

  return (
    <PageShell maxWidth="max-w-[1440px]">
      <PageHeader
        eyebrow="Lead generation"
        title="Email logs"
        subtitle="Track all sent, failed, and pending emails."
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Total emails"
          value={total}
          hint={verifiedOnly ? 'Click to show all' : 'Matching current view'}
          icon={FiMail}
          onClick={showAllEmails}
          active={!verifiedOnly}
        />
        <MetricCard label="On this page" value={rowCount} hint="Loaded activity" tone="green" icon={FiActivity} />
        <MetricCard
          label="Verified emails"
          value={verifiedTotal}
          hint={verifiedOnly ? 'Showing unique prospects — click to clear' : 'Click to view verified'}
          tone="green"
          icon={FiCheckCircle}
          onClick={toggleVerifiedOnly}
          active={verifiedOnly}
        />
        <MetricCard
          label="Filters applied"
          value={filterCount}
          hint={hasActiveFilters ? 'Click to clear filters' : 'Narrowing results'}
          tone="amber"
          icon={FiFilter}
          onClick={hasActiveFilters ? clearFilters : undefined}
          active={hasActiveFilters}
        />
      </div>

      {verifiedOnly ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-900">
          <p>
            Showing each <span className="font-semibold">verified</span> prospect once. Click a row to see every email and send.
          </p>
          <button
            type="button"
            onClick={showAllEmails}
            className="shrink-0 text-xs font-semibold text-emerald-800 underline hover:text-emerald-950"
          >
            Show all emails
          </button>
        </div>
      ) : null}

      <div className="surface-card space-y-4 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <SearchInput
            value={searchInput}
            onChange={(val) => {
              setSearchInput(val);
              debouncedSearch(val);
            }}
            placeholder="Search by prospect or campaign..."
            className="min-w-0 flex-1"
          />
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="control w-full shrink-0 sm:w-auto sm:min-w-[10.5rem]"
          >
            <option value="">All Statuses</option>
            <option value="sent">Sent</option>
            <option value="failed">Failed</option>
            <option value="pending">Pending</option>
            <option value="bounced">Bounced</option>
          </select>
        </div>
        <div className="grid grid-cols-1 gap-3 border-t border-gray-100 pt-3 sm:grid-cols-2 lg:grid-cols-[1.15fr_1.15fr_1.15fr_0.9fr_0.9fr]">
          <div className="min-w-0">
            <label className="label">User/Login</label>
            <select
              className="control w-full"
              value={filters.userId}
              onChange={(e) => updateFilter('userId', e.target.value)}
            >
              <option value="">All Users</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </select>
          </div>
          <div className="min-w-0">
            <label className="label">Campaign</label>
            <select
              className="control w-full"
              value={filters.campaignId}
              onChange={(e) => updateFilter('campaignId', e.target.value)}
            >
              <option value="">All Campaigns</option>
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>{c.campaign_name}</option>
              ))}
            </select>
          </div>
          <div className="min-w-0">
            <label className="label">Prospect List</label>
            <select
              className="control w-full"
              value={filters.groupId}
              onChange={(e) => updateFilter('groupId', e.target.value)}
            >
              <option value="">All Lists</option>
              {groupsFilter.map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </div>
          <div className="min-w-0">
            <label className="label">From</label>
            <input
              type="date"
              className="control w-full"
              value={filters.dateFrom}
              max={filters.dateTo || undefined}
              onChange={(e) => updateFilter('dateFrom', e.target.value)}
            />
          </div>
          <div className="min-w-0">
            <label className="label">To</label>
            <input
              type="date"
              className="control w-full"
              value={filters.dateTo}
              min={filters.dateFrom || undefined}
              onChange={(e) => updateFilter('dateTo', e.target.value)}
            />
          </div>
        </div>
        {hasActiveFilters ? (
          <div className="flex justify-end">
            <button type="button" onClick={clearFilters} className="btn-secondary text-sm">
              Clear Filters
            </button>
          </div>
        ) : null}
      </div>

      <div className="surface-card overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-12"><LoadingSpinner size="lg" /></div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="data-table min-w-[900px]">
                <thead className="sticky top-0 z-[1] border-b border-slate-200 bg-slate-50/95">
                  <tr>
                    <th className="px-6 py-3 font-medium">Prospect</th>
                    <th className="px-6 py-3 font-medium">Campaign</th>
                    <th className="px-6 py-3 font-medium">Sent By</th>
                    <th className="px-6 py-3 font-medium">Date</th>
                    <th className="px-6 py-3 font-medium">Status</th>
                    <th className="px-6 py-3 font-medium">Error Message</th>
                  </tr>
                </thead>
                <tbody>
                  {grouped
                    ? groups.map((group) => {
                        const key = (group.group_key || group.recipient_email || '').toLowerCase();
                        const open = expandedEmails.has(key);
                        const sendLabel = group.send_count === 1 ? '1 send' : `${group.send_count} sends`;
                        const emailLabel =
                          group.email_count > 1
                            ? `${group.email_count} emails`
                            : (group.recipient_email || group.emails?.[0] || '');
                        return (
                          <Fragment key={key}>
                            <tr
                              className="cursor-pointer hover:bg-slate-50/80"
                              onClick={() => toggleExpanded(key)}
                              aria-expanded={open}
                            >
                              <td className="px-6 py-4">
                                <div className="flex items-start gap-2">
                                  <span className="mt-0.5 text-slate-400">
                                    {open ? <FiChevronDown size={16} /> : <FiChevronRight size={16} />}
                                  </span>
                                  <div>
                                    <p className="font-medium text-gray-900">
                                      {group.recipient_name || group.recipient_email}
                                    </p>
                                    <p className="text-xs text-gray-500">{emailLabel}</p>
                                    <p className="mt-1 text-[11px] font-medium text-emerald-700">{sendLabel}</p>
                                  </div>
                                </div>
                              </td>
                              <td className="px-6 py-4 text-gray-600">
                                {group.latest_campaign_name || '—'}
                                {group.send_count > 1 ? (
                                  <p className="text-xs text-gray-400">Latest of {group.send_count}</p>
                                ) : null}
                              </td>
                              <td className="px-6 py-4 text-gray-400 text-sm">Click to expand</td>
                              <td className="px-6 py-4 text-gray-600 whitespace-nowrap">
                                {group.latest_sent_at ? formatDateTime(group.latest_sent_at) : '—'}
                              </td>
                              <td className="px-6 py-4">
                                {group.latest_status ? <StatusBadge status={group.latest_status} /> : '—'}
                              </td>
                              <td className="px-6 py-4 text-gray-400">—</td>
                            </tr>
                            {open
                              ? group.logs.map((log) => (
                                  <tr key={`${key}-${log.id}`} className="bg-slate-50/70">
                                    <td className="px-6 py-3 pl-12">
                                      <p className="text-xs font-medium text-gray-700">{log.recipient_email}</p>
                                      <p className="text-[11px] text-gray-400">Send detail</p>
                                    </td>
                                    <LogDetailCells log={log} />
                                  </tr>
                                ))
                              : null}
                          </Fragment>
                        );
                      })
                    : logs.map((log) => (
                        <tr key={log.id}>
                          <td className="px-6 py-4">
                            <p className="font-medium text-gray-900">{log.recipient_name || `Prospect #${log.recipient_id}`}</p>
                            <p className="text-xs text-gray-500">{log.recipient_email}</p>
                          </td>
                          <LogDetailCells log={log} />
                        </tr>
                      ))}
                  {rowCount === 0 && (
                    <tr>
                      <td colSpan={6} className="px-6 py-12 text-center text-gray-400">No email logs found</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="border-t border-gray-100 px-4">
              <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
            </div>
          </>
        )}
      </div>
    </PageShell>
  );
}
