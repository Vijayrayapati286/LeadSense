import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { FiArrowLeft, FiArrowRight, FiCheck, FiZap, FiEdit3, FiFileText, FiUsers, FiMail } from 'react-icons/fi';
import { campaignService, templateService, emailService, recipientService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { generateCampaignId, extractPlaceholders, renderTemplate } from '../utils/helpers';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import EmailPreview from '../components/EmailPreview';

const STEPS = ['Campaign Info', 'Choose Template', 'Select Recipients', 'Preview & Send'];
const TEST_EMAIL_TARGET = import.meta.env.VITE_TEST_EMAIL || 'd.nikhileswar.reddy@gmail.com';

const TEMPLATE_TYPES = [
  { id: 'manual', label: 'Manual', icon: FiEdit3, desc: 'Write your own email with rich text' },
  { id: 'placeholder', label: 'Placeholder', icon: FiFileText, desc: 'Use templates with dynamic placeholders' },
  { id: 'ai', label: 'AI Generated', icon: FiZap, desc: 'Let AI craft your email content' },
];

export default function CreateCampaignPage() {
  const { user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const { id } = useParams();
  const isEditMode = Boolean(id);
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [campaignId, setCampaignId] = useState(id || null);

  // Step 1: Campaign Info
  const [form, setForm] = useState({
    campaign_name: '',
    campaign_id: generateCampaignId(),
    description: '',
    owner: user?.name || '',
    department: user?.department || 'Sales',
    target_audience: '',
    subject: '',
  });

  // Step 2: Template
  const [templateType, setTemplateType] = useState('manual');
  const [emailContent, setEmailContent] = useState({ subject: '', body: '', closing: '', cta: '' });
  const [placeholderTemplates, setPlaceholderTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [placeholderValues, setPlaceholderValues] = useState({});
  const [aiPrompt, setAiPrompt] = useState({ additional_context: '' });
  const [recipientOptions, setRecipientOptions] = useState([]);
  const [recipientLoading, setRecipientLoading] = useState(false);
  const [recipientSearch, setRecipientSearch] = useState('');
  const [selectedRecipientIds, setSelectedRecipientIds] = useState([]);

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
          subject: data.subject || '',
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

  useEffect(() => {
    if (step !== 2) return;

    const loadRecipients = async () => {
      setRecipientLoading(true);
      try {
        const stored = JSON.parse(localStorage.getItem('selectedRecipientIds') || '[]');
        setSelectedRecipientIds(stored);
        const { data } = await recipientService.getAll({ page: 1, page_size: 100, search: recipientSearch });
        setRecipientOptions(data.items);
      } catch {
        toast.error('Failed to load recipients');
      } finally {
        setRecipientLoading(false);
      }
    };

    loadRecipients();
  }, [step, recipientSearch, toast]);

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
    setLoading(true);
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
      setLoading(false);
    }
  };

  const handleNext = async () => {
    if (step === 0) {
      if (!form.campaign_name || !form.campaign_id) {
        toast.error('Please fill in required fields');
        return;
      }
      setLoading(true);
      try {
        const { data } = isEditMode
          ? await campaignService.update(campaignId, form)
          : await campaignService.create(form);
        setCampaignId(data.id);
        setStep(1);
      } catch (err) {
        toast.error(err.response?.data?.detail || (isEditMode ? 'Failed to update campaign' : 'Failed to create campaign'));
      } finally {
        setLoading(false);
      }
    } else if (step === 1) {
      if (!emailContent.subject || !emailContent.body) {
        toast.error('Please complete the email template');
        return;
      }
      setLoading(true);
      try {
        await campaignService.saveTemplate(campaignId, {
          campaign_id: campaignId,
          type: templateType,
          subject: emailContent.subject,
          body: emailContent.body,
          closing: emailContent.closing,
          cta: emailContent.cta,
        });
        setStep(2);
      } catch {
        toast.error('Failed to save template');
      } finally {
        setLoading(false);
      }
    } else if (step === 2) {
      localStorage.setItem('selectedRecipientIds', JSON.stringify(selectedRecipientIds));
      setStep(3);
    }
  };

  const handleSend = async () => {
    setLoading(true);
    try {
      const recipientIds = JSON.parse(localStorage.getItem('selectedRecipientIds') || '[]');
      const { data } = await emailService.send({
        campaign_id: campaignId,
        subject: emailContent.subject,
        body: emailContent.body + (emailContent.closing ? `\n\n${emailContent.closing}` : ''),
        recipient_ids: recipientIds,
      });
      toast.success(`Send complete. Sent: ${data.sent}, Failed: ${data.failed}, Pending: ${data.pending}`);
      navigate('/campaigns');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send emails');
    } finally {
      setLoading(false);
    }
  };

  const toggleRecipient = (recipientId) => {
    setSelectedRecipientIds((prev) => {
      const next = prev.includes(recipientId)
        ? prev.filter((id) => id !== recipientId)
        : [...prev, recipientId];
      localStorage.setItem('selectedRecipientIds', JSON.stringify(next));
      return next;
    });
  };

  const selectAllRecipients = () => {
    const next = recipientOptions.map((recipient) => recipient.id);
    setSelectedRecipientIds(next);
    localStorage.setItem('selectedRecipientIds', JSON.stringify(next));
  };

  const clearRecipients = () => {
    setSelectedRecipientIds([]);
    localStorage.setItem('selectedRecipientIds', '[]');
  };

  const previewContext = {
    Name: placeholderValues.Name || 'John Doe',
    Company: placeholderValues.Company || 'Acme Corp',
    Designation: placeholderValues.Designation || 'CEO',
    Industry: placeholderValues.Industry || 'Technology',
    Email: 'john@acme.com',
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{isEditMode ? 'Edit Campaign' : 'Create Campaign'}</h1>
        <p className="text-gray-500 mt-1">Set up your email campaign in 3 easy steps</p>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-2">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2 flex-1">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                i < step ? 'bg-green-500 text-white' : i === step ? 'bg-primary-600 text-white' : 'bg-gray-200 text-gray-500'
              }`}
            >
              {i < step ? <FiCheck size={16} /> : i + 1}
            </div>
            <span className={`text-sm hidden sm:block ${i === step ? 'font-medium text-gray-900' : 'text-gray-500'}`}>
              {label}
            </span>
            {i < STEPS.length - 1 && <div className={`flex-1 h-0.5 ${i < step ? 'bg-green-500' : 'bg-gray-200'}`} />}
          </div>
        ))}
      </div>

      <div className="card">
        {/* Step 1: Campaign Information */}
        {step === 0 && (
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
              <div>
                <label className="label">Subject</label>
                <input className="input-field" value={form.subject} onChange={(e) => updateForm('subject', e.target.value)} placeholder="Email subject line" />
              </div>
            </div>
          </div>
        )}

        {/* Step 2: Choose Template */}
        {step === 1 && (
          <div className="space-y-6">
            <h2 className="text-lg font-semibold">Choose Email Template</h2>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {TEMPLATE_TYPES.map(({ id, label, icon: Icon, desc }) => (
                <button
                  key={id}
                  onClick={() => handleTemplateTypeChange(id)}
                  className={`p-4 rounded-xl border-2 text-left transition-all ${
                    templateType === id ? 'border-primary-500 bg-primary-50' : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <Icon size={24} className={templateType === id ? 'text-primary-600' : 'text-gray-400'} />
                  <p className="font-medium mt-2">{label}</p>
                  <p className="text-xs text-gray-500 mt-1">{desc}</p>
                </button>
              ))}
            </div>

            {/* Manual Template */}
            {templateType === 'manual' && (
              <div className="space-y-4">
                <div>
                  <label className="label">Subject</label>
                  <input className="input-field" value={emailContent.subject} onChange={(e) => setEmailContent((p) => ({ ...p, subject: e.target.value }))} />
                </div>
                <div>
                  <label className="label">Email Body</label>
                  <textarea className="input-field font-mono text-sm" rows={10} value={emailContent.body} onChange={(e) => setEmailContent((p) => ({ ...p, body: e.target.value }))} placeholder="Write your email content here. Use {{Name}}, {{Company}} for personalization." />
                </div>
                <div>
                  <label className="label">Closing</label>
                  <input className="input-field" value={emailContent.closing} onChange={(e) => setEmailContent((p) => ({ ...p, closing: e.target.value }))} />
                </div>
                <div>
                  <label className="label">CTA</label>
                  <input className="input-field" value={emailContent.cta} onChange={(e) => setEmailContent((p) => ({ ...p, cta: e.target.value }))} />
                </div>
              </div>
            )}

            {/* Placeholder Template */}
            {templateType === 'placeholder' && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {placeholderTemplates.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => handleSelectPlaceholderTemplate(t)}
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
                            onChange={(e) => setPlaceholderValues((p) => ({ ...p, [key]: e.target.value }))}
                            placeholder={`Sample ${key}`}
                          />
                        </div>
                      ))}
                    </div>
                    <div className="p-4 bg-gray-50 rounded-lg">
                      <p className="text-xs text-gray-500 mb-2">Live Preview</p>
                      <p className="font-medium text-sm">{renderTemplate(emailContent.subject, previewContext)}</p>
                      <p className="text-sm text-gray-600 mt-2 whitespace-pre-wrap">{renderTemplate(emailContent.body, previewContext)}</p>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* AI Template */}
            {templateType === 'ai' && (
              <div className="space-y-4">
                <div>
                  <label className="label">Additional Context (optional)</label>
                  <textarea className="input-field" rows={3} value={aiPrompt.additional_context} onChange={(e) => setAiPrompt({ additional_context: e.target.value })} placeholder="Any specific details for the AI to include..." />
                </div>
                <button onClick={handleGenerateAI} disabled={loading} className="btn-primary flex items-center gap-2">
                  {loading ? <LoadingSpinner size="sm" /> : <FiZap size={18} />}
                  Generate with AI
                </button>
                {(emailContent.subject || emailContent.body) && (
                  <div className="space-y-3">
                    <div>
                      <label className="label">Subject (editable)</label>
                      <input className="input-field" value={emailContent.subject} onChange={(e) => setEmailContent((p) => ({ ...p, subject: e.target.value }))} />
                    </div>
                    <div>
                      <label className="label">Body (editable)</label>
                      <textarea className="input-field" rows={8} value={emailContent.body} onChange={(e) => setEmailContent((p) => ({ ...p, body: e.target.value }))} />
                    </div>
                    <div>
                      <label className="label">Closing</label>
                      <input className="input-field" value={emailContent.closing} onChange={(e) => setEmailContent((p) => ({ ...p, closing: e.target.value }))} />
                    </div>
                    <div>
                      <label className="label">CTA</label>
                      <input className="input-field" value={emailContent.cta} onChange={(e) => setEmailContent((p) => ({ ...p, cta: e.target.value }))} />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Step 3: Select Recipients */}
        {step === 2 && (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold flex items-center gap-2"><FiUsers size={18} /> Select Recipients</h2>
                <p className="text-sm text-gray-500 mt-1">Choose who should receive this campaign. In mock mode, the message is routed to the configured test inbox.</p>
              </div>
              <div className="flex gap-2">
                <button onClick={selectAllRecipients} className="btn-secondary text-sm">Select All</button>
                <button onClick={clearRecipients} className="btn-secondary text-sm">Clear</button>
              </div>
            </div>

            <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
              <div className="flex items-center justify-between text-sm text-gray-600">
                <span>{selectedRecipientIds.length} selected</span>
                <span className="inline-flex items-center gap-2 text-amber-700">
                  <FiMail size={14} /> Test delivery target: {TEST_EMAIL_TARGET}
                </span>
              </div>
            </div>

            <input
              className="input-field"
              placeholder="Search recipients by name or email"
              value={recipientSearch}
              onChange={(e) => setRecipientSearch(e.target.value)}
            />

            {recipientLoading ? (
              <div className="flex justify-center py-6"><LoadingSpinner size="md" /></div>
            ) : recipientOptions.length === 0 ? (
              <div className="rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
                No recipients found yet. Upload an Excel file from the Recipients page first.
              </div>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                {recipientOptions.map((recipient) => (
                  <label key={recipient.id} className="flex cursor-pointer items-start gap-3 rounded-xl border border-gray-200 bg-white p-3 hover:border-primary-300">
                    <input
                      type="checkbox"
                      checked={selectedRecipientIds.includes(recipient.id)}
                      onChange={() => toggleRecipient(recipient.id)}
                      className="mt-1 rounded border-gray-300"
                    />
                    <div className="flex-1">
                      <div className="flex items-center justify-between gap-3">
                        <p className="font-medium text-gray-900">{recipient.name}</p>
                        <span className="text-xs text-gray-500">{recipient.company || '—'}</span>
                      </div>
                      <p className="text-sm text-gray-600">{recipient.email}</p>
                      <p className="text-xs text-gray-500">{recipient.designation || '—'} • {recipient.industry || '—'}</p>
                    </div>
                  </label>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 4: Preview & Send */}
        {step === 3 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Preview & Send</h2>
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              <p className="font-semibold">Testing mode enabled</p>
              <p className="mt-1">This demo will route the message to your configured inbox so you can show the flow live.</p>
            </div>
            <EmailPreview
              subject={renderTemplate(emailContent.subject, previewContext)}
              recipientName={previewContext.Name}
              body={renderTemplate(emailContent.body, previewContext)}
              closing={emailContent.closing}
              cta={emailContent.cta}
            />
          </div>
        )}

        {/* Navigation */}
        <div className="flex justify-between mt-8 pt-6 border-t border-gray-100">
          <button
            onClick={() => (step > 0 ? setStep(step - 1) : navigate('/campaigns'))}
            className="btn-secondary flex items-center gap-2"
          >
            <FiArrowLeft size={16} />
            {step === 0 ? 'Cancel' : 'Back'}
          </button>

          {step < 3 ? (
            <button onClick={handleNext} disabled={loading} className="btn-primary flex items-center gap-2">
              {loading ? <LoadingSpinner size="sm" /> : <>Next <FiArrowRight size={16} /></>}
            </button>
          ) : (
            <button onClick={handleSend} disabled={loading} className="btn-primary flex items-center gap-2">
              {loading ? <LoadingSpinner size="sm" /> : <>Send Campaign <FiCheck size={16} /></>}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
