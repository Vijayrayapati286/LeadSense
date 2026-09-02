import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  FiArrowLeft,
  FiCheck,
  FiRefreshCw,
  FiDatabase,
  FiSend,
  FiX,
} from 'react-icons/fi';
import MatchCandidatePanel from '../components/offerings/MatchCandidatePanel';
import IcpDatabasePicker from '../components/offerings/IcpDatabasePicker';
import OfferingEmailSummary from '../components/offerings/OfferingEmailSummary';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import PageShell from '../components/ui/PageShell';
import Pagination from '../components/ui/Pagination';
import SearchInput from '../components/ui/SearchInput';
import { useToast } from '../hooks/useToast';
import { offeringsService } from '../services/services';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'matching', label: 'Matching Results' },
];

const PAGE_SIZE = 25;
const OFFERING_SEND_KEY = 'leadsense_offering_send_offer';

function ChipList({ items }) {
  if (!items?.length) return <p className="text-sm text-gray-400">None defined</p>;
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <span
          key={item}
          className="inline-flex rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function scoreColor(score) {
  if (score >= 80) return 'text-emerald-600';
  if (score >= 50) return 'text-amber-600';
  return 'text-red-500';
}

function scoreDot(score) {
  if (score >= 80) return '🟢';
  if (score >= 50) return '🟡';
  return '🔴';
}

export default function OfferingDetailPage() {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabRaw = searchParams.get('tab') || 'overview';
  const tab = ['overview', 'matching'].includes(tabRaw) ? tabRaw : 'overview';
  const toast = useToast();
  const navigate = useNavigate();

  const [offering, setOffering] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [matchStatus, setMatchStatus] = useState(null);
  const [matching, setMatching] = useState(false);

  const [matches, setMatches] = useState([]);
  const [matchTotal, setMatchTotal] = useState(0);
  const [matchPage, setMatchPage] = useState(1);
  const [matchLoading, setMatchLoading] = useState(false);
  const [tierFilter, setTierFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortBy, setSortBy] = useState('fit_score');
  const [search, setSearch] = useState('');
  const [selectedMatch, setSelectedMatch] = useState(null);
  const [selectFirstAfterLoad, setSelectFirstAfterLoad] = useState(false);
  const [selectedMatchIds, setSelectedMatchIds] = useState(() => new Set());
  const [selectedIcpIds, setSelectedIcpIds] = useState(() => new Set());
  const [icpPickerOpen, setIcpPickerOpen] = useState(false);

  const setTab = (next) => {
    const params = new URLSearchParams(searchParams);
    params.set('tab', next);
    setSearchParams(params);
  };

  const loadOffering = useCallback(async () => {
    setLoading(true);
    try {
      const [o, s, st] = await Promise.all([
        offeringsService.get(id),
        offeringsService.stats(id),
        offeringsService.matchingStatus(id),
      ]);
      setOffering(o);
      setStats(s);
      setMatchStatus(st);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load offering');
      navigate('/offerings');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const loadMatches = useCallback(async () => {
    setMatchLoading(true);
    try {
      const data = await offeringsService.listMatches(id, {
        page: matchPage,
        limit: PAGE_SIZE,
        match_tier: tierFilter || undefined,
        status: statusFilter || undefined,
        sort_by: sortBy,
        search: search || undefined,
      });
      setMatches(data.items || []);
      setMatchTotal(data.total || 0);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to load matches');
    } finally {
      setMatchLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, matchPage, tierFilter, statusFilter, sortBy, search]);

  useEffect(() => {
    loadOffering();
  }, [loadOffering]);

  useEffect(() => {
    if (tab === 'matching') loadMatches();
  }, [tab, loadMatches]);

  useEffect(() => {
    if (!selectFirstAfterLoad || matchLoading || matches.length === 0) return;
    setSelectedMatch(matches[0]);
    setSelectFirstAfterLoad(false);
  }, [selectFirstAfterLoad, matchLoading, matches]);

  // Poll while matching
  useEffect(() => {
    if (!matchStatus || !['pending', 'running'].includes(matchStatus.status)) return undefined;
    const t = setInterval(async () => {
      try {
        const st = await offeringsService.matchingStatus(id);
        setMatchStatus(st);
        if (st.status === 'done' || st.status === 'failed') {
          const s = await offeringsService.stats(id);
          setStats(s);
          if (tab === 'matching') loadMatches();
          if (st.status === 'done') toast.success('Matching complete');
          if (st.status === 'failed') toast.error(st.error || 'Matching failed');
        }
      } catch {
        /* ignore poll errors */
      }
    }, 1500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchStatus?.status, id, tab]);

  async function handleFindCandidates(force = false) {
    setMatching(true);
    try {
      const st = await offeringsService.startMatch(id, force);
      setMatchStatus(st);
      setTab('matching');
      toast.info('Matching candidates in the background…');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to start matching');
    } finally {
      setMatching(false);
    }
  }

  async function handleApprove(match) {
    try {
      const updated = await offeringsService.approveMatch(id, match.id);
      toast.success('Candidate approved — linked to Verified ICP');
      setSelectedMatch(updated);
      loadMatches();
      const s = await offeringsService.stats(id);
      setStats(s);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Approve failed');
    }
  }

  async function handleApproveAndNext(match) {
    const idx = matches.findIndex((m) => m.id === match.id);
    const hasNextOnPage = idx >= 0 && idx < matches.length - 1;
    const hasNextPage = matchPage * PAGE_SIZE < matchTotal;

    try {
      await offeringsService.approveMatch(id, match.id);
      toast.success('Candidate kept — linked to Verified ICP');

      if (hasNextOnPage) {
        setSelectedMatch(matches[idx + 1]);
      } else if (hasNextPage) {
        setSelectedMatch(null);
        setSelectFirstAfterLoad(true);
        setMatchPage((p) => p + 1);
      } else {
        setSelectedMatch(null);
        toast.info('All candidates reviewed');
      }

      loadMatches();
      const s = await offeringsService.stats(id);
      setStats(s);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Approve failed');
    }
  }

  async function handleReject(match) {
    try {
      const updated = await offeringsService.rejectMatch(id, match.id);
      toast.success('Candidate rejected');
      setSelectedMatch(updated);
      loadMatches();
      const s = await offeringsService.stats(id);
      setStats(s);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Reject failed');
    }
  }

  const isMatching = useMemo(
    () => matchStatus && ['pending', 'running'].includes(matchStatus.status),
    [matchStatus],
  );

  const pageMatchIds = useMemo(() => matches.map((m) => m.id), [matches]);
  const allOnPageSelected = pageMatchIds.length > 0 && pageMatchIds.every((id) => selectedMatchIds.has(id));
  const someOnPageSelected = pageMatchIds.some((id) => selectedMatchIds.has(id));

  function toggleMatchSelection(matchId, checked) {
    setSelectedMatchIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(matchId);
      else next.delete(matchId);
      return next;
    });
  }

  function toggleSelectAllOnPage() {
    setSelectedMatchIds((prev) => {
      const next = new Set(prev);
      if (allOnPageSelected) {
        pageMatchIds.forEach((matchId) => next.delete(matchId));
      } else {
        pageMatchIds.forEach((matchId) => next.add(matchId));
      }
      return next;
    });
  }

  function toggleIcpSelection(icpId, checked) {
    setSelectedIcpIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(icpId);
      else next.delete(icpId);
      return next;
    });
  }

  const totalSelectedCount = selectedMatchIds.size + selectedIcpIds.size;

  function handleSendOffer() {
    if (totalSelectedCount === 0) {
      toast.error('Select at least one candidate or ICP contact to send an offer');
      return;
    }

    const payload = {
      offeringId: Number(id),
      offeringName: offering.name,
      offeringDescription: offering.description || offering.short_description || '',
      matchIds: [...selectedMatchIds],
      icpRecordIds: [...selectedIcpIds],
      prospectCount: totalSelectedCount,
    };

    sessionStorage.setItem(OFFERING_SEND_KEY, JSON.stringify(payload));
    navigate('/campaigns/create', { state: { offeringSendOffer: payload } });
  }

  if (loading || !offering) {
    return (
      <div className="flex justify-center py-20">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <PageShell maxWidth="max-w-7xl">
      <PageHeader
        eyebrow="Offering studio"
        title={offering.name}
        subtitle={offering.short_description || offering.description || 'No description'}
        actions={
        <div className="flex flex-wrap gap-2">
          <Link to="/offerings" className="btn-secondary inline-flex items-center gap-2">
            <FiArrowLeft size={16} /> Back
          </Link>
          <Link
            to={`/offerings/${id}/edit`}
            className="btn-secondary"
          >
            Edit
          </Link>
          <button
            type="button"
            disabled={matching || isMatching}
            onClick={() => handleFindCandidates(false)}
            className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
          >
            <FiRefreshCw size={14} className={isMatching ? 'animate-spin' : ''} />
            {isMatching ? 'Matching…' : 'Find Best Candidates'}
          </button>
        </div>
        }
      />

      {stats ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            ['Total Candidates', stats.total_candidates],
            ['Strong Matches', stats.strong_matches],
            ['Potential', stats.potential_matches],
            ['Approved', stats.approved],
            ['Pending Review', stats.pending_review],
            ['Rejected', stats.rejected],
          ].map(([label, value]) => (
            <div key={label} className="min-h-[88px] rounded-2xl border border-slate-200/80 bg-white px-4 py-3 shadow-sm">
              <p className="text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400">{label}</p>
              <p className="mt-1 text-2xl font-bold text-slate-950">{(value || 0).toLocaleString()}</p>
            </div>
          ))}
        </div>
      ) : null}

      {isMatching ? (
        <div className="rounded-xl border border-primary-200 bg-primary-50 px-4 py-3">
          <p className="text-sm font-medium text-primary-900">Matching Candidates…</p>
          <div className="mt-2 h-2 rounded-full bg-primary-100 overflow-hidden">
            <div
              className="h-full bg-primary-600 transition-all"
              style={{ width: `${matchStatus.percent || 0}%` }}
            />
          </div>
          <p className="text-xs text-primary-800 mt-2">
            {matchStatus.processed_count || 0} / {matchStatus.total_count || 0} processed ·{' '}
            {matchStatus.strong_count || 0} strong matches found · {matchStatus.percent || 0}%
          </p>
        </div>
      ) : null}

      <div className="flex gap-1 overflow-x-auto border-b border-gray-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 -mb-px ${
              tab === t.id
                ? 'border-primary-600 text-primary-700'
                : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="rounded-2xl border border-gray-200 bg-white p-5 space-y-5">
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-1">Description</h3>
            <p className="text-sm text-gray-600 whitespace-pre-wrap">
              {offering.description || offering.short_description || '—'}
            </p>
          </div>
          <div className="grid sm:grid-cols-2 gap-5">
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-2">Target Industries</h3>
              <ChipList items={offering.target_industries} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-2">Target Buyers</h3>
              <ChipList items={offering.target_job_titles} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-2">Pain Points</h3>
              <ChipList items={offering.pain_points} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-2">Use Cases</h3>
              <ChipList items={offering.use_cases} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-2">Benefits</h3>
              <ChipList items={offering.benefits} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-2">Buying Signals</h3>
              <ChipList
                items={[
                  ...(offering.buying_roles || []),
                  ...(offering.decision_maker_types || []),
                ]}
              />
            </div>
          </div>
          <OfferingEmailSummary offering={offering} />
          <div className="grid sm:grid-cols-3 gap-4 text-sm border-t border-gray-100 pt-4">
            <div>
              <p className="text-xs text-gray-400 uppercase">Company size</p>
              <p className="font-medium text-gray-800 mt-0.5">
                {offering.company_size_label ||
                  [offering.company_size_min, offering.company_size_max]
                    .filter((v) => v != null)
                    .join(' – ') ||
                  '—'}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase">Geography</p>
              <p className="font-medium text-gray-800 mt-0.5">
                {(offering.target_geographies || []).slice(0, 4).join(', ') || '—'}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase">Status</p>
              <p className="font-medium text-gray-800 mt-0.5 capitalize">{offering.status || '—'}</p>
            </div>
          </div>
        </div>
      )}

      {tab === 'matching' && (
        <div className="space-y-4">
          <div className="flex flex-col lg:flex-row gap-3 lg:items-center lg:justify-between">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-lg font-semibold text-gray-900">Best Candidates</h2>
              {totalSelectedCount > 0 ? (
                <span className="rounded-full bg-primary-50 px-2.5 py-1 text-xs font-medium text-primary-700">
                  {totalSelectedCount} selected
                  {selectedIcpIds.size > 0 ? ` (${selectedIcpIds.size} from database)` : ''}
                </span>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setIcpPickerOpen(true)}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                <FiDatabase size={14} />
                Add from ICP Database
                {selectedIcpIds.size > 0 ? ` (${selectedIcpIds.size})` : ''}
              </button>
              <button
                type="button"
                disabled={totalSelectedCount === 0}
                onClick={handleSendOffer}
                className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <FiSend size={14} />
                Send Offer{totalSelectedCount > 0 ? ` (${totalSelectedCount})` : ''}
              </button>
              <div className="flex flex-wrap gap-2">
              {[
                ['', 'All'],
                ['strong', 'Strong Match'],
                ['potential', 'Potential'],
                ['poor', 'Poor Match'],
              ].map(([value, label]) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => {
                    setTierFilter(value);
                    setMatchPage(1);
                  }}
                  className={`rounded-full px-3 py-1 text-xs font-medium border ${
                    tierFilter === value
                      ? 'bg-primary-600 text-white border-primary-600'
                      : 'bg-white text-gray-600 border-gray-300'
                  }`}
                >
                  {label}
                </button>
              ))}
              </div>
            </div>
          </div>

          <div className="flex flex-col md:flex-row gap-3">
            <SearchInput
              className="flex-1"
              value={search}
              placeholder="Search name, company, designation…"
              onChange={(val) => {
                setSearch(val);
                setMatchPage(1);
              }}
            />
            <select
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setMatchPage(1);
              }}
            >
              <option value="">All statuses</option>
              <option value="ai_matched">AI Matched</option>
              <option value="needs_review">Needs Review</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
            <select
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
            >
              <option value="fit_score">Highest Match</option>
              <option value="lowest">Lowest Match</option>
              <option value="recently_matched">Recently Matched</option>
              <option value="recently_added">Recently Added</option>
            </select>
          </div>

          {matchLoading ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : matches.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-gray-300 bg-white px-6 py-14 text-center">
              <h3 className="text-lg font-semibold text-gray-900">No matching results yet</h3>
              <p className="text-sm text-gray-500 mt-2 max-w-md mx-auto">
                Run the matching engine to find the best candidates from your ICP database.
              </p>
              <button
                type="button"
                disabled={matching || isMatching}
                onClick={() => handleFindCandidates(false)}
                className="mt-5 inline-flex items-center gap-2 rounded-lg bg-primary-600 text-white px-4 py-2 text-sm font-medium hover:bg-primary-700 disabled:opacity-60"
              >
                Find Best Candidates
              </button>
            </div>
          ) : (
            <div className="rounded-2xl border border-gray-200 bg-white overflow-hidden">
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                      <th className="w-10 px-4 py-3">
                        <input
                          type="checkbox"
                          className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                          checked={allOnPageSelected}
                          ref={(el) => {
                            if (el) el.indeterminate = someOnPageSelected && !allOnPageSelected;
                          }}
                          onChange={toggleSelectAllOnPage}
                          aria-label="Select all candidates on this page"
                        />
                      </th>
                      <th className="px-4 py-3">Name</th>
                      <th className="px-4 py-3">Company</th>
                      <th className="px-4 py-3">Designation</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3 text-right">Fit Score</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {matches.map((m) => (
                      <tr
                        key={m.id}
                        className={`hover:bg-gray-50 cursor-pointer ${
                          selectedMatchIds.has(m.id) ? 'bg-primary-50/40' : ''
                        }`}
                        onClick={() => setSelectedMatch(m)}
                      >
                        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                            checked={selectedMatchIds.has(m.id)}
                            onChange={(e) => toggleMatchSelection(m.id, e.target.checked)}
                            aria-label={`Select ${m.name || 'candidate'}`}
                          />
                        </td>
                        <td className="px-4 py-3 font-medium text-gray-900">{m.name || '—'}</td>
                        <td className="px-4 py-3 text-gray-600">{m.company_name || '—'}</td>
                        <td className="px-4 py-3 text-gray-600">{m.designation || '—'}</td>
                        <td className="px-4 py-3">
                          <StatusPill status={m.status} />
                        </td>
                        <td className={`px-4 py-3 text-right font-semibold ${scoreColor(m.fit_score)}`}>
                          {m.fit_score}% {scoreDot(m.fit_score)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="px-4 py-3 border-t border-gray-100">
                <Pagination
                  page={matchPage}
                  pageSize={PAGE_SIZE}
                  total={matchTotal}
                  onPageChange={setMatchPage}
                />
              </div>
            </div>
          )}
        </div>
      )}

      <MatchCandidatePanel
        match={selectedMatch}
        onClose={() => setSelectedMatch(null)}
        onApprove={() => handleApprove(selectedMatch)}
        onApproveAndNext={() => handleApproveAndNext(selectedMatch)}
        onReject={() => handleReject(selectedMatch)}
      />

      <IcpDatabasePicker
        isOpen={icpPickerOpen}
        onClose={() => setIcpPickerOpen(false)}
        selectedIds={selectedIcpIds}
        onToggle={toggleIcpSelection}
        onConfirm={() => {
          setIcpPickerOpen(false);
          if (selectedIcpIds.size > 0) {
            toast.success(`${selectedIcpIds.size} contact(s) added from ICP database`);
          }
        }}
      />
    </PageShell>
  );
}

function StatusPill({ status }) {
  const map = {
    approved: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    rejected: 'bg-red-50 text-red-700 border-red-200',
    needs_review: 'bg-amber-50 text-amber-800 border-amber-200',
    ai_matched: 'bg-blue-50 text-blue-700 border-blue-200',
    new: 'bg-gray-50 text-gray-600 border-gray-200',
  };
  const cls = map[status] || map.new;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status === 'approved' ? <FiCheck size={12} /> : null}
      {status === 'rejected' ? <FiX size={12} /> : null}
      {(status || 'new').replace(/_/g, ' ')}
    </span>
  );
}
