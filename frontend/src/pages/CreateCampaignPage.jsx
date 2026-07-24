import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { FiArrowLeft, FiArrowRight, FiCheck, FiSave, FiBookOpen } from 'react-icons/fi';
import { campaignService, templateService, mailerService, customFieldService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { generateCampaignId, extractPlaceholders } from '../utils/helpers';
import { buildSamplePreviewContext, getUnknownPlaceholders } from '../utils/mergeFields';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import TemplateEditor from '../components/TemplateEditor';
import Modal from '../components/ui/Modal';
import ConfirmDialog from '../components/ui/ConfirmDialog';

const TABS = [
  { id: 'campaign', label: 'Campaign' },
  { id: 'template', label: 'Template' },
];

export default function CreateCampaignPage() {
  const { user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const { id } = useParams();
  const isEditMode = Boolean(id);
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

  useEffect(() => {
    customFieldService.getAll().then(({ data }) => setCustomFields(data)).catch(() => {});
  }, []);

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
          setTemplateType(templateRes.data.type || 'manual');
          setEmailContent({
            subject: templateRes.data.subject || '',
            body: templateRes.data.body || '',
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

  const loadPlaceholderTemplates = async () => {
    if (placeholderTemplates.length > 0) return;
    try {
      const { data } = await templateService.getPlaceholderTemplates();
      setPlaceholderTemplates(data);
    } catch {
      toast.error('Failed to load templates');
    }
  };

  const handleTemplateTypeChange = (type) => {
    setTemplateType(type);
    if (type === 'placeholder') loadPlaceholderTemplates();
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
    setEmailContent({ subject: mailer.subject, body: mailer.body, closing: mailer.closing || '', cta: mailer.cta || '' });
    toast.success(`Loaded mailer "${mailer.name}"`);
  };

  const handleConfirmSaveMailer = async () => {
    if (!newMailerName.trim()) {
      toast.error('Enter a name for this mailer');
      return;
    }
    if (!emailContent.subject.trim() || !emailContent.body.trim()) {
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
    const hasBody = emailContent.body.trim().length > 0;
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
    const hasBody = emailContent.body.trim().length > 0;

    setLoading(true);
    try {
      const { data } = isEditMode
        ? await campaignService.update(campaignId, form)
        : await campaignService.create(form);
      const newCampaignId = data.id;
      setCampaignId(newCampaignId);

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

      toast.success(isEditMode ? 'Campaign updated' : 'Campaign created');
      navigate(`/campaigns/${newCampaignId}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || (isEditMode ? 'Failed to update campaign' : 'Failed to create campaign'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-fade-in">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{isEditMode ? 'Edit Campaign' : 'Create Campaign'}</h1>
          <p className="text-gray-500 mt-1">Step {activeTab === 'campaign' ? '1' : '2'} of 2</p>
        </div>
        <div className="flex items-center gap-2">
          {activeTab === 'campaign' ? (
            <button onClick={() => navigate('/campaigns')} className="btn-secondary flex items-center gap-2">
              <FiArrowLeft size={16} /> Cancel
            </button>
          ) : (
            <button onClick={() => setActiveTab('campaign')} className="btn-secondary flex items-center gap-2">
              <FiArrowLeft size={16} /> Back
            </button>
          )}
        </div>
      </div>

      {/* Tabs — same pattern as the campaign detail page: freely switchable, no locking */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-6">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="card">
        {activeTab === 'campaign' && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Campaign Information</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="label">Campaign Name *</label>
                <input className="input-field" value={form.campaign_name} onChange={(e) => updateForm('campaign_name', e.target.value)} placeholder="Q1 Product Launch" />
              </div>
              <div>
                <label className="label">Campaign ID *</label>
                <input className="input-field font-mono text-sm" value={form.campaign_id} onChange={(e) => updateForm('campaign_id', e.target.value)} />
              </div>
              <div className="md:col-span-2">
                <label className="label">Description</label>
                <textarea className="input-field" rows={3} value={form.description} onChange={(e) => updateForm('description', e.target.value)} placeholder="Describe the campaign purpose..." />
              </div>
              <div>
                <label className="label">Owner</label>
                <input className="input-field" value={form.owner} onChange={(e) => updateForm('owner', e.target.value)} />
              </div>
              <div>
                <label className="label">Department</label>
                <input className="input-field" value={form.department} onChange={(e) => updateForm('department', e.target.value)} />
              </div>
              <div>
                <label className="label">Target Audience</label>
                <input className="input-field" value={form.target_audience} onChange={(e) => updateForm('target_audience', e.target.value)} placeholder="B2B Decision Makers" />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'template' && (
          <div className="space-y-6">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <h2 className="text-lg font-semibold">Choose Email Template</h2>
              <div className="flex items-center gap-2">
                <select
                  className="input-field w-auto text-sm"
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
                  disabled={!emailContent.subject.trim() || !emailContent.body.trim()}
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
          <button onClick={handleNext} className="btn-primary flex items-center gap-2">
            Next <FiArrowRight size={16} />
          </button>
        ) : (
          <button onClick={handleSubmit} disabled={loading} className="btn-primary flex items-center gap-2">
            {loading ? <LoadingSpinner size="sm" /> : <>{isEditMode ? 'Save Changes' : 'Create Campaign'} <FiCheck size={16} /></>}
          </button>
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
    </div>
  );
}
