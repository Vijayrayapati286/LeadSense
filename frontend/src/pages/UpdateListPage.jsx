import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams, useNavigate, useLocation } from 'react-router-dom';
import {
  FiArrowLeft,
  FiCheckCircle,
  FiCalendar,
  FiSend,
  FiX,
  FiArrowRight,
} from 'react-icons/fi';
import { campaignService, recipientService, sequenceService } from '../services/services';
import { useToast } from '../hooks/useToast';
import StatusBadge from '../components/ui/StatusBadge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import SearchInput from '../components/ui/SearchInput';
import PageShell from '../components/ui/PageShell';
import PageHeader from '../components/ui/PageHeader';
import SurfaceCard from '../components/ui/SurfaceCard';
import CampaignCard from '../components/campaigns/CampaignCard';
import Button from '../components/ui/Button';
import Modal from '../components/ui/Modal';
import { debounce, formatDateTime } from '../utils/helpers';

function defaultScheduleValue() {
  const d = new Date(Date.now() + 5 * 60 * 1000);
  d.setSeconds(0, 0);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * Update list:
 * 1) Campaign cards (search by campaign name/ID OR recipient email/name).
 * 2) Open campaign → full recipient table with checkboxes for replied + schedule.
 */
export default function UpdateListPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get('campaign')
    ? Number(searchParams.get('campaign'))
    : null;

  const [campaigns, setCampaigns] = useState([]);
  const [campaignLoading, setCampaignLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [emailMatchedCampaignIds, setEmailMatchedCampaignIds] = useState(null);
  const [searchingRecipients, setSearchingRecipients] = useState(false);

  const [emailRows, setEmailRows] = useState([]);
  const [emailsLoading, setEmailsLoading] = useState(false);
  const [emailSearch, setEmailSearch] = useState('');
  const [selectedRecipientIds, setSelectedRecipientIds] = useState([]);
  const [markingReplied, setMarkingReplied] = useState(false);
  const [stages, setStages] = useState([]);
  const [followUpModalOpen, setFollowUpModalOpen] = useState(false);
  const [followUpAt, setFollowUpAt] = useState('');
  const [schedulingFollowUp, setSchedulingFollowUp] = useState(false);
  const [pendingOpenSchedule, setPendingOpenSchedule] = useState(false);
  const [updateTarget, setUpdateTarget] = useState(null);
  const [updateForm, setUpdateForm] = useState({
    name: '',
    email: '',
    company: '',
    designation: '',
    industry: '',
    replied: false,
  });
  const [savingUpdate, setSavingUpdate] = useState(false);

  const loadCampaigns = useCallback(async () => {
    setCampaignLoading(true);
    try {
      const { data } = await campaignService.getAll();
      setCampaigns(Array.isArray(data) ? data : []);
    } catch {
      toast.error('Failed to load campaigns');
    } finally {
      setCampaignLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadCampaigns();
  }, [loadCampaigns]);

  /** Resolve campaigns that contain a matching recipient email/name. */
  const resolveRecipientCampaigns = useCallback(async (term) => {
    const q = (term || '').trim();
    if (!q) {
      setEmailMatchedCampaignIds(null);
      return;
    }
    setSearchingRecipients(true);
    try {
      const { data } = await campaignService.listEmailsForUpdate(q);
      const ids = new Set();
      for (const card of data?.items || []) {
        for (const c of card.campaigns || []) {
          ids.add(c.campaign_id);
        }
      }
      setEmailMatchedCampaignIds(ids);
    } catch {
      setEmailMatchedCampaignIds(new Set());
    } finally {
      setSearchingRecipients(false);
    }
  }, []);

  const debouncedCampaignSearch = useMemo(
    () =>
      debounce((val) => {
        setSearch(val);
        resolveRecipientCampaigns(val);
      }, 300),
    [resolveRecipientCampaigns]
  );

  const filteredCampaigns = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return campaigns;
    return campaigns.filter((c) => {
      const byName =
        c.campaign_name?.toLowerCase().includes(term) ||
        c.campaign_id?.toLowerCase().includes(term);
      const byRecipient = emailMatchedCampaignIds?.has(c.id);
      return byName || byRecipient;
    });
  }, [campaigns, search, emailMatchedCampaignIds]);

  const selectedCampaign = useMemo(
    () => campaigns.find((c) => c.id === selectedId) || null,
    [campaigns, selectedId]
  );

  const loadEmails = useCallback(
    async (campaignId) => {
      setEmailsLoading(true);
      try {
        const [recipientsRes, stagesRes] = await Promise.all([
          campaignService.getRecipients(campaignId),
          sequenceService.getAll(campaignId).catch(() => ({ data: [] })),
        ]);
        setStages(stagesRes.data || []);
        const items = recipientsRes.data?.items || [];
        const rows = items
          .map((r) => ({
            key: `${r.recipient_id}`,
            recipient_id: r.recipient_id,
            name: r.recipient_name,
            email: r.recipient_email,
            company: r.recipient_company,
            designation: r.recipient_designation,
            industry: r.recipient_industry,
            status: r.status,
            follow_up_state: r.follow_up_state,
            follow_up_label: r.follow_up_label,
            last_sent_at: r.last_sent_at,
            is_suppressed: r.is_suppressed,
          }));
        setEmailRows(rows);
      } catch {
        toast.error('Failed to load campaign emails');
        setEmailRows([]);
      } finally {
        setEmailsLoading(false);
      }
    },
    [toast]
  );

  useEffect(() => {
    if (selectedId) {
      setSelectedRecipientIds([]);
      loadEmails(selectedId);
      setEmailSearch('');
    } else {
      setEmailRows([]);
      setSelectedRecipientIds([]);
    }
  }, [selectedId, loadEmails]);

  /* Restore selection + open schedule after returning from Follow-up Sequence */
  useEffect(() => {
    const ids = location.state?.selectedRecipientIds;
    const openSchedule = location.state?.openSchedule;
    if (!selectedId || (!ids?.length && !openSchedule)) return;

    // Wait until emails finished loading so we don't get cleared by loadEmails
    if (emailsLoading) return;

    if (Array.isArray(ids) && ids.length) {
      setSelectedRecipientIds(ids);
    }
    if (openSchedule) {
      setPendingOpenSchedule(true);
    }
    navigate(`${location.pathname}${location.search}`, { replace: true, state: {} });
  }, [selectedId, location.state, location.pathname, location.search, navigate, emailsLoading]);

  useEffect(() => {
    if (!pendingOpenSchedule || emailsLoading) return;
    if (selectedRecipientIds.length === 0) {
      setPendingOpenSchedule(false);
      return;
    }
    setFollowUpAt(defaultScheduleValue());
    setFollowUpModalOpen(true);
    setPendingOpenSchedule(false);
  }, [pendingOpenSchedule, emailsLoading, selectedRecipientIds.length]);

  const filteredEmailRows = useMemo(() => {
    const term = emailSearch.trim().toLowerCase();
    if (!term) return emailRows;
    return emailRows.filter((r) => {
      const name = (r.name || '').toLowerCase();
      const email = (r.email || '').toLowerCase();
      const company = (r.company || '').toLowerCase();
      return name.includes(term) || email.includes(term) || company.includes(term);
    });
  }, [emailRows, emailSearch]);

  const openUpdate = (row) => {
    setUpdateTarget(row);
    setUpdateForm({
      name: row.name || '',
      email: row.email || '',
      company: row.company || '',
      designation: row.designation || '',
      industry: row.industry || '',
      replied: row.status === 'replied',
    });
  };

  const saveUpdate = async () => {
    if (!updateTarget) return;
    const name = updateForm.name.trim();
    const email = updateForm.email.trim();
    if (!name || !email) {
      toast.error('Name and email are required');
      return;
    }
    setSavingUpdate(true);
    try {
      await recipientService.update(updateTarget.recipient_id, {
        name,
        email,
        company: updateForm.company.trim() || null,
        designation: updateForm.designation.trim() || null,
        industry: updateForm.industry.trim() || null,
      });
      if (updateForm.replied && updateTarget.status !== 'replied') {
        await campaignService.markReplied(selectedId, [updateTarget.recipient_id]);
      } else if (!updateForm.replied && updateTarget.status === 'replied') {
        await campaignService.unmarkReplied(selectedId, [updateTarget.recipient_id]);
      }
      toast.success('Contact updated');
      setUpdateTarget(null);
      await loadEmails(selectedId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update contact');
    } finally {
      setSavingUpdate(false);
    }
  };

  const isEligible = (r) =>
    r.status !== 'replied' &&
    r.status !== 'bounced' &&
    r.status !== 'invalid_email' &&
    r.status !== 'risky' &&
    !r.is_suppressed;

  const isSchedulable = (r) =>
    isEligible(r) &&
    ['sent', 'delivered', 'opened', 'clicked', 'out_of_office'].includes(r.status);

  const selectableRows = filteredEmailRows.filter(isEligible);
  const allSelected =
    selectableRows.length > 0 &&
    selectableRows.every((r) => selectedRecipientIds.includes(r.recipient_id));

  const selectedSchedulableCount = filteredEmailRows.filter(
    (r) => selectedRecipientIds.includes(r.recipient_id) && isSchedulable(r)
  ).length;

  const toggleSelect = (recipientId) => {
    setSelectedRecipientIds((prev) =>
      prev.includes(recipientId)
        ? prev.filter((id) => id !== recipientId)
        : [...prev, recipientId]
    );
  };

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedRecipientIds([]);
    } else {
      setSelectedRecipientIds(selectableRows.map((r) => r.recipient_id));
    }
  };

  const backToCampaigns = () => {
    setSearchParams({});
  };

  const handleMarkReplied = async () => {
    if (!selectedId || selectedRecipientIds.length === 0) {
      toast.error('Select at least one recipient');
      return;
    }
    setMarkingReplied(true);
    try {
      const { data } = await campaignService.markReplied(selectedId, selectedRecipientIds);
      toast.success(`Marked ${data.updated} as replied`);
      await loadEmails(selectedId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to mark as replied');
    } finally {
      setMarkingReplied(false);
    }
  };

  const openScheduleModal = () => {
    if (selectedSchedulableCount === 0) {
      toast.error('Select recipients that can receive a follow-up');
      return;
    }
    setFollowUpAt(defaultScheduleValue());
    setFollowUpModalOpen(true);
  };

  const openScheduleForRow = (row) => {
    if (!isSchedulable(row)) return;
    setSelectedRecipientIds([row.recipient_id]);
    setFollowUpAt(defaultScheduleValue());
    setFollowUpModalOpen(true);
  };

  const handleScheduleFollowUp = async () => {
    if (!followUpAt || !selectedId) {
      toast.error('Choose a follow-up date and time');
      return;
    }
    const ids = filteredEmailRows
      .filter((r) => selectedRecipientIds.includes(r.recipient_id) && isSchedulable(r))
      .map((r) => r.recipient_id);
    if (ids.length === 0) {
      toast.error('No eligible recipients selected');
      return;
    }

    setSchedulingFollowUp(true);
    try {
      const { data } = await campaignService.scheduleFollowUp(selectedId, {
        scheduled_at: new Date(followUpAt).toISOString(),
        recipient_ids: ids,
        all_non_replied: false,
      });
      toast.success(
        `Scheduled follow-up for ${data.scheduled} recipient(s)` +
          (data.skipped ? ` (${data.skipped} skipped)` : '')
      );
      setFollowUpModalOpen(false);
      await loadEmails(selectedId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to schedule follow-up');
    } finally {
      setSchedulingFollowUp(false);
    }
  };

  const followUpShort = (r) => {
    if (r.follow_up_state === 'sent') return 'Sent';
    if (r.follow_up_state === 'scheduled') return 'Scheduled';
    if (r.status === 'replied') return '—';
    return 'None';
  };

  if (campaignLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  /* ── Campaign emails table ────────────────────────────────────────────── */
  if (selectedId) {
    return (
      <PageShell maxWidth="max-w-[1500px]">
        <PageHeader
          eyebrow="Schedule email"
          title={selectedCampaign?.campaign_name || 'Campaign emails'}
          subtitle={
            selectedCampaign
              ? `${emailRows.length} contact${emailRows.length === 1 ? '' : 's'} · mark replies & schedule follow-ups`
              : 'Mark replies for this campaign'
          }
          actions={
            <Button variant="secondary" icon={FiArrowLeft} onClick={backToCampaigns}>
              Back to campaigns
            </Button>
          }
        />

        <SurfaceCard variant="filter" className="space-y-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <SearchInput
              value={emailSearch}
              onChange={setEmailSearch}
              placeholder="Search by email or name..."
              className="w-full max-w-xl"
            />
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleMarkReplied}
                disabled={markingReplied || selectedRecipientIds.length === 0}
                className="btn-primary text-sm flex items-center gap-2 disabled:opacity-50"
              >
                {markingReplied ? <LoadingSpinner size="sm" /> : <FiCheckCircle size={14} />}
                Mark replied
                {selectedRecipientIds.length > 0 && (
                  <span className="rounded-full bg-white/20 px-1.5 text-xs">
                    {selectedRecipientIds.length}
                  </span>
                )}
              </button>
              <button
                type="button"
                onClick={openScheduleModal}
                disabled={selectedSchedulableCount === 0}
                className="btn-secondary text-sm flex items-center gap-2 disabled:opacity-50"
              >
                <FiCalendar size={14} /> Schedule
                {selectedSchedulableCount > 0 && (
                  <span className="rounded-full bg-primary-50 px-1.5 text-xs font-semibold text-primary-700">
                    {selectedSchedulableCount}
                  </span>
                )}
              </button>
            </div>
          </div>
          {!emailsLoading && (
            <p className="text-sm text-slate-500">
              Showing <span className="font-semibold text-slate-800">{filteredEmailRows.length}</span>{' '}
              email{filteredEmailRows.length !== 1 ? 's' : ''}
              {selectedRecipientIds.length > 0 && (
                <> · <span className="font-semibold text-primary-700">{selectedRecipientIds.length}</span> selected</>
              )}
            </p>
          )}
        </SurfaceCard>

        <div className="surface-card overflow-hidden">
          {emailsLoading ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner size="lg" />
            </div>
          ) : filteredEmailRows.length === 0 ? (
            <div className="py-12 text-center text-slate-400">
              {emailSearch.trim()
                ? 'No emails match that search.'
                : 'No successfully sent emails in this campaign yet.'}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table min-w-[980px]">
                <thead className="sticky top-0 z-[1] border-b border-slate-200 bg-slate-50/95">
                  <tr>
                    <th className="w-12 px-4 py-3">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={toggleSelectAll}
                        disabled={selectableRows.length === 0}
                        className="rounded border-gray-300"
                        aria-label="Select all"
                      />
                    </th>
                    <th className="px-6 py-3 font-medium">Prospect</th>
                    <th className="px-6 py-3 font-medium">Email</th>
                    <th className="px-6 py-3 font-medium">Status</th>
                    <th className="px-6 py-3 font-medium">Follow-up</th>
                    <th className="px-6 py-3 font-medium">Last sent</th>
                    <th className="px-6 py-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEmailRows.map((row) => {
                    const eligible = isEligible(row);
                    const selected = selectedRecipientIds.includes(row.recipient_id);
                    return (
                      <tr key={row.key} className="hover:bg-slate-50/80">
                        <td className="px-4 py-4">
                          <input
                            type="checkbox"
                            checked={selected}
                            disabled={!eligible}
                            onChange={() => toggleSelect(row.recipient_id)}
                            className="rounded border-gray-300 disabled:opacity-40"
                            aria-label={`Select ${row.email}`}
                          />
                        </td>
                        <td className="px-6 py-4">
                          <p className="font-medium text-gray-900">{row.name || '—'}</p>
                          {(row.designation || row.company) && (
                            <p className="text-xs text-gray-500">
                              {[row.designation, row.company].filter(Boolean).join(' · ')}
                            </p>
                          )}
                        </td>
                        <td className="px-6 py-4 text-gray-700">{row.email}</td>
                        <td className="px-6 py-4">
                          <StatusBadge status={row.status} />
                        </td>
                        <td className="px-6 py-4">
                          {isSchedulable(row) ? (
                            <button
                              type="button"
                              onClick={() => openScheduleForRow(row)}
                              className="text-sm font-medium text-primary-700 hover:underline"
                            >
                              {followUpShort(row)}
                            </button>
                          ) : (
                            <span className="text-sm text-gray-500">{followUpShort(row)}</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-gray-600 whitespace-nowrap">
                          {row.last_sent_at ? formatDateTime(row.last_sent_at) : '—'}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex flex-wrap items-center gap-2">
                            <button
                              type="button"
                              onClick={() => openUpdate(row)}
                              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-50"
                            >
                              <FiCheckCircle size={12} /> Update
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <Modal
          isOpen={!!updateTarget}
          onClose={() => !savingUpdate && setUpdateTarget(null)}
          title="Update contact"
          size="md"
        >
          <div className="space-y-4">
            <p className="text-sm text-slate-500">
              Change this contact’s details, or mark them as replied.
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="label">Name *</label>
                <input
                  className="input-field"
                  value={updateForm.name}
                  onChange={(e) => setUpdateForm((f) => ({ ...f, name: e.target.value }))}
                  autoFocus
                />
              </div>
              <div>
                <label className="label">Email *</label>
                <input
                  type="email"
                  className="input-field"
                  value={updateForm.email}
                  onChange={(e) => setUpdateForm((f) => ({ ...f, email: e.target.value }))}
                />
              </div>
              <div>
                <label className="label">Company</label>
                <input
                  className="input-field"
                  value={updateForm.company}
                  onChange={(e) => setUpdateForm((f) => ({ ...f, company: e.target.value }))}
                />
              </div>
              <div>
                <label className="label">Designation</label>
                <input
                  className="input-field"
                  value={updateForm.designation}
                  onChange={(e) => setUpdateForm((f) => ({ ...f, designation: e.target.value }))}
                />
              </div>
              <div className="sm:col-span-2">
                <label className="label">Industry</label>
                <input
                  className="input-field"
                  value={updateForm.industry}
                  onChange={(e) => setUpdateForm((f) => ({ ...f, industry: e.target.value }))}
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="rounded border-gray-300"
                checked={updateForm.replied}
                onChange={(e) => setUpdateForm((f) => ({ ...f, replied: e.target.checked }))}
              />
              Mark as replied
            </label>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                className="btn-secondary"
                disabled={savingUpdate}
                onClick={() => setUpdateTarget(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary"
                disabled={savingUpdate}
                onClick={saveUpdate}
              >
                {savingUpdate ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </Modal>

        <Modal
          isOpen={followUpModalOpen}
          onClose={() => !schedulingFollowUp && setFollowUpModalOpen(false)}
          size="md"
          hideHeader
        >
          <div className="p-6 sm:p-7">
            {/* Header */}
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary-50 text-primary-600">
                  <FiCalendar size={22} />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-slate-950">Schedule Follow-up</h2>
                  <p className="mt-0.5 text-sm text-slate-500">
                    Schedule a follow-up for{' '}
                    <span className="font-semibold text-slate-700">{selectedSchedulableCount}</span>{' '}
                    selected recipient{selectedSchedulableCount !== 1 ? 's' : ''}.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => !schedulingFollowUp && setFollowUpModalOpen(false)}
                className="rounded-xl p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
                aria-label="Close"
              >
                <FiX size={20} />
              </button>
            </div>

            {stages.length > 0 && (
              <div className="mt-5 flex items-start gap-2.5 rounded-2xl border border-emerald-100 bg-emerald-50/80 px-3.5 py-3">
                <FiSend size={16} className="mt-0.5 shrink-0 text-emerald-600" />
                <p className="text-sm text-emerald-900">
                  <span className="font-semibold">Follow-up email</span>
                  <span className="text-emerald-800/80">
                    {' '}
                    — Using stage {stages[0]?.stage_order}: “{stages[0]?.subject}”
                  </span>
                </p>
              </div>
            )}

            <div className="mt-5 space-y-4">
              <div>
                <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-slate-700">
                  <FiCalendar size={14} className="text-primary-500" />
                  Follow-up date &amp; time <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <FiCalendar
                    size={14}
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                  />
                  <input
                    type="datetime-local"
                    className="input-field w-full pl-9"
                    value={followUpAt}
                    min={defaultScheduleValue()}
                    onChange={(e) => setFollowUpAt(e.target.value)}
                  />
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="mt-6 flex items-center justify-between gap-3 border-t border-slate-100 pt-5">
              <button
                type="button"
                onClick={() => setFollowUpModalOpen(false)}
                className="rounded-xl border border-slate-200 bg-slate-50 px-5 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:opacity-50"
                disabled={schedulingFollowUp}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleScheduleFollowUp}
                disabled={schedulingFollowUp || !followUpAt}
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-primary-600 to-primary-500 px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-primary-500/25 transition hover:from-primary-700 hover:to-primary-600 disabled:opacity-50"
              >
                {schedulingFollowUp ? (
                  <LoadingSpinner size="sm" />
                ) : (
                  <FiCalendar size={16} />
                )}
                Schedule Follow-up
                <FiArrowRight size={16} />
              </button>
            </div>
          </div>
        </Modal>
      </PageShell>
    );
  }

  /* ── Campaign card grid ───────────────────────────────────────────────── */
  return (
    <PageShell maxWidth="max-w-[1500px]">
      <PageHeader
        eyebrow="Lead generation"
        title="Schedule email"
        subtitle="Search by campaign or recipient email — open a campaign to mark replies"
        actions={
          <Button variant="secondary" icon={FiArrowLeft} to="/campaigns">
            Back to campaigns
          </Button>
        }
      />

      <SurfaceCard variant="filter">
        <SearchInput
          value={searchInput}
          onChange={(val) => {
            setSearchInput(val);
            debouncedCampaignSearch(val);
          }}
          placeholder="Search by email, name, or campaign ID..."
          className="min-w-[200px] w-full max-w-xl"
        />
        {searchingRecipients && (
          <p className="mt-2 text-xs text-slate-400">Looking up recipient emails…</p>
        )}
      </SurfaceCard>

      {filteredCampaigns.length === 0 ? (
        <SurfaceCard className="py-12 text-center text-slate-400">
          {campaigns.length === 0
            ? 'No campaigns yet. Create your first campaign to get started.'
            : 'No campaigns match your search.'}
        </SurfaceCard>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredCampaigns.map((c) => (
            <CampaignCard
              key={c.id}
              campaign={c}
              hideEdit
              hideDelete
              detailsTo={`/campaigns/update-list?campaign=${c.id}`}
              detailsLabel="Open emails"
            />
          ))}
        </div>
      )}
    </PageShell>
  );
}
