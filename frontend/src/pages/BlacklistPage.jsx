import { useEffect, useState, useCallback } from 'react';
import { FiShield, FiRotateCcw } from 'react-icons/fi';
import { blacklistService } from '../services/services';
import { useToast } from '../hooks/useToast';
import SearchInput from '../components/ui/SearchInput';
import Pagination from '../components/ui/Pagination';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import StatusBadge from '../components/ui/StatusBadge';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { formatDateTime, debounce } from '../utils/helpers';

export default function BlacklistPage() {
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [overridingEntry, setOverridingEntry] = useState(null);
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

  const handleOverride = async () => {
    try {
      await blacklistService.override(overridingEntry.id);
      toast.success(`${overridingEntry.email} can now receive campaigns again`);
      loadEntries();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to override suppression');
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <FiShield size={22} /> Blacklisted Emails
        </h1>
        <p className="text-gray-500 mt-1">
          Addresses automatically suppressed after a permanent (hard) bounce, a complaint, or too many
          temporary (soft) bounces in a row. Excluded from all future campaigns and follow-ups until an
          admin explicitly overrides the entry below.
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
                    <th className="px-4 py-3 font-medium">Bounce Type</th>
                    <th className="px-4 py-3 font-medium">SMTP Error</th>
                    <th className="px-4 py-3 font-medium">Campaign</th>
                    <th className="px-4 py-3 font-medium">Date Blacklisted</th>
                    <th className="px-4 py-3 w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr key={entry.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                      <td className="px-4 py-3 font-medium text-gray-900">{entry.email}</td>
                      <td className="px-4 py-3 text-gray-600">{entry.company || '—'}</td>
                      <td className="px-4 py-3"><StatusBadge status={entry.reason} /></td>
                      <td className="px-4 py-3 text-gray-600">{entry.bounce_type || '—'}</td>
                      <td className="px-4 py-3 text-gray-600" title={entry.detail || ''}>
                        {entry.smtp_code || '—'}
                        {entry.detail && <p className="text-xs text-gray-400 truncate max-w-[200px]">{entry.detail}</p>}
                      </td>
                      <td className="px-4 py-3 text-gray-600">{entry.campaign_name || '—'}</td>
                      <td className="px-4 py-3 text-gray-600">{formatDateTime(entry.created_at)}</td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => setOverridingEntry(entry)}
                          className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-primary-600"
                          title="Admin override — allow sending to this address again"
                        >
                          <FiRotateCcw size={15} />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {entries.length === 0 && (
                    <tr>
                      <td colSpan={8} className="px-4 py-12 text-center text-gray-400">
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

      <ConfirmDialog
        isOpen={!!overridingEntry}
        onClose={() => setOverridingEntry(null)}
        onConfirm={handleOverride}
        title="Admin Override"
        message={`Allow future campaigns and follow-ups to be sent to "${overridingEntry?.email}" again? Only do this if you've confirmed the underlying delivery issue is resolved — the suppression history is kept either way.`}
        confirmText="Override & Un-suppress"
        variant="primary"
      />
    </div>
  );
}
