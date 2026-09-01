import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiCheck, FiEdit2, FiExternalLink, FiPlus, FiSend, FiX } from 'react-icons/fi';
import SlideOver from '../ui/SlideOver';
import { icpService, offeringsService } from '../../services/services';
import { useToast } from '../../hooks/useToast';

function Field({ label, value }) {
  if (value == null || value === '') {
    return (
      <div>
        <dt className="text-[11px] uppercase tracking-wide text-gray-400">{label}</dt>
        <dd className="mt-0.5 text-sm text-gray-400">—</dd>
      </div>
    );
  }
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-gray-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-gray-900 whitespace-pre-wrap break-words">{value}</dd>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 border-b border-slate-100 pb-2">
        {title}
      </p>
      <dl className="space-y-3">{children}</dl>
    </section>
  );
}

function tierLabel(score) {
  if (score >= 80) return 'Strong Match';
  if (score >= 65) return 'Good Match';
  if (score >= 50) return 'Possible Match';
  return 'Low Match';
}

function tierColor(score) {
  if (score >= 80) return 'text-emerald-700 bg-emerald-50 border-emerald-200';
  if (score >= 65) return 'text-sky-700 bg-sky-50 border-sky-200';
  if (score >= 50) return 'text-amber-800 bg-amber-50 border-amber-200';
  return 'text-gray-600 bg-gray-50 border-gray-200';
}

export default function IcpRecordDetail({ record, isOpen, onClose, onSaved, focusOfferings = false }) {
  const toast = useToast();
  const offeringsRef = useRef(null);  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({});
  const [offeringMatches, setOfferingMatches] = useState([]);
  const [sortBy, setSortBy] = useState('fit_score');
  const [busyMatchId, setBusyMatchId] = useState(null);

  useEffect(() => {
    if (!record) return;
    setEditing(false);
    setForm({
      name: record.name || '',
      company_name: record.company_name || '',
      designation: record.designation || '',
      about: record.about || '',
      industry: record.industry || '',
      company_size: record.company_size || '',
      location: record.location || '',
      company_website: record.company_website || '',
      linkedin_url: record.linkedin_url || '',
      icp_status: record.icp_status || 'verified',
      icp_score: record.icp_score ?? '',
    });
    loadRecommendations(record.id, sortBy);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [record?.id]);

  useEffect(() => {
    if (!record?.id) return;
    loadRecommendations(record.id, sortBy);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortBy]);

  useEffect(() => {
    if (!isOpen || !focusOfferings) return;
    const timer = setTimeout(() => {
      offeringsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 150);
    return () => clearTimeout(timer);
  }, [isOpen, focusOfferings, record?.id]);

  function loadRecommendations(icpId, sort) {
    offeringsService
      .matchesForIcp(icpId, { min_score: 50, limit: 5, sort_by: sort })
      .then((data) => setOfferingMatches(data.items || []))
      .catch(() => setOfferingMatches([]));
  }

  if (!record) return null;

  async function save() {
    setSaving(true);
    try {
      const payload = {
        ...form,
        icp_score: form.icp_score === '' || form.icp_score == null ? null : Number(form.icp_score),
      };
      const updated = await icpService.update(record.id, payload);
      toast.success('ICP record updated');
      setEditing(false);
      onSaved?.(updated);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to update ICP record');
    } finally {
      setSaving(false);
    }
  }

  async function handleFeedback(matchId, action) {
    setBusyMatchId(matchId);
    try {
      await offeringsService.feedback(matchId, action);
      toast.success(action === 'accepted' || action === 'recommended' ? 'Saved' : 'Updated');
      loadRecommendations(record.id, sortBy);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Feedback failed');
    } finally {
      setBusyMatchId(null);
    }
  }

  function setField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  const title = record.name || 'ICP Record';
  const subtitle = [record.designation, record.company_name].filter(Boolean).join(' · ');

  return (
    <SlideOver isOpen={isOpen} onClose={onClose} title={title} subtitle={subtitle} width="lg">
      <div className="space-y-6">
        {!editing ? (
          <>
            <div className="rounded-2xl bg-gradient-to-br from-slate-900 to-slate-800 p-5 text-white">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary-300">ICP confidence</p>
                  <p className="mt-2 text-3xl font-bold">{record.icp_score ?? '—'}{record.icp_score != null ? '%' : ''}</p>
                  <p className="mt-1 text-sm text-slate-300">{record.icp_status || 'Status not set'}</p>
                </div>
                <button type="button" onClick={() => setEditing(true)} className="inline-flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2 text-sm font-semibold hover:bg-white/20">
                  <FiEdit2 size={15} /> Edit record
                </button>
              </div>
            </div>
            {record.about ? (
              <Section title="LinkedIn Summary">
                <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
                  {record.about}
                </p>
              </Section>
            ) : (
              <div className="rounded-xl border border-dashed border-amber-200 bg-amber-50/60 px-3 py-2 text-sm text-amber-900">
                No LinkedIn summary on this record yet — problem-fit scoring will be weaker.
              </div>
            )}

            <section ref={offeringsRef} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 border-b border-slate-100 pb-2">
                Recommended Offerings
              </p>
              <div className="flex items-center justify-between gap-2 mb-2">
                <p className="text-xs text-gray-500">Top matches for this contact</p>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="rounded-md border border-gray-200 bg-white px-2 py-1 text-xs"
                >
                  <option value="fit_score">Match Score</option>
                  <option value="strongest">Strongest Match</option>
                  <option value="recently_added">Recently Added</option>
                </select>
              </div>
              {offeringMatches.length === 0 ? (
                <p className="text-sm text-gray-400">No high-confidence offering matches yet.</p>
              ) : (
                <ul className="space-y-3">
                  {offeringMatches.map((m) => (
                    <li
                      key={m.match_id}
                      className={`rounded-xl border p-3 ${tierColor(m.fit_score)}`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-semibold text-sm truncate">{m.offering_name}</p>
                          <p className="text-xs mt-0.5 opacity-80">
                            {m.fit_score}% · {tierLabel(m.fit_score)}
                          </p>
                        </div>
                      </div>
                      <ul className="mt-2 space-y-1">
                        {(m.match_reasons || []).slice(0, 4).map((r) => (
                          <li key={r} className="flex items-start gap-1.5 text-xs">
                            <FiCheck size={12} className="mt-0.5 shrink-0" />
                            <span>{r}</span>
                          </li>
                        ))}
                      </ul>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Link
                          to={`/offerings/${m.offering_id}?tab=matching`}
                          className="rounded-md border border-current/20 bg-white/70 px-2.5 py-1 text-xs font-medium hover:bg-white"
                        >
                          View Details
                        </Link>
                        <button
                          type="button"
                          disabled={busyMatchId === m.match_id}
                          onClick={() => handleFeedback(m.match_id, 'recommended')}
                          className="inline-flex items-center gap-1 rounded-md bg-primary-600 text-white px-2.5 py-1 text-xs font-medium hover:bg-primary-700 disabled:opacity-50"
                        >
                          <FiSend size={12} /> Send Match
                        </button>
                        <button
                          type="button"
                          disabled={busyMatchId === m.match_id}
                          onClick={() => handleFeedback(m.match_id, 'rejected')}
                          className="inline-flex items-center gap-1 rounded-md border border-current/20 bg-white/70 px-2.5 py-1 text-xs font-medium hover:bg-white disabled:opacity-50"
                        >
                          <FiPlus size={12} /> Not a Match
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <Section title="Person">
              <Field label="Name" value={record.name} />
              <Field label="Designation" value={record.designation} />
            </Section>
            <Section title="Company">
              <Field label="Company" value={record.company_name} />
              <Field label="Industry" value={record.industry} />
              <Field label="Company Size" value={record.company_size} />
              <Field label="Location" value={record.location} />
              <Field label="Website" value={record.company_website} />
            </Section>
            <Section title="ICP">
              <Field label="ICP Status" value={record.icp_status} />
              <Field label="ICP Score" value={record.icp_score} />
              <Field
                label="Tags"
                value={(record.tags || []).length ? record.tags.join(', ') : null}
              />
            </Section>
            <Section title="Source">
              {record.linkedin_url ? (
                <div>
                  <dt className="text-[11px] uppercase tracking-wide text-gray-400">LinkedIn URL</dt>
                  <dd className="mt-0.5 text-sm">
                    <a
                      href={record.linkedin_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary-600 hover:underline inline-flex items-center gap-1 break-all"
                    >
                      {record.linkedin_url}
                      <FiExternalLink size={12} />
                    </a>
                  </dd>
                </div>
              ) : (
                <Field label="LinkedIn URL" value={null} />
              )}
              <Field label="Source" value={record.source} />
            </Section>
            <Section title="Verification">
              <div className={`flex items-center gap-2 text-sm font-medium ${(record.icp_status || 'verified').toLowerCase() === 'verified' ? 'text-green-700' : 'text-amber-700'}`}>
                <FiCheck /> {record.icp_status || 'Verified'}
              </div>
              <Field
                label="Verified At"
                value={
                  record.verified_at
                    ? new Date(record.verified_at).toLocaleString()
                    : null
                }
              />
              <Field label="Verification Status" value={record.verification_status} />
            </Section>
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              <FiEdit2 size={14} /> Edit Record
            </button>
          </>
        ) : (
          <div className="space-y-3">
            {[
              ['name', 'Name'],
              ['company_name', 'Company'],
              ['designation', 'Designation'],
              ['industry', 'Industry'],
              ['company_size', 'Company Size'],
              ['location', 'Location'],
              ['company_website', 'Website'],
              ['linkedin_url', 'LinkedIn URL'],
              ['icp_status', 'ICP Status'],
              ['icp_score', 'ICP Score'],
            ].map(([key, label]) => (
              <label key={key} className="block">
                <span className="text-xs font-medium text-gray-500">{label}</span>
                <input
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  value={form[key] ?? ''}
                  onChange={(e) => setField(key, e.target.value)}
                />
              </label>
            ))}
            <label className="block">
              <span className="text-xs font-medium text-gray-500">LinkedIn Summary</span>
              <textarea
                rows={4}
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                value={form.about || ''}
                onChange={(e) => setField('about', e.target.value)}
              />
            </label>
            <div className="flex gap-2 pt-2">
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
              >
                <FiX size={14} /> Cancel
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={save}
                className="inline-flex items-center gap-1 rounded-lg bg-primary-600 text-white px-4 py-2 text-sm font-medium hover:bg-primary-700 disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>
        )}
      </div>
    </SlideOver>
  );
}
