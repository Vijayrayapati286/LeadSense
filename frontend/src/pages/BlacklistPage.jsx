import { useEffect, useState, useCallback } from 'react';
import { FiShield } from 'react-icons/fi';
import { blacklistService } from '../services/services';
import { useToast } from '../hooks/useToast';
import SearchInput from '../components/ui/SearchInput';
import Pagination from '../components/ui/Pagination';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import StatusBadge from '../components/ui/StatusBadge';
import { formatDateTime, debounce } from '../utils/helpers';

export default function BlacklistPage() {
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const toast = useToast();
  const pageSize = 10;

  const loadEntries = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await blacklistService.getAll({ page, page_size: pageSize, search });
      setEntries(data.items);
      setTotal(data.total);
    } catch {
      toast.error('Failed to load blacklist');
    } finally {
      setLoading(false);
    }
  }, [page, search, toast]);

  useEffect(() => {
    loadEntries();
  }, [loadEntries]);

  const debouncedSearch = useCallback(debounce((val) => { setSearch(val); setPage(1); }, 400), []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <FiShield size={22} /> Blacklisted Emails
        </h1>
        <p className="text-gray-500 mt-1">
          Addresses automatically suppressed after a permanent delivery failure or complaint. This list is view-only — entries cannot be edited or removed to protect sender reputation.
        </p>
      </div>

      <div className="card">
        <SearchInput
          onChange={debouncedSearch}
          placeholder="Search by email or company..."
          className="max-w-md"
        />
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
                    <th className="px-4 py-3 font-medium">Email</th>
                    <th className="px-4 py-3 font-medium">Company</th>
                    <th className="px-4 py-3 font-medium">Reason</th>
                    <th className="px-4 py-3 font-medium">Campaign</th>
                    <th className="px-4 py-3 font-medium">Date Blacklisted</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr key={entry.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                      <td className="px-4 py-3 font-medium text-gray-900">{entry.email}</td>
                      <td className="px-4 py-3 text-gray-600">{entry.company || '—'}</td>
                      <td className="px-4 py-3"><StatusBadge status={entry.reason} /></td>
                      <td className="px-4 py-3 text-gray-600">{entry.campaign_name || '—'}</td>
                      <td className="px-4 py-3 text-gray-600">{formatDateTime(entry.created_at)}</td>
                    </tr>
                  ))}
                  {entries.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-12 text-center text-gray-400">
                        No blacklisted emails yet.
                      </td>
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
