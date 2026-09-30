import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { FiAlertCircle, FiArrowLeft, FiCheck, FiChevronDown, FiPlus, FiSave, FiX } from 'react-icons/fi';
import { campaignService } from '../services/services';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { formatDate, generateCampaignId } from '../utils/helpers';
import Button from '../components/ui/Button';
import PageHeader from '../components/ui/PageHeader';
import PageShell from '../components/ui/PageShell';
import SearchInput from '../components/ui/SearchInput';
import StatusBadge from '../components/ui/StatusBadge';

const SUBJECT_LIMIT = 200;
const BODY_LIMIT = 5000;

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

function splitAddresses(value) {
  return value
    .split(/[,;]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function localTimezoneLabel() {
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Local time';
    const abbr = new Intl.DateTimeFormat('en-US', { timeZoneName: 'short' })
      .formatToParts(new Date())
      .find((part) => part.type === 'timeZoneName')?.value;
    return abbr ? `${zone} (${abbr})` : zone;
  } catch {
    return 'Local time';
  }
}

function formatMissing(items) {
  if (items.length === 0) return '';
  if (items.length === 1) return `Add ${items[0]} to save.`;
  if (items.length === 2) return `Add ${items[0]} and ${items[1]} to save.`;
  return `Add ${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]} to save.`;
}

function SectionHeading({ step, title, description }) {
  return (
    <div className="flex items-start gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-600 text-sm font-semibold text-white">
        {step}
      </span>
      <div>
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        <p className="mt-0.5 text-sm text-slate-500">{description}</p>
      </div>
    </div>
  );
}

function ChoiceCard({ selected, title, description, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`flex w-full items-start gap-3 rounded-xl border px-4 py-3 text-left transition ${
        selected
          ? 'border-primary-500 bg-primary-50/80 ring-1 ring-primary-500'
          : 'border-slate-200 bg-white hover:border-slate-300'
      }`}
    >
      <span
        className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
          selected ? 'border-primary-600' : 'border-slate-300'
        }`}
        aria-hidden="true"
      >
        {selected ? <span className="h-2 w-2 rounded-full bg-primary-600" /> : null}
      </span>
      <span>
        <span className="block text-sm font-semibold text-slate-900">{title}</span>
        <span className="mt-0.5 block text-xs text-slate-500">{description}</span>
      </span>
    </button>
  );
}

function FieldLabel({ htmlFor, children, required = false, optional = false }) {
  return (
    <label htmlFor={htmlFor} className="field-label">
      {children}
      {required ? <span className="ml-0.5 text-rose-500">*</span> : null}
      {optional ? <span className="ml-1.5 font-normal text-slate-400">Optional</span> : null}
    </label>
  );
}

export default function RecordOutsideMailPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const toast = useToast();
  const { user } = useAuth();
  const bodyRef = useRef(null);

  const [mode, setMode] = useState('existing');
  const [campaigns, setCampaigns] = useState([]);
  const [campaignQuery, setCampaignQuery] = useState('');
  const [campaign, setCampaign] = useState(null);
  const [campaignName, setCampaignName] = useState('');
  const [description, setDescription] = useState('');

  const [contactEmail, setContactEmail] = useState('');
  const [emailError, setEmailError] = useState('');
  const [selected, setSelected] = useState([]);

  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sentDate, setSentDate] = useState(todayInputValue);
  const [followUpOpen, setFollowUpOpen] = useState(false);
  const [followUpDate, setFollowUpDate] = useState('');
  const [followUpTime, setFollowUpTime] = useState('09:00');
  const [followUpAction, setFollowUpAction] = useState('');
  const [followUpError, setFollowUpError] = useState('');
  const [saving, setSaving] = useState(false);

  const timezoneLabel = useMemo(() => localTimezoneLabel(), []);

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
    if (match) setCampaign(match);
  }, [searchParams, campaigns]);

  useEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.max(el.scrollHeight, 160)}px`;
  }, [body]);

  const campaignMatches = useMemo(() => {
    const term = campaignQuery.trim().toLowerCase();
    if (!term) return campaigns;
    return campaigns.filter(
      (c) =>
        c.campaign_name.toLowerCase().includes(term) ||
        (c.campaign_id || '').toLowerCase().includes(term)
    );
  }, [campaigns, campaignQuery]);

  const pendingParts = splitAddresses(contactEmail);
  const pendingInvalid = pendingParts.filter((part) => !looksLikeEmail(part));
  const pendingValid = pendingParts.filter((part) => looksLikeEmail(part));

  const followUpBeforeSent = Boolean(followUpOpen && followUpDate && sentDate && followUpDate < sentDate);
  const followUpWhen = followUpOpen && followUpDate ? followUpInstant(followUpDate, followUpTime) : null;
  const schedulingSupported = mode === 'existing' && Boolean(campaign) && campaign?.origin !== 'external';

  const missing = [];
  if (mode === 'existing' && !campaign) missing.push('a campaign');
  if (mode === 'new' && !campaignName.trim()) missing.push('a campaign name');
  if (selected.length === 0 && pendingValid.length === 0) missing.push('a recipient email');
  if (!subject.trim()) missing.push('an email subject');
  if (!body.trim()) missing.push('the email body');
  if (!sentDate) missing.push('the sent date');

  const canSave = missing.length === 0 && pendingInvalid.length === 0 && !followUpBeforeSent && !saving;
  const canSchedule =
    canSave &&
    followUpOpen &&
    schedulingSupported &&
    Boolean(followUpWhen) &&
    followUpWhen > new Date();

  const mergeContacts = (current, extras) => {
    const seen = new Set(current.map((contact) => contact.email.toLowerCase()));
    const next = [...current];
    extras.forEach((email) => {
      const normalized = email.toLowerCase();
      if (seen.has(normalized)) return;
      seen.add(normalized);
      next.push({ name: normalized.split('@')[0], email: normalized, isNew: true });
    });
    return next;
  };

  const addEmail = () => {
    if (pendingParts.length === 0) return;
    if (pendingValid.length > 0) {
      setSelected((prev) => mergeContacts(prev, pendingValid));
    }
    if (pendingInvalid.length > 0) {
      setContactEmail(pendingInvalid.join(', '));
      setEmailError(
        pendingInvalid.length === 1
          ? `${pendingInvalid[0]} is not a valid email address.`
          : 'One or more addresses are not valid emails.'
      );
      return;
    }
    setContactEmail('');
    setEmailError('');
  };

  const onContactKeyDown = (event) => {
    if (event.key !== 'Enter' && event.key !== ',') return;
    if (event.key === ',' && !contactEmail.trim()) return;
    event.preventDefault();
    addEmail();
  };

  const removeSelected = (email) => {
    setSelected((prev) => prev.filter((contact) => contact.email !== email));
  };

  const handleSave = async (sendFollowUp) => {
    if (saving) return;
    if (mode === 'existing' && !campaign) return;
    if (mode === 'new' && !campaignName.trim()) return;
    if (pendingInvalid.length > 0) {
      setEmailError(
        pendingInvalid.length === 1
          ? `${pendingInvalid[0]} is not a valid email address.`
          : 'One or more addresses are not valid emails.'
      );
      return;
    }
    if (followUpBeforeSent) {
      setFollowUpError('Follow-up date cannot be earlier than the sent date.');
      return;
    }

    let contacts = selected;
    if (pendingValid.length > 0) {
      contacts = mergeContacts(selected, pendingValid);
      setSelected(contacts);
      setContactEmail('');
      setEmailError('');
    }
    if (contacts.length === 0 || !subject.trim() || !body.trim() || !sentDate) return;

    if (sendFollowUp) {
      if (!schedulingSupported || !followUpOpen) return;
      const when = followUpInstant(followUpDate, followUpTime);
      if (!when || when <= new Date()) {
        setFollowUpError('Choose a future follow-up date and time.');
        return;
      }
    }

    const includeFollowUp = followUpOpen && Boolean(followUpDate);
    setSaving(sendFollowUp ? 'schedule' : 'record');
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
        follow_up_at: includeFollowUp ? followUpInstant(followUpDate, followUpTime)?.toISOString() ?? null : null,
        follow_up_action: includeFollowUp ? followUpAction.trim() || null : null,
        send_follow_up: Boolean(sendFollowUp),
      });
      if (sendFollowUp) {
        toast.success(
          `Email saved and follow-up scheduled for ${data.follow_ups_scheduled} contact${data.follow_ups_scheduled === 1 ? '' : 's'}.`
        );
      } else {
        toast.success('Email saved successfully.');
      }
      navigate(`/campaigns/${data.campaign_id}`);
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to record outside mail');
    } finally {
      setSaving(false);
    }
  };

  const scheduleHint = !followUpOpen
    ? ''
    : followUpBeforeSent
      ? 'Follow-up date cannot be earlier than the sent date.'
      : !schedulingSupported
        ? mode === 'new' || campaign?.origin === 'external'
          ? 'This follow-up is saved as a reminder. LeadSense will not send it.'
          : 'Select an existing LeadSense campaign to schedule the follow-up.'
        : followUpDate && followUpWhen && followUpWhen <= new Date()
          ? 'Choose a future follow-up date and time.'
          : '';

  return (
    <PageShell maxWidth="max-w-4xl">
      <PageHeader
        eyebrow="Lead generation"
        title="Mail from outside"
        subtitle="Log an email you already sent. This won’t send another email."
        actions={
          <Button variant="secondary" icon={FiArrowLeft} onClick={() => navigate('/campaigns')}>
            Back
          </Button>
        }
      />

      <form
        className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-card"
        onSubmit={(event) => {
          event.preventDefault();
          if (canSave) handleSave(false);
        }}
      >
        <section className="space-y-5 p-5 sm:p-6">
          <SectionHeading
            step="1"
            title="Campaign"
            description="Choose an existing campaign or create a new one."
          />

          <div className="grid gap-3 sm:grid-cols-2">
            <ChoiceCard
              selected={mode === 'existing'}
              title="Existing campaign"
              description="Select from your existing campaigns"
              onClick={() => setMode('existing')}
            />
            <ChoiceCard
              selected={mode === 'new'}
              title="New campaign"
              description="Create a new campaign"
              onClick={() => setMode('new')}
            />
          </div>

          {mode === 'existing' ? (
            <div className="space-y-3">
              <FieldLabel htmlFor="campaign-search" required>
                Campaign
              </FieldLabel>
              <SearchInput
                id="campaign-search"
                value={campaignQuery}
                onChange={setCampaignQuery}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') event.preventDefault();
                }}
                placeholder="Search by campaign name or ID..."
              />
              <div className={`grid gap-3 ${campaign ? 'lg:grid-cols-[minmax(0,1fr)_16rem]' : ''}`}>
                <ul className="max-h-64 overflow-auto rounded-xl border border-slate-200">
                  {campaignMatches.length === 0 ? (
                    <li className="px-3 py-3 text-sm text-slate-400">No campaigns match</li>
                  ) : (
                    campaignMatches.map((item) => {
                      const isSelected = campaign?.id === item.id;
                      return (
                        <li key={item.id} className="border-b border-slate-100 last:border-b-0">
                          <button
                            type="button"
                            className={`flex w-full items-start gap-3 px-3 py-2.5 text-left ${
                              isSelected ? 'bg-primary-50' : 'hover:bg-slate-50'
                            }`}
                            onClick={() => setCampaign(item)}
                          >
                            <span
                              className={`mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                                isSelected ? 'border-primary-600' : 'border-slate-300'
                              }`}
                              aria-hidden="true"
                            >
                              {isSelected ? <span className="h-2 w-2 rounded-full bg-primary-600" /> : null}
                            </span>
                            <span className="min-w-0">
                              <span className="flex flex-wrap items-center gap-2">
                                <span className="truncate text-sm font-medium text-slate-900">{item.campaign_name}</span>
                                <StatusBadge status={item.status} />
                              </span>
                              <span className="mt-0.5 block text-xs text-slate-400">
                                {item.campaign_id} · Created on {formatDate(item.created_at)}
                              </span>
                            </span>
                          </button>
                        </li>
                      );
                    })
                  )}
                </ul>

                {campaign ? (
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50/80 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <p className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700">
                        <FiCheck size={14} />
                        Selected campaign
                      </p>
                      <button
                        type="button"
                        className="text-slate-400 hover:text-slate-700"
                        aria-label="Clear selected campaign"
                        onClick={() => setCampaign(null)}
                      >
                        <FiX size={16} />
                      </button>
                    </div>
                    <p className="mt-3 flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-900">
                      {campaign.campaign_name}
                      <StatusBadge status={campaign.status} />
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {campaign.campaign_id} · Created on {formatDate(campaign.created_at)}
                    </p>
                  </div>
                ) : null}
              </div>
              {!campaign ? (
                <p className="flex items-center gap-2 rounded-xl border border-rose-100 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  <FiAlertCircle size={15} className="shrink-0" />
                  Please select a campaign before saving.
                </p>
              ) : null}
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <FieldLabel htmlFor="campaign-name" required>
                  Campaign name
                </FieldLabel>
                <input
                  id="campaign-name"
                  className="control"
                  value={campaignName}
                  onChange={(e) => setCampaignName(e.target.value)}
                  placeholder="Q3 outreach from Outlook"
                />
              </div>
              <div>
                <FieldLabel htmlFor="campaign-description" optional>
                  Description
                </FieldLabel>
                <input
                  id="campaign-description"
                  className="control"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Optional note about this campaign"
                />
              </div>
            </div>
          )}
        </section>

        <section className="space-y-5 border-t border-slate-100 p-5 sm:p-6">
          <SectionHeading
            step="2"
            title="Email details"
            description="Add the recipient and details of the email you already sent."
          />

          <div>
            <FieldLabel htmlFor="recipient-email" required>
              Recipient email
            </FieldLabel>
            <p className="mb-1.5 text-xs text-slate-500">Enter the email address you already contacted.</p>
            <div className="flex items-start gap-2">
              <div
                className={`flex min-h-11 flex-1 flex-wrap items-center gap-1.5 rounded-xl border bg-white px-2 py-1.5 ${
                  emailError ? 'border-rose-300 ring-4 ring-rose-50' : 'border-slate-300 focus-within:border-primary-500 focus-within:ring-4 focus-within:ring-primary-100'
                }`}
              >
                {selected.map((contact) => (
                  <span
                    key={contact.email}
                    className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1 text-sm text-slate-700"
                  >
                    {contact.email}
                    <button
                      type="button"
                      onClick={() => removeSelected(contact.email)}
                      className="text-slate-400 hover:text-slate-700"
                      aria-label={`Remove ${contact.email}`}
                    >
                      <FiX size={13} />
                    </button>
                  </span>
                ))}
                <input
                  id="recipient-email"
                  type="text"
                  className="min-w-[12rem] flex-1 bg-transparent px-1 py-1 text-sm text-slate-900 outline-none placeholder:text-slate-400"
                  value={contactEmail}
                  onChange={(e) => {
                    setContactEmail(e.target.value);
                    if (emailError) setEmailError('');
                  }}
                  onKeyDown={onContactKeyDown}
                  onBlur={() => {
                    if (pendingInvalid.length > 0) addEmail();
                  }}
                  placeholder={selected.length === 0 ? 'name@company.com' : ''}
                />
              </div>
              <Button type="button" variant="secondary" onClick={addEmail} disabled={pendingValid.length === 0}>
                Add
              </Button>
            </div>
            {emailError ? (
              <p className="mt-1.5 text-xs text-rose-600">{emailError}</p>
            ) : selected.length > 0 && pendingInvalid.length === 0 ? (
              <p className="mt-1.5 flex items-center gap-1.5 text-xs font-medium text-emerald-600">
                <FiCheck size={13} />
                Valid email addresses
              </p>
            ) : null}
          </div>

          <div>
            <div className="flex items-end justify-between gap-3">
              <FieldLabel htmlFor="email-subject" required>
                Email subject
              </FieldLabel>
              <span className={`mb-1.5 text-xs ${subject.length >= SUBJECT_LIMIT ? 'text-rose-500' : 'text-slate-400'}`}>
                {subject.length}/{SUBJECT_LIMIT}
              </span>
            </div>
            <input
              id="email-subject"
              className="control"
              value={subject}
              maxLength={SUBJECT_LIMIT}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>

          <div>
            <div className="flex items-end justify-between gap-3">
              <FieldLabel htmlFor="email-body" required>
                Email body
              </FieldLabel>
              <span className={`mb-1.5 text-xs ${body.length >= BODY_LIMIT ? 'text-rose-500' : 'text-slate-400'}`}>
                {body.length}/{BODY_LIMIT}
              </span>
            </div>
            <p className="mb-1.5 text-xs text-slate-500">Paste the email you sent.</p>
            <textarea
              id="email-body"
              ref={bodyRef}
              className="control min-h-[160px] resize-y py-2.5"
              value={body}
              maxLength={BODY_LIMIT}
              onChange={(e) => setBody(e.target.value)}
            />
            <p className="mt-1.5 text-xs text-slate-400">Plain text only.</p>
          </div>

          <div className="max-w-xs">
            <FieldLabel htmlFor="sent-date" required>
              Sent date
            </FieldLabel>
            <p className="mb-1.5 text-xs text-slate-500">
              The date the email was actually sent from Outlook or another mailbox.
            </p>
            <input
              id="sent-date"
              className="control"
              type="date"
              value={sentDate}
              onChange={(e) => {
                setSentDate(e.target.value);
                setFollowUpError('');
              }}
            />
          </div>
        </section>

        <section className="border-t border-slate-100 p-5 sm:p-6">
          <SectionHeading
            step="3"
            title="Follow-up"
            description="Optionally schedule the next follow-up action."
          />

          <button
            type="button"
            className="mt-4 flex w-full items-center justify-between rounded-xl border border-primary-100 bg-primary-50/50 px-4 py-3 text-left text-sm font-semibold text-primary-700 hover:bg-primary-50"
            aria-expanded={followUpOpen}
            onClick={() => {
              setFollowUpOpen((open) => !open);
              setFollowUpError('');
            }}
          >
            <span className="inline-flex items-center gap-2">
              <FiPlus size={15} />
              {followUpOpen ? 'Hide follow-up' : 'Add follow-up'}
            </span>
            <FiChevronDown size={16} className={`transition ${followUpOpen ? 'rotate-180' : ''}`} />
          </button>

          {followUpOpen ? (
            <div className="mt-4 space-y-4">
              <p className="text-xs text-slate-500">Optionally schedule the next action for this prospect.</p>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <FieldLabel htmlFor="follow-up-date" optional>
                    Next follow-up date
                  </FieldLabel>
                  <input
                    id="follow-up-date"
                    className="control"
                    type="date"
                    min={sentDate || undefined}
                    value={followUpDate}
                    onChange={(e) => {
                      setFollowUpDate(e.target.value);
                      setFollowUpError('');
                    }}
                  />
                </div>
                <div>
                  <FieldLabel htmlFor="follow-up-time" optional>
                    Next follow-up time
                  </FieldLabel>
                  <input
                    id="follow-up-time"
                    className="control"
                    type="time"
                    value={followUpTime}
                    onChange={(e) => {
                      setFollowUpTime(e.target.value);
                      setFollowUpError('');
                    }}
                  />
                </div>
              </div>
              <p className="text-xs text-slate-500">Times use {timezoneLabel}.</p>
              <div>
                <FieldLabel htmlFor="follow-up-action" optional>
                  Follow-up action
                </FieldLabel>
                <input
                  id="follow-up-action"
                  className="control"
                  value={followUpAction}
                  onChange={(e) => setFollowUpAction(e.target.value)}
                  placeholder="Call, send follow-up, connect on LinkedIn..."
                />
              </div>
              {followUpError || followUpBeforeSent ? (
                <p className="text-xs text-rose-600">
                  {followUpError || 'Follow-up date cannot be earlier than the sent date.'}
                </p>
              ) : scheduleHint ? (
                <p className="text-xs text-slate-500">{scheduleHint}</p>
              ) : null}
            </div>
          ) : null}
        </section>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-4 sm:px-6">
          <div className="min-w-0 text-sm text-slate-500">
            {!canSave && missing.length > 0 ? formatMissing(missing) : null}
            {followUpBeforeSent && missing.length === 0
              ? 'Follow-up date cannot be earlier than the sent date.'
              : null}
            {pendingInvalid.length > 0 && missing.length === 0 && !followUpBeforeSent
              ? 'Fix the recipient email before saving.'
              : null}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button variant="secondary" onClick={() => navigate('/campaigns')} disabled={Boolean(saving)}>
              Cancel
            </Button>
            {followUpOpen && schedulingSupported ? (
              <Button
                variant="secondary"
                loading={saving === 'schedule'}
                disabled={!canSchedule}
                onClick={() => handleSave(true)}
              >
                Save and schedule follow-up
              </Button>
            ) : null}
            <Button icon={FiSave} loading={saving === 'record'} disabled={!canSave} onClick={() => handleSave(false)}>
              Save email
            </Button>
          </div>
        </div>
      </form>
    </PageShell>
  );
}
