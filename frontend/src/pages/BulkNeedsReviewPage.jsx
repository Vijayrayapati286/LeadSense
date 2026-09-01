import { useEffect, useState } from 'react';
import { FiAlertCircle, FiCheckCircle, FiClock, FiLayers } from 'react-icons/fi';
import { Link, useSearchParams } from 'react-router-dom';
import AuditLogPanel from '../components/bulk/AuditLogPanel';
import ExtractionReviewPanel from '../components/bulk/ExtractionReviewPanel';
import SlideOver from '../components/ui/SlideOver';
import { useToast } from '../hooks/useToast';
import { linkedinProfileService } from '../services/services';
import {
  EmptyState,
  ExtractorNav,
  LoadingAnnouncement,
  MetricCard,
  SkeletonCards,
  WorkspaceHeader,
} from '../components/ui/GrowthWorkspace';

export default function BulkNeedsReviewPage() {
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const jobFilter = searchParams.get('job') || '';
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(jobFilter);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [audit, setAudit] = useState([]);
  const [auditOpen, setAuditOpen] = useState(false);

  async function loadJobs() {
    const payload = await linkedinProfileService.listBulkJobs({
      needs_review: true,
      page_size: 50,
    });
    setJobs(payload.items || []);
    if (!selectedJob && payload.items?.length) {
      setSelectedJob(payload.items[0].job_id);
    }
  }

  async function loadItems(jobId) {
    if (!jobId) {
      setItems([]);
      return;
    }
    const [allPayload, conflictsPayload] = await Promise.all([
      linkedinProfileService.listBulkJobItems(jobId, { page_size: 500 }),
      linkedinProfileService.getBulkConflicts(jobId, { page_size: 500 }),
    ]);
    const conflictMap = new Map(
      (conflictsPayload.items || []).map((row) => [row.item_id, row]),
    );
    const merged = (allPayload.items || []).map((item) => {
      const conflictRow = conflictMap.get(item.item_id);
      return conflictRow ? { ...item, conflicts: conflictRow.conflicts } : item;
    });
    setItems(merged);
    try {
      const auditPayload = await linkedinProfileService.getBulkJobAudit(jobId);
      setAudit(auditPayload.items || []);
    } catch {
      setAudit([]);
    }
  }

  async function refresh() {
    setLoading(true);
    try {
      await loadJobs();
      const jobId = selectedJob || jobFilter;
      if (jobId) await loadItems(jobId);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load conflicts');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedJob) return;
    setSearchParams({ job: selectedJob });
    loadItems(selectedJob).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedJob]);

  async function onResolve(item, decisions) {
    if (!item || !selectedJob) return;
    setBusy(true);
    try {
      const result = await linkedinProfileService.resolveConflict(selectedJob, item.item_id, decisions);
      if (result?.icp_synced) {
        toast.success('Resolved and added to ICP Database');
      } else {
        toast.success('Record resolved');
      }
      await loadItems(selectedJob);
      await loadJobs();
      const remaining = await linkedinProfileService.getBulkConflicts(selectedJob, {
        page_size: 1,
      });
      if (!(remaining.items || []).length) {
        toast.success('All conflicts resolved. You can download a clean Excel.');
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Resolve failed');
      throw err;
    } finally {
      setBusy(false);
    }
  }

  async function onBulkResolve(itemIds, decisions) {
    if (!selectedJob || !itemIds.length) return;
    setBusy(true);
    try {
      const result = await linkedinProfileService.bulkResolveConflicts(selectedJob, {
        item_ids: itemIds,
        decisions,
        confirm: true,
      });
      toast.success(`Resolved ${result?.updated ?? itemIds.length} records`);
      await loadItems(selectedJob);
      await loadJobs();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Bulk resolve failed');
      throw err;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace-shell">
      <WorkspaceHeader
        eyebrow="Quality queue"
        title="Resolve exceptions with confidence"
        description="Review only the fields that changed, choose the trusted value, and keep a complete audit trail before records reach your ICP database."
      >
        <ExtractorNav />
      </WorkspaceHeader>

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard label="Jobs in queue" value={jobs.length} hint="Require attention" tone="amber" icon={FiLayers} />
        <MetricCard label="Open records" value={items.filter((item) => (item.verification_status || '').toUpperCase() !== 'VERIFIED').length} hint="In selected job" tone="red" icon={FiAlertCircle} />
        <MetricCard label="Verified records" value={items.filter((item) => ['VERIFIED', 'RESOLVED'].includes((item.verification_status || '').toUpperCase())).length} hint="In selected job" tone="green" icon={FiCheckCircle} />
      </div>

      <div className="surface-card flex flex-col gap-3 p-4 sm:flex-row sm:items-end sm:p-5">
        <div className="min-w-0 flex-1 sm:max-w-lg">
          <label htmlFor="review-job" className="field-label">
            Reviewing sheet
          </label>
          <select
            id="review-job"
            value={selectedJob}
            onChange={(e) => setSelectedJob(e.target.value)}
            className="control"
          >
            <option value="">Select a job…</option>
            {jobs.map((j) => (
              <option key={j.job_id} value={j.job_id}>
                {(j.original_file_name || j.job_id).slice(0, 48)} ({j.needs_review} open)
              </option>
            ))}
          </select>
        </div>
        {selectedJob && (
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`/linkedin-history/${selectedJob}`} className="btn-secondary">
              Open job detail
            </Link>
            <button
              type="button"
              onClick={() => setAuditOpen(true)}
              className="btn-secondary inline-flex items-center gap-2"
            >
              <FiClock size={15} />
              Audit log
              {audit.length > 0 ? <span className="badge badge-neutral">{audit.length}</span> : null}
            </button>
          </div>
        )}
      </div>

      {loading ? (
        <>
          <LoadingAnnouncement label="Loading review queue" />
          <SkeletonCards count={3} className="h-32" />
        </>
      ) : !selectedJob ? (
        <EmptyState title="Your review queue is clear" description="New conflicts will appear here when an extraction finds meaningful differences." icon={FiCheckCircle} />
      ) : (
        <ExtractionReviewPanel
          items={items}
          busy={busy}
          onResolve={onResolve}
          onBulkResolve={onBulkResolve}
          emptyMessage="No records for this job yet."
        />
      )}

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
