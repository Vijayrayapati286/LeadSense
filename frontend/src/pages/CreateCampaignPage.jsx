import { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { FiArrowLeft, FiCheck, FiCheckSquare, FiSave, FiBookOpen } from 'react-icons/fi';
import { campaignService, templateService, recipientService, mailerService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { useContactSearch } from '../hooks/useContactSearch';
import { generateCampaignId, extractPlaceholders, toDatetimeLocalValue } from '../utils/helpers';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import SearchInput from '../components/ui/SearchInput';
import Pagination from '../components/ui/Pagination';
import StatusBadge from '../components/ui/StatusBadge';
import FilterBuilder from '../components/FilterBuilder';
import TemplateEditor from '../components/TemplateEditor';
import Modal from '../components/ui/Modal';

const TABS = [
  { id: 'campaign', label: 'Campaign' },
  { id: 'template', label: 'Template' },
  { id: 'contacts', label: 'Prospects' },
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
    subject: '',
    scheduled_at: '',
    use_recipient_timezone: false,
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

  // Contacts tab — same filter-builder search used on the Contacts page and
  // the campaign detail page's Contacts tab.
  const {
    setSearch, sortBy, setSortBy, sortOrder, setSortOrder,
    activeFieldKeys, filterValues, distinctOptions, distinctLoading,
    results, total, page, setPage, loading: contactsLoading,
    groups, tags, campaigns, activeParams,
    handleAddField, handleRemoveField, handleValueChange, clearAllFilters,
  } = useContactSearch({ toast });
  const [selectedIds, setSelectedIds] = useState([]);
  const [selectingAll, setSelectingAll] = useState(false);

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
          scheduled_at: toDatetimeLocalValue(data.scheduled_at),
          use_recipient_timezone: data.use_recipient_timezone || false,
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

  const debouncedSearch = useCallback((val) => { setSearch(val); setPage(1); }, [setSearch, setPage]);

  const toggleContact = (contactId) => {
    setSelectedIds((prev) =>
      prev.includes(contactId) ? prev.filter((cid) => cid !== contactId) : [...prev, contactId]
    );
  };

  const handleSelectAllMatching = async () => {
    setSelectingAll(true);
    try {
      const { data } = await recipientService.searchIds({ ...activeParams, exclude_suppressed: true });
      setSelectedIds(data.ids);
      toast.success(`Selected all ${data.total} matching prospect(s)`);
    } catch {
      toast.error('Failed to select all matching prospects');
    } finally {
      setSelectingAll(false);
    }
  };

  const previewContext = {
    Name: placeholderValues.Name || 'John Doe',
    Company: placeholderValues.Company || 'Acme Corp',
    Designation: placeholderValues.Designation || 'CEO',
    Industry: placeholderValues.Industry || 'Technology',
    Email: 'john@acme.com',
  };

  const handleSubmit = async () => {
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

    setLoading(true);
    try {
      const payload = {
        ...form,
        scheduled_at: form.scheduled_at ? new Date(form.scheduled_at).toISOString() : null,
      };
      const { data } = isEditMode
        ? await campaignService.update(campaignId, payload)
        : await campaignService.create(payload);
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
      navigate(`/campaigns/${newCampaignId}`, {
        state: selectedIds.length > 0 ? { preselectedContactIds: selectedIds } : undefined,
      });
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
          <p className="text-gray-500 mt-1">Move freely between tabs — nothing is saved until you submit.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => navigate('/campaigns')} className="btn-secondary flex items-center gap-2">
            <FiArrowLeft size={16} /> Cancel
          </button>
          <button onClick={handleSubmit} disabled={loading} className="btn-primary flex items-center gap-2">
            {loading ? <LoadingSpinner size="sm" /> : <>{isEditMode ? 'Save Changes' : 'Create Campaign'} <FiCheck size={16} /></>}
          </button>
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
              <div>
                <label className="label">Subject</label>
                <input className="input-field" value={form.subject} onChange={(e) => updateForm('subject', e.target.value)} placeholder="Email subject line" />
              </div>
            </div>

            <div className="pt-2 border-t border-gray-100 space-y-3">
              <h3 className="text-sm font-semibold text-gray-700">Scheduling</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="label">Schedule For (optional)</label>
                  <input
                    type="datetime-local"
                    className="input-field"
                    value={form.scheduled_at}
                    onChange={(e) => updateForm('scheduled_at', e.target.value)}
                  />
                  <p className="text-xs text-gray-400 mt-1">Leave blank to send as soon as you hit Send Campaign.</p>
                </div>
                <div className="flex items-end pb-1">
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.use_recipient_timezone}
                      onChange={(e) => updateForm('use_recipient_timezone', e.target.checked)}
                      className="rounded border-gray-300"
                    />
                    Send at each prospect's local business hours (9am–6pm)
                  </label>
                </div>
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

        {activeTab === 'contacts' && (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h2 className="text-lg font-semibold">Prospects</h2>
                <p className="text-sm text-gray-500 mt-1">
                  Optionally pick who this campaign is for now — you'll confirm and send from the campaign page after it's created.
                </p>
              </div>
              <button onClick={handleSubmit} disabled={loading} className="btn-primary flex items-center gap-2 flex-shrink-0">
                {loading ? <LoadingSpinner size="sm" /> : <>{isEditMode ? 'Save Changes' : 'Create Campaign'} <FiCheck size={16} /></>}
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <SearchInput
                onChange={debouncedSearch}
                placeholder="Quick search (name, email, company)..."
                className="flex-1 min-w-[200px]"
              />
              <select className="input-field w-auto" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                <option value="name">Sort: Name</option>
                <option value="email">Sort: Email</option>
                <option value="company">Sort: Company</option>
                <option value="designation">Sort: Designation</option>
                <option value="industry">Sort: Industry</option>
              </select>
              <select className="input-field w-auto" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}>
                <option value="asc">Ascending</option>
                <option value="desc">Descending</option>
              </select>
            </div>

            <FilterBuilder
              activeFieldKeys={activeFieldKeys}
              values={filterValues}
              onAddField={handleAddField}
              onRemoveField={handleRemoveField}
              onValueChange={handleValueChange}
              distinctOptions={distinctOptions}
              distinctLoading={distinctLoading}
              groups={groups}
              tags={tags}
              campaigns={campaigns}
            />

            <div className="flex flex-wrap items-center gap-2">
              <button onClick={clearAllFilters} className="btn-secondary text-sm">Clear All</button>
              <button onClick={() => setSelectedIds([])} className="btn-secondary text-sm">Clear Selection</button>
              <button onClick={handleSelectAllMatching} disabled={selectingAll || total === 0} className="btn-secondary text-sm flex items-center gap-1 ml-auto">
                {selectingAll ? <LoadingSpinner size="sm" /> : <FiCheckSquare size={14} />} Select All {total} Matching
              </button>
            </div>

            <p className="text-sm text-gray-600">
              <span className="font-semibold text-gray-900">{total}</span> matching prospect{total !== 1 ? 's' : ''}
              {selectedIds.length > 0 && <span className="ml-2 text-primary-600 font-medium">({selectedIds.length} selected)</span>}
            </p>

            {contactsLoading ? (
              <div className="flex justify-center py-6"><LoadingSpinner size="md" /></div>
            ) : results.length === 0 ? (
              <div className="rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
                No prospects found. Upload prospects from the Prospects page or adjust your filters.
              </div>
            ) : (
              <>
                <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                  {results.map((r) => (
                    <label
                      key={r.id}
                      className={`flex items-start gap-3 rounded-xl border p-3 ${
                        r.is_suppressed
                          ? 'border-gray-200 bg-gray-50 cursor-not-allowed'
                          : 'cursor-pointer border-gray-200 bg-white hover:border-primary-300'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={!r.is_suppressed && selectedIds.includes(r.id)}
                        onChange={() => toggleContact(r.id)}
                        disabled={r.is_suppressed}
                        title={r.is_suppressed ? 'Blacklisted prospects cannot be selected' : undefined}
                        className="mt-1 rounded border-gray-300 disabled:opacity-40 disabled:cursor-not-allowed"
                      />
                      <div className="flex-1">
                        <div className="flex items-center justify-between gap-3">
                          <p className={`font-medium ${r.is_suppressed ? 'text-gray-400' : 'text-gray-900'}`}>{r.name}</p>
                          <span className="text-xs text-gray-500">{r.company || '—'}</span>
                        </div>
                        <p className={`text-sm ${r.is_suppressed ? 'text-gray-400' : 'text-gray-600'}`}>{r.email}</p>
                        <p className="text-xs text-gray-500">
                          {r.designation || '—'} • {r.industry || '—'}
                        </p>
                        {r.is_suppressed && (
                          <div className="mt-1"><StatusBadge status={r.suppression_reason} /></div>
                        )}
                      </div>
                    </label>
                  ))}
                </div>
                <Pagination page={page} pageSize={10} total={total} onPageChange={setPage} />
              </>
            )}
          </div>
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
    </div>
  );
}
