import { useEffect, useState, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { FiActivity, FiCheckCircle, FiDownload, FiFilter, FiMail } from 'react-icons/fi';
import { logService, userService, campaignService, recipientGroupService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { hasPermission } from '../utils/permissions';
import SearchInput from '../components/ui/SearchInput';
import Pagination from '../components/ui/Pagination';
import StatusBadge from '../components/ui/StatusBadge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Button from '../components/ui/Button';
import PageHeader from '../components/ui/PageHeader';
import PageShell from '../components/ui/PageShell';
import { MetricCard } from '../components/ui/GrowthWorkspace';
import { formatDateTime, debounce } from '../utils/helpers';
import { deliveryStatusDisplay } from '../utils/verificationStatus';

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
      <td className="px-6 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge {...deliveryStatusDisplay(log.status, { errorMessage: log.error_message })} />
          {log.source === 'manual' && (
            <span className="text-xs font-medium text-primary-700">Outside mail</span>
          )}
        </div>
      </td>
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
  const [searchParams, setSearchParams] = useSearchParams();
  const category = searchParams.get('category') || '';
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [users, setUsers] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [groupsFilter, setGroupsFilter] = useState([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(null);
  const toast = useToast();
  const { user } = useAuth();
  const navigate = useNavigate();
  const pageSize = 10;

  useEffect(() => {
    if (hasPermission(user, 'members:read')) {
      userService.getAll().then(({ data }) => setUsers(data)).catch(() => {});
    }
    campaignService.getAll().then(({ data }) => setCampaigns(data)).catch(() => {});
    recipientGroupService.getAll().then(({ data }) => setGroupsFilter(data)).catch(() => {});
  }, [user]);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await logService.getAll({
        page,
        page_size: pageSize,
        search,
        status: statusFilter,
        category: category || undefined,
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
    } catch {
      toast.error('Failed to load email logs');
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter, category, filters, toast]);

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
    setSearchParams({});
    setPage(1);
  };
  const showAllEmails = () => {
    setSearchParams({});
    setPage(1);
  };
  const selectCategory = (next) => {
    const params = new URLSearchParams(searchParams);
    if (category === next) params.delete('category');
    else params.set('category', next);
    setSearchParams(params);
    setPage(1);
  };
  const openProspect = (group) => {
    const params = new URLSearchParams();
    if (category) params.set('category', category);
    params.set('key', group.group_key || group.recipient_email || '');
    navigate(`/logs/prospect?${params.toString()}`);
  };
  const downloadEmails = async (category) => {
    setDownloading(category);
    try {
      const { data } = await logService.exportCategory(category);
      const text = await data.text();
      const count = Math.max(0, text.trim().split(/\r?\n/).filter(Boolean).length - 1);
      if (count === 0) {
        toast.error(`No ${category} emails to download`);
        return;
      }
      const blob = new Blob([text], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${category}_emails.csv`;
      link.click();
      window.URL.revokeObjectURL(url);
      toast.success(`Downloaded ${count} ${category} email${count === 1 ? '' : 's'}`);
    } catch {
      toast.error('Download failed');
    } finally {
      setDownloading(null);
    }
  };
  const filterCount = (statusFilter ? 1 : 0) + (category ? 1 : 0) + Object.values(filters).filter(Boolean).length;
  const hasActiveFilters = filterCount > 0;
  const rowCount = grouped ? groups.length : logs.length;

  return (
    <PageShell maxWidth="max-w-[1440px]">
      <PageHeader
        eyebrow="Lead generation"
        title="Email logs"
        subtitle="Track all sent, failed, and pending emails."
        actions={
          <>
            <Button
              variant={category === 'risky' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => selectCategory('risky')}
            >
              Risky
            </Button>
            <Button
              variant={category === 'invalid' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => selectCategory('invalid')}
            >
              Invalid
            </Button>
            <Button
              variant={category === 'verified' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => selectCategory('verified')}
            >
              Verified
            </Button>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Total emails"
          value={total}
          hint={category ? 'Click to show all' : 'Matching current view'}
          icon={FiMail}
          onClick={showAllEmails}
          active={!category}
        />
        <MetricCard label="On this page" value={rowCount} hint="Loaded activity" tone="green" icon={FiActivity} />
        <MetricCard
          label="Verified emails"
          value={verifiedTotal}
          hint={category === 'verified' ? 'Click to clear' : 'Click to view verified'}
          tone="green"
          icon={FiCheckCircle}
          onClick={() => selectCategory('verified')}
          active={category === 'verified'}
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

      {category ? (
        <div className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-2.5 text-sm ${
          category === 'invalid'
            ? 'border-red-200 bg-red-50 text-red-950'
            : category === 'risky'
              ? 'border-amber-200 bg-amber-50 text-amber-950'
              : 'border-emerald-200 bg-emerald-50 text-emerald-900'
        }`}>
          <p>
            Showing all <span className="font-semibold capitalize">{category}</span> emails. Select a person to see every send.
          </p>
          <div className="flex shrink-0 items-center gap-3">
            <Button
              variant="secondary"
              size="sm"
              icon={FiDownload}
              loading={downloading === category}
              disabled={Boolean(downloading)}
              onClick={() => downloadEmails(category)}
            >
              Download
            </Button>
            <button
              type="button"
              onClick={showAllEmails}
              className="text-xs font-semibold underline"
            >
              Show all emails
            </button>
          </div>
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
              <table className={`data-table ${grouped ? 'min-w-full' : 'min-w-[900px]'}`}>
                <thead className="sticky top-0 z-[1] border-b border-slate-200 bg-slate-50/95">
                  <tr>
                    {grouped ? (
                      <>
                        <th className="px-6 py-3 font-medium">Name</th>
                        <th className="px-6 py-3 font-medium">Email</th>
                        <th className="px-6 py-3 font-medium">Company</th>
                      </>
                    ) : (
                      <>
                        <th className="px-6 py-3 font-medium">Prospect</th>
                        <th className="px-6 py-3 font-medium">Campaign</th>
                        <th className="px-6 py-3 font-medium">Sent By</th>
                        <th className="px-6 py-3 font-medium">Date</th>
                        <th className="px-6 py-3 font-medium">Status</th>
                        <th className="px-6 py-3 font-medium">Error Message</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {grouped
                    ? groups.map((group) => {
                        const key = (group.group_key || group.recipient_email || '').toLowerCase();
                        return (
                          <tr
                            key={key}
                            className="cursor-pointer hover:bg-slate-50/80"
                            onClick={() => openProspect(group)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault();
                                openProspect(group);
                              }
                            }}
                            tabIndex={0}
                          >
                            <td className="px-6 py-4">
                              <p className="font-medium text-gray-900">{group.recipient_name || group.recipient_email || '—'}</p>
                            </td>
                            <td className="px-6 py-4 text-gray-600">{group.recipient_email || '—'}</td>
                            <td className="px-6 py-4 text-gray-600">{group.company || '—'}</td>
                          </tr>
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
                      <td colSpan={grouped ? 3 : 6} className="px-6 py-12 text-center text-gray-400">No email logs found</td>
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
