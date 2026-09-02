import { useEffect, useRef, useState } from 'react';
import { FiCheck, FiFileText, FiUpload, FiZap } from 'react-icons/fi';
import { offeringsService } from '../../services/services';
import { useToast } from '../../hooks/useToast';
import { formToEmailContext, offeringEmailTemplateName } from './offeringFormUtils';
import { renderMarkdownLite, renderTemplate } from '../../utils/helpers';
import { buildSamplePreviewContext } from '../../utils/mergeFields';
import LoadingSpinner from '../ui/LoadingSpinner';

const ACCEPT = '.html,.htm,.txt,.docx';

const ANGLE_LABELS = {
  pain_led: 'Pain-led',
  benefit_led: 'Benefit-led',
  direct: 'Direct',
};

function ContextSummary({ form }) {
  const chips = [
    { label: 'Industries', items: form.target_industries },
    { label: 'Buyers', items: form.target_job_titles },
    { label: 'Pain points', items: form.pain_points },
    { label: 'Benefits', items: form.benefits },
  ];

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 space-y-3">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Offering context</p>
        <p className="mt-1 text-sm font-semibold text-slate-900">{form.name || 'Untitled offering'}</p>
        <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">
          {form.short_description || form.description || 'No description yet'}
        </p>
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        {chips.map(({ label, items }) => (
          <div key={label}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1">{label}</p>
            <div className="flex flex-wrap gap-1">
              {(Array.isArray(items) ? items : []).slice(0, 4).map((item) => (
                <span
                  key={item}
                  className="inline-flex rounded-full bg-white px-2 py-0.5 text-[10px] font-medium text-slate-600 border border-slate-200"
                >
                  {item}
                </span>
              ))}
              {!items?.length ? <span className="text-xs text-slate-400">—</span> : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function VersionCard({ version, selected, onSelect }) {
  const previewContext = buildSamplePreviewContext();
  const angleLabel = ANGLE_LABELS[version.angle] || version.angle;

  return (
    <button
      type="button"
      onClick={() => onSelect(version)}
      className={`w-full rounded-xl border p-4 text-left transition ${
        selected
          ? 'border-primary-500 bg-primary-50 ring-2 ring-primary-200'
          : 'border-slate-200 bg-white hover:border-primary-300'
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-primary-700">{angleLabel}</span>
        {selected ? (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-primary-700">
            <FiCheck size={12} /> Selected
          </span>
        ) : null}
      </div>
      <p className="text-sm font-semibold text-slate-900 line-clamp-1">
        {renderTemplate(version.subject, previewContext)}
      </p>
      <p className="mt-2 text-xs text-slate-500 line-clamp-4 whitespace-pre-wrap">
        {renderTemplate(version.body, previewContext)}
      </p>
    </button>
  );
}

export default function OfferingEmailWizardStep({ form, emailTemplate, onChange }) {
  const toast = useToast();
  const inputRef = useRef(null);
  const [generating, setGenerating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [versions, setVersions] = useState([]);
  const [selectedAngle, setSelectedAngle] = useState(null);
  const [subject, setSubject] = useState(emailTemplate?.subject || '');
  const [body, setBody] = useState(emailTemplate?.body || '');
  const [additionalContext, setAdditionalContext] = useState('');

  const previewContext = buildSamplePreviewContext();
  const hasDraft = Boolean(subject.trim() && body.trim());

  useEffect(() => {
    if (emailTemplate?.subject && emailTemplate?.body) {
      setSubject(emailTemplate.subject);
      setBody(emailTemplate.body);
    }
  }, [emailTemplate?.subject, emailTemplate?.body]);

  function defaultTemplateName() {
    return offeringEmailTemplateName(form.name, emailTemplate?.name);
  }

  function syncTemplate(nextSubject, nextBody, meta = {}) {
    setSubject(nextSubject);
    setBody(nextBody);
    if (nextSubject.trim() && nextBody.trim()) {
      onChange({
        name: meta.name || defaultTemplateName(),
        subject: nextSubject.trim(),
        body: nextBody.trim(),
        source_filename: meta.source_filename || null,
        uploaded_at: new Date().toISOString(),
        source: meta.source || 'ai_generated',
      });
    }
  }

  function selectVersion(version) {
    setSelectedAngle(version.angle);
    syncTemplate(version.subject, version.body, { source: 'ai_generated', name: defaultTemplateName() });
  }

  async function handleGenerate() {
    if (!form.name?.trim()) {
      toast.error('Add an offering name before generating emails');
      return;
    }
    setGenerating(true);
    try {
      const payload = {
        ...formToEmailContext(form),
        additional_context: additionalContext.trim() || null,
      };
      const result = await offeringsService.generateEmailTemplates(payload);
      const nextVersions = result.versions || [];
      setVersions(nextVersions);
      if (nextVersions.length > 0) {
        selectVersion(nextVersions[0]);
      }
      if (result.is_mock) {
        toast.info('Using mock email drafts (AI not configured)');
      } else {
        toast.success(`Generated ${nextVersions.length} email version(s)`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to generate emails');
    } finally {
      setGenerating(false);
    }
  }

  async function uploadFile(file) {
    if (!file) return;
    setUploading(true);
    try {
      const parsed = await offeringsService.parseEmailTemplate(file);
      setVersions([]);
      setSelectedAngle(null);
      syncTemplate(parsed.subject, parsed.body, {
        name: offeringEmailTemplateName(form.name, parsed.name),
        source_filename: parsed.source_filename,
        source: 'upload',
      });
      toast.success('Email template uploaded');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to parse email template');
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  function handleSubjectChange(value) {
    setSubject(value);
    if (value.trim() && body.trim()) {
      onChange({
        ...(emailTemplate || { name: defaultTemplateName() }),
        subject: value.trim(),
        body: body.trim(),
        uploaded_at: new Date().toISOString(),
      });
    }
  }

  function handleBodyChange(value) {
    setBody(value);
    if (subject.trim() && value.trim()) {
      onChange({
        ...(emailTemplate || { name: defaultTemplateName() }),
        subject: subject.trim(),
        body: value.trim(),
        uploaded_at: new Date().toISOString(),
      });
    }
  }

  function handleClear() {
    setVersions([]);
    setSelectedAngle(null);
    setSubject('');
    setBody('');
    onChange(null);
  }

  return (
    <div className="space-y-5 animate-rise-in">
      <section className="surface-card space-y-5 p-5 sm:p-6">
        <div>
          <p className="workspace-eyebrow">Step 4</p>
          <h2 className="text-xl font-semibold text-slate-900">Generate outreach email</h2>
          <p className="mt-1 text-sm text-slate-500">
            AI uses your offering and buyer context to draft 2–3 versions. Pick one, edit, and save as your
            offering template — it loads automatically when you create campaigns.
          </p>
        </div>

        <ContextSummary form={form} />

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Additional context <span className="text-slate-400 font-normal">(optional)</span>
          </label>
          <textarea
            rows={2}
            className="control resize-y"
            placeholder="Any specific angle, proof point, or CTA to include…"
            value={additionalContext}
            onChange={(e) => setAdditionalContext(e.target.value)}
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={generating}
            onClick={handleGenerate}
            className="btn-primary inline-flex items-center gap-2"
          >
            {generating ? <LoadingSpinner size="sm" /> : <FiZap size={16} />}
            {generating ? 'Generating…' : versions.length ? 'Regenerate versions' : 'Generate 3 versions'}
          </button>
          <button
            type="button"
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
            className="btn-secondary inline-flex items-center gap-2"
          >
            <FiUpload size={16} />
            {uploading ? 'Uploading…' : 'Upload instead'}
          </button>
          {hasDraft ? (
            <button type="button" onClick={handleClear} className="btn-secondary text-red-600">
              Clear template
            </button>
          ) : null}
        </div>

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => uploadFile(e.target.files?.[0])}
        />
      </section>

      {versions.length > 0 ? (
        <section className="surface-card space-y-4 p-5 sm:p-6">
          <h3 className="text-sm font-semibold text-slate-900">Compare versions</h3>
          <div className="grid gap-3 md:grid-cols-3">
            {versions.map((version) => (
              <VersionCard
                key={version.angle}
                version={version}
                selected={selectedAngle === version.angle}
                onSelect={selectVersion}
              />
            ))}
          </div>
        </section>
      ) : null}

      {hasDraft ? (
        <section className="surface-card space-y-4 p-5 sm:p-6">
          <div className="flex items-center gap-2">
            <FiFileText className="text-primary-600" size={18} />
            <h3 className="text-sm font-semibold text-slate-900">Edit selected template</h3>
          </div>
          <div>
            <label className="field-label">Subject</label>
            <input
              className="control mt-1"
              value={subject}
              onChange={(e) => handleSubjectChange(e.target.value)}
              placeholder="Email subject with {{Company}} placeholders"
            />
          </div>
          <div>
            <label className="field-label">Body</label>
            <textarea
              rows={10}
              className="control mt-1 font-mono text-sm resize-y"
              value={body}
              onChange={(e) => handleBodyChange(e.target.value)}
              placeholder="Hi {{Name}}, ..."
            />
            <p className="mt-1.5 text-xs text-slate-400">
              Use {'{{Name}}'}, {'{{Company}}'}, {'{{Designation}}'}, {'{{Industry}}'} for personalization.
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Preview</p>
            <p className="text-sm font-semibold text-slate-900">
              {renderTemplate(subject, previewContext)}
            </p>
            <div
              className="mt-2 text-sm text-slate-600 prose-sm"
              dangerouslySetInnerHTML={{
                __html: renderMarkdownLite(renderTemplate(body, previewContext)),
              }}
            />
          </div>
        </section>
      ) : (
        <section className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-5 py-8 text-center">
          <p className="text-sm text-slate-500">
            Generate AI versions or upload a template. You can skip this step and add an email later.
          </p>
        </section>
      )}
    </div>
  );
}
