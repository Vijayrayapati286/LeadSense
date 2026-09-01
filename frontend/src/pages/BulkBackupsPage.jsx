import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiArchive, FiDownload, FiShield, FiUpload } from 'react-icons/fi';
import { EmptyState, ExtractorNav, SkeletonCards, WorkspaceHeader } from '../components/ui/GrowthWorkspace';
import { useToast } from '../hooks/useToast';
import { linkedinProfileService } from '../services/services';
import { downloadBlob, formatDateTime } from '../utils/helpers';

const BACKUP_TONE = { ready: 'success', failed: 'danger', none: 'neutral' };

export default function BulkBackupsPage() {
  const toast = useToast();
  const fileRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const payload = await linkedinProfileService.listBulkBackups();
      setItems(payload.items || []);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load backups');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onDownload(backupId, jobId) {
    try {
      const { data } = await linkedinProfileService.downloadBackup(backupId);
      downloadBlob(data, `bulk-job-${jobId}-backup.zip`);
    } catch {
      toast.error('Download failed');
    }
  }

  async function onRestore(file) {
    if (!file) return;
    setBusy(true);
    try {
      const result = await linkedinProfileService.restoreBulkBackup(file);
      toast.success(`Restored as new job ${result.job_id}`);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Restore failed');
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  return (
    <div className="workspace-shell">
      <WorkspaceHeader
        eyebrow="Profile intelligence"
        title="Extraction backups"
        description="Keep recoverable snapshots of important extraction jobs. Restoring a backup always creates a new job and never overwrites your original."
        actions={
          <div>
          <input
            ref={fileRef}
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            onChange={(e) => onRestore(e.target.files?.[0])}
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
            className="btn-primary inline-flex items-center gap-2"
          >
            <FiUpload size={16} /> Restore ZIP
          </button>
          </div>
        }
      >
        <ExtractorNav />
      </WorkspaceHeader>

      {loading ? (
        <SkeletonCards count={3} className="h-24" />
      ) : items.length ? (
        <section className="surface-card divide-y divide-slate-100 overflow-hidden">
          {items.map((b) => (
            <div
              key={b.id}
              className="flex flex-col justify-between gap-4 p-4 transition-colors hover:bg-slate-50/70 sm:flex-row sm:items-center sm:p-5"
            >
              <div className="flex min-w-0 items-start gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-700">
                  <FiArchive size={18} />
                </span>
                <div className="min-w-0">
                <p className="truncate font-semibold text-slate-900">{b.original_file_name || b.job_id}</p>
                <p className="mt-1 text-xs text-slate-500">
                  Version {b.backup_version} · {formatDateTime(b.created_at)}
                </p>
                <Link
                  to={`/linkedin-history/${b.job_id}`}
                  className="mt-1 inline-block text-xs font-semibold text-primary-600 hover:text-primary-700"
                >
                  Open original job →
                </Link>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`badge capitalize badge-${BACKUP_TONE[b.status] || 'neutral'}`}>
                  <FiShield size={12} /> {b.status}
                </span>
                <button
                  type="button"
                  onClick={() => onDownload(b.id, b.job_id)}
                  className="btn-secondary inline-flex items-center gap-2"
                >
                  <FiDownload size={14} /> Download
                </button>
              </div>
            </div>
          ))}
        </section>
      ) : (
        <section className="surface-card p-5">
          <EmptyState
            title="No backups yet"
            description="Open a completed job from History and create its first recoverable snapshot."
            icon={FiArchive}
            action={<Link to="/linkedin-history" className="btn-primary inline-flex">Browse history</Link>}
          />
        </section>
      )}
    </div>
  );
}
