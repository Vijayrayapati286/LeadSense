import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FiCheckCircle, FiMail, FiPackage, FiPlus, FiSearch, FiTrash2 } from 'react-icons/fi';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Pagination from '../components/ui/Pagination';
import PageHeader from '../components/ui/PageHeader';
import PageShell from '../components/ui/PageShell';
import SearchInput from '../components/ui/SearchInput';
import SurfaceCard from '../components/ui/SurfaceCard';
import { MetricCard } from '../components/ui/GrowthWorkspace';
import { useToast } from '../hooks/useToast';
import { offeringsService } from '../services/services';
import { debounce } from '../utils/helpers';

const PAGE_SIZE = 12;

export default function OfferingsPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await offeringsService.list({
        search: search || undefined,
        page,
        limit: PAGE_SIZE,
      });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load offerings');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, page]);

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

  async function handleDelete(id) {
    setDeleting(true);
    try {
      await offeringsService.remove(id);
      toast.success('Offering deleted');
      setDeleteTarget(null);
      const remaining = total - 1;
      const lastPage = Math.max(1, Math.ceil(remaining / PAGE_SIZE));
      if (page > lastPage) {
        setPage(lastPage);
      } else {
        load();
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to delete offering');
    } finally {
      setDeleting(false);
    }
  }

  const activeCount = items.filter((item) => (item.status || '').toLowerCase() === 'active').length;
  const withEmailCount = items.filter((item) => item.email_template?.subject && item.email_template?.body).length;

  return (
    <PageShell maxWidth="max-w-[1440px]">
      <PageHeader
        eyebrow="Offering studio"
        title="Offerings"
        subtitle="Define what you sell and match it against your ICP Database."
        actions={
        <button
          type="button"
          onClick={() => navigate('/offerings/new')}
          className="btn-primary inline-flex items-center gap-2 shadow-lg shadow-primary-200/60"
        >
          <FiPlus size={16} /> Create Offering
        </button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard label="Total offerings" value={(total || 0).toLocaleString()} hint="In your workspace" icon={FiPackage} />
        <MetricCard label="Active this page" value={activeCount} hint="Ready to match" tone="green" icon={FiCheckCircle} />
        <MetricCard label="Email ready" value={withEmailCount} hint="With outreach template" tone="amber" icon={FiMail} />
      </div>

      <SurfaceCard variant="filter">
        <SearchInput
          value={searchInput}
          placeholder="Search offerings..."
          onChange={(val) => {
            setSearchInput(val);
            debouncedSearch(val);
          }}
        />
      </SurfaceCard>

      {loading ? (
        <div className="flex justify-center py-16">
          <LoadingSpinner />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-gray-300 bg-white px-6 py-16 text-center">
          <FiSearch className="mx-auto text-gray-300 mb-3" size={32} />
          <h2 className="text-lg font-semibold text-gray-900">No offerings yet</h2>
          <p className="text-sm text-gray-500 mt-2 max-w-md mx-auto">
            Define what you&apos;re selling and let AI find your best ICP candidates.
          </p>
          <button
            type="button"
            onClick={() => navigate('/offerings/new')}
            className="mt-5 inline-flex items-center gap-2 rounded-lg bg-primary-600 text-white px-4 py-2 text-sm font-medium hover:bg-primary-700"
          >
            <FiPlus size={16} /> Create Offering
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((o) => (
            <div
              key={o.id}
              className="rounded-2xl border border-gray-200 bg-white p-5 hover:border-primary-200 transition-colors"
            >
              <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                <div className="min-w-0">
                  <h2 className="text-lg font-semibold text-gray-900">{o.name}</h2>
                  <p className="text-sm text-gray-500 mt-1">
                    {o.short_description || o.description || 'No description'}
                  </p>
                  <div className="flex flex-wrap gap-4 mt-4 text-sm text-gray-600">
                    <span>
                      <strong className="text-gray-900">
                        {(o.total_matches || 0).toLocaleString()}
                      </strong>{' '}
                      ICP Records
                    </span>
                    <span>
                      <strong className="text-emerald-700">
                        {(o.strong_matches || 0).toLocaleString()}
                      </strong>{' '}
                      Strong Matches
                    </span>
                    <span>
                      <strong className="text-amber-700">
                        {(o.potential_matches || 0).toLocaleString()}
                      </strong>{' '}
                      Potential
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 shrink-0">
                  <Link
                    to={`/offerings/${o.id}`}
                    className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    View
                  </Link>
                  <Link
                    to={`/offerings/${o.id}?tab=matching`}
                    className="rounded-lg bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700"
                  >
                    Find Candidates
                  </Link>
                  <Link
                    to={`/offerings/${o.id}/edit`}
                    className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Edit
                  </Link>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(o)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50"
                  >
                    <FiTrash2 size={14} /> Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
          <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
        </div>
      )}

      <ConfirmDialog
        isOpen={Boolean(deleteTarget)}
        onClose={() => !deleting && setDeleteTarget(null)}
        onConfirm={() => handleDelete(deleteTarget?.id)}
        title="Delete offering?"
        message={`This will permanently remove "${deleteTarget?.name || 'this offering'}" and all its match data.`}
        confirmText={deleting ? 'Deleting…' : 'Delete offering'}
      />
    </PageShell>
  );
}
