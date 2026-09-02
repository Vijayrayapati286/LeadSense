import { FiFileText } from 'react-icons/fi';
import { offeringEmailTemplateName } from './offeringFormUtils';
import { renderMarkdownLite, renderTemplate } from '../../utils/helpers';
import { buildSamplePreviewContext } from '../../utils/mergeFields';

function sourceLabel(source) {
  if (source === 'upload') return 'Uploaded';
  if (source === 'ai_generated') return 'AI generated';
  return null;
}

/** Read-only outreach email block for offering overview / detail pages. */
export default function OfferingEmailSummary({ offering, showPreview = true }) {
  const template = offering?.email_template;
  if (!template?.subject || !template?.body) {
    return (
      <section className="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 px-4 py-5">
        <div className="flex items-center gap-2 text-slate-500">
          <FiFileText size={16} />
          <p className="text-sm">No outreach email saved yet.</p>
        </div>
        <p className="mt-1 text-xs text-slate-400">
          Add one in the offering wizard (Email step) or edit this offering.
        </p>
      </section>
    );
  }

  const badge = sourceLabel(template.source);
  const previewContext = buildSamplePreviewContext();

  return (
    <section className="rounded-xl border border-primary-200 bg-primary-50/30 p-5 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-primary-700">Outreach email</p>
          <p className="text-sm font-semibold text-slate-900 mt-0.5">
            {offeringEmailTemplateName(offering.name, template.name)}
          </p>
        </div>
        {badge ? (
          <span className="inline-flex rounded-full bg-white px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary-700 border border-primary-200">
            {badge}
          </span>
        ) : null}
      </div>

      <div>
        <p className="text-xs font-medium text-slate-500 mb-1">Subject</p>
        <p className="text-sm text-slate-800 font-medium">{template.subject}</p>
      </div>

      <div>
        <p className="text-xs font-medium text-slate-500 mb-1">Body</p>
        <pre className="text-sm text-slate-700 whitespace-pre-wrap font-sans leading-relaxed max-h-64 overflow-y-auto rounded-lg border border-primary-100 bg-white/80 p-3">
          {template.body}
        </pre>
      </div>

      {showPreview ? (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Sample preview</p>
          <p className="text-sm font-semibold text-slate-900">
            {renderTemplate(template.subject, previewContext)}
          </p>
          <div
            className="mt-2 text-sm text-slate-600 prose-sm"
            dangerouslySetInnerHTML={{
              __html: renderMarkdownLite(renderTemplate(template.body, previewContext)),
            }}
          />
        </div>
      ) : null}
    </section>
  );
}
