import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  FiArrowLeft,
  FiEdit2,
  FiMail,
  FiUsers,
  FiEye,
  FiSend,
  FiCheckSquare,
  FiSquare,
} from 'react-icons/fi';
import { campaignService, recipientService, emailService } from '../services/services';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import StatusBadge from '../components/ui/StatusBadge';
import SearchInput from '../components/ui/SearchInput';
import Modal from '../components/ui/Modal';
import EmailPreview from '../components/EmailPreview';
import { formatDate, formatDateTime, renderTemplate, debounce } from '../utils/helpers';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'template', label: 'Template' },
  { id: 'candidates', label: 'Candidates' },
];

export default function CampaignDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [campaign, setCampaign] = useState(null);
  const [template, setTemplate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  const [recipients, setRecipients] = useState([]);
  const [recipientLoading, setRecipientLoading] = useState(false);
  const [recipientSearch, setRecipientSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState([]);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewRecipientId, setPreviewRecipientId] = useState(null);
  const [sending, setSending] = useState(false);

  const loadCampaign = useCallback(async () => {
    try {
      const [campaignRes, templateRes] = await Promise.all([
        campaignService.getById(id),
        campaignService.getTemplate(id).catch(() => null),
      ]);
      setCampaign(campaignRes.data);
      setTemplate(templateRes?.data ?? null);
    } catch {
      toast.error('Failed to load campaign details');
    } finally {
      setLoading(false);
    }
  }, [id, toast]);

  useEffect(() => {
    loadCampaign();
  }, [loadCampaign]);

  useEffect(() => {
    if (activeTab !== 'candidates') return;

    const loadRecipients = async () => {
      setRecipientLoading(true);
      try {
        const { data } = await recipientService.getAll({ page: 1, page_size: 100, search: recipientSearch });
        setRecipients(data.items);
      } catch {
        toast.error('Failed to load candidates');
      } finally {
        setRecipientLoading(false);
      }
    };

    loadRecipients();
  }, [activeTab, recipientSearch, toast]);

  const debouncedSearch = useCallback(debounce((val) => setRecipientSearch(val), 400), []);

  const toggleRecipient = (recipientId) => {
    setSelectedIds((prev) =>
      prev.includes(recipientId) ? prev.filter((rid) => rid !== recipientId) : [...prev, recipientId]
    );
  };

  const selectAllRecipients = () => setSelectedIds(recipients.map((r) => r.id));
  const clearSelection = () => setSelectedIds([]);

  const selectedRecipients = recipients.filter((r) => selectedIds.includes(r.id));

  useEffect(() => {
    if (selectedRecipients.length === 0) {
      setPreviewRecipientId(null);
    } else if (!selectedRecipients.some((r) => r.id === previewRecipientId)) {
      setPreviewRecipientId(selectedRecipients[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIds, recipients]);

  const previewRecipient = recipients.find((r) => r.id === previewRecipientId);
  const previewContext = previewRecipient
    ? {
        Name: previewRecipient.name,
        Company: previewRecipient.company || '—',
        Designation: previewRecipient.designation || '—',
        Industry: previewRecipient.industry || '—',
        Email: previewRecipient.email,
      }
    : null;

  const handleOpenPreview = () => {
    if (!template) {
      toast.error('This campaign has no template yet. Add one from Edit Campaign.');
      return;
    }
    if (selectedIds.length === 0) {
      toast.error('Select at least one candidate first');
      return;
    }
    setPreviewOpen(true);
  };

  const handleSend = async () => {
    setSending(true);
    try {
      const { data } = await emailService.send({
        campaign_id: campaign.id,
        subject: template.subject,
        body: template.body + (template.closing ? `\n\n${template.closing}` : ''),
        recipient_ids: selectedIds,
      });
      toast.success(`Send complete. Sent: ${data.sent}, Failed: ${data.failed}, Pending: ${data.pending}`);
      setPreviewOpen(false);
      clearSelection();
      loadCampaign();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send emails');
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!campaign) {
    return null;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/campaigns')} className="btn-secondary flex items-center gap-2">
            <FiArrowLeft size={16} /> Back
          </button>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl font-bold text-gray-900">{campaign.campaign_name}</h1>
              <StatusBadge status={campaign.status} />
            </div>
            <p className="text-gray-500 mt-1">{campaign.campaign_id}</p>
          </div>
        </div>
        <button onClick={() => navigate(`/campaigns/${id}/edit`)} className="btn-primary flex items-center gap-2">
          <FiEdit2 size={16} /> Edit Campaign
        </button>
      </div>

      {/* Tabs */}
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {activeTab === 'overview' && (
            <div className="card">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Campaign Overview</h2>
                <StatusBadge status={campaign.status} />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 text-sm">
                <div>
                  <p className="text-gray-500">Owner</p>
                  <p className="font-medium text-gray-900">{campaign.owner}</p>
                </div>
                <div>
                  <p className="text-gray-500">Department</p>
                  <p className="font-medium text-gray-900">{campaign.department || '—'}</p>
                </div>
                <div>
                  <p className="text-gray-500">Target Audience</p>
                  <p className="font-medium text-gray-900">{campaign.target_audience || '—'}</p>
                </div>
                <div>
                  <p className="text-gray-500">Created</p>
                  <p className="font-medium text-gray-900">{formatDate(campaign.created_at)}</p>
                </div>
              </div>
              {campaign.description && (
                <div className="mt-4">
                  <p className="text-gray-500">Description</p>
                  <p className="text-gray-700 mt-1">{campaign.description}</p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'template' && (
            <div className="card">
              <h2 className="text-lg font-semibold">Email Template</h2>
              {template ? (
                <div className="mt-4 space-y-3 text-sm">
                  <div>
                    <p className="text-gray-500">Type</p>
                    <p className="font-medium text-gray-900 capitalize">{template.type}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Subject</p>
                    <p className="font-medium text-gray-900">{template.subject}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Body</p>
                    <p className="text-gray-700 whitespace-pre-wrap">{template.body}</p>
                  </div>
                  {template.closing && (
                    <div>
                      <p className="text-gray-500">Closing</p>
                      <p className="text-gray-700 whitespace-pre-wrap">{template.closing}</p>
                    </div>
                  )}
                  {template.cta && (
                    <div>
                      <p className="text-gray-500">CTA</p>
                      <p className="text-gray-700">{template.cta}</p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="mt-4 space-y-3">
                  <p className="text-sm text-gray-500">No template has been saved for this campaign yet.</p>
                  <button onClick={() => navigate(`/campaigns/${id}/edit`)} className="btn-secondary text-sm">
                    Add a template
                  </button>
                </div>
              )}
            </div>
          )}

          {activeTab === 'candidates' && (
            <div className="card">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                  <h2 className="text-lg font-semibold flex items-center gap-2">
                    <FiUsers size={18} /> Candidates
                  </h2>
                  <p className="text-sm text-gray-500 mt-1">
                    Select who should receive this campaign, then preview and send.
                  </p>
                </div>
                <button
                  onClick={handleOpenPreview}
                  disabled={selectedIds.length === 0}
                  className="btn-primary flex items-center gap-2 disabled:opacity-50"
                >
                  <FiEye size={16} /> Preview & Send
                </button>
              </div>

              {!template && (
                <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                  This campaign doesn't have an email template yet.{' '}
                  <button onClick={() => navigate(`/campaigns/${id}/edit`)} className="underline font-medium">
                    Add one
                  </button>{' '}
                  before sending.
                </div>
              )}

              <div className="flex flex-wrap items-center gap-3 mt-4">
                <SearchInput
                  onChange={debouncedSearch}
                  placeholder="Search candidates by name or email..."
                  className="flex-1 min-w-[200px]"
                />
                <button onClick={selectAllRecipients} className="btn-secondary text-sm flex items-center gap-1">
                  <FiCheckSquare size={14} /> Select All
                </button>
                <button onClick={clearSelection} className="btn-secondary text-sm flex items-center gap-1">
                  <FiSquare size={14} /> Clear
                </button>
              </div>

              <p className="text-sm text-gray-600 mt-3">{selectedIds.length} selected</p>

              {recipientLoading ? (
                <div className="flex justify-center py-6">
                  <LoadingSpinner size="md" />
                </div>
              ) : recipients.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 mt-3">
                  No candidates found. Upload recipients from the Recipients page first.
                </div>
              ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto pr-1 mt-3">
                  {recipients.map((r) => (
                    <label
                      key={r.id}
                      className="flex cursor-pointer items-start gap-3 rounded-xl border border-gray-200 bg-white p-3 hover:border-primary-300"
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(r.id)}
                        onChange={() => toggleRecipient(r.id)}
                        className="mt-1 rounded border-gray-300"
                      />
                      <div className="flex-1">
                        <div className="flex items-center justify-between gap-3">
                          <p className="font-medium text-gray-900">{r.name}</p>
                          <span className="text-xs text-gray-500">{r.company || '—'}</span>
                        </div>
                        <p className="text-sm text-gray-600">{r.email}</p>
                        <p className="text-xs text-gray-500">
                          {r.designation || '—'} • {r.industry || '—'}
                        </p>
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="space-y-6">
          <div className="card">
            <h2 className="text-lg font-semibold">Statistics</h2>
            <div className="space-y-3 mt-4 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-gray-500">Emails Sent</span>
                <span className="font-medium text-gray-900">{campaign.emails_sent}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-500">Last Updated</span>
                <span className="font-medium text-gray-900">{formatDateTime(campaign.created_at)}</span>
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <FiMail size={18} /> Next Steps
            </h2>
            <ul className="mt-4 space-y-2 text-sm text-gray-600">
              <li>• Review the campaign details in the Overview tab.</li>
              <li>• Confirm the email content in the Template tab.</li>
              <li>• Select candidates and preview & send from the Candidates tab.</li>
            </ul>
          </div>
        </div>
      </div>

      <Modal isOpen={previewOpen} onClose={() => setPreviewOpen(false)} title="Preview & Send" size="lg">
        {template && previewContext && (
          <div className="space-y-4">
            {selectedRecipients.length > 1 && (
              <div>
                <label className="label">Preview as</label>
                <select
                  className="input-field"
                  value={previewRecipientId ?? ''}
                  onChange={(e) => setPreviewRecipientId(Number(e.target.value))}
                >
                  {selectedRecipients.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} ({r.email})
                    </option>
                  ))}
                </select>
              </div>
            )}
            <EmailPreview
              subject={renderTemplate(template.subject, previewContext)}
              recipientName={previewContext.Name}
              body={renderTemplate(template.body, previewContext)}
              closing={template.closing}
              cta={template.cta}
            />
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600">
              Sending to {selectedIds.length} candidate{selectedIds.length !== 1 ? 's' : ''}
            </div>
            <div className="flex justify-end gap-3">
              <button className="btn-secondary" onClick={() => setPreviewOpen(false)} disabled={sending}>
                Cancel
              </button>
              <button className="btn-primary flex items-center gap-2" onClick={handleSend} disabled={sending}>
                {sending ? (
                  <LoadingSpinner size="sm" />
                ) : (
                  <>
                    <FiSend size={16} /> Send Campaign
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
