import { useRef, useState } from 'react';
import { FiDownload, FiFile, FiTrash2, FiUpload } from 'react-icons/fi';
import { filesService } from '../../services/services';
import { useToast } from '../../hooks/useToast';

const ACCEPT =
  '.pdf,.ppt,.pptx,.xlsx,.xls,.xlsm,.csv,.ods,.doc,.docx,application/pdf,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

function formatBytes(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function fileIcon(filename = '') {
  const ext = filename.split('.').pop()?.toLowerCase();
  if (ext === 'pdf') return 'PDF';
  if (ext === 'ppt' || ext === 'pptx') return 'PPT';
  if (['xlsx', 'xls', 'xlsm', 'csv', 'ods'].includes(ext)) return 'XLS';
  if (ext === 'doc' || ext === 'docx') return 'DOC';
  return 'FILE';
}

export default function OfferingVouchersSection({ vouchers = [], batchId, onChange }) {
  const toast = useToast();
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);

  async function uploadFiles(fileList) {
    const files = Array.from(fileList || []).filter(Boolean);
    if (!files.length) return;

    setUploading(true);
    const added = [];
    try {
      for (const file of files) {
        const result = await filesService.uploadVoucher(file, batchId);
        added.push({
          file_id: result.file_id,
          filename: result.filename,
          file_size: result.file_size || file.size || 0,
          mime_type: file.type || null,
          uploaded_at: new Date().toISOString(),
        });
      }
      onChange([...(vouchers || []), ...added]);
      toast.success(added.length === 1 ? 'Brochure uploaded' : `${added.length} brochures uploaded`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    if (!uploading) uploadFiles(e.dataTransfer?.files);
  }

  function removeVoucher(fileId) {
    onChange((vouchers || []).filter((v) => v.file_id !== fileId));
  }

  async function downloadVoucher(voucher) {
    try {
      const blob = await filesService.downloadContent(voucher.file_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = voucher.filename || 'voucher';
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Download failed');
    }
  }

  return (
    <section className="surface-card space-y-4 p-5 sm:p-6">
      <div>
        <h2 className="font-semibold text-slate-900">Brochures</h2>
        <p className="mt-1 text-sm text-slate-500">
          Upload sales collateral — PDF decks, PowerPoint, Excel sheets, or Word docs.
        </p>
      </div>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => uploadFiles(e.target.files)}
      />

      <button
        type="button"
        disabled={uploading}
        onClick={() => !uploading && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!uploading) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`w-full rounded-2xl border-2 border-dashed px-5 py-8 text-left transition-colors ${
          dragOver
            ? 'border-primary-500 bg-primary-50'
            : 'border-slate-200 bg-slate-50 hover:border-primary-300 hover:bg-white'
        }`}
      >
        <div className="flex flex-col items-center gap-3 text-center sm:flex-row sm:text-left">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-primary-600">
            <FiUpload size={20} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-slate-900">
              {uploading ? 'Uploading…' : 'Drop files here or click to browse'}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">PDF, PPT, Excel, CSV, Word — multiple files allowed</p>
          </div>
        </div>
      </button>

      {vouchers?.length ? (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-100">
          {vouchers.map((voucher) => (
            <li key={voucher.file_id} className="flex items-center gap-3 px-4 py-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-[10px] font-bold text-slate-600">
                {fileIcon(voucher.filename)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-slate-900">{voucher.filename}</p>
                <p className="text-xs text-slate-400">{formatBytes(voucher.file_size)}</p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  onClick={() => downloadVoucher(voucher)}
                  className="rounded-lg p-2 text-slate-400 hover:bg-slate-50 hover:text-primary-600"
                  title="Download"
                >
                  <FiDownload size={16} />
                </button>
                <button
                  type="button"
                  onClick={() => removeVoucher(voucher.file_id)}
                  className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600"
                  title="Remove"
                >
                  <FiTrash2 size={16} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="flex items-center gap-2 text-xs text-slate-400">
          <FiFile size={14} />
          No brochures uploaded yet
        </p>
      )}
    </section>
  );
}
