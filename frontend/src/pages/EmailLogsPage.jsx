import { useEffect, useState, useCallback } from 'react';
import { logService } from '../services/services';
import { useToast } from '../hooks/useToast';
import SearchInput from '../components/ui/SearchInput';
import Pagination from '../components/ui/Pagination';
import StatusBadge from '../components/ui/StatusBadge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { formatDateTime, debounce } from '../utils/helpers';

export default function EmailLogsPage() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const toast = useToast();
  const pageSize = 10;

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await logService.getAll({
        page,
        page_size: pageSize,
        search,
        status: statusFilter,
      });
      setLogs(data.items);
      setTotal(data.total);
    } catch {
      toast.error('Failed to load email logs');
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter, toast]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const debouncedSearch = useCallback(debounce((val) => { setSearch(val); setPage(1); }, 400), []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Email Logs</h1>
        <p className="text-gray-500 mt-1">Track all sent, failed, and pending emails</p>
      </div>

      <div className="card">
        <div className="flex flex-wrap items-center gap-4">
          <SearchInput
            onChange={debouncedSearch}
            placeholder="Search by contact or campaign..."
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
          </select>
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
                    <th className="px-6 py-3 font-medium">Contact</th>
                    <th className="px-6 py-3 font-medium">Campaign</th>
                    <th className="px-6 py-3 font-medium">Date</th>
                    <th className="px-6 py-3 font-medium">Status</th>
                    <th className="px-6 py-3 font-medium">Error Message</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                      <td className="px-6 py-4">
                        <p className="font-medium text-gray-900">{log.recipient_name || `Contact #${log.recipient_id}`}</p>
                        <p className="text-xs text-gray-500">{log.recipient_email}</p>
                      </td>
                      <td className="px-6 py-4 text-gray-600">{log.campaign_name || `Campaign #${log.campaign_id}`}</td>
                      <td className="px-6 py-4 text-gray-600 whitespace-nowrap">{formatDateTime(log.sent_at)}</td>
                      <td className="px-6 py-4"><StatusBadge status={log.status} /></td>
                      <td className="px-6 py-4 text-gray-500 text-xs max-w-xs truncate">{log.error_message || '—'}</td>
                    </tr>
                  ))}
                  {logs.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-6 py-12 text-center text-gray-400">No email logs found</td>
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
