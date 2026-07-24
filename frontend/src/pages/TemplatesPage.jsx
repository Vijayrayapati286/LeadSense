import { useEffect, useState } from 'react';
import { FiPlus, FiEdit2, FiTrash2, FiBookOpen } from 'react-icons/fi';
import { mailerService, templateService } from '../services/services';
import { useToast } from '../hooks/useToast';
import { extractPlaceholders } from '../utils/helpers';
import { buildSamplePreviewContext } from '../utils/mergeFields';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import SearchInput from '../components/ui/SearchInput';
import Modal from '../components/ui/Modal';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import TemplateEditor from '../components/TemplateEditor';

const EMPTY_CONTENT = { subject: '', body: '', closing: '', cta: '' };

export default function TemplatesPage() {
  const toast = useToast();
  const [mailers, setMailers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingMailer, setEditingMailer] = useState(null);
  const [mailerName, setMailerName] = useState('');
  const [templateType, setTemplateType] = useState('manual');
  const [emailContent, setEmailContent] = useState(EMPTY_CONTENT);
  const [placeholderTemplates, setPlaceholderTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [placeholderValues, setPlaceholderValues] = useState({});
  const [aiPrompt, setAiPrompt] = useState({ additional_context: '' });
  const [aiLoading, setAiLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState(null);

  useEffect(() => {
    loadMailers();
  }, [search]);

  const loadMailers = async () => {
    setLoading(true);
    try {
      const { data } = await mailerService.getAll({ search });
      setMailers(data);
    } catch {
      toast.error('Failed to load mailers');
    } finally {
      setLoading(false);
    }
  };

  const loadPlaceholderTemplates = async () => {
    if (placeholderTemplates.length > 0) return;
    try {
      const { data } = await templateService.getPlaceholderTemplates();
      setPlaceholderTemplates(data);
    } catch {
      toast.error('Failed to load placeholder templates');
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
        campaign_name: mailerName || 'Sample Campaign',
        target_audience: 'B2B Decision Makers',
        additional_context: aiPrompt.additional_context,
      });
      setEmailContent({ subject: data.subject, body: data.body, closing: data.closing, cta: data.cta });
      if (data.is_mock) toast.info('Using mock AI response (OpenAI not configured)');
      else toast.success('AI email generated successfully');
    } catch {
      toast.error('Failed to generate AI template');
    } finally {
      setAiLoading(false);
    }
  };

  const previewContext = buildSamplePreviewContext(placeholderValues);

  const openNewMailer = () => {
    setEditingMailer(null);
    setMailerName('');
    setTemplateType('manual');
    setEmailContent(EMPTY_CONTENT);
    setSelectedTemplate(null);
    setPlaceholderValues({});
    setAiPrompt({ additional_context: '' });
    setEditorOpen(true);
  };

  const openEditMailer = (mailer) => {
    setEditingMailer(mailer);
    setMailerName(mailer.name);
    setTemplateType(mailer.type);
    setEmailContent({
      subject: mailer.subject,
      body: mailer.body,
      closing: mailer.closing || '',
      cta: mailer.cta || '',
    });
    setSelectedTemplate(null);
    setPlaceholderValues({});
    setAiPrompt({ additional_context: '' });
    setEditorOpen(true);
  };

  const handleSaveMailer = async () => {
    if (!mailerName.trim()) {
      toast.error('Enter a name for this mailer');
      return;
    }
    if (!emailContent.subject.trim() || !emailContent.body.trim()) {
      toast.error('Subject and body are required');
      return;
    }
    setSaving(true);
    const payload = {
      name: mailerName.trim(),
      type: templateType,
      subject: emailContent.subject,
      body: emailContent.body,
      closing: emailContent.closing,
      cta: emailContent.cta,
    };
    try {
      if (editingMailer) {
        await mailerService.update(editingMailer.id, payload);
        toast.success('Mailer updated');
      } else {
        await mailerService.create(payload);
        toast.success('Mailer saved');
      }
      setEditorOpen(false);
      loadMailers();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save mailer');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await mailerService.delete(deleteTarget.id);
      toast.success('Mailer deleted');
      loadMailers();
    } catch {
      toast.error('Failed to delete mailer');
    } finally {
      setDeleteTarget(null);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Mailers</h1>
          <p className="text-gray-500 mt-1">Your reusable email templates — save once, find and reuse across campaigns.</p>
        </div>
        <button onClick={openNewMailer} className="btn-primary flex items-center gap-2">
          <FiPlus size={16} /> New Mailer
        </button>
      </div>

      <SearchInput value={search} onChange={setSearch} placeholder="Search mailers by name..." className="max-w-md" />

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <LoadingSpinner size="lg" />
        </div>
      ) : mailers.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500">
          {search ? 'No mailers match your search.' : 'No mailers saved yet. Create one to get started.'}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {mailers.map((m) => (
            <div key={m.id} className="card hover:shadow-md transition-shadow">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <FiBookOpen className="text-primary-500 flex-shrink-0" size={18} />
                  <p className="font-medium text-gray-900 truncate">{m.name}</p>
                </div>
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded flex-shrink-0 capitalize">{m.type}</span>
              </div>
              <p className="text-sm text-gray-500 mt-2 truncate">{m.subject}</p>
              <p className="text-xs text-gray-400 mt-1">{new Date(m.created_at).toLocaleDateString()}</p>
              <div className="flex items-center gap-2 mt-4">
                <button onClick={() => openEditMailer(m)} className="btn-secondary text-sm flex items-center gap-1 flex-1 justify-center">
                  <FiEdit2 size={14} /> Edit
                </button>
                <button onClick={() => setDeleteTarget(m)} className="btn-secondary text-sm text-red-600 hover:bg-red-50 flex items-center gap-1">
                  <FiTrash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal isOpen={editorOpen} onClose={() => setEditorOpen(false)} title={editingMailer ? 'Edit Mailer' : 'New Mailer'} size="xl">
        <div className="space-y-6">
          <div>
            <label className="label">Mailer Name *</label>
            <input
              className="input-field"
              value={mailerName}
              onChange={(e) => setMailerName(e.target.value)}
              placeholder="e.g. Cold Outreach - Tech Decision Makers"
              autoFocus
            />
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

          <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
            <button onClick={() => setEditorOpen(false)} className="btn-secondary">Cancel</button>
            <button onClick={handleSaveMailer} disabled={saving} className="btn-primary flex items-center gap-2">
              {saving ? <LoadingSpinner size="sm" /> : (editingMailer ? 'Save Changes' : 'Save Mailer')}
            </button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete Mailer"
        message={`Delete "${deleteTarget?.name}"? This cannot be undone.`}
        confirmText="Delete"
      />
    </div>
  );
}
