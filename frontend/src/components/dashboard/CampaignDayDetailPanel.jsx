import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiArrowRight, FiDatabase, FiMail, FiTrendingUp } from 'react-icons/fi';
import SlideOver from '../ui/SlideOver';
import LoadingSpinner from '../ui/LoadingSpinner';
import StatusBadge from '../ui/StatusBadge';
import { logService } from '../../services/services';
import { formatDateTime } from '../../utils/helpers';
import { deliveryStatusDisplay } from '../../utils/verificationStatus';

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
  return new Date(`${isoDate}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long' });
}

function MetricExplain({ icon: Icon, label, value, hint, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-50 text-slate-600',
    orange: 'bg-orange-50 text-orange-600',
    green: 'bg-emerald-50 text-emerald-600',
    blue: 'bg-blue-50 text-blue-600',
  };
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-start gap-3">
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${tones[tone]}`}>
          <Icon size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</p>
            <p className="text-lg font-bold text-slate-900">{value}</p>
          </div>
          <p className="mt-1.5 text-xs leading-5 text-slate-500">{hint}</p>
        </div>
      </div>
    </div>
  );
}

export default function CampaignDayDetailPanel({
  day,
  isOpen,
  onClose,
  filters = {},
}) {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const loadLogs = useCallback(async () => {
    if (!day?.isoDate) return;
    setLoading(true);
    try {
      const { data } = await logService.getAll({
        page: 1,
        page_size: 8,
        status: 'sent',
        user_id: filters.userId || undefined,
        campaign_id: filters.campaignId || undefined,
        date_from: day.isoDate,
        date_to: day.isoDate,
      });
      setLogs(data.items || []);
      setTotal(data.total ?? 0);
    } catch {
      setLogs([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [day?.isoDate, filters.userId, filters.campaignId]);

  useEffect(() => {
    if (!isOpen || !day) return;
    loadLogs();
  }, [isOpen, day, loadLogs]);

  if (!day) return null;

  const subtitleParts = [
    weekdayLabel(day.isoDate),
    day.isToday ? 'Today' : day.isYesterday ? 'Yesterday' : null,
  ].filter(Boolean);

  const logsHref = `/logs?dateFrom=${day.isoDate}&dateTo=${day.isoDate}`;
  const icpDayLabel = day.icpDbDay > 0 ? `+ ${formatCount(day.icpDbDay)}` : '0';

  return (
    <SlideOver
      isOpen={isOpen}
      onClose={onClose}
      title="Day performance"
      subtitle={[formatDisplayDate(day.isoDate), ...subtitleParts].filter(Boolean).join(' · ')}
      width="lg"
    >
      <div className="space-y-5">
        <section className="grid gap-3 sm:grid-cols-2">
          <MetricExplain
            icon={FiMail}
            label="Sent"
            value={formatCount(day.sent)}
            hint="Emails successfully sent on this day from campaigns in the current filter."
            tone="orange"
          />
          <MetricExplain
            icon={FiTrendingUp}
            label={`Cum (${day.monthLabel || 'month'})`}
            value={formatCount(day.cumulativeMonth)}
            hint="Running total of sends in this calendar month, up to and including this day."
            tone="blue"
          />
          <MetricExplain
            icon={FiTrendingUp}
            label="Cum all"
            value={formatCount(day.cumulativeOverall)}
            hint="All-time running total of successful sends through this day."
            tone="slate"
          />
          <MetricExplain
            icon={FiDatabase}
            label="ICP day"
            value={icpDayLabel}
            hint="New Ideal Customer Profile records added to the ICP database on this day."
            tone="green"
          />
          <MetricExplain
            icon={FiDatabase}
            label="ICP total"
            value={formatCount(day.icpDbCumulative)}
            hint="Running cumulative count of ICP database records through this day."
            tone="green"
          />
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white">
          <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
            <div>
              <h3 className="text-sm font-bold text-slate-900">Emails sent</h3>
              <p className="mt-0.5 text-xs text-slate-500">
                {loading ? 'Loading…' : `${formatCount(total)} sent this day`}
              </p>
            </div>
            <Link
              to={logsHref}
              className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-700"
            >
              View all <FiArrowRight size={12} />
            </Link>
          </div>

          {loading ? (
            <div className="flex justify-center py-10">
              <LoadingSpinner size="sm" />
            </div>
          ) : logs.length === 0 ? (
            <p className="px-4 py-10 text-center text-xs text-slate-400">No emails sent on this day</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {logs.map((log) => (
                <li key={log.id} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-800">
                        {log.recipient_email || log.recipient_name || 'Unknown recipient'}
                      </p>
                      <p className="mt-0.5 truncate text-xs text-slate-400">
                        {log.campaign_name || `Campaign #${log.campaign_id}`}
                        {log.sender_name ? ` · ${log.sender_name}` : ''}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-400">{formatDateTime(log.sent_at)}</p>
                    </div>
                    <StatusBadge {...deliveryStatusDisplay(log.status, { errorMessage: log.error_message })} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </SlideOver>
  );
}
