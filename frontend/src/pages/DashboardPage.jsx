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
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import { campaignService, dashboardService, userService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { hasPermission } from '../utils/permissions';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import StatusBadge from '../components/ui/StatusBadge';
import Button from '../components/ui/Button';
import NotificationBell from '../components/NotificationBell';
import PageShell from '../components/ui/PageShell';
import PageHeader from '../components/ui/PageHeader';
import SurfaceCard from '../components/ui/SurfaceCard';
import MetricCard from '../components/ui/MetricCard';
import PanelHeader from '../components/ui/PanelHeader';
import FilterBar, { FilterField } from '../components/ui/FilterBar';
import CampaignDayDetailPanel from '../components/dashboard/CampaignDayDetailPanel';
import { CHART_COLORS } from '../design-tokens';
import { formatDate } from '../utils/helpers';

const EMPTY_FILTERS = { userId: '', campaignId: '', dateFrom: '', dateTo: '' };

const STATUS_COLORS = {
  Draft: '#3578f6',
  Active: '#14b87a',
  Completed: '#ffac32',
  Paused: '#f2535a',
};

function toLocalIsoDate(value = new Date()) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function shiftIsoDate(isoDate, days) {
  const date = new Date(`${isoDate}T12:00:00`);
  date.setDate(date.getDate() + days);
  return toLocalIsoDate(date);
}

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

function formatDisplayDate(isoDate) {
  if (!isoDate) return '—';
  const [year, month, day] = isoDate.split('-');
  return `${day} - ${month} - ${year}`;
}

function weekdayLabel(isoDate) {
  if (!isoDate) return '';
  const date = new Date(`${isoDate}T12:00:00`);
  return date.toLocaleDateString(undefined, { weekday: 'short' });
}

function dayNumber(isoDate) {
  if (!isoDate) return '';
  return Number(isoDate.slice(-2));
}

function statusColor(status, index = 0) {
  return STATUS_COLORS[status] || CHART_COLORS[index % CHART_COLORS.length];
}

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
  const [performanceRange, setPerformanceRange] = useState('week');
  const [selectedDay, setSelectedDay] = useState(null);
  const { user } = useAuth();
  const toast = useToast();

  useEffect(() => {
    if (hasPermission(user, 'members:read')) {
      userService.getAll().then(({ data: result }) => setUsers(result)).catch(() => {});
    }
    campaignService.getAll().then(({ data: result }) => setCampaigns(result)).catch(() => {});
  }, [user]);

  const buildParams = () => {
    const today = toLocalIsoDate();
    const hasCustomDates = Boolean(filters.dateFrom || filters.dateTo);
    const rangeDays = performanceRange === 'day' ? 0 : 6;
    return {
      user_id: filters.userId || undefined,
      campaign_id: filters.campaignId || undefined,
      date_from: filters.dateFrom || (!hasCustomDates ? shiftIsoDate(today, -rangeDays) : undefined),
      date_to: filters.dateTo || (!hasCustomDates ? today : undefined),
    };
  };

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
  }, [filters, performanceRange, toast]);

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
  const todayIso = toLocalIsoDate();
  const yesterdayIso = toLocalIsoDate(new Date(Date.now() - 86_400_000));
  const dailyRows = emailsPerDay.map((row) => {
    const isoDate = row.iso_date || '';
    return {
      ...row,
      isoDate,
      sent: Number(row.sent ?? row.count ?? 0),
      cumulativeMonth: Number(row.cumulative_month ?? 0),
      cumulativeOverall: Number(row.cumulative_overall ?? 0),
      icpDbDay: Number(row.icp_db_day ?? 0),
      icpDbCumulative: Number(row.icp_db_cumulative ?? 0),
      monthLabel: row.month_label || (isoDate ? new Date(`${isoDate}T12:00:00`).toLocaleString(undefined, { month: 'short' }).toUpperCase() : ''),
      isToday: isoDate === todayIso,
      isYesterday: isoDate === yesterdayIso,
    };
  });
  const monthColumnLabel = dailyRows[0]?.monthLabel || new Date().toLocaleString(undefined, { month: 'short' }).toUpperCase();

  return (
    <>
    <PageShell>
      <PageHeader
        eyebrow="Overview"
        title={<>Welcome back, {firstName}! <span aria-hidden="true">👋</span></>}
        subtitle="Here's what's happening with your campaigns today."
        actions={
          <>
            <NotificationBell />
            <Button icon={FiDownload} loading={exporting} onClick={handleExportReport}>
              Export report
            </Button>
          </>
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
          <input type="date" className="control min-w-[10rem] py-2 text-xs" value={filters.dateFrom} max={filters.dateTo || undefined} onChange={(event) => updateFilter('dateFrom', event.target.value)} />
        </FilterField>
        <FilterField label="To">
          <input type="date" className="control min-w-[10rem] py-2 text-xs" value={filters.dateTo} min={filters.dateFrom || undefined} onChange={(event) => updateFilter('dateTo', event.target.value)} />
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

      <section className="grid gap-6 xl:grid-cols-[1.45fr_.9fr]">
        <SurfaceCard className="overflow-hidden p-0">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
            <div>
              <h2 className="text-sm font-bold text-slate-900">Campaign Performance</h2>
              <p className="mt-0.5 text-xs text-slate-500">Daily volume, cumulatives &amp; ICP growth</p>
            </div>
            <div className="inline-flex rounded-full bg-slate-100 p-1 text-xs font-semibold">
              {[
                { key: 'day', label: 'Day' },
                { key: 'week', label: 'Week' },
              ].map((option) => (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => setPerformanceRange(option.key)}
                  className={`rounded-full px-3.5 py-1.5 transition ${
                    performanceRange === option.key
                      ? 'bg-slate-800 text-white shadow-sm'
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  <th className="px-4 py-3">Date</th>
                  <th className="px-3 py-3">Sent</th>
                  <th className="px-3 py-3">Cum ({monthColumnLabel})</th>
                  <th className="px-3 py-3">Cum all</th>
                  <th className="px-3 py-3">ICP day</th>
                  <th className="px-3 py-3 pr-4">ICP total</th>
                </tr>
              </thead>
              <tbody>
                {dailyRows.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-12 text-center text-sm text-slate-400">No daily activity yet</td>
                  </tr>
                ) : dailyRows.map((row) => {
                  const isSelected = selectedDay?.isoDate === row.isoDate;
                  return (
                  <tr
                    key={row.isoDate || row.date}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedDay(row)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        setSelectedDay(row);
                      }
                    }}
                    className={`cursor-pointer border-t border-slate-100 transition ${
                      isSelected
                        ? 'bg-orange-50 ring-1 ring-inset ring-[#FF7A00]/40'
                        : row.isToday
                          ? 'bg-[#FFF9F5] hover:bg-[#FFF3EB]'
                          : 'hover:bg-slate-50'
                    }`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <span
                          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                            row.isToday || isSelected ? 'bg-[#FF7A00] text-white' : 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {dayNumber(row.isoDate)}
                        </span>
                        <div className="min-w-0">
                          <p className="text-[13px] font-medium leading-5 text-slate-800">
                            {formatDisplayDate(row.isoDate)}
                            <span className="ml-1.5 font-normal text-slate-400">{weekdayLabel(row.isoDate)}</span>
                          </p>
                        </div>
                        {row.isToday && (
                          <span className="rounded-full bg-[#FF7A00] px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white">
                            Today
                          </span>
                        )}
                        {row.isYesterday && (
                          <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white">
                            Yesterday
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <span className="font-medium text-slate-800">{formatCount(row.sent)}</span>
                    </td>
                    <td className="px-3 py-3 text-slate-700">{formatCount(row.cumulativeMonth)}</td>
                    <td className="px-3 py-3 text-slate-700">{formatCount(row.cumulativeOverall)}</td>
                    <td className="px-3 py-3">
                      {row.icpDbDay > 0 ? (
                        <span className="inline-flex rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                          + {formatCount(row.icpDbDay)}
                        </span>
                      ) : (
                        <span className="inline-flex rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">
                          - 0
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-3 pr-4 text-slate-700">{formatCount(row.icpDbCumulative)}</td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </SurfaceCard>

        <SurfaceCard className="flex flex-col">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-bold text-slate-900">Campaign status</h2>
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">
              {campaignTotal} total
            </span>
          </div>
          <div className="relative mx-auto mt-4 h-[210px] w-full max-w-[230px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={campaignStatus}
                  dataKey="count"
                  nameKey="status"
                  innerRadius={62}
                  outerRadius={88}
                  paddingAngle={2}
                  stroke="none"
                >
                  {campaignStatus.map((item, index) => (
                    <Cell key={`${item.status}-${index}`} fill={statusColor(item.status, index)} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #e2e8f0', fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-bold text-slate-950">{campaignTotal}</span>
              <span className="text-[11px] text-slate-400">Total campaigns</span>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2.5">
            {campaignStatus.map((item, index) => {
              const percent = campaignTotal ? Math.round((Number(item.count || 0) / campaignTotal) * 100) : 0;
              return (
                <div key={item.status} className="rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2.5">
                  <div className="flex items-center gap-1.5 text-xs text-slate-500">
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: statusColor(item.status, index) }} />
                    <span className="truncate capitalize">{item.status}</span>
                  </div>
                  <div className="mt-1.5 flex items-end justify-between gap-2">
                    <span className="text-lg font-bold leading-none text-slate-900">{item.count}</span>
                    <span className="text-[11px] font-medium text-slate-400">{percent}%</span>
                  </div>
                </div>
              );
            })}
            {campaignStatus.length === 0 && (
              <p className="col-span-2 py-6 text-center text-xs text-slate-400">No campaign data</p>
            )}
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

      <section className="ai-outreach-banner relative overflow-hidden rounded-2xl px-6 py-7 text-white">
        <div className="absolute -right-12 -top-20 h-52 w-52 rounded-full border-[26px] border-white/10" />
        <div className="absolute bottom-3 right-36 h-2 w-2 rotate-45 bg-white/70" />
        <div className="absolute right-20 top-8 h-3 w-3 rotate-45 bg-white/50" />
        <div className="relative max-w-lg">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold">Boost your outreach with AI</h2>
            <FiZap className="text-amber-300" />
          </div>
          <p className="ai-outreach-sub mt-2 text-xs leading-5">Create personalized email campaigns in seconds and reach the right prospects with smarter messaging.</p>
          <Link to="/campaigns/create" className="ai-outreach-cta mt-5 inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-xs font-bold shadow-lg transition hover:-translate-y-0.5 hover:shadow-xl">
            Create AI campaign <FiArrowRight size={14} />
          </Link>
        </div>
      </section>

    </PageShell>

    <CampaignDayDetailPanel
      day={selectedDay}
      isOpen={Boolean(selectedDay)}
      onClose={() => setSelectedDay(null)}
      filters={filters}
    />
    </>
  );
}
