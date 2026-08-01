import { useEffect } from 'react';
import { FiZap, FiEdit3, FiFileText } from 'react-icons/fi';
import LoadingSpinner from './ui/LoadingSpinner';
import RichTextEditor from './RichTextEditor';
import { renderTemplate, renderMarkdownLite, isTemplateBodyEmpty } from '../utils/helpers';
import { KNOWN_MERGE_FIELDS } from '../utils/mergeFields';
import { buildDefaultSignature } from '../utils/emailSignature';

/** Compact reference list of every supported {{Field}} merge tag, so users
 * don't have to guess which prospect fields a template can pull in. */
function MergeFieldHints() {
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {KNOWN_MERGE_FIELDS.map(({ key, label }) => (
        <span
          key={key}
          title={label}
          className="text-xs font-mono px-1.5 py-0.5 rounded bg-gray-100 text-gray-600"
        >
          {`{{${key}}}`}
        </span>
      ))}
    </div>
  );
}

export const TEMPLATE_TYPES = [
  { id: 'manual', label: 'Manual', icon: FiEdit3, desc: 'Write your own email with rich text' },
  { id: 'placeholder', label: 'Placeholder', icon: FiFileText, desc: 'Use templates with dynamic placeholders' },
  { id: 'ai', label: 'AI Generated', icon: FiZap, desc: 'Let AI craft your email content' },
];

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
}) {
  const updateContent = (field, value) => onEmailContentChange((p) => ({ ...p, [field]: value }));

  // The Feuji footer is mandatory on every Manual Compose email — pre-fill
  // it the moment Manual is opened with an empty body (fresh compose),
  // rather than requiring it to be pasted in by hand each time. Only fires
  // when the body is actually empty, so it never clobbers an existing
  // draft/saved template, and only re-fires on a type switch (not on every
  // keystroke) so deliberately clearing it doesn't cause it to reappear.
  useEffect(() => {
    if (templateType === 'manual' && isTemplateBodyEmpty(emailContent.body, 'manual')) {
      onEmailContentChange((p) => ({ ...p, body: buildDefaultSignature() }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateType]);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {TEMPLATE_TYPES.map(({ id: typeId, label, icon: Icon, desc }) => (
          <button
            key={typeId}
            onClick={() => onTemplateTypeChange(typeId)}
            className={`p-4 rounded-xl border-2 text-left transition-all ${
              templateType === typeId ? 'border-primary-500 bg-primary-50' : 'border-gray-200 hover:border-gray-300'
            }`}
          >
            <Icon size={24} className={templateType === typeId ? 'text-primary-600' : 'text-gray-400'} />
            <p className="font-medium mt-2">{label}</p>
            <p className="text-xs text-gray-500 mt-1">{desc}</p>
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
            <label className="label">Email Body</label>
            <RichTextEditor
              value={emailContent.body}
              onChange={(html) => updateContent('body', html)}
              placeholder="Write your email content here. Use {{Name}}, {{Company}} for personalization."
            />
            <p className="text-xs text-gray-400 mt-2">Available fields:</p>
            <MergeFieldHints />
          </div>
        </div>
      )}

      {templateType === 'placeholder' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {placeholderTemplates.map((t) => (
              <button
                key={t.id}
                onClick={() => onSelectPlaceholderTemplate(t)}
                className={`p-3 rounded-lg border text-left text-sm ${
                  selectedTemplate?.id === t.id ? 'border-primary-500 bg-primary-50' : 'border-gray-200'
                }`}
              >
                <p className="font-medium">{t.name}</p>
                <p className="text-xs text-gray-500 mt-1 truncate">{t.subject}</p>
              </button>
            ))}
          </div>
          {selectedTemplate && (
            <>
              <div className="grid grid-cols-2 gap-3">
                {Object.keys(placeholderValues).map((key) => (
                  <div key={key}>
                    <label className="label">{key}</label>
                    <input
                      className="input-field"
                      value={placeholderValues[key]}
                      onChange={(e) => onPlaceholderValueChange(key, e.target.value)}
                      placeholder={`Sample ${key}`}
                    />
                  </div>
                ))}
              </div>
              {previewContext && (
                <div className="p-4 bg-gray-50 rounded-lg">
                  <p className="text-xs text-gray-500 mb-2">Live Preview</p>
                  <p className="font-medium text-sm">{renderTemplate(emailContent.subject, previewContext)}</p>
                  <div
                    className="text-sm text-gray-600 mt-2"
                    dangerouslySetInnerHTML={{
                      __html: renderMarkdownLite(renderTemplate(emailContent.body, previewContext)),
                    }}
                  />
                </div>
              )}
            </>
          )}
        </div>
      )}

      {templateType === 'ai' && (
        <div className="space-y-4">
          <div>
            <label className="label">Additional Context (optional)</label>
            <textarea className="input-field" rows={3} value={aiPrompt.additional_context} onChange={(e) => onAiPromptChange({ additional_context: e.target.value })} placeholder="Any specific details for the AI to include..." />
          </div>
          <button onClick={onGenerateAI} disabled={aiLoading} className="btn-primary flex items-center gap-2">
            {aiLoading ? <LoadingSpinner size="sm" /> : <FiZap size={18} />}
            Generate with AI
          </button>
          {(emailContent.subject || emailContent.body) && (
            <div className="space-y-3">
              <div>
                <label className="label">Subject (editable)</label>
                <input className="input-field" value={emailContent.subject} onChange={(e) => updateContent('subject', e.target.value)} />
              </div>
              <div>
                <label className="label">Body (editable)</label>
                <textarea className="input-field" rows={8} value={emailContent.body} onChange={(e) => updateContent('body', e.target.value)} />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
