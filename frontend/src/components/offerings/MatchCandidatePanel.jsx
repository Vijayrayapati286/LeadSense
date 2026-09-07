import { FiCheck, FiX } from 'react-icons/fi';
import SlideOver from '../ui/SlideOver';

const BREAKDOWN = [
  ['ICP Fit', 'icp_fit_score', 25],
  ['Problem Fit', 'problem_fit_score', 20],
  ['Role Fit', 'role_fit_score', 15],
  ['Industry Fit', 'industry_score', 15],
  ['Company Fit', 'company_fit_score', 10],
  ['Buying Signal', 'buying_signal_score', 10],
  ['Historical', 'historical_score', 5],
];

function tierLabel(score) {
  if (score >= 80) return 'Strong Match';
  if (score >= 65) return 'Good Match';
  if (score >= 50) return 'Possible Match';
  return 'Poor Match';
}

function tierColor(score) {
  if (score >= 80) return 'text-emerald-700';
  if (score >= 65) return 'text-sky-700';
  if (score >= 50) return 'text-amber-700';
  return 'text-red-600';
}

export default function MatchCandidatePanel({
  match,
  onClose,
  onApprove,
  onReject,
  onApproveAndNext,
}) {
  if (!match) return null;

  const reasons = match.match_reasons || [];
  const missing = match.missing_information || match.ai_analysis?.missing_information || [];
  const dims = match.ai_analysis?.dimensions || {};
  const explanation = match.explanation || match.ai_analysis?.explanation;

  return (
    <SlideOver
      isOpen={Boolean(match)}
      onClose={onClose}
      title={match.name || 'Candidate'}
      subtitle={[match.designation, match.company_name].filter(Boolean).join(' · ')}
      width="lg"
    >
      <div className="space-y-6">
        <div>
          <p className="text-sm text-gray-500">Offering Fit</p>
          <p className={`text-3xl font-semibold mt-1 ${tierColor(match.fit_score)}`}>
            {match.fit_score}%{' '}
            <span className="text-base font-medium">{tierLabel(match.fit_score)}</span>
          </p>
        </div>

        {match.about ? (
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-1">LinkedIn Summary</h3>
            <p className="text-sm text-gray-700 whitespace-pre-wrap">{match.about}</p>
          </div>
        ) : null}

        <div>
          <h3 className="text-sm font-semibold text-gray-900 mb-2">Why this candidate?</h3>
          <ul className="space-y-1.5">
            {reasons.length ? (
              reasons.map((r) => (
                <li key={r} className="flex items-start gap-2 text-sm text-gray-700">
                  <FiCheck className="text-emerald-600 mt-0.5 shrink-0" size={14} />
                  <span>{r}</span>
                </li>
              ))
            ) : (
              <li className="text-sm text-gray-400">No explanation available</li>
            )}
          </ul>
          {missing.length ? (
            <ul className="mt-3 space-y-1">
              {missing.map((m) => (
                <li key={m} className="text-sm text-amber-800">
                  ⚠ {m}
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        {explanation ? (
          <pre className="rounded-xl bg-gray-50 border border-gray-200 p-3 text-xs text-gray-700 whitespace-pre-wrap font-sans">
            {explanation}
          </pre>
        ) : null}

        <div>
          <h3 className="text-sm font-semibold text-gray-900 mb-2">Score Breakdown</h3>
          <div className="rounded-xl border border-gray-200 divide-y divide-gray-100">
            {BREAKDOWN.map(([label, key, weight]) => {
              const score = match[key] ?? 0;
              const dimKey = key.replace('_score', '').replace('industry', 'industry_fit');
              const reason =
                dims[`${dimKey}_match`]?.reason ||
                dims[`${key.replace('_score', '')}_match`]?.reason;
              return (
                <div key={key} className="px-3 py-2.5">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-700">
                      {label}{' '}
                      <span className="text-xs text-gray-400">({weight}%)</span>
                    </span>
                    <span className="font-medium text-gray-900">{score}/100</span>
                  </div>
                  <div className="mt-1.5 h-1.5 rounded-full bg-gray-100 overflow-hidden">
                    <div
                      className="h-full bg-primary-500 rounded-full"
                      style={{ width: `${Math.min(100, score)}%` }}
                    />
                  </div>
                  {reason ? <p className="text-xs text-gray-500 mt-1">{reason}</p> : null}
                </div>
              );
            })}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 pt-2">
          <button
            type="button"
            onClick={onReject}
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <FiX size={16} /> Reject
          </button>
          <button
            type="button"
            onClick={onApprove}
            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-300 bg-white px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50"
          >
            <FiCheck size={16} /> Approve
          </button>
          {onApproveAndNext ? (
            <button
              type="button"
              onClick={onApproveAndNext}
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 text-white px-4 py-2 text-sm font-medium hover:bg-emerald-700"
            >
              <FiCheck size={16} /> Keep &amp; Next
            </button>
          ) : null}
        </div>
      </div>
    </SlideOver>
  );
}
