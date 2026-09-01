import { useCallback, useEffect, useState } from 'react';
import { FiDatabase, FiPlus } from 'react-icons/fi';
import LoadingSpinner from '../ui/LoadingSpinner';
import Modal from '../ui/Modal';
import Pagination from '../ui/Pagination';
import SearchInput from '../ui/SearchInput';
import SlideOver from '../ui/SlideOver';
import { useToast } from '../../hooks/useToast';
import { icpService } from '../../services/services';
import { debounce } from '../../utils/helpers';

const PAGE_SIZE = 12;

export default function IcpDatabasePicker({
  isOpen,
  onClose,
  selectedIds,
  onToggle,
  onConfirm,
}) {
  const toast = useToast();
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState({ name: '', company_name: '', designation: '', linkedin_url: '' });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!isOpen) return;
    setLoading(true);
    try {
      const data = await icpService.list({
        page,
        limit: PAGE_SIZE,
        sort_by: 'name',
        sort_order: 'asc',
        search: search || undefined,
      });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load ICP database');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, page, search]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!isOpen) {
      setSearch('');
      setSearchInput('');
      setPage(1);
    }
  }, [isOpen]);

  const debouncedSearch = useCallback(
    debounce((val) => {
      setSearch(val);
      setPage(1);
    }, 400),
    [],
  );

  const pageIds = items.map((row) => row.id);
  const allOnPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
  const someOnPageSelected = pageIds.some((id) => selectedIds.has(id));

  function togglePage(checked) {
    pageIds.forEach((id) => onToggle(id, checked));
  }

  async function handleAdd() {
    if (!addForm.name?.trim() && !addForm.linkedin_url?.trim()) {
      toast.error('Name or LinkedIn URL is required');
      return;
    }
    setSaving(true);
    try {
      const created = await icpService.create(addForm);
      toast.success('ICP record added');
      onToggle(created.id, true);
      setAddOpen(false);
      setAddForm({ name: '', company_name: '', designation: '', linkedin_url: '' });
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to create record');
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <SlideOver
        isOpen={isOpen}
        onClose={onClose}
        title="ICP Database"
        subtitle="Pick contacts from your full database to include in this offer"
        width="3xl"
      >
        <div className="flex h-full flex-col -mx-1 -my-1">
          <div className="flex flex-wrap items-center gap-2 pb-4">
            <SearchInput
              className="flex-1 min-w-[200px]"
              value={searchInput}
              placeholder="Search name, company, designation…"
              onChange={(val) => {
                setSearchInput(val);
                debouncedSearch(val);
              }}
            />
            <button
              type="button"
              onClick={() => setAddOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              <FiPlus size={14} /> Add record
            </button>
          </div>

          {selectedIds.size > 0 ? (
            <p className="mb-3 text-sm text-primary-700 font-medium">
              {selectedIds.size} contact{selectedIds.size === 1 ? '' : 's'} selected from database
            </p>
          ) : null}

          <div className="flex-1 min-h-0 overflow-auto rounded-xl border border-gray-200">
            {loading && items.length === 0 ? (
              <div className="flex justify-center py-16">
                <LoadingSpinner />
              </div>
            ) : items.length === 0 ? (
              <div className="py-16 text-center text-sm text-gray-500">
                <FiDatabase className="mx-auto mb-2 text-gray-300" size={28} />
                No ICP records found. Add a record or adjust your search.
              </div>
            ) : (
              <table className="min-w-full text-sm">
                <thead className="sticky top-0 bg-gray-50 border-b border-gray-200">
                  <tr className="text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="w-10 px-3 py-2.5">
                      <input
                        type="checkbox"
                        className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                        checked={allOnPageSelected}
                        ref={(el) => {
                          if (el) el.indeterminate = someOnPageSelected && !allOnPageSelected;
                        }}
                        onChange={(e) => togglePage(e.target.checked)}
                        aria-label="Select all on page"
                      />
                    </th>
                    <th className="px-3 py-2.5">Name</th>
                    <th className="px-3 py-2.5">Company</th>
                    <th className="px-3 py-2.5">Designation</th>
                    <th className="px-3 py-2.5">Industry</th>
                  </tr>
                </thead>
                <tbody className={`divide-y divide-gray-100 ${loading ? 'opacity-60' : ''}`}>
                  {items.map((row) => (
                    <tr
                      key={row.id}
                      className={`hover:bg-gray-50 cursor-pointer ${
                        selectedIds.has(row.id) ? 'bg-primary-50/50' : ''
                      }`}
                      onClick={() => onToggle(row.id, !selectedIds.has(row.id))}
                    >
                      <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                          checked={selectedIds.has(row.id)}
                          onChange={(e) => onToggle(row.id, e.target.checked)}
                          aria-label={`Select ${row.name || 'record'}`}
                        />
                      </td>
                      <td className="px-3 py-2.5 font-medium text-gray-900">{row.name || '—'}</td>
                      <td className="px-3 py-2.5 text-gray-600">{row.company_name || '—'}</td>
                      <td className="px-3 py-2.5 text-gray-600">{row.designation || '—'}</td>
                      <td className="px-3 py-2.5 text-gray-600 capitalize">{row.industry || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {total > 0 ? (
            <div className="mt-3 border-t border-gray-100 pt-2">
              <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
            </div>
          ) : null}

          <div className="mt-4 flex justify-end gap-2 border-t border-gray-100 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onConfirm}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
            >
              Add selected ({selectedIds.size})
            </button>
          </div>
        </div>
      </SlideOver>

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
              Save &amp; select
            </button>
          </div>
        </div>
      </Modal>
    </>
  );
}
