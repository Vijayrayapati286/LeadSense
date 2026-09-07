import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  FiArrowLeft,
  FiArrowRight,
  FiCheck,
  FiMail,
  FiTarget,
  FiUsers,
  FiZap,
} from 'react-icons/fi';
import {
  AreaField,
  EMPTY_OFFERING,
  formToPayload,
  ListField,
  offeringEmailTemplateName,
  TextField,
} from '../components/offerings/offeringFormUtils';
import {
  acceptAiSuggestion,
  AI_EDITABLE_FIELDS,
  applyAllAiSuggestions,
  keepCurrentSuggestion,
  reconcileAiDraft,
  validateOffering,
} from '../components/offerings/offeringDraftUtils';
import OfferingVouchersSection from '../components/offerings/OfferingVouchersSection';
import OfferingEmailWizardStep from '../components/offerings/OfferingEmailWizardStep';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { useToast } from '../hooks/useToast';
import { offeringsService } from '../services/services';
import { WorkspaceHeader } from '../components/ui/GrowthWorkspace';

const STEPS = [
  { label: 'Offering', hint: 'AI draft & basics', icon: FiZap },
  { label: 'Target customer', hint: 'Companies & buyers', icon: FiTarget },
  { label: 'Value', hint: 'Problems & outcomes', icon: FiUsers },
  { label: 'Email', hint: 'Outreach template', icon: FiMail },
  { label: 'Review', hint: 'Preview & save', icon: FiCheck },
];

const PREVIEW_GROUPS = [
  ['Offering basics', ['product_type', 'short_description', 'detailed_description', 'website_url', 'pricing_range']],
  ['Target customer', ['target_customer', 'target_industries', 'target_company_size', 'target_job_titles']],
  ['Customer problems', ['pain_points', 'current_challenges']],
  ['Use cases', ['use_cases']],
  ['Benefits and selling points', ['benefits', 'selling_points']],
];

const LABELS = {
  name: 'Offering name',
  product_type: 'Product / service type',
  short_description: 'Short description',
  detailed_description: 'Detailed description',
  website_url: 'Website URL',
  pricing_range: 'Pricing range',
  target_customer: 'Target customer',
  target_industries: 'Target industries',
  target_company_size: 'Target company size',
  target_job_titles: 'Target job titles',
  pain_points: 'Pain points',
  current_challenges: 'Challenges this offering solves',
  use_cases: 'Use cases',
  benefits: 'Benefits',
  selling_points: 'Selling points',
};

function displayValue(value) {
  if (Array.isArray(value)) return value.join(', ') || 'Not provided';
  return value || 'Not provided';
}

function SuggestionReview({ field, item, onKeep, onAccept }) {
  if (!item) return null;
  return (
    <div className="mt-2 rounded-xl border border-violet-200 bg-violet-50/60 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Current</p>
          <p className="mt-1 text-sm text-slate-700">{displayValue(item.current)}</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wide text-violet-600">AI suggestion</p>
          <p className="mt-1 text-sm font-medium text-slate-900">{displayValue(item.suggested)}</p>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <button type="button" onClick={() => onKeep(field)} className="btn-secondary px-3 py-1.5 text-xs">
          Keep current
        </button>
        <button type="button" onClick={() => onAccept(field)} className="btn-primary px-3 py-1.5 text-xs">
          Use AI suggestion
        </button>
      </div>
    </div>
  );
}

function PreviewValue({ value }) {
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-slate-400">Not provided</span>;
    return (
      <div className="flex flex-wrap gap-1.5">
        {value.map((item) => (
          <span key={item.toLocaleLowerCase()} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">
            {item}
          </span>
        ))}
      </div>
    );
  }
  return <p className="whitespace-pre-wrap text-sm text-slate-700">{value || 'Not provided'}</p>;
}

export default function OfferingCreatePage() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const toast = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState({ ...EMPTY_OFFERING, status: 'active' });
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [regeneratingField, setRegeneratingField] = useState('');
  const [generationState, setGenerationState] = useState('idle');
  const [suggestions, setSuggestions] = useState({});
  const [provenance, setProvenance] = useState({});
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(isEdit);
  const [runMatch, setRunMatch] = useState(true);
  const [previewConfirmed, setPreviewConfirmed] = useState(false);
  const [step, setStep] = useState(0);
  const voucherBatchId = useRef(
    id ? `offering-voucher-${id}` : `offering-voucher-${crypto.randomUUID()}`,
  );
  const pendingSuggestionCount = Object.keys(suggestions).length;

  const fieldProps = (field) => ({
    generated: Boolean(provenance[field]),
    regenerating: regeneratingField === field,
    onRegenerate: AI_EDITABLE_FIELDS.includes(field) ? () => handleGenerate([field]) : undefined,
    error: errors[field],
  });

  function setField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setPreviewConfirmed(false);
    setErrors((prev) => ({ ...prev, [key]: undefined }));
    if (provenance[key]) {
      setProvenance((prev) => ({ ...prev, [key]: 'ai_edited' }));
    }
  }

  useEffect(() => {
    if (!isEdit) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await offeringsService.get(id);
        if (!cancelled) {
          setForm({
            ...EMPTY_OFFERING,
            ...data,
            detailed_description: data.detailed_description || data.description || '',
            target_company_size:
              data.target_company_size ||
              (data.company_size_label ? [data.company_size_label] : []),
            company_size_min: data.company_size_min ?? '',
            company_size_max: data.company_size_max ?? '',
            status: data.status || 'active',
            vouchers: Array.isArray(data.vouchers) ? data.vouchers : [],
            email_template: data.email_template || null,
          });
          setAiPrompt(data.detailed_description || data.description || data.short_description || '');
        }
      } catch (err) {
        toast.error(err?.response?.data?.detail || 'Failed to load offering');
        navigate('/offerings');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isEdit]);

  async function handleGenerate(requestedFields = null) {
    if (!aiPrompt.trim() || aiPrompt.trim().length < 10) {
      toast.error('Describe what you sell, the problem it solves, and your best customers.');
      return;
    }
    if (requestedFields?.length) setRegeneratingField(requestedFields[0]);
    else setAiLoading(true);
    setGenerationState('loading');
    try {
      const result = await offeringsService.generateIcp({
        description: aiPrompt.trim(),
        requested_fields: requestedFields || [],
        current_values: formToPayload(form),
      });
      const reconciled = reconcileAiDraft(form, result, requestedFields);
      setForm(reconciled.form);
      setSuggestions((prev) => {
        if (!requestedFields?.length) return reconciled.suggestions;
        const next = { ...prev };
        requestedFields.forEach((field) => delete next[field]);
        return { ...next, ...reconciled.suggestions };
      });
      setProvenance((prev) => ({ ...prev, ...reconciled.provenance }));
      setGenerationState('success');
      setPreviewConfirmed(false);
      toast.success(
        pendingSuggestionCount || Object.keys(reconciled.suggestions).length
          ? 'AI draft ready — review the suggestions before applying them'
          : 'AI draft added — every generated field remains editable',
      );
    } catch (err) {
      setGenerationState('error');
      toast.error(err?.response?.data?.detail || 'AI generation failed. Your current data was not changed.');
    } finally {
      setAiLoading(false);
      setRegeneratingField('');
    }
  }

  function acceptSuggestion(field) {
    const result = acceptAiSuggestion(form, suggestions, field);
    setForm(result.form);
    setSuggestions(result.suggestions);
    setProvenance((prev) => ({ ...prev, [field]: 'ai_accepted' }));
    setPreviewConfirmed(false);
  }

  function keepSuggestion(field) {
    setSuggestions((prev) => keepCurrentSuggestion(prev, field));
  }

  function applyAllSuggestions() {
    const fields = Object.keys(suggestions);
    const result = applyAllAiSuggestions(form, suggestions);
    setForm(result.form);
    setSuggestions(result.suggestions);
    setProvenance((prev) => ({
      ...prev,
      ...Object.fromEntries(fields.map((field) => [field, 'ai_accepted'])),
    }));
    setPreviewConfirmed(false);
    toast.success('All AI suggestions applied');
  }

  function nextStep() {
    if (step === 0) {
      const nextErrors = validateOffering(form);
      setErrors(nextErrors);
      if (nextErrors.name || nextErrors.product_type) {
        toast.error('Complete the required offering basics before continuing');
        return;
      }
    }
    setStep((current) => Math.min(STEPS.length - 1, current + 1));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function handleSave() {
    const nextErrors = validateOffering(form);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) {
      setStep(0);
      toast.error('Fix the highlighted fields before saving');
      return;
    }
    if (pendingSuggestionCount) {
      toast.error('Apply or keep each pending AI suggestion before saving');
      return;
    }
    if (!previewConfirmed) {
      toast.error('Confirm the final preview before saving');
      return;
    }
    setSaving(true);
    try {
      const payload = formToPayload(form);
      let offeringId = id;
      if (isEdit) {
        await offeringsService.update(id, payload);
        toast.success('Offering updated');
      } else {
        const created = await offeringsService.create(payload);
        offeringId = created.id;
        toast.success('Offering created');
      }
      if (runMatch && offeringId) {
        try {
          await offeringsService.startMatch(offeringId, true, false);
          toast.success('Matching ICP contacts…');
        } catch {
          toast.error('Offering saved, but candidate matching could not be started');
        }
      }
      navigate(`/offerings/${offeringId}?tab=matching`);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const message = Array.isArray(detail)
        ? detail.map((item) => item.msg || JSON.stringify(item)).join('; ')
        : detail || err?.message || 'Failed to save offering';
      toast.error(message);
    } finally {
      setSaving(false);
    }
  }

  const previewName = useMemo(() => form.name?.trim() || 'Untitled offering', [form.name]);

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <LoadingSpinner />
      </div>
    );
  }

  const suggestionFor = (field) => (
    <SuggestionReview
      field={field}
      item={suggestions[field]}
      onKeep={keepSuggestion}
      onAccept={acceptSuggestion}
    />
  );

  return (
    <div className="workspace-shell max-w-6xl">
      <WorkspaceHeader
        eyebrow="Offering studio"
        title={isEdit ? 'Refine your offering' : 'Create offering'}
        description="Build a precise offering profile for stronger candidate recommendations. AI suggests; you decide."
        actions={
          <Link to={isEdit ? `/offerings/${id}` : '/offerings'} className="btn-secondary inline-flex items-center gap-2">
            <FiArrowLeft size={16} /> Exit
          </Link>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="surface-card h-fit p-3 lg:sticky lg:top-6">
          <ol className="space-y-1">
            {STEPS.map(({ label, hint, icon: Icon }, index) => (
              <li key={label}>
                <button
                  type="button"
                  onClick={() => setStep(index)}
                  className={`flex w-full items-center gap-3 rounded-xl p-3 text-left transition ${
                    step === index ? 'bg-primary-50 text-primary-800' : 'text-slate-500 hover:bg-slate-50'
                  }`}
                  aria-current={step === index ? 'step' : undefined}
                >
                  <span className={`flex h-9 w-9 items-center justify-center rounded-xl ${step === index ? 'bg-primary-600 text-white' : 'bg-slate-100'}`}>
                    <Icon size={17} />
                  </span>
                  <span>
                    <span className="block text-sm font-semibold">{label}</span>
                    <span className="block text-xs opacity-70">{hint}</span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </aside>

        <main className="min-w-0 space-y-5">
          {step === 0 ? (
            <div className="space-y-5 animate-rise-in">
              <section className="overflow-hidden rounded-2xl border border-violet-200 bg-gradient-to-br from-violet-50 via-white to-primary-50 p-5 sm:p-6">
                <div className="flex items-start gap-3">
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-violet-600 text-white shadow-lg shadow-violet-200">
                    <FiZap size={19} />
                  </span>
                  <div>
                    <h2 className="font-semibold text-slate-950">Generate offering draft with AI</h2>
                    <p className="mt-1 text-sm text-slate-600">Describe what you sell, the problem it solves, and your best customers.</p>
                  </div>
                </div>
                <textarea
                  rows={5}
                  className="control mt-4 resize-y border-violet-200 bg-white"
                  placeholder="A comprehensive commercial banking solution designed to help businesses access flexible financing…"
                  value={aiPrompt}
                  onChange={(event) => setAiPrompt(event.target.value)}
                />
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <button type="button" disabled={aiLoading} onClick={() => handleGenerate()} className="btn-primary inline-flex items-center gap-2">
                    <FiZap size={16} /> {aiLoading ? 'Generating draft…' : 'Generate draft'}
                  </button>
                  {generationState === 'success' ? <p className="text-xs font-medium text-emerald-700">Draft generated successfully</p> : null}
                  {generationState === 'error' ? <p className="text-xs font-medium text-red-600">Generation failed; your form is unchanged</p> : null}
                </div>
                {aiLoading ? (
                  <div className="mt-4 grid animate-pulse gap-2 sm:grid-cols-3">
                    {[1, 2, 3].map((item) => <div key={item} className="h-10 rounded-lg bg-violet-100/80" />)}
                  </div>
                ) : null}
              </section>

              {pendingSuggestionCount ? (
                <section className="flex flex-col gap-3 rounded-2xl border border-violet-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">{pendingSuggestionCount} AI suggestion{pendingSuggestionCount === 1 ? '' : 's'} ready for review</p>
                    <p className="text-xs text-slate-500">Nothing has replaced your existing information.</p>
                  </div>
                  <button type="button" onClick={applyAllSuggestions} className="btn-primary whitespace-nowrap">Apply all AI suggestions</button>
                </section>
              ) : null}

              <section className="surface-card space-y-5 p-5 sm:p-6">
                <div>
                  <h2 className="text-lg font-semibold text-slate-950">Offering basics</h2>
                  <p className="mt-1 text-sm text-slate-500">Clear, specific details prevent irrelevant recommendations.</p>
                </div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <div><TextField label="Offering name" required value={form.name} onChange={(value) => setField('name', value)} {...fieldProps('name')} />{suggestionFor('name')}</div>
                  <div><TextField label="Product or service type" required value={form.product_type} onChange={(value) => setField('product_type', value)} {...fieldProps('product_type')} />{suggestionFor('product_type')}</div>
                </div>
                <div><TextField label="Short description" value={form.short_description} onChange={(value) => setField('short_description', value)} {...fieldProps('short_description')} />{suggestionFor('short_description')}</div>
                <div><AreaField label="Detailed description" value={form.detailed_description} onChange={(value) => setField('detailed_description', value)} rows={5} {...fieldProps('detailed_description')} />{suggestionFor('detailed_description')}</div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <TextField label="Website URL" type="url" placeholder="https://example.com" value={form.website_url} onChange={(value) => setField('website_url', value)} {...fieldProps('website_url')} />
                  <TextField label="Pricing range" value={form.pricing_range} onChange={(value) => setField('pricing_range', value)} {...fieldProps('pricing_range')} />
                </div>
              </section>
              <OfferingVouchersSection vouchers={form.vouchers} batchId={voucherBatchId.current} onChange={(value) => setField('vouchers', value)} />
            </div>
          ) : null}

          {step === 1 ? (
            <div className="space-y-5 animate-rise-in">
              <section className="surface-card space-y-5 p-5 sm:p-6">
                <div><h2 className="text-lg font-semibold text-slate-950">Target customer</h2><p className="mt-1 text-sm text-slate-500">Define the companies and people most likely to benefit.</p></div>
                <div><AreaField label="Target customer description" rows={3} value={form.target_customer} onChange={(value) => setField('target_customer', value)} {...fieldProps('target_customer')} />{suggestionFor('target_customer')}</div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <div><ListField label="Target industries" value={form.target_industries} onChange={(value) => setField('target_industries', value)} {...fieldProps('target_industries')} />{suggestionFor('target_industries')}</div>
                  <div><ListField label="Target company size" hint="Examples: 50–200 employees, Enterprise" value={form.target_company_size} onChange={(value) => setField('target_company_size', value)} {...fieldProps('target_company_size')} />{suggestionFor('target_company_size')}</div>
                  <div className="sm:col-span-2"><ListField label="Target job titles" value={form.target_job_titles} onChange={(value) => setField('target_job_titles', value)} {...fieldProps('target_job_titles')} />{suggestionFor('target_job_titles')}</div>
                </div>
              </section>
              <details className="surface-card p-5">
                <summary className="cursor-pointer text-sm font-semibold text-slate-800">Advanced matching criteria</summary>
                <div className="mt-5 grid gap-5 sm:grid-cols-2">
                  <ListField label="Target seniority" value={form.target_seniority} onChange={(value) => setField('target_seniority', value)} />
                  <ListField label="Target departments" value={form.target_departments} onChange={(value) => setField('target_departments', value)} />
                  <ListField label="Geographies" value={form.target_geographies} onChange={(value) => setField('target_geographies', value)} />
                  <ListField label="Business models" value={form.business_models} onChange={(value) => setField('business_models', value)} />
                </div>
              </details>
            </div>
          ) : null}

          {step === 2 ? (
            <div className="space-y-5 animate-rise-in">
              <section className="surface-card space-y-5 p-5 sm:p-6">
                <div><h2 className="text-lg font-semibold text-slate-950">Customer problems</h2><p className="mt-1 text-sm text-slate-500">Describe the problems visible in a candidate’s role and responsibilities.</p></div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <div><ListField label="Pain points" value={form.pain_points} onChange={(value) => setField('pain_points', value)} {...fieldProps('pain_points')} />{suggestionFor('pain_points')}</div>
                  <div><ListField label="Challenges this offering solves" value={form.current_challenges} onChange={(value) => setField('current_challenges', value)} {...fieldProps('current_challenges')} />{suggestionFor('current_challenges')}</div>
                </div>
              </section>
              <section className="surface-card space-y-5 p-5 sm:p-6">
                <div><h2 className="text-lg font-semibold text-slate-950">Use cases</h2><p className="mt-1 text-sm text-slate-500">Add practical reasons customers choose this offering.</p></div>
                <div><ListField label="Use cases" value={form.use_cases} onChange={(value) => setField('use_cases', value)} {...fieldProps('use_cases')} />{suggestionFor('use_cases')}</div>
              </section>
              <section className="surface-card space-y-5 p-5 sm:p-6">
                <div><h2 className="text-lg font-semibold text-slate-950">Benefits and selling points</h2><p className="mt-1 text-sm text-slate-500">Separate customer outcomes from the reasons your offer wins.</p></div>
                <div className="grid gap-5 sm:grid-cols-2">
                  <div><ListField label="Benefits" value={form.benefits} onChange={(value) => setField('benefits', value)} {...fieldProps('benefits')} />{suggestionFor('benefits')}</div>
                  <div><ListField label="Selling points" value={form.selling_points} onChange={(value) => setField('selling_points', value)} {...fieldProps('selling_points')} />{suggestionFor('selling_points')}</div>
                </div>
              </section>
            </div>
          ) : null}

          {step === 3 ? (
            <OfferingEmailWizardStep form={form} emailTemplate={form.email_template} onChange={(value) => setField('email_template', value)} />
          ) : null}

          {step === 4 ? (
            <div className="space-y-5 animate-rise-in">
              <section className="surface-card p-5 sm:p-6">
                <p className="workspace-eyebrow">Final preview</p>
                <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div><h2 className="text-2xl font-semibold text-slate-950">{previewName}</h2><p className="mt-1 text-sm text-slate-500">{form.short_description || 'No short description provided'}</p></div>
                  <select className="control sm:w-40" value={form.status || 'active'} onChange={(event) => setField('status', event.target.value)}>
                    <option value="active">Active</option><option value="draft">Draft</option><option value="archived">Archived</option>
                  </select>
                </div>
              </section>
              {PREVIEW_GROUPS.map(([title, fields]) => (
                <section key={title} className="surface-card p-5 sm:p-6">
                  <h3 className="font-semibold text-slate-900">{title}</h3>
                  <dl className="mt-4 grid gap-4 sm:grid-cols-2">
                    {fields.map((field) => (
                      <div key={field} className={field === 'detailed_description' || field === 'target_customer' ? 'sm:col-span-2' : ''}>
                        <dt className="mb-1 text-[10px] font-bold uppercase tracking-wide text-slate-400">{LABELS[field]}</dt>
                        <dd><PreviewValue value={form[field]} /></dd>
                      </div>
                    ))}
                  </dl>
                </section>
              ))}
              {form.email_template?.subject && form.email_template?.body ? (
                <section className="rounded-2xl border border-primary-200 bg-primary-50/30 p-5">
                  <p className="text-[10px] font-bold uppercase tracking-wide text-primary-700">Email template</p>
                  <p className="mt-1 font-semibold text-slate-900">{offeringEmailTemplateName(form.name, form.email_template.name)}</p>
                  <p className="mt-1 text-sm text-slate-600">{form.email_template.subject}</p>
                </section>
              ) : null}
              {pendingSuggestionCount ? (
                <section className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                  Resolve {pendingSuggestionCount} pending AI suggestion{pendingSuggestionCount === 1 ? '' : 's'} before saving.
                </section>
              ) : null}
              <label className="surface-card flex cursor-pointer items-start gap-3 p-5">
                <input type="checkbox" className="mt-1 h-4 w-4 rounded border-slate-300 text-primary-600" checked={previewConfirmed} onChange={(event) => setPreviewConfirmed(event.target.checked)} />
                <span><span className="block text-sm font-semibold text-slate-900">I reviewed this offering and confirm the information is accurate</span><span className="mt-0.5 block text-xs text-slate-500">This data will be used to rank candidate relevance.</span></span>
              </label>
              <label className="surface-card flex cursor-pointer items-start gap-3 p-5">
                <input type="checkbox" className="mt-1 h-4 w-4 rounded border-slate-300 text-primary-600" checked={runMatch} onChange={(event) => setRunMatch(event.target.checked)} />
                <span><span className="block text-sm font-semibold text-slate-900">Recommend matching contacts after save</span><span className="mt-0.5 block text-xs text-slate-500">Search your ICP contacts and rank the strongest opportunities.</span></span>
              </label>
            </div>
          ) : null}

          <div className="sticky bottom-4 z-10 flex items-center justify-between rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-xl shadow-slate-200/50 backdrop-blur">
            <button type="button" onClick={() => setStep((current) => Math.max(0, current - 1))} disabled={step === 0} className="btn-secondary inline-flex items-center gap-2 disabled:invisible"><FiArrowLeft size={16} /> Back</button>
            <p className="hidden text-xs font-medium text-slate-400 sm:block">Step {step + 1} of {STEPS.length}</p>
            {step < STEPS.length - 1 ? (
              <button type="button" onClick={nextStep} className="btn-primary inline-flex items-center gap-2">Continue <FiArrowRight size={16} /></button>
            ) : (
              <button type="button" disabled={saving || !previewConfirmed || pendingSuggestionCount > 0} onClick={handleSave} className="btn-primary inline-flex items-center gap-2">
                <FiCheck size={16} /> {saving ? 'Saving…' : isEdit ? 'Save offering' : 'Save & recommend'}
              </button>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
