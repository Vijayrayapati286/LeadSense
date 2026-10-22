import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiArrowRight } from 'react-icons/fi';
import SlideOver from '../ui/SlideOver';
import LoadingSpinner from '../ui/LoadingSpinner';
import StatusBadge from '../ui/StatusBadge';
import { campaignService, logService } from '../../services/services';
import { formatDateTime } from '../../utils/helpers';
import { deliveryStatusDisplay } from '../../utils/verificationStatus';

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

function weekdayLabel(isoDate) {
  if (!isoDate) return '';
  return new Date(`${isoDate}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long' });
}

function formatLongDate(isoDate) {
  if (!isoDate) return '—';
  const date = new Date(`${isoDate}T12:00:00`);
  return `${date.getDate()} ${date.toLocaleDateString('en-GB', { month: 'short' })} ${date.getFullYear()}`;
}

function Fact({ label, value }) {
  return (
    <div className="border-t border-slate-100 py-2.5">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-sm text-slate-900">{value}</p>
    </div>
  );
}

function NavLink({ to, children }) {
  return (
    <Link
      to={to}
      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800"
    >
      {children}
      <FiArrowRight size={14} />
    </Link>
  );
}

function LogList({ logs, loading, empty }) {
  if (loading) {
    return (
      <div className="flex justify-center py-10">
        <LoadingSpinner size="sm" />
      </div>
    );
  }
  if (!logs.length) {
    return <p className="py-8 text-center text-sm text-slate-400">{empty}</p>;
  }
  return (
    <ul className="divide-y divide-slate-100">
      {logs.map((log) => (
        <li key={log.id}>
          <Link
            to={log.campaign_id ? `/campaigns/${log.campaign_id}` : '/logs'}
            className="flex items-start justify-between gap-3 py-3"
          >
            <div className="min-w-0">
              <p className="truncate text-sm text-slate-800">
                {log.recipient_email || log.recipient_name || 'Unknown recipient'}
              </p>
              <p className="mt-0.5 truncate text-xs text-slate-500">
                {log.campaign_name || (log.campaign_id ? `Campaign #${log.campaign_id}` : 'No campaign')}
                {log.sender_name ? ` · ${log.sender_name}` : ''}
              </p>
              <p className="mt-1 text-[11px] text-slate-400">{formatDateTime(log.sent_at)}</p>
            </div>
            <StatusBadge {...deliveryStatusDisplay(log.status, { errorMessage: log.error_message })} />
          </Link>
        </li>
      ))}
    </ul>
  );
}

function useLogs(enabled, params) {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const key = JSON.stringify(params);

  const load = useCallback(async () => {
    if (!enabled) return;
    const query = JSON.parse(key);
    setLoading(true);
    try {
      const { data } = await logService.getAll({ page: 1, page_size: 20, ...query });
      setLogs(data.items || []);
      setTotal(data.total ?? 0);
    } catch {
      setLogs([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [enabled, key]);

  useEffect(() => {
    load();
  }, [load]);

  return { logs, total, loading };
}

const OUTCOME_STATUS = {
  Sent: 'sent',
  Pending: 'pending',
  Failed: 'failed',
  'Hard bounces': 'bounced',
};

export default function DashboardDetailPanel({
  selection,
  isOpen,
  onClose,
  filters = {},
  campaigns = [],
}) {
  const kind = selection?.kind;
  const logsEnabled = Boolean(
    isOpen && (
      kind === 'day'
      || kind === 'month'
      || kind === 'campaign'
      || (kind === 'outcome' && OUTCOME_STATUS[selection?.label])
    ),
  );
  const logParams = useMemo(() => {
    if (kind === 'day') {
      return {
        status: 'sent',
        user_id: filters.userId || undefined,
        campaign_id: filters.campaignId || undefined,
        date_from: selection.isoDate,
        date_to: selection.isoDate,
      };
    }
    if (kind === 'month') {
      return {
        status: 'sent',
        user_id: filters.userId || undefined,
        campaign_id: filters.campaignId || undefined,
        date_from: selection.dateFrom,
        date_to: selection.dateTo,
      };
    }
    if (kind === 'outcome') {
      return {
        status: OUTCOME_STATUS[selection.label] || undefined,
        user_id: filters.userId || undefined,
        campaign_id: filters.campaignId || undefined,
        date_from: filters.dateFrom || undefined,
        date_to: filters.dateTo || undefined,
      };
    }
    if (kind === 'campaign') {
      return {
        campaign_id: selection.id,
        user_id: filters.userId || undefined,
        date_from: filters.dateFrom || undefined,
        date_to: filters.dateTo || undefined,
      };
    }
    return {};
  }, [kind, selection, filters]);

  const { logs, total, loading } = useLogs(logsEnabled, logParams);
  const [campaignDetail, setCampaignDetail] = useState(null);

  useEffect(() => {
    if (!isOpen || kind !== 'campaign' || !selection?.id) {
      setCampaignDetail(null);
      return undefined;
    }
    let cancelled = false;
    campaignService.getById(selection.id)
      .then(({ data }) => {
        if (!cancelled) setCampaignDetail(data);
      })
      .catch(() => {
        if (!cancelled) setCampaignDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, kind, selection?.id]);

  if (!selection) return null;

  const logQuery = new URLSearchParams(
    Object.entries({
      status: logParams.status,
      dateFrom: logParams.date_from,
      dateTo: logParams.date_to,
      userId: filters.userId,
      campaignId: logParams.campaign_id || filters.campaignId,
    }).filter(([, value]) => value),
  ).toString();

  let title = 'Details';
  let subtitle = '';
  let facts = [];
  let nav = [];
  let listTitle = '';
  let listEmpty = 'No records';
  let extraList = null;

  if (kind === 'day') {
    title = formatLongDate(selection.isoDate);
    subtitle = [weekdayLabel(selection.isoDate), selection.isToday ? 'Today' : selection.isYesterday ? 'Yesterday' : null]
      .filter(Boolean)
      .join(' · ');
    facts = [
      { label: 'Sent', value: formatCount(selection.sent) },
      { label: 'Delivered', value: formatCount(selection.delivered) },
      { label: `Cum (${selection.monthLabel || 'month'})`, value: formatCount(selection.cumulativeMonth) },
      { label: 'Cum all', value: formatCount(selection.cumulativeOverall) },
      { label: 'ICP added', value: formatCount(selection.icpDbDay) },
      { label: 'ICP total', value: formatCount(selection.icpDbCumulative) },
    ];
    nav = [
      { to: `/logs?${logQuery}`, label: 'Open email logs' },
      { to: '/icp-contacts', label: 'Open ICP contacts' },
    ];
    listTitle = `Emails sent (${formatCount(total)})`;
    listEmpty = 'No emails sent on this day';
  }

  if (kind === 'month') {
    title = `${selection.month || 'Month'} ${selection.year || ''}`.trim();
    subtitle = 'Month totals through the selected end date';
    facts = [
      { label: 'Mails sent', value: formatCount(selection.mailsSent) },
      { label: 'ICP database', value: formatCount(selection.icpDatabase) },
    ];
    nav = [
      { to: `/logs?${logQuery}`, label: 'Open email logs' },
      { to: '/icp-contacts', label: 'Open ICP contacts' },
    ];
    listTitle = `Emails sent (${formatCount(total)})`;
    listEmpty = 'No emails sent in this month';
  }

  if (kind === 'campaign-status') {
    const status = (selection.status || '').toLowerCase();
    const matches = campaigns.filter((item) => (item.status || '').toLowerCase() === status);
    title = `${selection.status} campaigns`;
    subtitle = `${formatCount(selection.count)} campaigns · ${selection.share || 0}% of total`;
    facts = [
      { label: 'Status', value: selection.status },
      { label: 'Campaigns', value: formatCount(selection.count) },
      { label: 'Share', value: `${selection.share || 0}%` },
    ];
    nav = [{ to: '/campaigns', label: 'Open all campaigns' }];
    extraList = (
      <ul className="divide-y divide-slate-100">
        {matches.length === 0 ? (
          <li className="py-8 text-center text-sm text-slate-400">No campaigns with this status</li>
        ) : matches.map((item) => (
          <li key={item.id}>
            <Link to={`/campaigns/${item.id}`} className="flex items-center justify-between gap-3 py-3">
              <span className="truncate text-sm text-slate-800">{item.campaign_name}</span>
              <span className="shrink-0 text-xs text-slate-500">{item.owner || '—'}</span>
            </Link>
          </li>
        ))}
      </ul>
    );
    listTitle = 'Campaigns';
  }

  if (kind === 'outcome') {
    title = selection.label;
    subtitle = `${formatCount(selection.value)} in the selected period`;
    facts = [
      { label: 'Count', value: formatCount(selection.value) },
      { label: 'Share of comparison set', value: selection.total ? `${Math.round((selection.value / selection.total) * 100)}%` : '—' },
    ];
    if (selection.label === 'Hard bounces' || selection.label === 'Soft bounces pending') {
      nav = [{ to: '/blacklist', label: 'Open blacklist' }, { to: `/logs?${logQuery}`, label: 'Open email logs' }];
      listEmpty = 'No matching email logs';
    } else {
      nav = [{ to: `/logs?${logQuery}`, label: 'Open email logs' }];
      listEmpty = `No ${selection.label.toLowerCase()} emails in this period`;
    }
    listTitle = `Matching emails (${formatCount(total)})`;
  }

  if (kind === 'campaign') {
    const detail = campaignDetail || selection;
    const status = (detail.status || '').charAt(0).toUpperCase() + (detail.status || '').slice(1);
    title = detail.campaign_name || 'Campaign';
    subtitle = detail.campaign_id ? `ID ${detail.campaign_id}` : 'Campaign detail';
    facts = [
      { label: 'Owner', value: detail.owner || '—' },
      { label: 'Status', value: status || '—' },
      { label: 'Emails sent', value: formatCount(detail.emails_sent) },
      { label: 'Created', value: detail.created_at ? formatDateTime(detail.created_at) : '—' },
    ];
    nav = [
      { to: `/campaigns/${selection.id}`, label: 'Open campaign' },
      { to: `/logs?campaignId=${selection.id}`, label: 'Open campaign logs' },
      { to: `/campaigns/update-list?campaign=${selection.id}`, label: 'Schedule list' },
    ];
    listTitle = `Recent emails (${formatCount(total)})`;
    listEmpty = 'No emails for this campaign in the selected period';
  }

  if (kind === 'icp') {
    title = selection.label;
    subtitle = `${formatCount(selection.value)} records`;
    facts = [
      { label: 'Count', value: formatCount(selection.value) },
      { label: 'Share', value: selection.total ? `${Math.round((selection.value / selection.total) * 100)}%` : '—' },
    ];
    nav = [{ to: selection.href, label: `Open ${selection.label}` }];
  }

  if (kind === 'verification') {
    title = `${selection.label} emails`;
    subtitle = `${formatCount(selection.value)} of ${formatCount(selection.total)} checked`;
    facts = [
      { label: 'Result', value: selection.label },
      { label: 'Count', value: formatCount(selection.value) },
      { label: 'Share', value: selection.total ? `${Math.round((selection.value / selection.total) * 100)}%` : '—' },
    ];
    nav = [{ to: '/recipients', label: 'Open prospects' }, { to: '/logs', label: 'Open email logs' }];
  }

  const showLogs = kind === 'day' || kind === 'month' || kind === 'outcome' || kind === 'campaign';

  return (
    <SlideOver
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      subtitle={subtitle}
      width="full"
      plain
    >
      <div className="space-y-6">
        {facts.length ? (
          <section>
            {facts.map((item) => (
              <Fact key={item.label} label={item.label} value={item.value} />
            ))}
          </section>
        ) : null}

        {nav.length ? (
          <section className="flex flex-wrap gap-2">
            {nav.map((item) => (
              <NavLink key={item.to} to={item.to}>{item.label}</NavLink>
            ))}
          </section>
        ) : null}

        {listTitle ? (
          <section>
            <h3 className="mb-2 text-sm font-semibold text-slate-900">{listTitle}</h3>
            {showLogs ? (
              <LogList logs={logs} loading={loading} empty={listEmpty} />
            ) : extraList}
          </section>
        ) : null}
      </div>
    </SlideOver>
  );
}
