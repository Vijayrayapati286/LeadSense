import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { FiChevronLeft, FiChevronRight, FiDownload } from 'react-icons/fi';
import { campaignService, dashboardService, userService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { hasPermission, isProviderOrg } from '../utils/permissions';
import { useToast } from '../hooks/useToast';
import { formatDateTime } from '../utils/helpers';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import DashboardDetailPanel from '../components/dashboard/DashboardDetailPanel';

const EMPTY_FILTERS = { userId: '', campaignId: '' };
const DAILY_RANGE_OPTIONS = [
  { key: 'week', label: 'Week' },
  { key: 'month', label: 'Month' },
];
const ANALYTICS_RANGE_OPTIONS = [
  { key: 'week', label: 'Week' },
  { key: 'month', label: 'Month' },
  { key: 'year', label: 'Year' },
];
const MONTH_OPTIONS = [
  { value: '', label: 'All months' },
  { value: '01', label: 'January' },
  { value: '02', label: 'February' },
  { value: '03', label: 'March' },
  { value: '04', label: 'April' },
  { value: '05', label: 'May' },
  { value: '06', label: 'June' },
  { value: '07', label: 'July' },
  { value: '08', label: 'August' },
  { value: '09', label: 'September' },
  { value: '10', label: 'October' },
  { value: '11', label: 'November' },
  { value: '12', label: 'December' },
];
const STATUS_DOT = {
  Draft: '#64748b',
  Active: '#2563eb',
  Completed: '#0f766e',
  Paused: '#b45309',
};
const ROW_DOTS = ['#ea580c', '#0f766e', '#2563eb', '#334155', '#64748b', '#b45309'];

function toLocalIsoDate(value = new Date()) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function addDays(isoDate, days) {
  const date = new Date(`${isoDate}T12:00:00`);
  date.setDate(date.getDate() + days);
  return toLocalIsoDate(date);
}

function todayIso() {
  return toLocalIsoDate();
}

function minIso(left, right) {
  return left <= right ? left : right;
}

function startOfMonth(isoDate) {
  const date = new Date(`${isoDate}T12:00:00`);
  return toLocalIsoDate(new Date(date.getFullYear(), date.getMonth(), 1));
}

function endOfMonth(isoDate) {
  const date = new Date(`${isoDate}T12:00:00`);
  return toLocalIsoDate(new Date(date.getFullYear(), date.getMonth() + 1, 0));
}

function startOfYear(isoDate) {
  const date = new Date(`${isoDate}T12:00:00`);
  return toLocalIsoDate(new Date(date.getFullYear(), 0, 1));
}

function endOfYear(year) {
  return `${year}-12-31`;
}

function windowFor(rangeKey, cursorIso) {
  const today = todayIso();
  const cursor = cursorIso > today ? today : cursorIso;
  if (rangeKey === 'week') {
    return { dateFrom: addDays(cursor, -6), dateTo: cursor };
  }
  if (rangeKey === 'year') {
    return { dateFrom: startOfYear(cursor), dateTo: minIso(endOfYear(new Date(`${cursor}T12:00:00`).getFullYear()), today) };
  }
  return {
    dateFrom: startOfMonth(cursor),
    dateTo: minIso(endOfMonth(cursor), today),
  };
}

function shiftCursor(rangeKey, cursorIso, direction) {
  const date = new Date(`${cursorIso}T12:00:00`);
  if (rangeKey === 'week') date.setDate(date.getDate() + direction * 7);
  else if (rangeKey === 'year') date.setFullYear(date.getFullYear() + direction);
  else date.setMonth(date.getMonth() + direction, 1);
  const next = toLocalIsoDate(date);
  const today = todayIso();
  return next > today ? today : next;
}

function formatParts(isoDate) {
  const date = new Date(`${isoDate}T12:00:00`);
  return {
    day: date.getDate(),
    month: date.toLocaleDateString('en-GB', { month: 'short' }),
    year: date.getFullYear(),
  };
}

function formatLongDate(isoDate) {
  if (!isoDate) return '—';
  const { day, month, year } = formatParts(isoDate);
  return `${day} ${month} ${year}`;
}

function formatTableDate(isoDate) {
  if (!isoDate) return '—';
  const [year, month, day] = isoDate.split('-');
  return `${day}-${month}-${year}`;
}

function formatRangeLabel(from, to) {
  if (from === to) return formatLongDate(to);
  const start = formatParts(from);
  const end = formatParts(to);
  const sameMonth = start.month === end.month && start.year === end.year;
  if (sameMonth) return `${start.day}–${end.day} ${end.month} ${end.year}`;
  if (start.year === end.year) return `${start.day} ${start.month} – ${end.day} ${end.month} ${end.year}`;
  return `${start.day} ${start.month} ${start.year} – ${end.day} ${end.month} ${end.year}`;
}

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

function selectClass() {
  return 'h-9 w-[9.5rem] shrink-0 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none focus:border-slate-400';
}

function compactSelectClass() {
  return 'h-8 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-800 outline-none focus:border-slate-400';
}

function yesterdayIso() {
  return addDays(todayIso(), -1);
}

function monthDateRange(monthKey, dateTo) {
  const [year, month] = (monthKey || '').split('-').map(Number);
  if (!year || !month) return { from: dateTo, to: dateTo };
  const from = `${year}-${String(month).padStart(2, '0')}-01`;
  const lastDay = new Date(year, month, 0).getDate();
  let to = `${year}-${String(month).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
  if (dateTo && to > dateTo) to = dateTo;
  return { from, to };
}

function currentMonthValue() {
  return String(new Date().getMonth() + 1).padStart(2, '0');
}

function monthNameFromNumber(month) {
  const value = String(month).padStart(2, '0');
  return MONTH_OPTIONS.find((option) => option.value === value)?.label || value;
}

function threeMonthSlots(year, month) {
  const slots = [];
  let nextYear = Number(year);
  let nextMonth = Number(month);
  for (let index = 0; index < 3; index += 1) {
    slots.unshift({
      year: nextYear,
      month: monthNameFromNumber(nextMonth),
      month_key: `${nextYear}-${String(nextMonth).padStart(2, '0')}`,
      mails_sent: 0,
      icp_database: 0,
    });
    nextMonth -= 1;
    if (nextMonth === 0) {
      nextMonth = 12;
      nextYear -= 1;
    }
  }
  return slots;
}

function monthDisplayName(row, showYear) {
  if (showYear) return `${row.month} ${row.year}`;
  return row.month;
}

function RangePills({ value, onChange, options, inverted = false }) {
  return (
    <div className={inverted
      ? 'inline-flex shrink-0 rounded-md bg-white/15 p-0.5 text-xs'
      : 'inline-flex h-9 shrink-0 rounded-lg border border-slate-200 bg-white p-0.5 text-sm'}
    >
      {options.map((option) => {
        const active = value === option.key;
        return (
          <button
            key={option.key}
            type="button"
            onClick={() => onChange(option.key)}
            className={inverted
              ? `rounded px-2.5 py-1 ${active ? 'bg-white text-slate-900' : 'text-white'}`
              : `rounded-md px-3 py-1 ${active ? 'bg-slate-900 text-white' : 'text-slate-600 hover:text-slate-900'}`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function PeriodNav({ label, onPrev, onNext, inverted = false }) {
  return (
    <div className={inverted
      ? 'inline-flex shrink-0 items-center gap-1 rounded-md bg-white/15 px-1 py-0.5 text-xs text-white'
      : 'inline-flex h-9 shrink-0 items-center gap-1 rounded-lg border border-slate-200 bg-white px-1 text-sm text-slate-700'}
    >
      <button type="button" className="rounded p-1" aria-label="Previous period" onClick={onPrev}>
        <FiChevronLeft size={14} />
      </button>
      <span className={`shrink-0 px-1 text-center tabular-nums ${inverted ? 'w-[9.75rem]' : 'w-[10rem]'}`}>{label}</span>
      <button type="button" className="rounded p-1" aria-label="Next period" onClick={onNext}>
        <FiChevronRight size={14} />
      </button>
    </div>
  );
}

function SplitBar({ value, total }) {
  const pct = total > 0 ? Math.min(100, Math.round((Number(value || 0) / total) * 100)) : 0;
  return (
    <div className="flex h-2 w-[7.5rem] overflow-hidden rounded-full bg-slate-200">
      <div className="h-full bg-slate-800" style={{ width: `${pct}%` }} />
    </div>
  );
}

function mapDailyRows(emailsPerDay) {
  return (emailsPerDay || []).map((row) => {
    const isoDate = row.iso_date || '';
    const sent = Number(row.sent ?? row.count ?? 0);
    const icpDay = Number(row.icp_db_day ?? 0);
    return {
      ...row,
      isoDate,
      sent,
      delivered: Number(row.delivered ?? sent),
      cumulativeMonth: Number(row.cumulative_month ?? 0),
      cumulativeOverall: Number(row.cumulative_overall ?? 0),
      icpDay,
      icpTotal: Number(row.icp_db_cumulative ?? 0),
      icpDbDay: icpDay,
      icpDbCumulative: Number(row.icp_db_cumulative ?? 0),
      monthLabel: row.month_label || '',
      isToday: isoDate === todayIso(),
      isYesterday: isoDate === yesterdayIso(),
    };
  });
}

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [monthData, setMonthData] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [adminData, setAdminData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [users, setUsers] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [dailyRange, setDailyRange] = useState('month');
  const [dailyCursor, setDailyCursor] = useState(todayIso());
  const [monthYear, setMonthYear] = useState(new Date().getFullYear());
  const [monthMonth, setMonthMonth] = useState(currentMonthValue());
  const [analyticsRange, setAnalyticsRange] = useState('month');
  const [analyticsCursor, setAnalyticsCursor] = useState(todayIso());
  const [selected, setSelected] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(new Date());
  const { user } = useAuth();
  const toast = useToast();
  const isTenant = !isProviderOrg(user);
  const canLoadAdmin = isTenant && hasPermission(user, 'members:read');

  const { dateFrom, dateTo } = useMemo(
    () => windowFor(dailyRange, dailyCursor),
    [dailyRange, dailyCursor],
  );

  const monthWiseEnd = useMemo(() => {
    const today = todayIso();
    if (monthMonth) return minIso(endOfMonth(`${monthYear}-${monthMonth}-01`), today);
    return minIso(endOfYear(monthYear), today);
  }, [monthYear, monthMonth]);

  const { dateFrom: analyticsFrom, dateTo: analyticsTo } = useMemo(
    () => windowFor(analyticsRange, analyticsCursor),
    [analyticsRange, analyticsCursor],
  );

  useEffect(() => {
    if (!isTenant) return;
    if (canLoadAdmin) {
      userService.getAll().then(({ data: result }) => setUsers(result)).catch(() => {});
      dashboardService.getAdminStats().then(({ data: result }) => setAdminData(result)).catch(() => setAdminData(null));
    }
    campaignService.getAll().then(({ data: result }) => setCampaigns(result)).catch(() => {});
  }, [user, isTenant, canLoadAdmin]);

  const sharedParams = useMemo(
    () => ({
      user_id: filters.userId || undefined,
      campaign_id: filters.campaignId || undefined,
    }),
    [filters],
  );

  const loadDashboard = useCallback(async () => {
    if (!isTenant) {
      setLoading(false);
      return;
    }
    try {
      const [dailyRes, monthRes, analyticsRes] = await Promise.all([
        dashboardService.getStats({ ...sharedParams, date_from: dateFrom, date_to: dateTo }),
        dashboardService.getStats({ ...sharedParams, date_to: monthWiseEnd }),
        dashboardService.getStats({ ...sharedParams, date_from: analyticsFrom, date_to: analyticsTo }),
      ]);
      setData(dailyRes.data);
      setMonthData(monthRes.data);
      setAnalyticsData(analyticsRes.data);
      setUpdatedAt(new Date());
    } catch {
      toast.error('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }, [sharedParams, dateFrom, dateTo, monthWiseEnd, analyticsFrom, analyticsTo, toast, isTenant]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const updateFilter = (field, value) => setFilters((previous) => ({ ...previous, [field]: value }));

  const handleExportReport = async () => {
    setExporting(true);
    try {
      const response = await dashboardService.exportReport({ ...sharedParams, date_from: analyticsFrom, date_to: analyticsTo });
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

  if (isProviderOrg(user)) {
    return <Navigate to="/dashboard" replace />;
  }

  if (loading && !data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-xl border border-slate-200 bg-white p-8 text-center">
        <h1 className="font-semibold text-slate-900">Dashboard unavailable</h1>
        <p className="mt-1 text-sm text-slate-500">We could not load your mail summary.</p>
        <button type="button" className="mt-4 rounded-lg border border-slate-200 px-4 py-2 text-sm" onClick={loadDashboard}>
          Try again
        </button>
      </div>
    );
  }

  const dailyRows = mapDailyRows(data.emails_per_day);
  const monthLabels = [...new Set(dailyRows.map((row) => row.monthLabel).filter(Boolean))];
  const cumMonthHeader = monthLabels.length === 1
    ? `Cumulative mails (${monthLabels[0]})`
    : 'Cumulative mails (month)';

  const allMonthRows = monthData?.month_wise || data.month_wise || [];
  const monthsByKey = Object.fromEntries(allMonthRows.map((row) => [row.month_key, row]));
  const yearChoices = [...new Set([
    new Date().getFullYear(),
    ...allMonthRows.map((row) => Number(row.year)).filter(Boolean),
  ])].sort((a, b) => b - a);
  const visibleMonths = monthMonth
    ? threeMonthSlots(monthYear, monthMonth).map((slot) => monthsByKey[slot.month_key] || slot)
    : allMonthRows.filter((row) => Number(row.year) === Number(monthYear));
  const monthWindowSpansYears = new Set(visibleMonths.map((row) => Number(row.year))).size > 1;
  const monthTotals = visibleMonths.reduce(
    (acc, row) => ({
      mails: acc.mails + Number(row.mails_sent || 0),
      icp: acc.icp + Number(row.icp_database || 0),
    }),
    { mails: 0, icp: 0 },
  );

  const statsSource = analyticsData || data;
  const stats = statsSource.stats || {};
  const campaignStatus = statsSource.campaign_status || [];
  const recentCampaigns = statsSource.recent_campaigns || [];
  const campaignTotal = campaignStatus.reduce((sum, item) => sum + Number(item.count || 0), 0);
  const sentCount = Number(stats.emails_sent || 0);
  const pendingCount = Number(stats.pending_emails || 0);
  const failedCount = Number(stats.failed_emails || 0);
  const outcomeTotal = sentCount + pendingCount + failedCount;
  const bounceRate = Number(stats.bounce_rate || 0);
  const outcomeRows = [
    { label: 'Sent', value: sentCount, total: outcomeTotal, color: ROW_DOTS[0] },
    { label: 'Pending', value: pendingCount, total: outcomeTotal, color: ROW_DOTS[1] },
    { label: 'Failed', value: failedCount, total: outcomeTotal, color: ROW_DOTS[2] },
    { label: 'Hard bounces', value: Number(stats.hard_bounces || 0), total: sentCount, color: ROW_DOTS[3] },
    { label: 'Soft bounces pending', value: Number(stats.soft_bounces_pending || 0), total: sentCount, color: ROW_DOTS[4] },
  ];

  const icp = adminData?.icp;
  const linkedin = adminData?.linkedin;
  const verification = adminData?.email_verification;
  const icpMix = Number(icp?.contacts || 0) + Number(icp?.accounts || 0);
  const linkedinMix = Number(linkedin?.total_extracted || 0);
  const verifiedTotal = Number(verification?.emails_verified || 0);

  return (
    <>
      <div className="mx-auto max-w-[1440px] space-y-8 pb-10">
        <header>
          <div className="min-w-0">
            <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">Dashboard</h1>
            <p className="mt-1 text-sm text-slate-500">Updated on {formatDateTime(updatedAt.toISOString())}</p>
          </div>
          <div className="mt-5 flex h-9 w-full flex-nowrap items-center justify-end gap-2 overflow-x-auto pr-1">
            <RangePills
              value={analyticsRange}
              onChange={setAnalyticsRange}
              options={ANALYTICS_RANGE_OPTIONS}
            />
            <PeriodNav
              label={formatRangeLabel(analyticsFrom, analyticsTo)}
              onPrev={() => setAnalyticsCursor(shiftCursor(analyticsRange, analyticsCursor, -1))}
              onNext={() => setAnalyticsCursor(shiftCursor(analyticsRange, analyticsCursor, 1))}
            />
            {canLoadAdmin ? (
              <label className="flex shrink-0 items-center gap-2 whitespace-nowrap text-sm text-slate-600">
                <span>User</span>
                <select className={selectClass()} value={filters.userId} onChange={(event) => updateFilter('userId', event.target.value)}>
                  <option value="">All users</option>
                  {users.map((item) => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
              </label>
            ) : null}
            <label className="flex shrink-0 items-center gap-2 whitespace-nowrap text-sm text-slate-600">
              <span>Campaign</span>
              <select className={selectClass()} value={filters.campaignId} onChange={(event) => updateFilter('campaignId', event.target.value)}>
                <option value="">All campaigns</option>
                {campaigns.map((item) => (
                  <option key={item.id} value={item.id}>{item.campaign_name}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={handleExportReport}
              disabled={exporting}
              className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700"
            >
              <FiDownload size={14} />
              {exporting ? 'Exporting…' : 'Export'}
            </button>
          </div>
        </header>

        <section className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(20rem,1fr)]">
          <article className="flex min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
            <div className="flex h-11 flex-nowrap items-center justify-between gap-3 bg-[#1570b8] px-4">
              <h2 className="shrink-0 text-sm font-semibold text-white">Daily mail activity</h2>
              <div className="flex flex-nowrap items-center gap-2">
                <RangePills
                  value={dailyRange}
                  onChange={setDailyRange}
                  options={DAILY_RANGE_OPTIONS}
                  inverted
                />
                <PeriodNav
                  inverted
                  label={formatRangeLabel(dateFrom, dateTo)}
                  onPrev={() => setDailyCursor(shiftCursor(dailyRange, dailyCursor, -1))}
                  onNext={() => setDailyCursor(shiftCursor(dailyRange, dailyCursor, 1))}
                />
              </div>
            </div>
            <div className="max-h-[28rem] min-h-[16rem] flex-1 overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 z-10">
                  <tr className="bg-[#1570b8] text-[11px] font-medium uppercase tracking-wide text-white">
                    <th className="px-4 py-2.5 font-medium">Date</th>
                    <th className="px-3 py-2.5 text-right font-medium">No. of Mails Sent</th>
                    <th className="px-3 py-2.5 text-right font-medium">{cumMonthHeader}</th>
                    <th className="px-3 py-2.5 text-right font-medium">Cumulative Mails Sent (overall)</th>
                    <th className="px-3 py-2.5 text-right font-medium">ICP DB (Day)</th>
                    <th className="px-4 py-2.5 text-right font-medium">ICP DB (Cumulative)</th>
                  </tr>
                </thead>
                <tbody>
                  {dailyRows.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-10 text-center text-slate-400">No mails or ICP records in this period</td>
                    </tr>
                  ) : dailyRows.map((row) => {
                    const isSelected = selected?.kind === 'day' && selected?.isoDate === row.isoDate;
                    return (
                      <tr
                        key={row.isoDate || row.date}
                        className={`cursor-pointer border-t border-slate-100 ${isSelected ? 'bg-slate-50' : 'hover:bg-slate-50'}`}
                        onClick={() => setSelected({ kind: 'day', ...row })}
                      >
                        <td className="px-4 py-2.5 text-slate-800">{formatTableDate(row.isoDate)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-slate-800">{formatCount(row.sent)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-slate-800">{formatCount(row.cumulativeMonth)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-slate-800">{formatCount(row.cumulativeOverall)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-slate-800">{formatCount(row.icpDay)}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-slate-800">{formatCount(row.icpTotal)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </article>

          <article className="flex min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
            <div className="flex h-11 flex-nowrap items-center justify-between gap-3 bg-[#1570b8] px-4">
              <h2 className="shrink-0 text-sm font-semibold text-white">Month Wise Data</h2>
              <div className="flex flex-nowrap items-center gap-2">
                <select
                  className={compactSelectClass()}
                  value={monthYear}
                  onChange={(event) => setMonthYear(Number(event.target.value))}
                  aria-label="Year"
                >
                  {yearChoices.map((year) => (
                    <option key={year} value={year}>{year}</option>
                  ))}
                </select>
                <select
                  className={compactSelectClass()}
                  value={monthMonth}
                  onChange={(event) => setMonthMonth(event.target.value)}
                  aria-label="Month"
                >
                  {MONTH_OPTIONS.map((option) => (
                    <option key={option.value || 'all'} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="max-h-[28rem] min-h-[16rem] flex-1 overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 z-10">
                  <tr className="bg-[#1570b8] text-[11px] font-medium uppercase tracking-wide text-white">
                    <th className="px-4 py-2.5 font-medium">Month</th>
                    <th className="px-3 py-2.5 text-right font-medium">Mails Sent</th>
                    <th className="px-4 py-2.5 text-right font-medium">ICP Database</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleMonths.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="px-4 py-10 text-center text-slate-400">No month totals yet</td>
                    </tr>
                  ) : (
                    <>
                      {visibleMonths.map((row) => {
                        const range = monthDateRange(row.month_key, monthWiseEnd);
                        const isSelected = selected?.kind === 'month' && selected?.monthKey === row.month_key;
                        return (
                          <tr
                            key={row.month_key}
                            className={`cursor-pointer border-t border-slate-100 ${isSelected ? 'bg-slate-50' : 'hover:bg-slate-50'}`}
                            onClick={() => setSelected({
                              kind: 'month',
                              monthKey: row.month_key,
                              month: row.month,
                              year: row.year,
                              mailsSent: Number(row.mails_sent || 0),
                              icpDatabase: Number(row.icp_database || 0),
                              dateFrom: range.from,
                              dateTo: range.to,
                            })}
                          >
                            <td className="px-4 py-2.5 text-slate-800">{monthDisplayName(row, monthWindowSpansYears)}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-slate-800">{formatCount(row.mails_sent)}</td>
                            <td className="px-4 py-2.5 text-right tabular-nums text-slate-800">{formatCount(row.icp_database)}</td>
                          </tr>
                        );
                      })}
                      <tr className="border-t border-slate-200 bg-slate-50">
                        <td className="px-4 py-2.5 font-semibold text-slate-900">Total</td>
                        <td className="px-3 py-2.5 text-right font-semibold tabular-nums text-slate-900">{formatCount(monthTotals.mails)}</td>
                        <td className="px-4 py-2.5 text-right font-semibold tabular-nums text-slate-900">{formatCount(monthTotals.icp)}</td>
                      </tr>
                    </>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <article className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="text-base font-semibold text-slate-900">Campaign status</h2>
            <p className="mt-1 text-sm text-slate-500">
              {formatRangeLabel(analyticsFrom, analyticsTo)}
              {' · '}
              {formatCount(stats.active_campaigns || 0)} active of {formatCount(stats.total_campaigns || campaignTotal)}
              {' · '}
              {formatCount(stats.ai_generated_emails || 0)} AI templates
            </p>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                    <th className="pb-2 pr-3 font-medium">Status</th>
                    <th className="pb-2 px-2 font-medium">Campaigns</th>
                    <th className="pb-2 px-2 font-medium">Share</th>
                    <th className="pb-2 pl-2 font-medium">Split</th>
                  </tr>
                </thead>
                <tbody>
                  {campaignStatus.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-10 text-center text-slate-400">No campaigns yet</td>
                    </tr>
                  ) : campaignStatus.map((item) => {
                    const count = Number(item.count || 0);
                    const share = campaignTotal ? Math.round((count / campaignTotal) * 100) : 0;
                    const isSelected = selected?.kind === 'campaign-status' && selected?.status === item.status;
                    return (
                      <tr
                        key={item.status}
                        className={`cursor-pointer border-t border-slate-100 ${isSelected ? 'bg-slate-50' : ''}`}
                        onClick={() => setSelected({ kind: 'campaign-status', ...item, count, share })}
                      >
                        <td className="py-2.5 pr-3">
                          <span className="inline-flex items-center gap-2 text-slate-800">
                            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: STATUS_DOT[item.status] || '#64748b' }} />
                            {item.status}
                          </span>
                        </td>
                        <td className="px-2 py-2.5 tabular-nums text-slate-800">{formatCount(count)}</td>
                        <td className="px-2 py-2.5 tabular-nums text-slate-800">{share}%</td>
                        <td className="py-2.5 pl-2"><SplitBar value={count} total={campaignTotal} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-4 text-sm">
              <Link to="/campaigns" className="font-medium text-slate-700 underline-offset-2 hover:underline">View all campaigns</Link>
            </p>
          </article>

          <article className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="text-base font-semibold text-slate-900">Delivery outcomes</h2>
            <p className="mt-1 text-sm text-slate-500">
              {formatCount(sentCount)} sent in {formatRangeLabel(analyticsFrom, analyticsTo)} · bounce rate {bounceRate}%
            </p>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                    <th className="pb-2 pr-3 font-medium">Outcome</th>
                    <th className="pb-2 px-2 font-medium">Count</th>
                    <th className="pb-2 pl-2 font-medium">Split</th>
                  </tr>
                </thead>
                <tbody>
                  {outcomeRows.map((row) => {
                    const isSelected = selected?.kind === 'outcome' && selected?.label === row.label;
                    return (
                      <tr
                        key={row.label}
                        className={`cursor-pointer border-t border-slate-100 ${isSelected ? 'bg-slate-50' : ''}`}
                        onClick={() => setSelected({ kind: 'outcome', ...row })}
                      >
                        <td className="py-2.5 pr-3">
                          <span className="inline-flex items-center gap-2 text-slate-800">
                            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: row.color }} />
                            {row.label}
                          </span>
                        </td>
                        <td className="px-2 py-2.5 tabular-nums text-slate-800">{formatCount(row.value)}</td>
                        <td className="py-2.5 pl-2"><SplitBar value={row.value} total={row.total} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-4 text-sm">
              <Link to="/logs" className="font-medium text-slate-700 underline-offset-2 hover:underline">View email logs</Link>
            </p>
          </article>
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <article className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="text-base font-semibold text-slate-900">Recent campaigns</h2>
            <p className="mt-1 text-sm text-slate-500">Latest campaigns in {formatRangeLabel(analyticsFrom, analyticsTo)}.</p>
            <div className="mt-4 max-h-[22rem] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                    <th className="pb-2 pr-3 font-medium">Campaign</th>
                    <th className="pb-2 px-2 font-medium">Owner</th>
                    <th className="pb-2 px-2 font-medium">Status</th>
                    <th className="pb-2 px-2 font-medium">Sent</th>
                    <th className="pb-2 pl-2 font-medium">Split</th>
                  </tr>
                </thead>
                <tbody>
                  {recentCampaigns.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-10 text-center text-slate-400">No campaigns in this period</td>
                    </tr>
                  ) : recentCampaigns.map((item, index) => {
                    const sent = Number(item.emails_sent || 0);
                    const status = (item.status || '').charAt(0).toUpperCase() + (item.status || '').slice(1);
                    const isSelected = selected?.kind === 'campaign' && selected?.id === item.id;
                    return (
                      <tr
                        key={item.id}
                        className={`cursor-pointer border-t border-slate-100 ${isSelected ? 'bg-slate-50' : ''}`}
                        onClick={() => setSelected({ kind: 'campaign', ...item })}
                      >
                        <td className="py-2.5 pr-3">
                          <span className="inline-flex items-center gap-2 text-slate-800">
                            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: ROW_DOTS[index % ROW_DOTS.length] }} />
                            <span className="max-w-[220px] truncate">{item.campaign_name}</span>
                          </span>
                        </td>
                        <td className="px-2 py-2.5 text-slate-800">{item.owner || '—'}</td>
                        <td className="px-2 py-2.5 text-slate-800">{status || '—'}</td>
                        <td className="px-2 py-2.5 tabular-nums text-slate-800">{formatCount(sent)}</td>
                        <td className="py-2.5 pl-2"><SplitBar value={sent} total={sentCount} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </article>

          {icp && linkedin && verification ? (
            <article className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="text-base font-semibold text-slate-900">ICP, LinkedIn & verification</h2>
              <p className="mt-1 text-sm text-slate-500">
                {formatCount(verifiedTotal)} addresses checked
                {adminData?.summary ? ` · ${formatCount(adminData.summary.replies)} replies` : ''}
              </p>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                      <th className="pb-2 pr-3 font-medium">Metric</th>
                      <th className="pb-2 px-2 font-medium">Count</th>
                      <th className="pb-2 pl-2 font-medium">Split</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { kind: 'icp', label: 'ICP contacts', value: icp.contacts, total: icpMix, color: ROW_DOTS[0], href: '/icp-contacts' },
                      { kind: 'icp', label: 'ICP accounts', value: icp.accounts, total: icpMix, color: ROW_DOTS[1], href: '/icp-accounts' },
                      { kind: 'icp', label: 'LinkedIn extracted', value: linkedin.successfully_extracted, total: linkedinMix, color: ROW_DOTS[2], href: '/linkedin-history' },
                      { kind: 'icp', label: 'LinkedIn failed', value: linkedin.failed, total: linkedinMix, color: ROW_DOTS[3], href: '/linkedin-history' },
                      { kind: 'verification', label: 'Good', value: verification.valid, total: verifiedTotal, color: ROW_DOTS[1] },
                      { kind: 'verification', label: 'Risky', value: verification.risky, total: verifiedTotal, color: ROW_DOTS[5] },
                      { kind: 'verification', label: 'Bad', value: verification.invalid, total: verifiedTotal, color: ROW_DOTS[3] },
                    ].map((row) => {
                      const isSelected = selected?.kind === row.kind && selected?.label === row.label;
                      return (
                        <tr
                          key={row.label}
                          className={`cursor-pointer border-t border-slate-100 ${isSelected ? 'bg-slate-50' : ''}`}
                          onClick={() => setSelected({ ...row })}
                        >
                          <td className="py-2.5 pr-3">
                            <span className="inline-flex items-center gap-2 text-slate-800">
                              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: row.color }} />
                              {row.label}
                            </span>
                          </td>
                          <td className="px-2 py-2.5 tabular-nums text-slate-800">{formatCount(row.value)}</td>
                          <td className="py-2.5 pl-2"><SplitBar value={row.value} total={row.total} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </article>
          ) : (
            <article className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="text-base font-semibold text-slate-900">Application activity</h2>
              <p className="mt-1 text-sm text-slate-500">Campaign and send totals for {formatRangeLabel(analyticsFrom, analyticsTo)}.</p>
              <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-lg border border-slate-100 p-3">
                  <dt className="text-slate-500">Campaigns</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums">{formatCount(stats.total_campaigns)}</dd>
                </div>
                <div className="rounded-lg border border-slate-100 p-3">
                  <dt className="text-slate-500">Mails sent</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums">{formatCount(sentCount)}</dd>
                </div>
                <div className="rounded-lg border border-slate-100 p-3">
                  <dt className="text-slate-500">Failed</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums">{formatCount(failedCount)}</dd>
                </div>
                <div className="rounded-lg border border-slate-100 p-3">
                  <dt className="text-slate-500">Bounce rate</dt>
                  <dd className="mt-1 text-lg font-semibold tabular-nums">{bounceRate}%</dd>
                </div>
              </dl>
            </article>
          )}
        </section>
      </div>

      <DashboardDetailPanel
        selection={selected}
        isOpen={Boolean(selected)}
        onClose={() => setSelected(null)}
        filters={{ ...filters, dateFrom: analyticsFrom, dateTo: analyticsTo }}
        campaigns={campaigns}
      />
    </>
  );
}
