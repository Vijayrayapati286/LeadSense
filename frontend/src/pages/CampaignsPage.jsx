import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiPlus, FiEdit2, FiTrash2, FiArrowRight } from 'react-icons/fi';
import { campaignService } from '../services/services';
import { useToast } from '../hooks/useToast';
import StatusBadge from '../components/ui/StatusBadge';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import SearchInput from '../components/ui/SearchInput';
import { formatDate, debounce } from '../utils/helpers';

const TABS = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'inactive', label: 'Inactive' },
];

function CampaignCard({ campaign, onDelete }) {
  const c = campaign;

  return (
    <div className="card p-5 border-t-4 border-t-primary-400 hover:shadow-md transition-shadow flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold text-gray-900 truncate">{c.campaign_name}</h3>
          <p className="text-sm text-gray-500 mt-0.5 truncate">
            {c.subject || c.target_audience || c.description || 'No description'}
          </p>
          <p className="text-xs text-gray-400 font-mono mt-1 truncate">
            {c.owner} · {c.campaign_id}
          </p>
        </div>
        <div className="shrink-0">
          <StatusBadge status={c.status} />
        </div>
      </div>

      {(c.department || c.target_audience) && (
        <div className="flex flex-wrap gap-1.5">
          {c.department && (
            <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-blue-50 text-blue-700 border border-blue-100">
              {c.department}
            </span>
          )}
          {c.target_audience && (
            <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-amber-50 text-amber-700 border border-amber-100">
              {c.target_audience}
            </span>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="bg-gray-50 rounded-lg py-3 text-center">
          <div className="text-lg font-bold text-gray-900">{c.emails_sent}</div>
          <div className="text-[11px] uppercase tracking-wide text-gray-400 mt-0.5">Emails Sent</div>
        </div>
        <div className="bg-gray-50 rounded-lg py-3 text-center">
          <div className="text-sm font-semibold text-gray-900">{formatDate(c.created_at)}</div>
          <div className="text-[11px] uppercase tracking-wide text-gray-400 mt-0.5">Created</div>
        </div>
      </div>

      <div className="flex items-center justify-between pt-3 border-t border-gray-100">
        <div className="flex items-center gap-2">
          <Link
            to={`/campaigns/${c.id}/edit`}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
          >
            <FiEdit2 size={13} /> Edit
          </Link>
          <button
            onClick={() => onDelete(c.id)}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-300 text-gray-600 hover:bg-red-50 hover:text-red-600 hover:border-red-200"
          >
            <FiTrash2 size={13} /> Delete
          </button>
        </div>
        <Link
          to={`/campaigns/${c.id}`}
          className="inline-flex items-center gap-1 text-sm font-medium text-primary-600 hover:text-primary-700"
        >
          Details <FiArrowRight size={14} />
        </Link>
      </div>
    </div>
  );
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleteId, setDeleteId] = useState(null);
  const [tab, setTab] = useState('all');
  const [search, setSearch] = useState('');
  const toast = useToast();

  useEffect(() => {
    loadCampaigns();
  }, []);

  const loadCampaigns = async () => {
    try {
      const { data } = await campaignService.getAll();
      setCampaigns(data);
    } catch {
      toast.error('Failed to load campaigns');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await campaignService.delete(id);
      setCampaigns((prev) => prev.filter((c) => c.id !== id));
      toast.success('Campaign deleted');
    } catch {
      toast.error('Failed to delete campaign');
    } finally {
      setDeleteId(null);
    }
  };

  const debouncedSearch = useCallback(debounce((val) => setSearch(val), 300), []);

  const counts = useMemo(
    () => ({
      all: campaigns.length,
      active: campaigns.filter((c) => c.status?.toLowerCase() === 'active').length,
      inactive: campaigns.filter((c) => c.status?.toLowerCase() !== 'active').length,
    }),
    [campaigns]
  );

  const filteredCampaigns = useMemo(() => {
    const term = search.trim().toLowerCase();
    return campaigns.filter((c) => {
      const isActive = c.status?.toLowerCase() === 'active';
      const matchesTab = tab === 'all' || (tab === 'active' ? isActive : !isActive);
      const matchesSearch =
        !term ||
        c.campaign_name.toLowerCase().includes(term) ||
        c.campaign_id.toLowerCase().includes(term);
      return matchesTab && matchesSearch;
    });
  }, [campaigns, tab, search]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Campaigns</h1>
          <p className="text-gray-500 mt-1">Manage your email campaigns</p>
        </div>
        <Link to="/campaigns/create" className="btn-primary flex items-center gap-2">
          <FiPlus size={18} />
          Create Campaign
        </Link>
      </div>

      <div className="card">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  tab === t.key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {t.label} ({counts[t.key]})
              </button>
            ))}
          </div>
          <SearchInput
            onChange={debouncedSearch}
            placeholder="Search by name or campaign ID..."
            className="flex-1 min-w-[200px]"
          />
        </div>
      </div>

      {filteredCampaigns.length === 0 ? (
        <div className="card text-center py-12 text-gray-400">
          {campaigns.length === 0
            ? 'No campaigns yet. Create your first campaign to get started.'
            : 'No campaigns match your filters.'}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {filteredCampaigns.map((c) => (
            <CampaignCard key={c.id} campaign={c} onDelete={setDeleteId} />
          ))}
        </div>
      )}

      <ConfirmDialog
        isOpen={!!deleteId}
        onClose={() => setDeleteId(null)}
        onConfirm={() => handleDelete(deleteId)}
        title="Delete Campaign"
        message="Are you sure you want to delete this campaign? This action cannot be undone."
        confirmText="Delete"
      />
    </div>
  );
}
