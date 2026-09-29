import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { FiArrowLeft, FiCheck, FiMail, FiSend, FiX } from 'react-icons/fi';
import { campaignService, recipientService, sequenceService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { debounce, generateCampaignId } from '../utils/helpers';
import Button from '../components/ui/Button';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import PageShell from '../components/ui/PageShell';
import SearchInput from '../components/ui/SearchInput';
import SegmentedControl from '../components/ui/SegmentedControl';
import SurfaceCard from '../components/ui/SurfaceCard';

function todayInputValue() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function dateToIso(value) {
  if (!value) return null;
  return new Date(`${value}T12:00:00`).toISOString();
}

function looksLikeEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export default function RecordOutsideMailPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const toast = useToast();
  const { user } = useAuth();

  const [mode, setMode] = useState('existing');
  const [campaigns, setCampaigns] = useState([]);
  const [campaignQuery, setCampaignQuery] = useState('');
  const [campaignListOpen, setCampaignListOpen] = useState(false);
  const [campaign, setCampaign] = useState(null);
  const [followUpStages, setFollowUpStages] = useState([]);
  const [campaignName, setCampaignName] = useState('');
  const [description, setDescription] = useState('');

  const [contactQuery, setContactQuery] = useState('');
  const [contactHits, setContactHits] = useState([]);
  const [searchingContacts, setSearchingContacts] = useState(false);
  const [selected, setSelected] = useState([]);
  const [newName, setNewName] = useState('');

  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sentDate, setSentDate] = useState(todayInputValue);
  const [followUpDate, setFollowUpDate] = useState('');
  const [followUpAction, setFollowUpAction] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    campaignService
      .getAll()
      .then(({ data }) => setCampaigns(data || []))
      .catch(() => setCampaigns([]));
  }, []);

  useEffect(() => {
    const preset = searchParams.get('campaign');
    if (!preset || campaigns.length === 0) return;
    const match = campaigns.find((c) => String(c.id) === String(preset));
    if (match) {
      setCampaign(match);
      setCampaignQuery(match.campaign_name);
    }
  }, [searchParams, campaigns]);

  useEffect(() => {
    if (!campaign || campaign.origin === 'external') {
      setFollowUpStages([]);
      return;
    }
    sequenceService
      .getAll(campaign.id)
      .then(({ data }) => setFollowUpStages(data || []))
      .catch(() => setFollowUpStages([]));
  }, [campaign]);

  const searchContacts = useMemo(
    () =>
      debounce(async (term) => {
        if (!term.trim()) {
          setContactHits([]);
          setSearchingContacts(false);
          return;
        }
        setSearchingContacts(true);
        try {
          const { data } = await recipientService.getAll({ search: term, page: 1, page_size: 20 });
          setContactHits(data.items || []);
        } catch {
          setContactHits([]);
        } finally {
          setSearchingContacts(false);
        }
      }, 250),
    []
  );

  useEffect(() => {
    searchContacts(contactQuery);
  }, [contactQuery, searchContacts]);

  const campaignMatches = useMemo(() => {
    const term = campaignQuery.trim().toLowerCase();
    if (!term) return campaigns;
    return campaigns.filter(
      (c) =>
        c.campaign_name.toLowerCase().includes(term) ||
        (c.campaign_id || '').toLowerCase().includes(term)
    );
  }, [campaigns, campaignQuery]);

  const selectedEmails = new Set(selected.map((c) => c.email.toLowerCase()));
  const typedEmail = contactQuery.trim();
  const canAddTyped =
    looksLikeEmail(typedEmail) &&
    !selectedEmails.has(typedEmail.toLowerCase()) &&
    !contactHits.some((c) => c.email.toLowerCase() === typedEmail.toLowerCase());

  const addExisting = (contact) => {
    if (selectedEmails.has(contact.email.toLowerCase())) return;
    setSelected((prev) => [
      ...prev,
      {
        id: contact.id,
        name: contact.name,
        email: contact.email,
        company: contact.company,
        isNew: false,
      },
    ]);
  };

  const addNew = () => {
    const email = typedEmail.toLowerCase();
    const name = newName.trim() || email.split('@')[0];
    setSelected((prev) => [...prev, { name, email, isNew: true }]);
    setNewName('');
    setContactQuery('');
    setContactHits([]);
  };

  const removeSelected = (email) => {
    setSelected((prev) => prev.filter((c) => c.email !== email));
  };

  const canSendFollowUp =
    mode === 'existing' &&
    campaign &&
    campaign.origin !== 'external' &&
    followUpStages.length > 0 &&
    Boolean(followUpDate);

  const sendHint =
    mode === 'new'
      ? 'A new outside-mail campaign is saved as a reminder. LeadSense will not send it.'
      : !campaign
        ? ''
        : campaign.origin === 'external'
          ? 'This campaign is tracked outside LeadSense. Save stores the follow-up as a reminder.'
          : followUpStages.length === 0
            ? 'Add a follow-up stage on this campaign before LeadSense can send one.'
            : !followUpDate
              ? 'Choose a follow-up date to send it from LeadSense.'
              : '';

  const handleSave = async (sendFollowUp) => {
    if (mode === 'existing' && !campaign) {
      toast.error('Select a campaign');
      return;
    }
    if (mode === 'new' && !campaignName.trim()) {
      toast.error('Enter a campaign name');
      return;
    }
    if (selected.length === 0) {
      toast.error('Select at least one contact');
      return;
    }
    if (!subject.trim() || !body.trim()) {
      toast.error('Enter the subject and email content');
      return;
    }
    if (!sentDate) {
      toast.error('Add the sent date');
      return;
    }
    if (sendFollowUp) {
      if (!canSendFollowUp) {
        toast.error(sendHint || 'This campaign cannot send a follow-up yet');
        return;
      }
      const when = new Date(`${followUpDate}T09:00:00`);
      if (Number.isNaN(when.getTime()) || when <= new Date()) {
        toast.error('Choose a future follow-up date');
        return;
      }
    }

    setSaving(sendFollowUp ? 'send' : 'record');
    try {
      const { data } = await campaignService.recordManualActivity({
        mode,
        campaign_id: mode === 'existing' ? campaign.id : null,
        campaign_name: mode === 'new' ? campaignName.trim() : null,
        campaign_code: mode === 'new' ? generateCampaignId() : null,
        description: mode === 'new' ? description.trim() || null : null,
        owner: user?.name || null,
        department: user?.department || null,
        recipient_ids: selected.filter((c) => !c.isNew && c.id).map((c) => c.id),
        new_contacts: selected.filter((c) => c.isNew).map((c) => ({ name: c.name, email: c.email })),
        subject: subject.trim(),
        body: body.trim(),
        sent_at: dateToIso(sentDate),
        follow_up_at: followUpDate ? new Date(`${followUpDate}T09:00:00`).toISOString() : null,
        follow_up_action: followUpAction.trim() || null,
        send_follow_up: Boolean(sendFollowUp),
      });
      if (sendFollowUp) {
        toast.success(
          `Recorded outside mail and scheduled a follow-up for ${data.follow_ups_scheduled} contact${data.follow_ups_scheduled === 1 ? '' : 's'}`
        );
      } else {
        toast.success(`Recorded outside mail for ${data.recorded} contact${data.recorded === 1 ? '' : 's'}`);
      }
      navigate(`/campaigns/${data.campaign_id}`);
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to record outside mail');
    } finally {
      setSaving(false);
    }
  };

  return (
    <PageShell maxWidth="max-w-3xl">
      <PageHeader
        eyebrow="Lead generation"
        title="Schedule email"
        subtitle="Record an email you already sent from Outlook or another mailbox. LeadSense will not send it."
        actions={
          <Button variant="secondary" icon={FiArrowLeft} onClick={() => navigate('/campaigns')}>
            Back
          </Button>
        }
      />

      <SurfaceCard className="space-y-5">
        <SegmentedControl
          options={[
            { key: 'existing', label: 'Existing campaign' },
            { key: 'new', label: 'New campaign' },
          ]}
          value={mode}
          onChange={setMode}
        />

        {mode === 'existing' ? (
          <div>
            <label className="label">Campaign</label>
            <div
              className="relative"
              onFocus={() => setCampaignListOpen(true)}
              onBlur={() => {
                window.setTimeout(() => setCampaignListOpen(false), 150);
              }}
            >
              <SearchInput
                value={campaignQuery}
                onChange={(val) => {
                  setCampaignQuery(val);
                  setCampaignListOpen(true);
                  if (campaign && val !== campaign.campaign_name) setCampaign(null);
                }}
                placeholder="Search by campaign name or ID..."
              />
              {campaignListOpen && (
                <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-xl border border-slate-200 bg-white shadow-lg">
                  {campaignMatches.length === 0 ? (
                    <li className="px-3 py-2 text-sm text-slate-400">No campaigns match</li>
                  ) : (
                    campaignMatches.map((c) => (
                      <li key={c.id}>
                        <button
                          type="button"
                          className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50"
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => {
                            setCampaign(c);
                            setCampaignQuery(c.campaign_name);
                            setCampaignListOpen(false);
                          }}
                        >
                          <span className="truncate font-medium text-slate-800">{c.campaign_name}</span>
                          <span className="ml-3 shrink-0 text-xs text-slate-400">{c.campaign_id}</span>
                        </button>
                      </li>
                    ))
                  )}
                </ul>
              )}
            </div>
            {campaign ? (
              <p className="mt-2 text-xs text-primary-700">Selected: {campaign.campaign_name}</p>
            ) : null}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="label">Campaign name</label>
              <input
                className="input-field"
                value={campaignName}
                onChange={(e) => setCampaignName(e.target.value)}
                placeholder="Q3 outreach from Outlook"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="label">Description</label>
              <input
                className="input-field"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional"
              />
            </div>
          </div>
        )}
      </SurfaceCard>

      <SurfaceCard className="space-y-4">
        <div>
          <label className="label">Contacts</label>
          <SearchInput
            value={contactQuery}
            onChange={setContactQuery}
            placeholder="Search name, email, or company..."
          />
          {searchingContacts && (
            <div className="mt-2 flex justify-center">
              <LoadingSpinner size="sm" />
            </div>
          )}
          {contactHits.length > 0 && (
            <ul className="mt-2 max-h-48 overflow-auto rounded-xl border border-slate-200">
              {contactHits.map((c) => {
                const added = selectedEmails.has(c.email.toLowerCase());
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      disabled={added}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50 disabled:opacity-50"
                      onClick={() => addExisting(c)}
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium text-slate-800">{c.name}</span>
                        <span className="block truncate text-xs text-slate-400">
                          {c.email}
                          {c.company ? ` · ${c.company}` : ''}
                        </span>
                      </span>
                      {added ? <FiCheck className="text-primary-600" /> : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {canAddTyped && (
            <div className="mt-3 flex flex-wrap items-end gap-2 rounded-xl border border-dashed border-slate-300 p-3">
              <div className="min-w-[180px] flex-1">
                <label className="label">New contact name</label>
                <input
                  className="input-field"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder={typedEmail.split('@')[0]}
                />
              </div>
              <Button type="button" variant="secondary" onClick={addNew}>
                Add {typedEmail}
              </Button>
            </div>
          )}
        </div>

        {selected.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {selected.map((c) => (
              <span
                key={c.email}
                className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700"
              >
                {c.name}
                <span className="text-slate-400">{c.email}</span>
                <button type="button" onClick={() => removeSelected(c.email)} className="text-slate-400 hover:text-slate-700">
                  <FiX size={14} />
                </button>
              </span>
            ))}
          </div>
        )}
      </SurfaceCard>

      <SurfaceCard className="space-y-4">
        <div>
          <label className="label">Subject</label>
          <input className="input-field" value={subject} onChange={(e) => setSubject(e.target.value)} />
        </div>
        <div>
          <label className="label">Email content</label>
          <textarea
            className="input-field min-h-[160px]"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Paste the email you sent"
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Sent date</label>
            <input className="input-field" type="date" value={sentDate} onChange={(e) => setSentDate(e.target.value)} />
          </div>
          <div>
            <label className="label">Next follow-up date</label>
            <input
              className="input-field"
              type="date"
              value={followUpDate}
              onChange={(e) => setFollowUpDate(e.target.value)}
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Follow-up action</label>
            <input
              className="input-field"
              value={followUpAction}
              onChange={(e) => setFollowUpAction(e.target.value)}
              placeholder="Call, send follow-up, connect on LinkedIn..."
            />
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {sendHint ? <p className="mr-auto max-w-md text-xs text-slate-500">{sendHint}</p> : null}
          <Button
            variant="secondary"
            icon={FiMail}
            loading={saving === 'record'}
            disabled={Boolean(saving)}
            onClick={() => handleSave(false)}
          >
            Save
          </Button>
          <Button
            icon={FiSend}
            loading={saving === 'send'}
            disabled={Boolean(saving) || !canSendFollowUp}
            onClick={() => handleSave(true)}
          >
            Save and send follow-up
          </Button>
        </div>
      </SurfaceCard>
    </PageShell>
  );
}
