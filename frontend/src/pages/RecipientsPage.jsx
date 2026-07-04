import { useEffect, useState, useCallback } from 'react';
import { FiUpload, FiCheckSquare, FiSquare } from 'react-icons/fi';
import { recipientService } from '../services/services';
import { useToast } from '../hooks/useToast';
import SearchInput from '../components/ui/SearchInput';
import Pagination from '../components/ui/Pagination';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { debounce } from '../utils/helpers';

export default function RecipientsPage() {
  const [recipients, setRecipients] = useState([]);
  const [total, setTotal] = useState(0);
  const [selectedCount, setSelectedCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [industry, setIndustry] = useState('');
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const toast = useToast();
  const pageSize = 10;

  const loadRecipients = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await recipientService.getAll({ page, page_size: pageSize, search, industry });
      setRecipients(data.items);
      setTotal(data.total);
      setSelectedCount(data.selected_count);
      const selected = new Set(data.items.filter((r) => r.is_selected).map((r) => r.id));
      setSelectedIds(selected);
    } catch {
      toast.error('Failed to load recipients');
    } finally {
      setLoading(false);
    }
  }, [page, search, industry, toast]);

  useEffect(() => {
    loadRecipients();
  }, [loadRecipients]);

  const debouncedSearch = useCallback(debounce((val) => { setSearch(val); setPage(1); }, 400), []);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const { data } = await recipientService.uploadExcel(file);
      toast.success(data.message);
      loadRecipients();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const toggleSelect = async (id) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) newSelected.delete(id);
    else newSelected.add(id);
    setSelectedIds(newSelected);

    await recipientService.selectRecipients({ recipient_ids: [...newSelected] });
    localStorage.setItem('selectedRecipientIds', JSON.stringify([...newSelected]));
    setSelectedCount(newSelected.size);
  };

  const handleSelectAll = async () => {
    await recipientService.selectRecipients({ select_all: true });
    localStorage.setItem('selectedRecipientIds', JSON.stringify(recipients.map((r) => r.id)));
    toast.success('All recipients selected');
    loadRecipients();
  };

  const handleDeselectAll = async () => {
    await recipientService.selectRecipients({ deselect_all: true });
    localStorage.setItem('selectedRecipientIds', '[]');
    setSelectedIds(new Set());
    setSelectedCount(0);
    toast.success('All recipients deselected');
    loadRecipients();
  };

  const industries = [...new Set(recipients.map((r) => r.industry).filter(Boolean))];

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Recipients</h1>
          <p className="text-gray-500 mt-1">
            Manage your email recipient list
            {selectedCount > 0 && (
              <span className="ml-2 text-primary-600 font-medium">({selectedCount} selected)</span>
            )}
          </p>
        </div>
        <label className="btn-primary flex items-center gap-2 cursor-pointer">
          {uploading ? <LoadingSpinner size="sm" /> : <FiUpload size={18} />}
          Upload Excel
          <input type="file" accept=".xlsx,.xls" onChange={handleUpload} className="hidden" />
        </label>
      </div>

      {/* Filters */}
      <div className="card">
        <div className="flex flex-wrap items-center gap-4">
          <SearchInput
            onChange={debouncedSearch}
            placeholder="Search by name, email, or company..."
            className="flex-1 min-w-[200px]"
          />
          <select
            value={industry}
            onChange={(e) => { setIndustry(e.target.value); setPage(1); }}
            className="input-field w-auto"
          >
            <option value="">All Industries</option>
            {industries.map((ind) => (
              <option key={ind} value={ind}>{ind}</option>
            ))}
          </select>
          <button onClick={handleSelectAll} className="btn-secondary text-sm flex items-center gap-1">
            <FiCheckSquare size={16} /> Select All
          </button>
          <button onClick={handleDeselectAll} className="btn-secondary text-sm flex items-center gap-1">
            <FiSquare size={16} /> Deselect All
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden p-0">
        {loading ? (
          <div className="flex justify-center py-12"><LoadingSpinner size="lg" /></div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b">
                  <tr className="text-left text-gray-500">
                    <th className="px-4 py-3 w-10">
                      <input
                        type="checkbox"
                        checked={selectedIds.size === recipients.length && recipients.length > 0}
                        onChange={() => selectedIds.size === recipients.length ? handleDeselectAll() : handleSelectAll()}
                        className="rounded border-gray-300"
                      />
                    </th>
                    <th className="px-4 py-3 font-medium">Name</th>
                    <th className="px-4 py-3 font-medium">Email</th>
                    <th className="px-4 py-3 font-medium">Company</th>
                    <th className="px-4 py-3 font-medium">Designation</th>
                    <th className="px-4 py-3 font-medium">Industry</th>
                  </tr>
                </thead>
                <tbody>
                  {recipients.map((r) => (
                    <tr key={r.id} className={`border-b border-gray-50 hover:bg-gray-50/50 ${selectedIds.has(r.id) ? 'bg-primary-50/30' : ''}`}>
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(r.id)}
                          onChange={() => toggleSelect(r.id)}
                          className="rounded border-gray-300"
                        />
                      </td>
                      <td className="px-4 py-3 font-medium text-gray-900">{r.name}</td>
                      <td className="px-4 py-3 text-gray-600">{r.email}</td>
                      <td className="px-4 py-3 text-gray-600">{r.company || '—'}</td>
                      <td className="px-4 py-3 text-gray-600">{r.designation || '—'}</td>
                      <td className="px-4 py-3 text-gray-600">{r.industry || '—'}</td>
                    </tr>
                  ))}
                  {recipients.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-12 text-center text-gray-400">
                        No recipients found. Upload an Excel file to get started.
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
