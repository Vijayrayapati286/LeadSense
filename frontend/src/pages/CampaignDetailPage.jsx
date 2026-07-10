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
  FiClock,
  FiPlus,
  FiTrash2,
  FiBarChart2,
} from 'react-icons/fi';
import {
  campaignService,
  recipientService,
  sequenceService,
  emailService,
} from '../services/services';
import { useToast } from '../hooks/useToast';
import { useContactSearch } from '../hooks/useContactSearch';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import StatusBadge from '../components/ui/StatusBadge';
import SearchInput from '../components/ui/SearchInput';
import Pagination from '../components/ui/Pagination';
import Modal from '../components/ui/Modal';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import EmailPreview from '../components/EmailPreview';
import FilterBuilder from '../components/FilterBuilder';
import { formatDate, formatDateTime, renderTemplate, debounce } from '../utils/helpers';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'template', label: 'Template' },
  { id: 'sequence', label: 'Follow-up Sequence' },
  { id: 'candidates', label: 'Contacts' },
  { id: 'tracking', label: 'Tracking' },
];

const EMPTY_STAGE_FORM = { delay_value: 3, delay_unit: 'days', subject: '', body: '', closing: '', cta: '' };

export default function CampaignDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [campaign, setCampaign] = useState(null);
  const [template, setTemplate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  const {
    search, setSearch, sortBy, setSortBy, sortOrder, setSortOrder,
    activeFieldKeys, filterValues, distinctOptions, distinctLoading,
    results, total, page, setPage, loading: contactsLoading,
    groups, tags, campaigns, activeParams,
    handleAddField, handleRemoveField, handleValueChange, clearAllFilters,
  } = useContactSearch({ toast });

  const [selectedIds, setSelectedIds] = useState([]);
  const [selectingAll, setSelectingAll] = useState(false);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewRecipientId, setPreviewRecipientId] = useState(null);
  const [sending, setSending] = useState(false);

  const [stages, setStages] = useState([]);
  const [stageLoading, setStageLoading] = useState(false);
  const [stageForm, setStageForm] = useState(EMPTY_STAGE_FORM);
  const [addingStage, setAddingStage] = useState(false);
  const [deletingStageId, setDeletingStageId] = useState(null);

  const [tracking, setTracking] = useState([]);
  const [trackingLoading, setTrackingLoading] = useState(false);

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

  const loadStages = useCallback(async () => {
    setStageLoading(true);
    try {
      const { data } = await sequenceService.getAll(id);
      setStages(data);
    } catch {
      toast.error('Failed to load follow-up sequence');
    } finally {
      setStageLoading(false);
    }
  }, [id, toast]);

  useEffect(() => {
    if (activeTab === 'sequence') loadStages();
  }, [activeTab, loadStages]);

  const loadTracking = useCallback(async () => {
    setTrackingLoading(true);
    try {
      const { data } = await campaignService.getRecipients(id);
      setTracking(data.items);
    } catch {
      toast.error('Failed to load tracking data');
    } finally {
      setTrackingLoading(false);
    }
  }, [id, toast]);

  useEffect(() => {
    if (activeTab === 'tracking') loadTracking();
  }, [activeTab, loadTracking]);

  const handleAddStage = async () => {
    if (!stageForm.subject || !stageForm.body) {
      toast.error('Subject and body are required');
      return;
    }
    setAddingStage(true);
    try {
      const nextOrder = stages.length > 0 ? Math.max(...stages.map((s) => s.stage_order)) + 1 : 1;
      await sequenceService.create(id, { ...stageForm, stage_order: nextOrder });
      toast.success('Follow-up stage added');
      setStageForm(EMPTY_STAGE_FORM);
      loadStages();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to add stage');
    } finally {
      setAddingStage(false);
    }
  };

  const handleDeleteStage = async () => {
    try {
      await sequenceService.delete(deletingStageId);
      toast.success('Stage removed');
      loadStages();
    } catch {
      toast.error('Failed to remove stage');
    }
  };

  const debouncedSearch = useCallback(debounce((val) => { setSearch(val); setPage(1); }, 400), []);

  const toggleRecipient = (recipientId) => {
    setSelectedIds((prev) =>
      prev.includes(recipientId) ? prev.filter((rid) => rid !== recipientId) : [...prev, recipientId]
    );
  };

  const clearSelection = () => setSelectedIds([]);

  const handleSelectAllMatching = async () => {
    setSelectingAll(true);
    try {
      const { data } = await recipientService.searchIds(activeParams);
      setSelectedIds(data.ids);
      toast.success(`Selected all ${data.total} matching contact(s)`);
    } catch {
      toast.error('Failed to select all matching contacts');
    } finally {
      setSelectingAll(false);
    }
  };

  const selectedRecipients = results.filter((r) => selectedIds.includes(r.id));

  useEffect(() => {
    if (selectedRecipients.length === 0) {
      setPreviewRecipientId(null);
    } else if (!selectedRecipients.some((r) => r.id === previewRecipientId)) {
      setPreviewRecipientId(selectedRecipients[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIds, results]);

  const previewRecipient = results.find((r) => r.id === previewRecipientId);
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
      toast.error('Select at least one contact first');
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

          {activeTab === 'sequence' && (
            <div className="card">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <FiClock size={18} /> Follow-up Sequence
              </h2>
              <p className="text-sm text-gray-500 mt-1">
                Stage 0 is the email on the Template tab, sent immediately. Add follow-up stages below —
                each fires automatically after the configured delay, as long as the contact hasn't
                replied, bounced, or been suppressed.
              </p>

              {stageLoading ? (
                <div className="flex justify-center py-6"><LoadingSpinner size="md" /></div>
              ) : (
                <div className="mt-4 space-y-3">
                  {stages.map((s) => (
                    <div key={s.id} className="rounded-xl border border-gray-200 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-gray-900">
                            Stage {s.stage_order} — after {s.delay_value} {s.delay_unit}
                          </p>
                          <p className="text-sm text-gray-600 mt-1">{s.subject}</p>
                          <p className="text-xs text-gray-500 mt-1 whitespace-pre-wrap">{s.body}</p>
                        </div>
                        <button
                          onClick={() => setDeletingStageId(s.id)}
                          className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-600"
                        >
                          <FiTrash2 size={15} />
                        </button>
                      </div>
                    </div>
                  ))}
                  {stages.length === 0 && (
                    <p className="text-sm text-gray-400">No follow-up stages yet — this campaign only sends the initial email.</p>
                  )}
                </div>
              )}

              <div className="mt-6 pt-4 border-t border-gray-100 space-y-3">
                <p className="text-sm font-medium text-gray-700">Add a follow-up stage</p>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-500">Send after</span>
                  <input
                    type="number"
                    min={1}
                    className="input-field w-20"
                    value={stageForm.delay_value}
                    onChange={(e) => setStageForm((p) => ({ ...p, delay_value: Number(e.target.value) }))}
                  />
                  <select
                    className="input-field w-auto"
                    value={stageForm.delay_unit}
                    onChange={(e) => setStageForm((p) => ({ ...p, delay_unit: e.target.value }))}
                  >
                    <option value="minutes">Minutes</option>
                    <option value="hours">Hours</option>
                    <option value="days">Days</option>
                  </select>
                </div>
                <input
                  className="input-field"
                  placeholder="Subject"
                  value={stageForm.subject}
                  onChange={(e) => setStageForm((p) => ({ ...p, subject: e.target.value }))}
                />
                <textarea
                  className="input-field font-mono text-sm"
                  rows={5}
                  placeholder="Body — use {{Name}}, {{Company}} etc for personalization"
                  value={stageForm.body}
                  onChange={(e) => setStageForm((p) => ({ ...p, body: e.target.value }))}
                />
                <input
                  className="input-field"
                  placeholder="Closing (optional)"
                  value={stageForm.closing}
                  onChange={(e) => setStageForm((p) => ({ ...p, closing: e.target.value }))}
                />
                <button onClick={handleAddStage} disabled={addingStage} className="btn-primary flex items-center gap-2">
                  {addingStage ? <LoadingSpinner size="sm" /> : <FiPlus size={16} />} Add Stage
                </button>
              </div>
            </div>
          )}

          {activeTab === 'candidates' && (
            <div className="card">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                  <h2 className="text-lg font-semibold flex items-center gap-2">
                    <FiUsers size={18} /> Contacts
                  </h2>
                  <p className="text-sm text-gray-500 mt-1">
                    Search, filter, and select who should receive this campaign, then preview and send.
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

              <div className="mt-4 space-y-4">
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
                  <button onClick={clearSelection} className="btn-secondary text-sm">Clear Selection</button>
                  <button onClick={handleSelectAllMatching} disabled={selectingAll || total === 0} className="btn-secondary text-sm flex items-center gap-1 ml-auto">
                    {selectingAll ? <LoadingSpinner size="sm" /> : <FiCheckSquare size={14} />} Select All {total} Matching
                  </button>
                </div>
              </div>

              <p className="text-sm text-gray-600 mt-3">
                <span className="font-semibold text-gray-900">{total}</span> matching contact{total !== 1 ? 's' : ''}
                {selectedIds.length > 0 && <span className="ml-2 text-primary-600 font-medium">({selectedIds.length} selected)</span>}
              </p>

              {contactsLoading ? (
                <div className="flex justify-center py-6">
                  <LoadingSpinner size="md" />
                </div>
              ) : results.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 mt-3">
                  No contacts found. Upload contacts from the Contacts page or adjust your filters.
                </div>
              ) : (
                <>
                  <div className="space-y-2 max-h-96 overflow-y-auto pr-1 mt-3">
                    {results.map((r) => (
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
                  <div className="mt-2">
                    <Pagination page={page} pageSize={10} total={total} onPageChange={setPage} />
                  </div>
                </>
              )}
            </div>
          )}

          {activeTab === 'tracking' && (
            <div className="card overflow-hidden">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <FiBarChart2 size={18} /> Contact Tracking
              </h2>
              <p className="text-sm text-gray-500 mt-1">
                Per-contact delivery status for this campaign, updated as emails are sent and follow-ups fire.
              </p>

              {trackingLoading ? (
                <div className="flex justify-center py-6"><LoadingSpinner size="md" /></div>
              ) : tracking.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 mt-4">
                  No sends recorded yet for this campaign.
                </div>
              ) : (
                <div className="overflow-x-auto mt-4 -mx-6">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-y">
                      <tr className="text-left text-gray-500">
                        <th className="px-6 py-3 font-medium">Name</th>
                        <th className="px-4 py-3 font-medium">Email</th>
                        <th className="px-4 py-3 font-medium">Company</th>
                        <th className="px-4 py-3 font-medium">Status</th>
                        <th className="px-4 py-3 font-medium">Stage</th>
                        <th className="px-4 py-3 font-medium">Last Sent</th>
                        <th className="px-6 py-3 font-medium">Replied At</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tracking.map((t) => (
                        <tr key={t.id} className="border-b border-gray-50">
                          <td className="px-6 py-3 font-medium text-gray-900">{t.recipient_name}</td>
                          <td className="px-4 py-3 text-gray-600">{t.recipient_email}</td>
                          <td className="px-4 py-3 text-gray-600">{t.recipient_company || '—'}</td>
                          <td className="px-4 py-3"><StatusBadge status={t.status} /></td>
                          <td className="px-4 py-3 text-gray-600">{t.current_stage}</td>
                          <td className="px-4 py-3 text-gray-600">{formatDateTime(t.last_sent_at)}</td>
                          <td className="px-6 py-3 text-gray-600">{formatDateTime(t.replied_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
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
              <li>• Select contacts and preview & send from the Contacts tab.</li>
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
              Sending to {selectedIds.length} contact{selectedIds.length !== 1 ? 's' : ''}
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

      <ConfirmDialog
        isOpen={!!deletingStageId}
        onClose={() => setDeletingStageId(null)}
        onConfirm={handleDeleteStage}
        title="Remove Follow-up Stage"
        message="Remove this follow-up stage? Contacts already scheduled for it will no longer receive it."
        confirmText="Remove"
      />
    </div>
  );
}
