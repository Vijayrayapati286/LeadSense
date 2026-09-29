import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { FiArrowLeft, FiMail, FiSend, FiX } from 'react-icons/fi';
import { campaignService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { generateCampaignId } from '../utils/helpers';
import Button from '../components/ui/Button';
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

function followUpInstant(date, time) {
  if (!date) return null;
  const clock = /^\d{2}:\d{2}/.test(time || '') ? time.slice(0, 5) : '09:00';
  const when = new Date(`${date}T${clock}:00`);
  return Number.isNaN(when.getTime()) ? null : when;
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
  const [campaignName, setCampaignName] = useState('');
  const [description, setDescription] = useState('');

  const [contactEmail, setContactEmail] = useState('');
  const [selected, setSelected] = useState([]);

  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sentDate, setSentDate] = useState(todayInputValue);
  const [followUpDate, setFollowUpDate] = useState('');
  const [followUpTime, setFollowUpTime] = useState('09:00');
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
  const typedEmail = contactEmail.trim();
  const canAddTyped = looksLikeEmail(typedEmail) && !selectedEmails.has(typedEmail.toLowerCase());

  const addEmail = () => {
    if (!canAddTyped) return;
    const email = typedEmail.toLowerCase();
    const name = email.split('@')[0];
    setSelected((prev) => [...prev, { name, email, isNew: true }]);
    setContactEmail('');
  };

  const onContactKeyDown = (event) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    addEmail();
  };

  const removeSelected = (email) => {
    setSelected((prev) => prev.filter((c) => c.email !== email));
  };

  const canSendFollowUp =
    mode === 'existing' &&
    campaign &&
    campaign.origin !== 'external' &&
    Boolean(followUpDate);

  const sendHint =
    mode === 'new'
      ? 'A new outside-mail campaign is saved as a reminder. LeadSense will not send it.'
      : !campaign
        ? 'Select a campaign above.'
        : campaign.origin === 'external'
          ? 'This campaign is tracked outside LeadSense. Save stores the follow-up as a reminder.'
          : !followUpDate
            ? 'Choose a follow-up date and time to send it from LeadSense.'
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
    let contacts = selected;
    if (typedEmail) {
      if (!looksLikeEmail(typedEmail)) {
        toast.error('Enter a valid email');
        return;
      }
      const email = typedEmail.toLowerCase();
      if (!selectedEmails.has(email)) {
        contacts = [...selected, { name: email.split('@')[0], email, isNew: true }];
        setSelected(contacts);
        setContactEmail('');
      }
    }
    if (contacts.length === 0) {
      toast.error('Enter at least one email');
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
      const when = followUpInstant(followUpDate, followUpTime);
      if (!when || when <= new Date()) {
        toast.error('Choose a future follow-up date and time');
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
        recipient_ids: contacts.filter((c) => !c.isNew && c.id).map((c) => c.id),
        new_contacts: contacts.filter((c) => c.isNew).map((c) => ({ name: c.name, email: c.email })),
        subject: subject.trim(),
        body: body.trim(),
        sent_at: dateToIso(sentDate),
        follow_up_at: followUpInstant(followUpDate, followUpTime)?.toISOString() ?? null,
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
        title="Mail from outside"
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
          <label className="label">Email</label>
          <div className="flex items-center gap-2">
            <input
              type="email"
              className="input-field"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              onKeyDown={onContactKeyDown}
              placeholder="name@company.com"
            />
            <Button type="button" variant="secondary" onClick={addEmail} disabled={!canAddTyped}>
              Add
            </Button>
          </div>
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
        <div className="grid gap-4 sm:grid-cols-3">
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
          <div>
            <label className="label">Next follow-up time</label>
            <input
              className="input-field"
              type="time"
              value={followUpTime}
              onChange={(e) => setFollowUpTime(e.target.value)}
            />
          </div>
          <div className="sm:col-span-3">
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
            disabled={Boolean(saving)}
            title={sendHint || undefined}
            onClick={() => handleSave(true)}
          >
            Save and send follow-up
          </Button>
        </div>
      </SurfaceCard>
    </PageShell>
  );
}
