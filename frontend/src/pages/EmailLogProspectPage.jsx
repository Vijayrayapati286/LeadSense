import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { FiArrowLeft } from 'react-icons/fi';
import { logService } from '../services/services';
import { useToast } from '../hooks/useToast';
import PageShell from '../components/ui/PageShell';
import PageHeader from '../components/ui/PageHeader';
import SurfaceCard from '../components/ui/SurfaceCard';
import StatusBadge from '../components/ui/StatusBadge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { formatDateTime } from '../utils/helpers';
import { deliveryStatusDisplay } from '../utils/verificationStatus';

export default function EmailLogProspectPage() {
  const [params] = useSearchParams();
  const key = params.get('key') || '';
  const category = params.get('category') || '';
  const toast = useToast();
  const [group, setGroup] = useState(null);
  const [loading, setLoading] = useState(true);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (!key) {
      setMissing(true);
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setMissing(false);
    logService.getProspect(key)
      .then(({ data }) => {
        if (!cancelled) setGroup(data);
      })
      .catch(() => {
        if (!cancelled) {
          setGroup(null);
          setMissing(true);
          toast.error('Failed to load this prospect');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [key, toast]);

  const backTo = category ? `/logs?category=${encodeURIComponent(category)}` : '/logs';
  const sendCount = group?.send_count ?? 0;
  const sendLabel = sendCount === 1 ? '1 email sent' : `${sendCount} emails sent`;
  const identity = [group?.recipient_email, group?.company].filter(Boolean).join(' · ');

  return (
    <PageShell maxWidth="max-w-[1100px]">
      <Link to={backTo} className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-800">
        <FiArrowLeft size={16} />
        Back to logs
      </Link>

      {loading ? (
        <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
      ) : missing || !group ? (
        <SurfaceCard className="p-8 text-center">
          <h1 className="font-bold text-slate-900">Prospect not found</h1>
          <p className="mt-1 text-sm text-slate-500">This address is not in the email logs.</p>
        </SurfaceCard>
      ) : (
        <>
          <PageHeader
            eyebrow="Email logs"
            title={group.recipient_name || group.recipient_email || 'Prospect'}
            subtitle={identity || 'No email on file'}
          />

          <p className="text-sm font-semibold text-slate-700">{sendLabel}</p>

          <div className="surface-card overflow-hidden">
            {sendCount === 0 ? (
              <p className="px-6 py-12 text-center text-sm text-slate-400">No emails sent to this person.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table min-w-[760px]">
                  <thead className="border-b border-slate-200 bg-slate-50/95">
                    <tr>
                      <th className="px-6 py-3 font-medium">Campaign</th>
                      <th className="px-6 py-3 font-medium">Sent by</th>
                      <th className="px-6 py-3 font-medium">Date</th>
                      <th className="px-6 py-3 font-medium">Status</th>
                      <th className="px-6 py-3 font-medium">Error message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(group.logs || []).map((log) => (
                      <tr key={log.id}>
                        <td className="px-6 py-4 text-slate-700">{log.campaign_name || `Campaign #${log.campaign_id}`}</td>
                        <td className="px-6 py-4 text-slate-600">
                          {log.sender_name || '—'}
                          {log.sender_email ? <p className="text-xs text-slate-400">{log.sender_email}</p> : null}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-slate-600">{formatDateTime(log.sent_at)}</td>
                        <td className="px-6 py-4">
                          <div className="flex flex-wrap items-center gap-2">
                            <StatusBadge {...deliveryStatusDisplay(log.status, { errorMessage: log.error_message })} />
                            {log.source === 'manual' ? (
                              <span className="text-xs font-medium text-primary-700">Outside mail</span>
                            ) : null}
                          </div>
                        </td>
                        <td className="max-w-xs truncate px-6 py-4 text-xs text-slate-500">{log.error_message || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </PageShell>
  );
}
