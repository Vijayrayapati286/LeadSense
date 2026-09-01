import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { FiAlertCircle, FiArchive, FiCheckCircle, FiClock, FiDownload, FiExternalLink, FiEye, FiFileText, FiRefreshCw, FiSearch, FiUsers } from 'react-icons/fi';
import AuditLogPanel from '../components/bulk/AuditLogPanel';
import ReviewCompareModal from '../components/bulk/ReviewCompareModal';
import Pagination from '../components/ui/Pagination';
import SlideOver from '../components/ui/SlideOver';
import {
  EmptyState,
  ExtractorNav,
  MetricCard,
  SkeletonRows,
  StatusBadge,
  WorkspaceHeader,
} from '../components/ui/GrowthWorkspace';
import { useToast } from '../hooks/useToast';
import { linkedinProfileService } from '../services/services';
import { downloadBlob, formatDateTime } from '../utils/helpers';

const PAGE_SIZE = 25;

export default function BulkJobDetailPage() {
  const { jobId } = useParams();
  const toast = useToast();
  const [job, setJob] = useState(null);
  const [items, setItems] = useState({ total: 0, page: 1, items: [] });
  const [q, setQ] = useState('');
  const [verification, setVerification] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [audit, setAudit] = useState([]);
  const [auditOpen, setAuditOpen] = useState(false);
  const [selectedItem, setSelectedItem] = useState(null);

  async function load(page = 1, overrides = {}) {
    const nextQ = overrides.q ?? q;
    const nextVerification = overrides.verification ?? verification;
    setLoading(true);
    try {
      const [status, itemsPage, auditPayload, conflictsPayload] = await Promise.all([
        linkedinProfileService.getBulkJob(jobId),
        linkedinProfileService.listBulkJobItems(jobId, {
          q: nextQ || undefined,
          verification_status: nextVerification || undefined,
          page,
          page_size: PAGE_SIZE,
        }),
        linkedinProfileService.getBulkJobAudit(jobId).catch(() => ({ items: [] })),
        linkedinProfileService.getBulkConflicts(jobId, { page_size: 500 }).catch(() => ({ items: [] })),
      ]);
      const conflictMap = new Map(
        (conflictsPayload.items || []).map((item) => [item.item_id, item.conflicts || []]),
      );
      const mergedItems = (itemsPage.items || []).map((item) =>
        conflictMap.has(item.item_id) ? { ...item, conflicts: conflictMap.get(item.item_id) } : item,
      );
      setJob(status);
      setItems({ ...itemsPage, items: mergedItems });
      setAudit(auditPayload.items || []);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load job');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  async function onDownload() {
    try {
      const { blob, filename } = await linkedinProfileService.downloadBulkJob(jobId);
      downloadBlob(blob, filename || `bulk_${jobId}.xlsx`);
    } catch {
      toast.error('Excel not ready');
    }
  }

  async function onBackup() {
    setBusy(true);
    try {
      await linkedinProfileService.createBulkBackup(jobId);
      const { data } = await linkedinProfileService.downloadBulkJobBackup(jobId);
      downloadBlob(data, `bulk-job-${jobId}-backup.zip`);
      toast.success('Backup created');
      load(items.page || 1);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Backup failed');
    } finally {
      setBusy(false);
    }
  }

  async function onResolveSelected(decisions) {
    if (!selectedItem) return;
    setBusy(true);
    try {
      const result = await linkedinProfileService.resolveConflict(jobId, selectedItem.item_id, decisions);
      toast.success(result?.icp_synced ? 'Resolved and added to ICP Database' : 'Profile resolved');
      await load(items.page || 1);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not resolve this profile');
      throw err;
    } finally {
      setBusy(false);
    }
  }

  if (loading && !job) {
    return (
      <div className="workspace-shell" aria-busy="true">
        <div className="skeleton h-44 rounded-3xl" />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="skeleton h-[5.5rem] rounded-2xl" />
          ))}
        </div>
        <div className="surface-card overflow-hidden">
          <SkeletonRows rows={6} columns={6} />
        </div>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="workspace-shell">
        <EmptyState
          title="Job not found"
          description="This extraction may have been removed, or it belongs to another account."
          icon={FiSearch}
          action={<Link to="/linkedin-history" className="btn-primary inline-flex">Back to history</Link>}
        />
      </div>
    );
  }

  return (
    <div className="workspace-shell">
      <WorkspaceHeader
        eyebrow="Extraction history / Job details"
        title={job.original_file_name || 'Bulk extraction'}
        description={`${job.total || 0} profiles · Uploaded ${formatDateTime(job.created_at || job.started_at)}`}
        actions={
          <>
          <button
            type="button"
            onClick={() => load(items.page || 1)}
            className="btn-secondary inline-flex items-center gap-2"
          >
            <FiRefreshCw size={14} /> Refresh
          </button>
          <button
            type="button"
            onClick={() => setAuditOpen(true)}
            className="btn-secondary inline-flex items-center gap-2"
          >
            <FiClock size={14} />
            Audit log
            {audit.length > 0 ? <span className="badge badge-neutral">{audit.length}</span> : null}
          </button>
          {(job.needs_review || 0) > 0 ? (
            <button
              type="button"
              onClick={onDownload}
              disabled={!job.download_ready}
              className="btn-secondary inline-flex items-center gap-2 border-amber-300 text-amber-900"
            >
              <FiDownload size={14} /> Download with conflicts
            </button>
          ) : (
            <button
              type="button"
              onClick={onDownload}
              disabled={!job.download_ready}
              className="btn-primary inline-flex items-center gap-2"
            >
              <FiDownload size={14} /> Excel
            </button>
          )}
          <button
            type="button"
            onClick={onBackup}
            disabled={busy}
            className="btn-secondary inline-flex items-center gap-2"
          >
            <FiArchive size={14} /> Backup
          </button>
          {(job.needs_review || 0) > 0 && (
            <Link
              to={`/linkedin-needs-review?job=${job.job_id}`}
              className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 font-medium text-white transition-colors hover:bg-amber-600"
            >
              Review {job.needs_review}
            </Link>
          )}
          </>
        }
      >
        <ExtractorNav />
        <div className="relative z-10 mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-500">
          <Link to="/linkedin-history" className="font-semibold text-primary-600 hover:text-primary-700">← All history</Link>
          <StatusBadge status={(job.needs_review || 0) > 0 && job.status === 'done' ? 'needs_review' : job.status} />
          <span className="font-mono">{job.job_id}</span>
          <span>Last updated {formatDateTime(job.updated_at || job.completed_at)}</span>
        </div>
      </WorkspaceHeader>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Total profiles" value={job.total || 0} hint={`Phase: ${job.phase || 'pending'}`} icon={FiUsers} />
        <MetricCard label="Successful" value={job.completed || job.success || 0} hint={`${job.verified || 0} verified`} tone="green" icon={FiCheckCircle} />
        <MetricCard label="Needs review" value={job.needs_review || 0} hint={`${job.resolved || 0} resolved`} tone="amber" icon={FiAlertCircle} />
        <MetricCard label="Failed" value={job.failed || 0} hint={`${job.retrying || 0} retrying`} tone="red" icon={FiFileText} />
      </div>

      <section className="surface-card overflow-hidden">
      <form
        className="flex flex-col gap-2 border-b border-slate-100 p-4 sm:flex-row sm:p-5"
        onSubmit={(e) => {
          e.preventDefault();
          load(1);
        }}
      >
        <div className="relative flex-1">
          <FiSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search profile name, company, or LinkedIn URL"
            className="control pl-10"
          />
        </div>
        <select
          value={verification}
          onChange={(e) => setVerification(e.target.value)}
          className="control sm:w-48"
        >
          <option value="">All verification</option>
          <option value="VERIFIED">Verified</option>
          <option value="MISMATCH">Mismatch</option>
          <option value="REVIEW">Review</option>
          <option value="RESOLVED">Resolved</option>
          <option value="NOT_VERIFIED">Not verified</option>
        </select>
        <button type="submit" className="btn-primary">
          Apply
        </button>
      </form>

      {loading ? (
        <SkeletonRows rows={6} columns={6} />
      ) : (
      <div className="overflow-x-auto">
        <table className="data-table min-w-[980px]">
          <thead>
            <tr>
              <th scope="col">Row</th>
              <th scope="col">Profile</th>
              <th scope="col">Company &amp; role</th>
              <th scope="col">Extraction</th>
              <th scope="col">Verification</th>
              <th scope="col"><span className="sr-only">View details</span></th>
            </tr>
          </thead>
          <tbody>
            {(items.items || []).map((row) => {
              const profileName = row.resolved?.name || row.extracted?.name || row.uploaded?.name || 'Unnamed profile';
              const company = row.resolved?.company || row.extracted?.company || row.uploaded?.company;
              const role = row.resolved?.designation || row.extracted?.designation || row.uploaded?.designation;
              return (
              <tr
                key={row.item_id}
                tabIndex={0}
                role="button"
                aria-label={`View all details for ${profileName}`}
                onClick={() => setSelectedItem(row)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    setSelectedItem(row);
                  }
                }}
                className={`group cursor-pointer focus:outline-none focus-visible:bg-primary-50/60 ${
                  row.needs_review ? 'bg-amber-50/30 hover:bg-amber-50/60' : ''
                }`}
              >
                <td className="text-slate-400">{row.source_row_number}</td>
                <td>
                  <div className="max-w-[300px]">
                    <p className="truncate font-semibold text-slate-900">{profileName}</p>
                    {row.url ? (
                      <a
                        href={row.url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(event) => event.stopPropagation()}
                        className="mt-1 inline-flex max-w-full items-center gap-1 text-xs text-primary-600 hover:text-primary-700"
                      >
                        <span className="truncate">{row.url.replace(/^https?:\/\/(www\.)?/, '')}</span>
                        <FiExternalLink className="shrink-0" size={12} />
                      </a>
                    ) : <span className="text-xs text-slate-400">No profile URL</span>}
                  </div>
                </td>
                <td>
                  <p className="max-w-[220px] truncate font-medium text-slate-700">{company || '—'}</p>
                  {role ? <p className="mt-0.5 max-w-[220px] truncate text-xs text-slate-500">{role}</p> : null}
                </td>
                <td>
                  <StatusBadge status={row.extraction_status} kind="extraction" />
                </td>
                <td>
                  <StatusBadge
                    status={row.verification_status || 'NOT_VERIFIED'}
                    kind="verification"
                    tone={row.needs_review ? 'warning' : undefined}
                  />
                </td>
                <td className="text-right">
                  <span className={`inline-flex items-center gap-1.5 text-xs font-semibold opacity-0 transition-opacity group-hover:opacity-100 group-focus:opacity-100 ${
                    row.needs_review ? 'text-amber-700' : 'text-primary-600'
                  }`}>
                    <FiEye size={14} /> {row.needs_review ? 'Review' : 'View'}
                  </span>
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
        {!items.items?.length && (
          <div className="p-5">
            <EmptyState
              title={q || verification ? 'No rows match these filters' : 'This job has no rows yet'}
              description="Adjust the search term or verification filter to see more of this job."
              icon={FiSearch}
              action={
                q || verification ? (
                  <button
                    type="button"
                    onClick={() => {
                      setQ('');
                      setVerification('');
                      load(1, { q: '', verification: '' });
                    }}
                    className="btn-secondary"
                  >
                    Clear filters
                  </button>
                ) : null
              }
            />
          </div>
        )}
      </div>
      )}
      {items.total > PAGE_SIZE ? (
        <div className="border-t border-slate-100 px-3">
          <Pagination
            page={items.page || 1}
            pageSize={items.page_size || PAGE_SIZE}
            total={items.total || 0}
            onPageChange={load}
          />
        </div>
      ) : null}
      </section>

      <ReviewCompareModal
        item={selectedItem}
        isOpen={Boolean(selectedItem)}
        onClose={() => {
          if (!busy) setSelectedItem(null);
        }}
        onResolve={onResolveSelected}
        busy={busy}
      />

      <SlideOver
        isOpen={auditOpen}
        onClose={() => setAuditOpen(false)}
        title="Audit log"
        subtitle="Who changed what on this sheet"
      >
        <AuditLogPanel entries={audit} />
      </SlideOver>
    </div>
  );
}
