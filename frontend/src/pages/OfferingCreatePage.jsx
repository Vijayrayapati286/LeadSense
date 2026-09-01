import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { FiArrowLeft, FiArrowRight, FiBriefcase, FiCheck, FiTarget, FiUsers, FiZap } from 'react-icons/fi';
import {
  applyGeneratedIcp,
  AreaField,
  EMPTY_OFFERING,
  formToPayload,
  ListField,
  TextField,
} from '../components/offerings/offeringFormUtils';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { useToast } from '../hooks/useToast';
import { offeringsService } from '../services/services';
import { WorkspaceHeader } from '../components/ui/GrowthWorkspace';

const STEPS = [
  { label: 'Offering', hint: 'What you sell', icon: FiBriefcase },
  { label: 'Companies', hint: 'Who it fits', icon: FiTarget },
  { label: 'Buyers', hint: 'Who decides', icon: FiUsers },
  { label: 'Review', hint: 'Confirm & match', icon: FiCheck },
];

function ChipList({ items, empty = '—' }) {
  if (!items?.length) return <p className="text-sm text-gray-400">{empty}</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span
          key={item}
          className="inline-flex rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

/** Compact read-only ICP summary — no Target Company / Persona / Keywords textareas */
function IcpSummaryCard({ form }) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-gray-900">AI ICP profile</h2>
        <p className="text-xs text-gray-500 mt-0.5">
          Generated from your description — used for matching (not edited field-by-field)
        </p>
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5">
            Industries
          </p>
          <ChipList items={form.target_industries} />
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5">
            Job titles
          </p>
          <ChipList items={form.target_job_titles} />
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5">
            Pain points
          </p>
          <ChipList items={form.pain_points} />
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5">
            Use cases
          </p>
          <ChipList items={form.use_cases} />
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5">
            Benefits
          </p>
          <ChipList items={form.benefits} />
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5">
            Buying signals
          </p>
          <ChipList items={[...(form.buying_roles || []), ...(form.decision_maker_types || [])]} />
        </div>
      </div>
      <div className="grid sm:grid-cols-3 gap-3 text-sm border-t border-gray-100 pt-3">
        <div>
          <p className="text-[11px] uppercase text-gray-400">Company size</p>
          <p className="font-medium text-gray-800">
            {form.company_size_label ||
              [form.company_size_min, form.company_size_max]
                .filter((v) => v !== '' && v != null)
                .join('–') ||
              '—'}
          </p>
        </div>
        <div>
          <p className="text-[11px] uppercase text-gray-400">Geography</p>
          <p className="font-medium text-gray-800">
            {(form.target_geographies || []).slice(0, 3).join(', ') || '—'}
          </p>
        </div>
        <div>
          <p className="text-[11px] uppercase text-gray-400">Keywords</p>
          <p className="font-medium text-gray-800 truncate">
            {(form.positive_keywords || []).slice(0, 4).join(', ') || '—'}
          </p>
        </div>
      </div>
    </div>
  );
}

export default function OfferingCreatePage() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const toast = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState({ ...EMPTY_OFFERING, status: 'active' });
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [generated, setGenerated] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(isEdit);
  const [runMatch, setRunMatch] = useState(true);
  const [step, setStep] = useState(0);

  function setField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function nextStep() {
    if (step === 0 && !form.name?.trim()) {
      toast.error('Add an offering name before continuing');
      return;
    }
    setStep((current) => Math.min(STEPS.length - 1, current + 1));
    window.scrollTo({ top: 0, behavior: 'smooth' });
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
            company_size_min: data.company_size_min ?? '',
            company_size_max: data.company_size_max ?? '',
            revenue_min: data.revenue_min ?? '',
            revenue_max: data.revenue_max ?? '',
            status: data.status || 'active',
          });
          setAiPrompt(data.description || data.short_description || '');
          setGenerated(true);
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

  async function handleGenerate() {
    if (!aiPrompt.trim() || aiPrompt.trim().length < 10) {
      toast.error('Describe what you are selling (at least a sentence)');
      return;
    }
    setAiLoading(true);
    try {
      const result = await offeringsService.generateIcp(aiPrompt.trim());
      setForm((prev) => {
        const next = applyGeneratedIcp(prev, result);
        next.description = result.description || aiPrompt.trim();
        if (!next.short_description) next.short_description = result.short_description || '';
        if (!next.name) next.name = result.suggested_name || '';
        next.status = prev.status || 'active';
        return next;
      });
      setGenerated(true);
      toast.success(
        result.is_mock
          ? 'Description + ICP ready (mock mode)'
          : 'Description + ICP ready — review basic info then save',
      );
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'AI generation failed');
    } finally {
      setAiLoading(false);
    }
  }

  async function handleSave() {
    if (!form.name?.trim()) {
      toast.error('Offering name is required');
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
          await offeringsService.startMatch(offeringId, true, true);
          toast.success('Matching verified ICP contacts…');
        } catch {
          /* best-effort */
        }
      }
      navigate(`/offerings/${offeringId}?tab=matching`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save offering');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="workspace-shell max-w-6xl">
      <WorkspaceHeader
        eyebrow="Offering studio"
        title={isEdit ? 'Refine your offering' : 'Create a market-ready offering'}
        description="Start with your own notes or let AI build the first draft. Every company, persona, signal, and rule remains fully editable."
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
                  onClick={() => (index < step || isEdit || generated) && setStep(index)}
                  disabled={index > step && !isEdit && !generated}
                  className={`flex w-full items-center gap-3 rounded-xl p-3 text-left transition ${
                    step === index ? 'bg-primary-50 text-primary-800' : 'text-slate-500 hover:bg-slate-50 disabled:opacity-45'
                  }`}
                  aria-current={step === index ? 'step' : undefined}
                >
                  <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${step === index ? 'bg-primary-600 text-white' : index < step ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                    {index < step ? <FiCheck size={17} /> : <Icon size={17} />}
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
              <section className="overflow-hidden rounded-2xl border border-primary-200 bg-gradient-to-br from-primary-50 to-white p-5 sm:p-6">
                <div className="flex items-start gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-600 text-white shadow-lg shadow-primary-200"><FiZap size={18} /></span>
                  <div>
                    <h2 className="font-semibold text-slate-900">Build a first draft with AI</h2>
                    <p className="mt-1 text-sm text-slate-500">Describe what you sell, the problem it solves, and your best customers. You can edit every generated field.</p>
                  </div>
                </div>
                <textarea rows={5} className="control mt-4 resize-y border-primary-200" placeholder="We sell an AI platform that analyzes customer calls and provides real-time coaching..." value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} />
                <button type="button" disabled={aiLoading} onClick={handleGenerate} className="btn-primary mt-3 inline-flex items-center gap-2">
                  <FiZap size={16} /> {aiLoading ? 'Building your ICP…' : generated ? 'Regenerate draft' : 'Generate offering & ICP'}
                </button>
              </section>

              <section className="surface-card space-y-5 p-5 sm:p-6">
                <div><h2 className="font-semibold text-slate-900">Offering basics</h2><p className="mt-1 text-sm text-slate-500">Give your team a clear, recognizable description.</p></div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <TextField label="Offering name" required value={form.name} onChange={(v) => setField('name', v)} />
                  <TextField label="Product or service type" value={form.product_type} onChange={(v) => setField('product_type', v)} />
                </div>
                <TextField label="Short description" value={form.short_description} onChange={(v) => setField('short_description', v)} />
                <AreaField label="Detailed description" value={form.description} onChange={(v) => setField('description', v)} rows={5} />
                <div className="grid gap-4 sm:grid-cols-2">
                  <TextField label="Website URL" value={form.website_url} onChange={(v) => setField('website_url', v)} />
                  <TextField label="Pricing range" value={form.pricing_range} onChange={(v) => setField('pricing_range', v)} />
                </div>
              </section>
            </div>
          ) : null}

          {step === 1 ? (
            <section className="surface-card space-y-6 p-5 sm:p-6 animate-rise-in">
              <div><p className="workspace-eyebrow">Step 2</p><h2 className="text-xl font-semibold text-slate-900">Define your best-fit companies</h2><p className="mt-1 text-sm text-slate-500">These criteria power matching and recommendation quality.</p></div>
              <div className="grid gap-5 sm:grid-cols-2">
                <ListField label="Target industries" hint="One value per line" value={form.target_industries} onChange={(v) => setField('target_industries', v)} />
                <ListField label="Target geographies" value={form.target_geographies} onChange={(v) => setField('target_geographies', v)} />
                <ListField label="Business models" value={form.business_models} onChange={(v) => setField('business_models', v)} />
                <ListField label="Target departments" value={form.target_departments} onChange={(v) => setField('target_departments', v)} />
              </div>
              <div className="grid gap-4 rounded-2xl bg-slate-50 p-4 sm:grid-cols-2">
                <label><span className="field-label">Minimum employees</span><input type="number" className="control" value={form.company_size_min} onChange={(e) => setField('company_size_min', e.target.value)} /></label>
                <label><span className="field-label">Maximum employees</span><input type="number" className="control" value={form.company_size_max} onChange={(e) => setField('company_size_max', e.target.value)} /></label>
                <label><span className="field-label">Minimum revenue</span><input type="number" className="control" value={form.revenue_min} onChange={(e) => setField('revenue_min', e.target.value)} /></label>
                <label><span className="field-label">Maximum revenue</span><input type="number" className="control" value={form.revenue_max} onChange={(e) => setField('revenue_max', e.target.value)} /></label>
              </div>
              <div className="grid gap-5 sm:grid-cols-3">
                <ListField label="Must-have rules" value={form.must_have_rules} onChange={(v) => setField('must_have_rules', v)} />
                <ListField label="Nice-to-have rules" value={form.nice_to_have_rules} onChange={(v) => setField('nice_to_have_rules', v)} />
                <ListField label="Exclusions" value={form.exclusion_rules} onChange={(v) => setField('exclusion_rules', v)} />
              </div>
            </section>
          ) : null}

          {step === 2 ? (
            <section className="surface-card space-y-6 p-5 sm:p-6 animate-rise-in">
              <div><p className="workspace-eyebrow">Step 3</p><h2 className="text-xl font-semibold text-slate-900">Describe the buyer and their signals</h2><p className="mt-1 text-sm text-slate-500">Focus recommendations on people who own the problem and can act.</p></div>
              <div className="grid gap-5 sm:grid-cols-2">
                <ListField label="Job titles" value={form.target_job_titles} onChange={(v) => setField('target_job_titles', v)} />
                <ListField label="Seniority levels" value={form.target_seniority} onChange={(v) => setField('target_seniority', v)} />
                <ListField label="Decision maker types" value={form.decision_maker_types} onChange={(v) => setField('decision_maker_types', v)} />
                <ListField label="Buying roles" value={form.buying_roles} onChange={(v) => setField('buying_roles', v)} />
                <ListField label="Pain points" value={form.pain_points} onChange={(v) => setField('pain_points', v)} />
                <ListField label="Business problems" value={form.business_problems} onChange={(v) => setField('business_problems', v)} />
                <ListField label="Current challenges" value={form.current_challenges} onChange={(v) => setField('current_challenges', v)} />
                <ListField label="Use cases" value={form.use_cases} onChange={(v) => setField('use_cases', v)} />
                <ListField label="Desired outcomes" value={form.desired_outcomes} onChange={(v) => setField('desired_outcomes', v)} />
                <ListField label="Benefits" value={form.benefits} onChange={(v) => setField('benefits', v)} />
                <ListField label="Positive keywords" value={form.positive_keywords} onChange={(v) => setField('positive_keywords', v)} />
                <ListField label="Negative keywords" value={form.negative_keywords} onChange={(v) => setField('negative_keywords', v)} />
              </div>
            </section>
          ) : null}

          {step === 3 ? (
            <div className="space-y-5 animate-rise-in">
              <section className="surface-card p-5 sm:p-6">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div><p className="workspace-eyebrow">Ready to launch</p><h2 className="text-xl font-semibold text-slate-900">{form.name || 'Untitled offering'}</h2><p className="mt-1 text-sm text-slate-500">{form.short_description || form.description || 'Add a description in the Offering step.'}</p></div>
                  <select className="control sm:w-40" value={form.status || 'active'} onChange={(e) => setField('status', e.target.value)}>
                    <option value="active">Active</option><option value="draft">Draft</option><option value="archived">Archived</option>
                  </select>
                </div>
              </section>
              <IcpSummaryCard form={form} />
              <label className="surface-card flex cursor-pointer items-start gap-3 p-5">
                <input type="checkbox" className="mt-1 h-4 w-4 rounded border-slate-300 text-primary-600" checked={runMatch} onChange={(e) => setRunMatch(e.target.checked)} />
                <span><span className="block text-sm font-semibold text-slate-900">Recommend matching contacts after save</span><span className="mt-0.5 block text-xs text-slate-500">Search verified ICP records immediately and rank the strongest opportunities.</span></span>
              </label>
            </div>
          ) : null}

          <div className="sticky bottom-4 z-10 flex items-center justify-between rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-xl shadow-slate-200/50 backdrop-blur">
            <button type="button" onClick={() => setStep((current) => Math.max(0, current - 1))} disabled={step === 0} className="btn-secondary inline-flex items-center gap-2 disabled:invisible"><FiArrowLeft size={16} /> Back</button>
            <p className="hidden text-xs font-medium text-slate-400 sm:block">Step {step + 1} of {STEPS.length}</p>
            {step < STEPS.length - 1 ? (
              <button type="button" onClick={nextStep} className="btn-primary inline-flex items-center gap-2">Continue <FiArrowRight size={16} /></button>
            ) : (
              <button type="button" disabled={saving || !form.name?.trim()} onClick={handleSave} className="btn-primary inline-flex items-center gap-2">
                <FiCheck size={16} /> {saving ? 'Saving…' : isEdit ? 'Save offering' : 'Save & recommend'}
              </button>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
