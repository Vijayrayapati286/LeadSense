import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiActivity, FiClock, FiLayers, FiPauseCircle, FiPlus } from 'react-icons/fi';
import { campaignService } from '../services/services';
import { useToast } from '../hooks/useToast';
import StatusBadge from '../components/ui/StatusBadge';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import SearchInput from '../components/ui/SearchInput';
import SlideOver from '../components/ui/SlideOver';
import Button from '../components/ui/Button';
import PageShell from '../components/ui/PageShell';
import PageHeader from '../components/ui/PageHeader';
import SurfaceCard from '../components/ui/SurfaceCard';
import SegmentedControl from '../components/ui/SegmentedControl';
import CampaignCard from '../components/campaigns/CampaignCard';
import { MetricCard } from '../components/ui/GrowthWorkspace';
import { formatDate, debounce } from '../utils/helpers';

const TABS = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'inactive', label: 'Inactive' },
];

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleteId, setDeleteId] = useState(null);
  const [tab, setTab] = useState('all');
  const [search, setSearch] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);
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

  const tabOptions = TABS.map((t) => ({ ...t, count: counts[t.key] }));

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
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <PageShell maxWidth="max-w-[1500px]">
      <PageHeader
        eyebrow="Lead generation"
        title="Campaigns"
        subtitle="Manage your email campaigns"
        actions={
          <>
            <Button variant="secondary" icon={FiClock} onClick={() => setHistoryOpen(true)}>
              History
            </Button>
            <Button variant="primary" icon={FiPlus} to="/campaigns/create">
              Create Campaign
            </Button>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard label="Total campaigns" value={counts.all} hint="In your workspace" icon={FiLayers} />
        <MetricCard label="Active" value={counts.active} hint="Currently running" tone="green" icon={FiActivity} />
        <MetricCard label="Inactive" value={counts.inactive} hint="Paused or completed" tone="amber" icon={FiPauseCircle} />
      </div>

      <SurfaceCard variant="filter">
        <div className="flex flex-wrap items-center gap-4">
          <SegmentedControl options={tabOptions} value={tab} onChange={setTab} />
          <SearchInput
            onChange={debouncedSearch}
            placeholder="Search by name or campaign ID..."
            className="min-w-[200px] flex-1"
          />
        </div>
      </SurfaceCard>

      {filteredCampaigns.length === 0 ? (
        <SurfaceCard className="py-12 text-center text-slate-400">
          {campaigns.length === 0
            ? 'No campaigns yet. Create your first campaign to get started.'
            : 'No campaigns match your filters.'}
        </SurfaceCard>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredCampaigns.map((c) => (
            <CampaignCard key={c.id} campaign={c} onDelete={setDeleteId} />
          ))}
        </div>
      )}

      <SlideOver
        isOpen={historyOpen}
        onClose={() => setHistoryOpen(false)}
        title="Campaign history"
        subtitle="Created dates, status, and send volume"
        width="lg"
      >
        {campaigns.length === 0 ? (
          <p className="py-10 text-center text-body-sm text-slate-400">No campaigns yet.</p>
        ) : (
          <div className="space-y-3">
            {[...campaigns]
              .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
              .map((c) => (
                <Link
                  key={c.id}
                  to={`/campaigns/${c.id}`}
                  onClick={() => setHistoryOpen(false)}
                  className="block rounded-xl border border-slate-200 p-4 transition hover:border-primary-300 hover:shadow-sm"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-slate-950">{c.campaign_name}</p>
                      <p className="mt-0.5 font-mono text-caption text-slate-400">{c.campaign_id}</p>
                    </div>
                    <StatusBadge status={c.status} />
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
                    <div>
                      <p className="text-micro font-semibold uppercase tracking-wider text-slate-400">Created</p>
                      <p className="mt-0.5 font-medium text-slate-800">{formatDate(c.created_at)}</p>
                    </div>
                    <div>
                      <p className="text-micro font-semibold uppercase tracking-wider text-slate-400">Emails sent</p>
                      <p className="mt-0.5 font-medium text-slate-800">{c.emails_sent}</p>
                    </div>
                  </div>
                </Link>
              ))}
          </div>
        )}
      </SlideOver>

      <ConfirmDialog
        isOpen={!!deleteId}
        onClose={() => setDeleteId(null)}
        onConfirm={() => handleDelete(deleteId)}
        title="Delete Campaign"
        message="Are you sure you want to delete this campaign? This action cannot be undone."
        confirmText="Delete"
      />
    </PageShell>
  );
}
