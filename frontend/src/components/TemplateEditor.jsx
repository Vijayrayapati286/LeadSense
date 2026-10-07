import { useEffect } from 'react';
import { FiZap, FiEdit3, FiFileText } from 'react-icons/fi';
import LoadingSpinner from './ui/LoadingSpinner';
import RichTextEditor from './RichTextEditor';
import { renderTemplate, renderMarkdownLite, isTemplateBodyEmpty } from '../utils/helpers';
import { OFFERING_EMAIL_MERGE_FIELDS } from '../utils/mergeFields';
import { buildDefaultSignature } from '../utils/emailSignature';

/** Compact merge-tag chips for offering / manual compose. */
function MergeFieldHints({ fields = OFFERING_EMAIL_MERGE_FIELDS }) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {fields.map(({ key, label }) => (
        <span
          key={key}
          title={label}
          className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600"
        >
          {`{{${key}}}`}
        </span>
      ))}
    </div>
  );
}

export const TEMPLATE_TYPES = [
  { id: 'manual', label: 'Manual', icon: FiEdit3, desc: 'Write your own email' },
  { id: 'placeholder', label: 'Offering Email', icon: FiFileText, desc: 'Personalized from offering content' },
  { id: 'ai', label: 'AI Generated', icon: FiZap, desc: 'Draft with AI' },
];

function templateSourceBadge(t) {
  if (t.source !== 'offering') return null;
  if (t.template_source === 'upload') return 'Uploaded';
  if (t.template_source === 'ai_generated' || t.template_source === 'offering_ai') return 'From offering';
  return 'From offering';
}

/** The manual/placeholder/AI template-type selector + editing forms, shared
 * between the campaign creation Template tab and the Mailers library so
 * both stay in sync instead of drifting as two copies. */
export default function TemplateEditor({
  templateType,
  onTemplateTypeChange,
  emailContent,
  onEmailContentChange,
  placeholderTemplates = [],
  selectedTemplate,
  onSelectPlaceholderTemplate,
  placeholderValues = {},
  onPlaceholderValueChange,
  aiPrompt = { additional_context: '' },
  onAiPromptChange,
  onGenerateAI,
  aiLoading = false,
  previewContext,
  senderName = '',
}) {
  const updateContent = (field, value) => onEmailContentChange((p) => ({ ...p, [field]: value }));

  useEffect(() => {
    if (templateType === 'manual' && isTemplateBodyEmpty(emailContent.body, 'manual')) {
      onEmailContentChange((p) => ({ ...p, body: buildDefaultSignature() }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateType]);

  // Keep FromName in sync with the logged-in sender when empty
  useEffect(() => {
    if (!senderName) return;
    if (!placeholderValues.FromName) {
      onPlaceholderValueChange?.('FromName', senderName);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [senderName, templateType]);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {TEMPLATE_TYPES.map(({ id: typeId, label, icon: Icon, desc }) => (
          <button
            key={typeId}
            type="button"
            onClick={() => onTemplateTypeChange(typeId)}
            className={`rounded-xl border-2 p-4 text-left transition-all ${
              templateType === typeId ? 'border-primary-500 bg-primary-50' : 'border-gray-200 hover:border-gray-300'
            }`}
          >
            <Icon size={22} className={templateType === typeId ? 'text-primary-600' : 'text-gray-400'} />
            <p className="mt-2 font-medium text-slate-900">{label}</p>
            <p className="mt-1 text-xs text-slate-500">{desc}</p>
          </button>
        ))}
      </div>

      {templateType === 'manual' && (
        <div className="space-y-4">
          <div>
            <label className="label">Subject</label>
            <input className="input-field" value={emailContent.subject} onChange={(e) => updateContent('subject', e.target.value)} />
          </div>
          <div>
            <label className="label">Email body</label>
            <RichTextEditor
              value={emailContent.body}
              onChange={(html) => updateContent('body', html)}
              placeholder="Write your email. Use {{Name}}, {{Company}}, {{FromName}} for personalization."
            />
            <p className="mt-2 text-xs text-slate-500">Personalization</p>
            <MergeFieldHints />
          </div>
        </div>
      )}

      {templateType === 'placeholder' && (
        <div className="space-y-4">
          {placeholderTemplates.length === 0 ? (
            <p className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-4 py-6 text-center text-sm text-gray-500">
              No offering templates yet. Select an offering on the campaign step, then return here.
            </p>
          ) : null}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {placeholderTemplates.map((t) => {
              const badge = templateSourceBadge(t);
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => onSelectPlaceholderTemplate(t)}
                  className={`rounded-lg border p-3 text-left text-sm transition-all ${
                    selectedTemplate?.id === t.id
                      ? 'border-primary-500 bg-primary-50 ring-2 ring-primary-200'
                      : 'border-gray-200 hover:border-slate-300'
                  }`}
                >
                  <p className="font-medium text-slate-900">{t.name}</p>
                  {badge ? (
                    <p className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-primary-600">{badge}</p>
                  ) : null}
                  <p className="mt-1 truncate text-xs text-slate-500">{t.subject}</p>
                </button>
              );
            })}
          </div>

          {selectedTemplate && (
            <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Selected template</p>
                <p className="mt-0.5 text-sm font-semibold text-slate-900">{selectedTemplate.name}</p>
              </div>

              <div>
                <label className="label">Subject</label>
                <input
                  className="input-field"
                  value={emailContent.subject}
                  onChange={(e) => updateContent('subject', e.target.value)}
                />
              </div>

              <div>
                <label className="label">From name (sender)</label>
                <input
                  className="input-field"
                  value={placeholderValues.FromName || ''}
                  onChange={(e) => onPlaceholderValueChange?.('FromName', e.target.value)}
                  placeholder="Your name appears after Regards"
                />
                <p className="mt-1 text-xs text-slate-500">
                  Appears after Regards (and before Lead Generation) in the sign-off.
                </p>
              </div>

              <div>
                <label className="label">Body</label>
                <textarea
                  className="input-field resize-y text-sm leading-relaxed font-sans"
                  rows={12}
                  value={emailContent.body}
                  onChange={(e) => updateContent('body', e.target.value)}
                  placeholder={'Hi {{Name}},\n\n...\n\nRegards,\n{{FromName}}\nLead Generation'}
                />
                <p className="mt-2 text-xs text-slate-500">
                  Personalization tags
                </p>
                <MergeFieldHints />
              </div>

              {previewContext && (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Preview</p>
                  <p className="text-sm font-semibold text-slate-900">
                    {renderTemplate(emailContent.subject, previewContext)}
                  </p>
                  <div
                    className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-700"
                    dangerouslySetInnerHTML={{
                      __html: renderMarkdownLite(renderTemplate(emailContent.body, previewContext)),
                    }}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {templateType === 'ai' && (
        <div className="space-y-4">
          <div>
            <label className="label">Additional context (optional)</label>
            <textarea
              className="input-field"
              rows={3}
              value={aiPrompt.additional_context}
              onChange={(e) => onAiPromptChange({ additional_context: e.target.value })}
              placeholder="Any specific details for the AI to include..."
            />
          </div>
          <button type="button" onClick={onGenerateAI} disabled={aiLoading} className="btn-primary flex items-center gap-2">
            {aiLoading ? <LoadingSpinner size="sm" /> : <FiZap size={18} />}
            Generate with AI
          </button>
          {(emailContent.subject || emailContent.body) && (
            <div className="space-y-3">
              <div>
                <label className="label">Subject</label>
                <input className="input-field" value={emailContent.subject} onChange={(e) => updateContent('subject', e.target.value)} />
              </div>
              <div>
                <label className="label">Body</label>
                <textarea className="input-field" rows={8} value={emailContent.body} onChange={(e) => updateContent('body', e.target.value)} />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
