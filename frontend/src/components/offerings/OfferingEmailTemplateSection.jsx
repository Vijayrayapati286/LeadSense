import { useRef, useState } from 'react';
import { FiFileText, FiTrash2, FiUpload } from 'react-icons/fi';
import { offeringsService } from '../../services/services';
import { useToast } from '../../hooks/useToast';

const ACCEPT = '.html,.htm,.txt,.docx';

export default function OfferingEmailTemplateSection({ emailTemplate, onChange }) {
  const toast = useToast();
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);

  async function uploadFile(file) {
    if (!file) return;
    setUploading(true);
    try {
      const parsed = await offeringsService.parseEmailTemplate(file);
      onChange({
        ...parsed,
        uploaded_at: new Date().toISOString(),
      });
      toast.success('Email template uploaded');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to parse email template');
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    if (!uploading) uploadFile(e.dataTransfer?.files?.[0]);
  }

  return (
    <section className="surface-card space-y-4 p-5 sm:p-6">
      <div>
        <h2 className="font-semibold text-slate-900">Email template</h2>
        <p className="mt-1 text-sm text-slate-500">
          Upload one outreach email — it appears as Introduction Outreach when creating campaigns for this offering.
        </p>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => uploadFile(e.target.files?.[0])}
      />

      {!emailTemplate ? (
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
                {uploading ? 'Parsing template…' : 'Drop template here or click to browse'}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">HTML, TXT, or Word (.docx) — one file only</p>
            </div>
          </div>
        </button>
      ) : (
        <div className="rounded-xl border border-primary-200 bg-primary-50/40 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-primary-600 shadow-sm">
                <FiFileText size={18} />
              </span>
              <div className="min-w-0">
                <p className="font-semibold text-slate-900">{emailTemplate.name || 'Introduction Outreach'}</p>
                <p className="mt-0.5 truncate text-sm text-slate-600">{emailTemplate.subject}</p>
                {emailTemplate.source_filename ? (
                  <p className="mt-1 text-xs text-slate-400">{emailTemplate.source_filename}</p>
                ) : null}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                disabled={uploading}
                onClick={() => inputRef.current?.click()}
                className="rounded-lg px-3 py-1.5 text-xs font-medium text-primary-700 hover:bg-white"
              >
                Replace
              </button>
              <button
                type="button"
                onClick={() => onChange(null)}
                className="rounded-lg p-2 text-slate-400 hover:bg-white hover:text-red-600"
                title="Remove template"
              >
                <FiTrash2 size={16} />
              </button>
            </div>
          </div>
          <p className="mt-3 line-clamp-3 whitespace-pre-wrap text-xs text-slate-500">{emailTemplate.body}</p>
        </div>
      )}
    </section>
  );
}
