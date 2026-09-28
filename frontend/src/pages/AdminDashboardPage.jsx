import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  FiAlertCircle,
  FiBell,
  FiCheckCircle,
  FiChevronDown,
  FiDatabase,
  FiLinkedin,
  FiMail,
  FiSend,
  FiTrendingUp,
  FiUsers,
  FiXCircle,
} from 'react-icons/fi';
import { dashboardService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Button from '../components/ui/Button';
import PageShell from '../components/ui/PageShell';
import SurfaceCard from '../components/ui/SurfaceCard';

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

function initials(name) {
  return (name || '?')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join('')
    .toUpperCase();
}

const METRIC_META = [
  { key: 'total_users', label: 'Total Users', icon: FiUsers, tone: 'bg-sky-100 text-sky-600', trend: 'In this tenant' },
  { key: 'campaigns', label: 'Campaigns', icon: FiMail, tone: 'bg-violet-100 text-violet-600', trend: 'All campaigns' },
  { key: 'emails_sent', label: 'Emails Sent', icon: FiSend, tone: 'bg-emerald-100 text-emerald-600', trend: 'Successful sends' },
  { key: 'delivered', label: 'Delivered', icon: FiCheckCircle, tone: 'bg-teal-100 text-teal-600', trend: 'Reached inbox' },
  { key: 'bounced', label: 'Bounced', icon: FiXCircle, tone: 'bg-rose-100 text-rose-600', trend: 'Needs attention' },
  { key: 'replies', label: 'Replies', icon: FiMail, tone: 'bg-amber-100 text-amber-600', trend: 'Responses received' },
];

const SPARK_PATHS = [
  'M2 26 L10 22 L18 14 L28 18 L38 10 L48 16 L58 8 L68 12 L78 6',
  'M2 20 L12 18 L22 12 L32 16 L42 10 L52 14 L62 8 L72 12 L78 10',
  'M2 24 L14 20 L24 12 L34 16 L44 8 L54 14 L64 10 L74 6 L78 8',
  'M2 22 L12 20 L20 14 L30 18 L40 12 L50 16 L60 10 L70 14 L78 8',
  'M2 28 L10 24 L18 20 L28 16 L38 18 L48 14 L58 16 L68 12 L78 10',
  'M2 18 L12 16 L22 12 L32 10 L42 14 L52 8 L62 12 L72 6 L78 4',
];

function Sparkline({ pathIndex = 0, stroke = '#38bdf8' }) {
  return (
    <svg viewBox="0 0 80 32" className="h-9 w-[72px] shrink-0" aria-hidden="true">
      <path d={SPARK_PATHS[pathIndex % SPARK_PATHS.length]} fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AdminMetricCard({ label, value, trend, icon: Icon, tone, sparkColor, index }) {
  return (
    <div
      className="stagger-item rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm"
      style={{ '--item-index': index }}
    >
      <div className="flex items-start justify-between">
        <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${tone}`}>
          {Icon ? <Icon size={20} /> : null}
        </div>
        <Sparkline pathIndex={index} stroke={sparkColor} />
      </div>
      <p className="mt-4 text-[11px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</p>
      <p className="mt-1 text-[2rem] font-bold leading-none tracking-tight text-slate-950">{value}</p>
      <p className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-emerald-600">
        <FiTrendingUp size={12} />
        {trend}
      </p>
    </div>
  );
}

function RingChart({ percent }) {
  const p = Math.max(0, Math.min(100, Number(percent) || 0));
  const r = 38;
  const c = 2 * Math.PI * r;
  const offset = c - (p / 100) * c;
  return (
    <div className="relative h-[104px] w-[104px] shrink-0">
      <svg viewBox="0 0 96 96" className="h-[104px] w-[104px] -rotate-90">
        <circle cx="48" cy="48" r={r} fill="none" stroke="#e2e8f0" strokeWidth="7" />
        <circle
          cx="48"
          cy="48"
          r={r}
          fill="none"
          stroke="#10b981"
          strokeWidth="7"
          strokeDasharray={c}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-bold text-slate-900">{p}%</span>
        <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Verified</span>
      </div>
    </div>
  );
}

function MiniBarChart({ values }) {
  const max = Math.max(...values, 1);
  const colors = ['#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe'];
  return (
    <div className="flex h-20 items-end justify-end gap-1.5" aria-hidden="true">
      {values.map((v, i) => (
        <div
          key={i}
          className="w-3 rounded-sm"
          style={{ height: `${Math.max(12, (v / max) * 100)}%`, backgroundColor: colors[i % colors.length] }}
        />
      ))}
    </div>
  );
}

export default function AdminDashboardPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [userFilter, setUserFilter] = useState('all');
  const [campaignRange, setCampaignRange] = useState('7');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: result } = await dashboardService.getAdminStats();
      setData(result);
    } catch {
      toast.error('Failed to load admin dashboard');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load, user?.org_id]);

  const filteredUsers = useMemo(() => {
    const rows = data?.user_activity || [];
    if (userFilter === 'active') return rows.filter((r) => r.status === 'ACTIVE');
    if (userFilter === 'inactive') return rows.filter((r) => r.status !== 'ACTIVE');
    return rows;
  }, [data, userFilter]);

  const displayedCampaigns = useMemo(() => {
    const rows = data?.campaign_performance || [];
    const limit = campaignRange === 'all' ? rows.length : Number(campaignRange) || 7;
    return rows.slice(0, limit);
  }, [data, campaignRange]);

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
        <h1 className="mt-3 font-bold text-slate-900">Admin dashboard unavailable</h1>
        <Button className="mt-5" onClick={load}>Try again</Button>
      </SurfaceCard>
    );
  }

  const { summary, icp, linkedin, email_verification: mv } = data;
  const tenantLabel = user?.org_name || data.org_id;
  const verifyPct = mv.emails_verified ? Math.round((mv.valid / mv.emails_verified) * 100) : 0;

  const sparkColors = ['#0ea5e9', '#8b5cf6', '#10b981', '#14b8a6', '#f43f5e', '#f59e0b'];
  const linkedinBars = [
    linkedin.total_extracted,
    linkedin.successfully_extracted,
    linkedin.failed,
    linkedin.added_to_icp,
  ];

  return (
    <PageShell maxWidth="max-w-[1400px]" className="pb-12">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-primary-600">Admin Dashboard</p>
          <h1 className="mt-1 text-[2rem] font-bold tracking-tight text-slate-950">{tenantLabel}</h1>
          <p className="mt-1 text-sm text-slate-500">
            Tenant: {data.org_id} — overall activity for your organization only.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm hover:bg-slate-50"
            aria-label="Notifications"
          >
            <FiBell size={18} />
            <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-rose-500" />
          </button>
          <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-600 text-xs font-bold text-white">
              {initials(user?.name)}
            </span>
            <div className="min-w-0 pr-1">
              <p className="truncate text-sm font-semibold text-slate-900">{user?.name}</p>
              <p className="truncate text-xs text-slate-500">{user?.role || 'Admin'}</p>
            </div>
            <FiChevronDown className="shrink-0 text-slate-400" size={16} />
          </div>
        </div>
      </div>

      <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {METRIC_META.map((meta, index) => (
          <AdminMetricCard
            key={meta.key}
            label={meta.label}
            value={formatCount(summary[meta.key])}
            trend={meta.trend}
            icon={meta.icon}
            tone={meta.tone}
            sparkColor={sparkColors[index]}
            index={index}
          />
        ))}
      </div>

      <div className="mt-8 grid gap-6 xl:grid-cols-2">
        <SurfaceCard className="overflow-hidden p-0 shadow-sm">
          <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
            <div>
              <h2 className="text-base font-semibold text-slate-900">User Activity</h2>
              <p className="mt-0.5 text-xs text-slate-500">Activity breakdown by user.</p>
            </div>
            <select
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm"
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value)}
            >
              <option value="all">All Users</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
          <div className="max-h-[380px] overflow-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="sticky top-0 bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                <tr>
                  <th className="px-5 py-3">User</th>
                  <th className="px-5 py-3">Campaigns</th>
                  <th className="px-5 py-3">Emails Sent</th>
                  <th className="px-5 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.length === 0 ? (
                  <tr><td colSpan={4} className="px-5 py-10 text-center text-slate-400">No users yet</td></tr>
                ) : filteredUsers.map((row) => (
                  <tr key={row.user_id} className="border-t border-slate-100">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-900 text-[11px] font-bold text-white">
                          {initials(row.name)}
                        </span>
                        <span className="font-medium text-slate-900">{row.name}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-slate-700">{formatCount(row.campaigns)}</td>
                    <td className="px-5 py-3.5 text-slate-700">{formatCount(row.emails_sent)}</td>
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ${
                        row.status === 'ACTIVE' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
                      }`}>
                        {row.status === 'ACTIVE' ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SurfaceCard>

        <SurfaceCard className="overflow-hidden p-0 shadow-sm">
          <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
            <div>
              <h2 className="text-base font-semibold text-slate-900">Campaign Performance</h2>
              <p className="mt-0.5 text-xs text-slate-500">Performance breakdown by campaign.</p>
            </div>
            <select
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm"
              value={campaignRange}
              onChange={(e) => setCampaignRange(e.target.value)}
            >
              <option value="7">Last 7 days</option>
              <option value="14">Last 14 days</option>
              <option value="all">All campaigns</option>
            </select>
          </div>
          <div className="max-h-[380px] overflow-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="sticky top-0 bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                <tr>
                  <th className="px-5 py-3">Campaign</th>
                  <th className="px-5 py-3">Sent</th>
                  <th className="px-5 py-3">Delivered</th>
                  <th className="px-5 py-3">Bounced</th>
                  <th className="px-5 py-3">Replied</th>
                </tr>
              </thead>
              <tbody>
                {displayedCampaigns.length === 0 ? (
                  <tr><td colSpan={5} className="px-5 py-10 text-center text-slate-400">No campaigns yet</td></tr>
                ) : displayedCampaigns.map((row) => (
                  <tr key={row.campaign_id} className="border-t border-slate-100">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-50 text-primary-600">
                          <FiMail size={15} />
                        </span>
                        <span className="max-w-[180px] truncate font-medium text-slate-900">{row.campaign_name}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-slate-700">{formatCount(row.sent)}</td>
                    <td className="px-5 py-3.5 text-slate-700">{formatCount(row.delivered)}</td>
                    <td className="px-5 py-3.5 text-slate-700">{formatCount(row.bounced)}</td>
                    <td className="px-5 py-3.5 text-slate-700">{formatCount(row.replied)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SurfaceCard>
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <SurfaceCard className="p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <FiDatabase className="text-slate-400" size={16} />
            <h2 className="text-base font-semibold text-slate-900">ICP Statistics</h2>
          </div>
          <dl className="mt-5 space-y-3.5 text-sm">
            <div className="flex justify-between"><dt className="text-slate-500">ICP Accounts</dt><dd className="font-semibold text-slate-900">{formatCount(icp.accounts)}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-500">ICP Contacts</dt><dd className="font-semibold text-slate-900">{formatCount(icp.contacts)}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-500">Verified Emails</dt><dd className="font-semibold text-slate-900">{formatCount(icp.verified_emails)}</dd></div>
            <div className="flex justify-between"><dt className="text-slate-500">Invalid Emails</dt><dd className="font-semibold text-slate-900">{formatCount(icp.invalid_emails)}</dd></div>
          </dl>
          <Link to="/icp-contacts" className="mt-5 inline-block text-sm font-medium text-primary-600 hover:underline">
            View details →
          </Link>
        </SurfaceCard>

        <SurfaceCard className="p-5 shadow-sm">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <FiLinkedin className="text-slate-400" size={16} />
                <h2 className="text-base font-semibold text-slate-900">LinkedIn Extraction</h2>
              </div>
              <dl className="mt-5 space-y-3.5 text-sm">
                <div className="flex justify-between"><dt className="text-slate-500">Total Extracted</dt><dd className="font-semibold text-slate-900">{formatCount(linkedin.total_extracted)}</dd></div>
                <div className="flex justify-between"><dt className="text-slate-500">Successfully Extracted</dt><dd className="font-semibold text-slate-900">{formatCount(linkedin.successfully_extracted)}</dd></div>
                <div className="flex justify-between"><dt className="text-slate-500">Failed</dt><dd className="font-semibold text-slate-900">{formatCount(linkedin.failed)}</dd></div>
                <div className="flex justify-between"><dt className="text-slate-500">Added to ICP</dt><dd className="font-semibold text-slate-900">{formatCount(linkedin.added_to_icp)}</dd></div>
              </dl>
            </div>
            <MiniBarChart values={linkedinBars} />
          </div>
          <Link to="/linkedin-history" className="mt-5 inline-block text-sm font-medium text-primary-600 hover:underline">
            View details →
          </Link>
        </SurfaceCard>

        <SurfaceCard className="p-5 shadow-sm">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <FiCheckCircle className="text-slate-400" size={16} />
                <h2 className="text-base font-semibold text-slate-900">Email Verification</h2>
              </div>
              <dl className="mt-5 space-y-3.5 text-sm">
                <div className="flex justify-between gap-4"><dt className="text-slate-500">Emails Verified</dt><dd className="font-semibold text-slate-900">{formatCount(mv.emails_verified)}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-slate-500">Valid</dt><dd className="font-semibold text-slate-900">{formatCount(mv.valid)}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-slate-500">Invalid</dt><dd className="font-semibold text-slate-900">{formatCount(mv.invalid)}</dd></div>
                <div className="flex justify-between gap-4"><dt className="text-slate-500">Risky</dt><dd className="font-semibold text-slate-900">{formatCount(mv.risky)}</dd></div>
              </dl>
            </div>
            <RingChart percent={verifyPct} />
          </div>
          <Link to="/recipients" className="mt-5 inline-block text-sm font-medium text-primary-600 hover:underline">
            View details →
          </Link>
        </SurfaceCard>
      </div>
    </PageShell>
  );
}
