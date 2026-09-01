import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  FiActivity,
  FiAlertCircle,
  FiArrowRight,
  FiClock,
  FiDownload,
  FiMail,
  FiSend,
  FiTrendingDown,
  FiZap,
} from 'react-icons/fi';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { campaignService, dashboardService, userService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import StatusBadge from '../components/ui/StatusBadge';
import Button from '../components/ui/Button';
import PageShell from '../components/ui/PageShell';
import PageHeader from '../components/ui/PageHeader';
import SurfaceCard from '../components/ui/SurfaceCard';
import MetricCard from '../components/ui/MetricCard';
import PanelHeader from '../components/ui/PanelHeader';
import FilterBar, { FilterField } from '../components/ui/FilterBar';
import { CHART_COLORS } from '../design-tokens';
import { formatDate } from '../utils/helpers';

const EMPTY_FILTERS = { userId: '', campaignId: '', dateFrom: '', dateTo: '' };

const STAT_META = [
  { key: 'total_campaigns', label: 'Total campaigns', icon: FiMail, tone: 'blue', note: 'All time' },
  { key: 'emails_sent', label: 'Emails sent', icon: FiSend, tone: 'green', note: 'Delivered outreach' },
  { key: 'pending_emails', label: 'Pending emails', icon: FiClock, tone: 'amber', note: 'Pending delivery' },
  { key: 'failed_emails', label: 'Failed emails', icon: FiAlertCircle, tone: 'red', note: 'Needs attention' },
  { key: 'active_campaigns', label: 'Active campaigns', icon: FiActivity, tone: 'cyan', note: 'Running now' },
  { key: 'ai_generated_emails', label: 'AI generated', icon: FiZap, tone: 'violet', note: 'This period' },
];

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [users, setUsers] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const { user } = useAuth();
  const toast = useToast();

  useEffect(() => {
    userService.getAll().then(({ data: result }) => setUsers(result)).catch(() => {});
    campaignService.getAll().then(({ data: result }) => setCampaigns(result)).catch(() => {});
  }, []);

  const buildParams = () => ({
    user_id: filters.userId || undefined,
    campaign_id: filters.campaignId || undefined,
    date_from: filters.dateFrom || undefined,
    date_to: filters.dateTo || undefined,
  });

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const { data: result } = await dashboardService.getStats(buildParams());
      setData(result);
    } catch {
      toast.error('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, toast]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const updateFilter = (field, value) => setFilters((previous) => ({ ...previous, [field]: value }));
  const hasActiveFilters = Object.values(filters).some(Boolean);

  const handleExportReport = async () => {
    setExporting(true);
    try {
      const response = await dashboardService.exportReport(buildParams());
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'leadsense_report.xlsx';
      link.click();
      window.URL.revokeObjectURL(url);
    } catch {
      toast.error('Failed to export report');
    } finally {
      setExporting(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!data) {
    return (
      <SurfaceCard className="mx-auto mt-20 max-w-md p-8 text-center">
        <FiAlertCircle className="mx-auto text-rose-500" size={28} />
        <h1 className="mt-3 font-bold text-slate-900">Dashboard unavailable</h1>
        <p className="mt-1 text-body-sm text-slate-500">We couldn&apos;t load your campaign summary.</p>
        <Button className="mt-5" onClick={loadDashboard}>Try again</Button>
      </SurfaceCard>
    );
  }

  const {
    stats = {},
    emails_per_day: emailsPerDay = [],
    campaign_status: campaignStatus = [],
    recent_activity: recentActivity = [],
    recent_campaigns: recentCampaigns = [],
  } = data;
  const campaignTotal = campaignStatus.reduce((sum, item) => sum + Number(item.count || 0), 0);
  const firstName = user?.name?.trim().split(/\s+/)[0] || 'there';

  return (
    <PageShell>
      <PageHeader
        title={<>Welcome back, {firstName}! <span aria-hidden="true">👋</span></>}
        subtitle="Here's what's happening with your campaigns today."
        actions={
          <Button icon={FiDownload} loading={exporting} onClick={handleExportReport}>
            Export report
          </Button>
        }
      />

      <FilterBar
        actions={
          <>
            {hasActiveFilters && (
              <button type="button" onClick={() => setFilters(EMPTY_FILTERS)} className="h-full whitespace-nowrap rounded-xl px-3 text-xs font-semibold text-slate-500 transition hover:bg-slate-100">
                Clear
              </button>
            )}
            {loading && <LoadingSpinner size="sm" />}
          </>
        }
      >
        <FilterField label="User / Login">
          <select className="control py-2 text-xs" value={filters.userId} onChange={(event) => updateFilter('userId', event.target.value)}>
            <option value="">All users</option>
            {users.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </FilterField>
        <FilterField label="Campaign">
          <select className="control py-2 text-xs" value={filters.campaignId} onChange={(event) => updateFilter('campaignId', event.target.value)}>
            <option value="">All campaigns</option>
            {campaigns.map((item) => <option key={item.id} value={item.id}>{item.campaign_name}</option>)}
          </select>
        </FilterField>
        <FilterField label="From">
          <input type="date" className="control py-2 text-xs" value={filters.dateFrom} max={filters.dateTo || undefined} onChange={(event) => updateFilter('dateFrom', event.target.value)} />
        </FilterField>
        <FilterField label="To">
          <input type="date" className="control py-2 text-xs" value={filters.dateTo} min={filters.dateFrom || undefined} onChange={(event) => updateFilter('dateTo', event.target.value)} />
        </FilterField>
      </FilterBar>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        {STAT_META.map((item, index) => (
          <MetricCard key={item.key} {...item} index={index} value={stats[item.key]} />
        ))}
        <MetricCard
          label="Bounce rate"
          value={`${stats.bounce_rate ?? 0}%`}
          icon={FiTrendingDown}
          tone="red"
          note={`${stats.hard_bounces ?? 0} hard · ${stats.soft_bounces_pending ?? 0} soft`}
          index={6}
        />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_.9fr]">
        <SurfaceCard>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-900">Emails sent per day</h2>
            <span className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-micro text-slate-500">Current period</span>
          </div>
          <div className="mt-5 h-[270px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={emailsPerDay} margin={{ top: 10, right: 8, left: -24, bottom: 0 }}>
                <defs>
                  <linearGradient id="emailArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3578f6" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#3578f6" stopOpacity={0.01} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="#eef2f7" />
                <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} dy={8} />
                <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#94a3b8' }} />
                <Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #e2e8f0', boxShadow: '0 8px 24px rgba(15,23,42,.08)', fontSize: 12 }} />
                <Area type="monotone" dataKey="count" stroke="#3578f6" strokeWidth={2.5} fill="url(#emailArea)" activeDot={{ r: 5, fill: '#3578f6', stroke: '#fff', strokeWidth: 2 }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </SurfaceCard>

        <SurfaceCard>
          <h2 className="text-sm font-bold text-slate-900">Campaign status</h2>
          <div className="mt-3 grid min-h-[285px] items-center gap-4 sm:grid-cols-[1fr_.9fr]">
            <div className="relative h-[245px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={campaignStatus} dataKey="count" nameKey="status" innerRadius={64} outerRadius={92} paddingAngle={2} stroke="none">
                    {campaignStatus.map((item, index) => <Cell key={`${item.status}-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #e2e8f0', fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-bold text-slate-950">{campaignTotal}</span>
                <span className="text-micro text-slate-400">Total</span>
              </div>
            </div>
            <div className="space-y-3">
              {campaignStatus.map((item, index) => {
                const percent = campaignTotal ? Math.round((Number(item.count || 0) / campaignTotal) * 100) : 0;
                return (
                  <div key={item.status} className="flex items-center gap-2 text-xs">
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: CHART_COLORS[index % CHART_COLORS.length] }} />
                    <span className="min-w-0 flex-1 truncate capitalize text-slate-600">{item.status}</span>
                    <span className="font-semibold text-slate-900">{item.count}</span>
                    <span className="w-8 text-right text-micro text-slate-400">{percent}%</span>
                  </div>
                );
              })}
              {campaignStatus.length === 0 && <p className="text-xs text-slate-400">No campaign data</p>}
            </div>
          </div>
        </SurfaceCard>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <SurfaceCard>
          <PanelHeader title="Recent activity" action="View all" to="/logs" />
          <div className="divide-y divide-slate-100">
            {recentActivity.slice(0, 5).map((item, index) => (
              <div key={item.id} className="group flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                <span className={`mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${index % 3 === 1 ? 'bg-amber-50 text-amber-600' : 'bg-blue-50 text-blue-600'}`}>
                  {index % 3 === 1 ? <FiClock size={14} /> : <FiMail size={14} />}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-slate-800">{item.action}</p>
                  <p className="mt-0.5 truncate text-micro text-slate-400">{item.description}</p>
                </div>
                <span className="max-w-24 text-right text-[9px] leading-4 text-slate-400">{formatDate(item.timestamp)}</span>
              </div>
            ))}
            {recentActivity.length === 0 && <p className="py-10 text-center text-xs text-slate-400">No recent activity</p>}
          </div>
        </SurfaceCard>

        <SurfaceCard>
          <PanelHeader title="Recent campaigns" action="View all" to="/campaigns" />
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-left text-micro font-semibold uppercase tracking-wider text-slate-400">
                  <th className="pb-3 font-semibold">Name</th>
                  <th className="pb-3 font-semibold">Status</th>
                  <th className="pb-3 text-right font-semibold">Sent</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {recentCampaigns.slice(0, 5).map((item) => (
                  <tr key={item.id} className="transition hover:bg-slate-50/70">
                    <td className="max-w-48 truncate py-3.5 font-semibold text-slate-700">{item.campaign_name}</td>
                    <td className="py-3.5"><StatusBadge status={item.status} /></td>
                    <td className="py-3.5 text-right font-medium text-slate-500">{item.emails_sent}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {recentCampaigns.length === 0 && <p className="py-10 text-center text-xs text-slate-400">No campaigns yet</p>}
          </div>
        </SurfaceCard>
      </section>

      <section className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-violet-700 via-indigo-600 to-blue-500 px-6 py-7 text-white shadow-xl shadow-indigo-600/15">
        <div className="absolute -right-12 -top-20 h-52 w-52 rounded-full border-[26px] border-white/10" />
        <div className="absolute bottom-3 right-36 h-2 w-2 rotate-45 bg-white/70" />
        <div className="absolute right-20 top-8 h-3 w-3 rotate-45 bg-white/50" />
        <div className="relative max-w-lg">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold">Boost your outreach with AI</h2>
            <FiZap className="text-amber-300" />
          </div>
          <p className="mt-2 text-xs leading-5 text-indigo-100">Create personalized email campaigns in seconds and reach the right prospects with smarter messaging.</p>
          <Link to="/campaigns/create" className="mt-5 inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-xs font-bold text-indigo-700 shadow-lg transition hover:-translate-y-0.5 hover:shadow-xl">
            Create AI campaign <FiArrowRight size={14} />
          </Link>
        </div>
      </section>
    </PageShell>
  );
}
