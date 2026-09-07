import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { FiArrowLeft, FiArrowRight, FiCheck, FiFileText, FiSave, FiBookOpen, FiTarget } from 'react-icons/fi';
import { campaignService, offeringsService, templateService, mailerService, customFieldService, userService } from '../services/services';
import { getWorkspaceDefaults } from '../utils/workspaceDefaults';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { generateCampaignId, extractPlaceholders, isTemplateBodyEmpty, ensureManualBodyIsHtml } from '../utils/helpers';
import { buildSamplePreviewContext, getUnknownPlaceholders } from '../utils/mergeFields';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import TemplateEditor from '../components/TemplateEditor';
import Modal from '../components/ui/Modal';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import Button from '../components/ui/Button';
import PageHeader from '../components/ui/PageHeader';
import PageShell from '../components/ui/PageShell';
import CampaignWizardStepper from '../components/campaigns/CampaignWizardStepper';
import CampaignFormFields from '../components/campaigns/CampaignFormFields';

const OFFERING_SEND_KEY = 'leadsense_offering_send_offer';

function buildDefaultForm(user) {
  return {
    campaign_name: '',
    campaign_id: generateCampaignId(),
    description: '',
    owner: user?.name || '',
    department: user?.department || 'Sales',
    target_audience: '',
  };
}

function buildOfferingEmailDraft(offeringName, offeringDescription) {
  const desc = offeringDescription?.trim() || 'our solution';
  return {
    subject: `Introducing ${offeringName}`,
    body: `<p>Hi {{name}},</p><p>I wanted to reach out about <strong>${offeringName}</strong>.</p><p>${desc}</p><p>Would you be open to a quick conversation to see if this is a fit for {{company}}?</p>`,
    closing: 'Best regards,',
    cta: 'Book a call',
  };
}

function readOfferingSendOffer(locationState) {
  if (locationState?.offeringSendOffer) return locationState.offeringSendOffer;
  try {
    const raw = sessionStorage.getItem(OFFERING_SEND_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export default function CreateCampaignPage() {
  const { user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const { id } = useParams();
  const isEditMode = Boolean(id);
  const offeringPrefillApplied = useRef(false);
  const [offeringSendOffer, setOfferingSendOffer] = useState(null);
  const [activeTab, setActiveTab] = useState('campaign');
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [campaignId, setCampaignId] = useState(id || null);

  // Campaign tab
  const [form, setForm] = useState({
    campaign_name: '',
    campaign_id: generateCampaignId(),
    description: '',
    owner: user?.name || '',
    department: user?.department || 'Sales',
    target_audience: '',
    use_recipient_timezone: !!getWorkspaceDefaults().default_use_recipient_timezone,
  });

  // Template tab
  const [templateType, setTemplateType] = useState('manual');
  const [emailContent, setEmailContent] = useState({ subject: '', body: '', closing: '', cta: '' });
  const [placeholderTemplates, setPlaceholderTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [placeholderValues, setPlaceholderValues] = useState({});
  const [aiPrompt, setAiPrompt] = useState({ additional_context: '' });
  const [mailers, setMailers] = useState([]);
  const [saveMailerModalOpen, setSaveMailerModalOpen] = useState(false);
  const [newMailerName, setNewMailerName] = useState('');
  const [savingMailer, setSavingMailer] = useState(false);

  const [customFields, setCustomFields] = useState([]);
  const [unknownFields, setUnknownFields] = useState(null);

  const [campaignSource, setCampaignSource] = useState('create');
  const [offerings, setOfferings] = useState([]);
  const [selectedOfferingId, setSelectedOfferingId] = useState('');
  const [selectedSmartOpsId, setSelectedSmartOpsId] = useState('');
  const [loadingSource, setLoadingSource] = useState(false);
  const [users, setUsers] = useState([]);

  useEffect(() => {
    customFieldService.getAll().then(({ data }) => setCustomFields(data)).catch(() => {});
    userService.getAll().then(({ data }) => setUsers(data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (isEditMode) return;
    offeringsService.list({ limit: 100 })
      .then((data) => setOfferings(data.items || []))
      .catch(() => {});
  }, [isEditMode]);

  useEffect(() => {
    if (isEditMode || offeringPrefillApplied.current) return;
    const payload = readOfferingSendOffer(location.state);
    if (!payload?.offeringId) return;
    const matchCount = payload.matchIds?.length || 0;
    const icpCount = payload.icpRecordIds?.length || 0;
    if (matchCount + icpCount === 0) return;

    offeringPrefillApplied.current = true;
    setOfferingSendOffer(payload);
    setCampaignSource('offering');
    setSelectedOfferingId(String(payload.offeringId));
    setForm({
      campaign_name: `Offer: ${payload.offeringName}`,
      campaign_id: generateCampaignId(),
      description: payload.offeringDescription || `Outreach for ${payload.offeringName}`,
      owner: user?.name || '',
      department: user?.department || 'Sales',
      target_audience: `Selected prospects (${payload.prospectCount || matchCount + icpCount})`,
    });
    setEmailContent(buildOfferingEmailDraft(payload.offeringName, payload.offeringDescription));
    setActiveTab('template');
    offeringsService.get(payload.offeringId).then(async (offering) => {
      await loadPlaceholderTemplates(payload.offeringId);
      if (!offering.email_template?.subject || !offering.email_template?.body) {
        setEmailContent(buildOfferingEmailDraft(payload.offeringName, payload.offeringDescription));
      }
    }).catch(() => {});
    toast.info(`${payload.prospectCount || matchCount + icpCount} prospect(s) ready — compose your offer email and create the campaign`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isEditMode, location.state]);

  useEffect(() => {
    const loadCampaignForEdit = async () => {
      if (!isEditMode || !id) return;
      try {
        const { data } = await campaignService.getById(id);
        setForm({
          campaign_name: data.campaign_name || '',
          campaign_id: data.campaign_id || '',
          description: data.description || '',
          owner: data.owner || user?.name || '',
          department: data.department || user?.department || 'Sales',
          target_audience: data.target_audience || '',
        });
        setCampaignId(data.id);
        const templateRes = await campaignService.getTemplate(id).catch(() => null);
        if (templateRes?.data) {
          const type = templateRes.data.type || 'manual';
          setTemplateType(type);
          setEmailContent({
            subject: templateRes.data.subject || '',
            body: type === 'manual' ? ensureManualBodyIsHtml(templateRes.data.body || '') : (templateRes.data.body || ''),
            closing: templateRes.data.closing || '',
            cta: templateRes.data.cta || '',
          });
        }
      } catch {
        toast.error('Failed to load campaign for editing');
      }
    };

    loadCampaignForEdit();
  }, [id, isEditMode, toast, user?.department, user?.name]);

  const updateForm = (field, value) => setForm((prev) => ({ ...prev, [field]: value }));

  const handleCampaignSourceChange = (source) => {
    setCampaignSource(source);
    setSelectedOfferingId('');
    setSelectedSmartOpsId('');
    if (source === 'create') {
      setOfferingSendOffer(null);
      sessionStorage.removeItem(OFFERING_SEND_KEY);
      setForm(buildDefaultForm(user));
      setEmailContent({ subject: '', body: '', closing: '', cta: '' });
      setTemplateType('manual');
    }
  };

  const handleOfferingSelect = async (offeringId) => {
    setSelectedOfferingId(offeringId);
    if (!offeringId) return;

    setLoadingSource(true);
    try {
      const offering = await offeringsService.get(offeringId);
      setOfferingSendOffer(null);
      sessionStorage.removeItem(OFFERING_SEND_KEY);
      setForm((prev) => ({
        ...prev,
        campaign_name: `Offer: ${offering.name}`,
        description: offering.description || offering.short_description || `Outreach for ${offering.name}`,
        target_audience: prev.target_audience || offering.target_industries?.join(', ') || '',
      }));

      await loadPlaceholderTemplates(offeringId);
      if (!offering.email_template?.subject || !offering.email_template?.body) {
        setEmailContent(buildOfferingEmailDraft(offering.name, offering.description || offering.short_description));
      } else {
        setActiveTab('template');
      }
      toast.success(
        offering.email_template?.subject
          ? `Loaded "${offering.name}" — outreach email ready on Template step`
          : `Loaded offering "${offering.name}"`,
      );
    } catch {
      toast.error('Failed to load offering');
      setSelectedOfferingId('');
    } finally {
      setLoadingSource(false);
    }
  };

  const handleSmartOpsSelect = (mailerId) => {
    setSelectedSmartOpsId(mailerId);
    if (!mailerId) return;

    const mailer = mailers.find((m) => String(m.id) === mailerId);
    if (!mailer) return;

    setTemplateType(mailer.type);
    setEmailContent({
      subject: mailer.subject,
      body: mailer.type === 'manual' ? ensureManualBodyIsHtml(mailer.body) : mailer.body,
      closing: mailer.closing || '',
      cta: mailer.cta || '',
    });
    setForm((prev) => ({
      ...prev,
      campaign_name: prev.campaign_name || mailer.name,
      description: prev.description || `Campaign from Smart Ops mailer: ${mailer.name}`,
    }));
    toast.success(`Loaded Smart Ops mailer "${mailer.name}"`);
  };

  const loadPlaceholderTemplates = async (offeringId) => {
    try {
      const params = offeringId ? { offering_id: offeringId } : {};
      const data = await templateService.getPlaceholderTemplates(params);
      setPlaceholderTemplates(data);
      const offeringTemplate = data.find((t) => t.source === 'offering') || data[0];
      if (offeringTemplate) {
        setTemplateType('placeholder');
        handleSelectPlaceholderTemplate(offeringTemplate);
      }
    } catch {
      toast.error('Failed to load templates');
    }
  };

  const handleTemplateTypeChange = (type) => {
    setTemplateType(type);
    if (type === 'placeholder') loadPlaceholderTemplates(selectedOfferingId || undefined);
  };

  const handleSelectPlaceholderTemplate = (template) => {
    setSelectedTemplate(template);
    const placeholders = extractPlaceholders(template.subject + ' ' + template.body);
    const values = {};
    placeholders.forEach((p) => { values[p] = ''; });
    setPlaceholderValues(values);
    setEmailContent({ subject: template.subject, body: template.body, closing: '', cta: '' });
  };

  const handleGenerateAI = async () => {
    setAiLoading(true);
    try {
      const { data } = await templateService.generateAI({
        campaign_name: form.campaign_name,
        campaign_description: form.description,
        target_audience: form.target_audience,
        additional_context: aiPrompt.additional_context,
      });
      setEmailContent({
        subject: data.subject,
        body: data.body,
        closing: data.closing,
        cta: data.cta,
      });
      if (data.is_mock) toast.info('Using mock AI response (OpenAI not configured)');
      else toast.success('AI email generated successfully');
    } catch {
      toast.error('Failed to generate AI template');
    } finally {
      setAiLoading(false);
    }
  };

  useEffect(() => {
    mailerService.getAll().then(({ data }) => setMailers(data)).catch(() => {});
  }, []);

  const handleSelectMailer = (mailerId) => {
    const mailer = mailers.find((m) => String(m.id) === mailerId);
    if (!mailer) return;
    setTemplateType(mailer.type);
    setEmailContent({
      subject: mailer.subject,
      body: mailer.type === 'manual' ? ensureManualBodyIsHtml(mailer.body) : mailer.body,
      closing: mailer.closing || '',
      cta: mailer.cta || '',
    });
    toast.success(`Loaded mailer "${mailer.name}"`);
  };

  const handleConfirmSaveMailer = async () => {
    if (!newMailerName.trim()) {
      toast.error('Enter a name for this mailer');
      return;
    }
    if (!emailContent.subject.trim() || isTemplateBodyEmpty(emailContent.body, templateType)) {
      toast.error('Subject and body are required to save a mailer');
      return;
    }
    setSavingMailer(true);
    try {
      await mailerService.create({
        name: newMailerName.trim(),
        type: templateType,
        subject: emailContent.subject,
        body: emailContent.body,
        closing: emailContent.closing,
        cta: emailContent.cta,
      });
      toast.success('Saved as a reusable mailer');
      setSaveMailerModalOpen(false);
      setNewMailerName('');
      const { data } = await mailerService.getAll();
      setMailers(data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save mailer');
    } finally {
      setSavingMailer(false);
    }
  };

  const previewContext = buildSamplePreviewContext(placeholderValues);

  const handleNext = () => {
    if (!form.campaign_name || !form.campaign_id) {
      toast.error('Campaign Name and Campaign ID are required');
      return;
    }
    setActiveTab('template');
  };

  const handleSubmit = () => {
    if (!form.campaign_name || !form.campaign_id) {
      toast.error('Campaign Name and Campaign ID are required');
      setActiveTab('campaign');
      return;
    }

    const hasSubject = emailContent.subject.trim().length > 0;
    const hasBody = !isTemplateBodyEmpty(emailContent.body, templateType);
    if (offeringSendOffer && (!hasSubject || !hasBody)) {
      toast.error('Subject and body are required to send an offer');
      setActiveTab('template');
      return;
    }
    if (hasSubject !== hasBody) {
      toast.error('Complete both Subject and Body for the template, or leave both empty');
      setActiveTab('template');
      return;
    }

    if (hasSubject && hasBody) {
      const unknown = getUnknownPlaceholders(
        [emailContent.subject, emailContent.body, emailContent.closing, emailContent.cta],
        customFields.map((f) => f.name)
      );
      if (unknown.length > 0) {
        setUnknownFields(unknown);
        return;
      }
    }

    performSubmit();
  };

  const handleProceedWithUnknownFields = async () => {
    try {
      await Promise.all(unknownFields.map((name) => customFieldService.create(name)));
      const { data } = await customFieldService.getAll();
      setCustomFields(data);
    } catch {
      // Registration failing shouldn't block the submit the user already confirmed.
    } finally {
      performSubmit();
    }
  };

  const performSubmit = async () => {
    const hasSubject = emailContent.subject.trim().length > 0;
    const hasBody = !isTemplateBodyEmpty(emailContent.body, templateType);

    // Campaign creation and the template save are two separate requests —
    // if the template save fails (e.g. a large embedded image), the
    // campaign from step one is already persisted. `newCampaignId` tracks
    // that locally (not via the `campaignId` state setter below, which
    // wouldn't be visible until a re-render) so a retry within this same
    // visit — or a subsequent submit click — updates/attaches the template
    // to that same campaign instead of trying to create a second one.
    let newCampaignId = campaignId;

    setLoading(true);
    try {
      if (!newCampaignId) {
        const { data } = await campaignService.create(form);
        newCampaignId = data.id;
        setCampaignId(newCampaignId);
      } else if (isEditMode) {
        await campaignService.update(newCampaignId, form);
      }

      if (hasSubject && hasBody) {
        await campaignService.saveTemplate(newCampaignId, {
          campaign_id: newCampaignId,
          type: templateType,
          subject: emailContent.subject,
          body: emailContent.body,
          closing: emailContent.closing,
          cta: emailContent.cta,
        });
      }

      let preselectedContactIds = null;
      if (offeringSendOffer && ((offeringSendOffer.matchIds?.length || 0) + (offeringSendOffer.icpRecordIds?.length || 0) > 0)) {
        const result = await offeringsService.prepareCampaignRecipients(offeringSendOffer.offeringId, {
          match_ids: offeringSendOffer.matchIds || [],
          icp_record_ids: offeringSendOffer.icpRecordIds || [],
          campaign_id: newCampaignId,
          group_name: offeringSendOffer.offeringName,
        });
        preselectedContactIds = result.recipient_ids || [];
        sessionStorage.removeItem(OFFERING_SEND_KEY);

        if (result.skipped?.length) {
          toast.warning(
            `${result.skipped.length} candidate(s) skipped — no email on file. Add emails in your prospect sheet and try again.`,
          );
        }
        if (preselectedContactIds.length) {
          toast.success(`${preselectedContactIds.length} prospect(s) added to this campaign`);
        } else if (!result.skipped?.length) {
          toast.warning('No prospects could be added — check that selected candidates have email addresses');
        }
      }

      toast.success(isEditMode ? 'Campaign updated' : 'Campaign created');
      navigate(`/campaigns/${newCampaignId}`, {
        state: preselectedContactIds?.length ? { preselectedContactIds } : undefined,
      });
    } catch (err) {
      const detail = err.response?.data?.detail;
      const message = typeof detail === 'string' && detail
        ? detail
        : newCampaignId
          ? 'Campaign saved, but the template failed to save. Fix the issue and submit again — it will reuse the same campaign.'
          : (isEditMode ? 'Failed to update campaign' : 'Failed to create campaign');
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const wizardStep = activeTab === 'campaign' ? 'campaign' : 'template';

  return (
    <PageShell maxWidth="max-w-5xl">
      <PageHeader
        eyebrow="Lead generation"
        title={isEditMode ? 'Edit campaign' : 'Create campaign'}
        subtitle={isEditMode ? 'Update your campaign details and email template.' : 'Set up your outreach campaign in a few steps.'}
        actions={activeTab === 'campaign' ? (
          <button onClick={() => navigate('/campaigns')} className="btn-secondary flex items-center gap-2">
            <FiArrowLeft size={16} /> Cancel
          </button>
        ) : (
          <button onClick={() => setActiveTab('campaign')} className="btn-secondary flex items-center gap-2">
            <FiArrowLeft size={16} /> Back
          </button>
        )}
      />

      <CampaignWizardStepper activeStep={wizardStep} />

      {offeringSendOffer ? (
        <div className="rounded-xl border border-primary-200 bg-primary-50 px-4 py-3 text-sm text-primary-900">
          Sending offer for <strong>{offeringSendOffer.offeringName}</strong> to{' '}
          <strong>{offeringSendOffer.prospectCount || (offeringSendOffer.matchIds?.length || 0) + (offeringSendOffer.icpRecordIds?.length || 0)}</strong>{' '}
          selected prospect
          {(offeringSendOffer.prospectCount || 0) === 1 ? '' : 's'}
          {offeringSendOffer.icpRecordIds?.length ? (
            <> ({offeringSendOffer.icpRecordIds.length} from ICP database)</>
          ) : null}
          . Compose your template, then create the campaign to preview and send.
        </div>
      ) : null}

      <div className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-6 sm:p-8 shadow-card">
        <div className="pointer-events-none absolute -right-8 -top-8 hidden sm:block">
          <div className="flex h-32 w-32 items-center justify-center rounded-2xl border border-slate-100 bg-slate-50/80 rotate-12">
            <FiTarget size={48} className="text-primary-200" />
          </div>
        </div>

        {activeTab === 'campaign' && (
          <div className="relative space-y-6">
            <div className="flex items-start gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-100 text-primary-600">
                <FiTarget size={22} />
              </div>
              <div>
                <h2 className="text-xl font-bold text-slate-900">Campaign Information</h2>
                <p className="text-sm text-slate-500 mt-0.5">Provide the basic details about your campaign.</p>
              </div>
            </div>

            <CampaignFormFields
              form={form}
              updateForm={updateForm}
              isEditMode={isEditMode}
              campaignSource={campaignSource}
              onCampaignSourceChange={handleCampaignSourceChange}
              offerings={offerings}
              mailers={mailers}
              selectedOfferingId={selectedOfferingId}
              selectedSmartOpsId={selectedSmartOpsId}
              onOfferingSelect={handleOfferingSelect}
              onSmartOpsSelect={handleSmartOpsSelect}
              loadingSource={loadingSource}
              users={users}
            />
          </div>
        )}

        {activeTab === 'template' && (
          <div className="relative space-y-6">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="flex items-start gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-violet-100 text-violet-600">
                  <FiFileText size={22} />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Email Template</h2>
                  <p className="text-sm text-slate-500 mt-0.5">Compose or load the email your prospects will receive.</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <select
                  className="campaign-field-select w-auto text-sm"
                  value=""
                  onChange={(e) => e.target.value && handleSelectMailer(e.target.value)}
                >
                  <option value="">From Saved Mailer...</option>
                  {mailers.map((m) => (
                    <option key={m.id} value={m.id}>{m.name}</option>
                  ))}
                </select>
                <button
                  onClick={() => setSaveMailerModalOpen(true)}
                  disabled={!emailContent.subject.trim() || isTemplateBodyEmpty(emailContent.body, templateType)}
                  className="btn-secondary text-sm flex items-center gap-1"
                >
                  <FiSave size={14} /> Save as Mailer
                </button>
              </div>
            </div>

            <TemplateEditor
              templateType={templateType}
              onTemplateTypeChange={handleTemplateTypeChange}
              emailContent={emailContent}
              onEmailContentChange={setEmailContent}
              placeholderTemplates={placeholderTemplates}
              selectedTemplate={selectedTemplate}
              onSelectPlaceholderTemplate={handleSelectPlaceholderTemplate}
              placeholderValues={placeholderValues}
              onPlaceholderValueChange={(key, value) => setPlaceholderValues((p) => ({ ...p, [key]: value }))}
              aiPrompt={aiPrompt}
              onAiPromptChange={setAiPrompt}
              onGenerateAI={handleGenerateAI}
              aiLoading={aiLoading}
              previewContext={previewContext}
            />
          </div>
        )}
      </div>

      <div className="flex justify-end">
        {activeTab === 'campaign' ? (
          <Button onClick={handleNext} icon={FiArrowRight} iconPosition="right" size="lg">
            Next
          </Button>
        ) : (
          <Button onClick={handleSubmit} disabled={loading} loading={loading} icon={FiCheck} size="lg">
            {offeringSendOffer ? 'Create & Send Offer' : isEditMode ? 'Save Changes' : 'Create Campaign'}
          </Button>
        )}
      </div>

      <Modal isOpen={saveMailerModalOpen} onClose={() => setSaveMailerModalOpen(false)} title="Save as Mailer" size="sm">
        <div className="space-y-4">
          <p className="text-sm text-gray-500">
            Save this template to the reusable Mailer library so it can be found and loaded into future campaigns.
          </p>
          <div>
            <label className="label">Mailer Name *</label>
            <input
              className="input-field"
              value={newMailerName}
              onChange={(e) => setNewMailerName(e.target.value)}
              placeholder="e.g. Cold Outreach - Tech Decision Makers"
              autoFocus
            />
          </div>
          <div className="flex justify-end gap-2">
            <button onClick={() => setSaveMailerModalOpen(false)} className="btn-secondary">Cancel</button>
            <button onClick={handleConfirmSaveMailer} disabled={savingMailer} className="btn-primary flex items-center gap-2">
              {savingMailer ? <LoadingSpinner size="sm" /> : <><FiBookOpen size={16} /> Save Mailer</>}
            </button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={!!unknownFields}
        onClose={() => setUnknownFields(null)}
        onConfirm={handleProceedWithUnknownFields}
        variant="primary"
        title="Unrecognized Field"
        message={
          unknownFields
            ? `This template uses ${unknownFields.map((f) => `{{${f}}}`).join(', ')} — not one of the standard prospect fields. You can go back and fix it, or proceed anyway: it'll render blank until prospect data exists for it, and won't be flagged again.`
            : ''
        }
        confirmText="Proceed Anyway"
        cancelText="Go Back & Edit"
      />
    </PageShell>
  );
}
