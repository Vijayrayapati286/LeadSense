import { useEffect, useState, useCallback } from 'react';
import { logService, userService, campaignService, recipientGroupService } from '../services/services';
import { useToast } from '../hooks/useToast';
import SearchInput from '../components/ui/SearchInput';
import Pagination from '../components/ui/Pagination';
import StatusBadge from '../components/ui/StatusBadge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { formatDateTime, debounce } from '../utils/helpers';

const EMPTY_FILTERS = { userId: '', campaignId: '', groupId: '', dateFrom: '', dateTo: '' };

export default function EmailLogsPage() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [users, setUsers] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();
  const pageSize = 10;

  useEffect(() => {
    userService.getAll().then(({ data }) => setUsers(data)).catch(() => {});
    campaignService.getAll().then(({ data }) => setCampaigns(data)).catch(() => {});
    recipientGroupService.getAll().then(({ data }) => setGroups(data)).catch(() => {});
  }, []);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await logService.getAll({
        page,
        page_size: pageSize,
        search,
        status: statusFilter,
        user_id: filters.userId || undefined,
        campaign_id: filters.campaignId || undefined,
        group_id: filters.groupId || undefined,
        date_from: filters.dateFrom || undefined,
        date_to: filters.dateTo || undefined,
      });
      setLogs(data.items);
      setTotal(data.total);
    } catch {
      toast.error('Failed to load email logs');
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter, filters, toast]);

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
    setPage(1);
  };
  const hasActiveFilters = statusFilter || Object.values(filters).some(Boolean);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Email Logs</h1>
        <p className="text-gray-500 mt-1">Track all sent, failed, and pending emails</p>
      </div>

      <div className="card space-y-3">
        <div className="flex flex-wrap items-center gap-4">
          <SearchInput
            onChange={debouncedSearch}
            placeholder="Search by prospect or campaign..."
            className="flex-1 min-w-[200px]"
          />
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="input-field w-auto"
          >
            <option value="">All Statuses</option>
            <option value="sent">Sent</option>
            <option value="failed">Failed</option>
            <option value="pending">Pending</option>
            <option value="bounced">Bounced</option>
          </select>
        </div>
        <div className="flex flex-wrap items-end gap-3 pt-2 border-t border-gray-100">
          <div>
            <label className="label">User/Login</label>
            <select
              className="input-field w-auto"
              value={filters.userId}
              onChange={(e) => updateFilter('userId', e.target.value)}
            >
              <option value="">All Users</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Campaign</label>
            <select
              className="input-field w-auto"
              value={filters.campaignId}
              onChange={(e) => updateFilter('campaignId', e.target.value)}
            >
              <option value="">All Campaigns</option>
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>{c.campaign_name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Prospect List</label>
            <select
              className="input-field w-auto"
              value={filters.groupId}
              onChange={(e) => updateFilter('groupId', e.target.value)}
            >
              <option value="">All Lists</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">From</label>
            <input
              type="date"
              className="input-field w-auto"
              value={filters.dateFrom}
              max={filters.dateTo || undefined}
              onChange={(e) => updateFilter('dateFrom', e.target.value)}
            />
          </div>
          <div>
            <label className="label">To</label>
            <input
              type="date"
              className="input-field w-auto"
              value={filters.dateTo}
              min={filters.dateFrom || undefined}
              onChange={(e) => updateFilter('dateTo', e.target.value)}
            />
          </div>
          {hasActiveFilters && (
            <button onClick={clearFilters} className="btn-secondary text-sm">Clear Filters</button>
          )}
        </div>
      </div>

      <div className="card overflow-hidden p-0">
        {loading ? (
          <div className="flex justify-center py-12"><LoadingSpinner size="lg" /></div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b">
                  <tr className="text-left text-gray-500">
                    <th className="px-6 py-3 font-medium">Prospect</th>
                    <th className="px-6 py-3 font-medium">Campaign</th>
                    <th className="px-6 py-3 font-medium">Sent By</th>
                    <th className="px-6 py-3 font-medium">Date</th>
                    <th className="px-6 py-3 font-medium">Status</th>
                    <th className="px-6 py-3 font-medium">Error Message</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                      <td className="px-6 py-4">
                        <p className="font-medium text-gray-900">{log.recipient_name || `Prospect #${log.recipient_id}`}</p>
                        <p className="text-xs text-gray-500">{log.recipient_email}</p>
                      </td>
                      <td className="px-6 py-4 text-gray-600">{log.campaign_name || `Campaign #${log.campaign_id}`}</td>
                      <td className="px-6 py-4 text-gray-600">
                        {log.sender_name || <span className="text-gray-400">—</span>}
                        {log.sender_email && <p className="text-xs text-gray-400">{log.sender_email}</p>}
                      </td>
                      <td className="px-6 py-4 text-gray-600 whitespace-nowrap">{formatDateTime(log.sent_at)}</td>
                      <td className="px-6 py-4"><StatusBadge status={log.status} /></td>
                      <td className="px-6 py-4 text-gray-500 text-xs max-w-xs truncate">{log.error_message || '—'}</td>
                    </tr>
                  ))}
                  {logs.length === 0 && (
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
    </div>
  );
}
