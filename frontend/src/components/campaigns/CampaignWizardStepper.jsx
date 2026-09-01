const STEPS = [
  { id: 'campaign', label: 'Campaign Information' },
  { id: 'template', label: 'Audience & Targeting' },
  { id: 'review', label: 'Review & Launch' },
];

export default function CampaignWizardStepper({ activeStep }) {
  const activeIndex = STEPS.findIndex((s) => s.id === activeStep);

  return (
    <div className="flex items-center justify-center gap-0 w-full max-w-3xl mx-auto">
      {STEPS.map((step, index) => {
        const isComplete = index < activeIndex;
        const isActive = index === activeIndex;
        const isUpcoming = index > activeIndex;

        return (
          <div key={step.id} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-2 min-w-0">
              <div
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold transition-colors ${
                  isActive
                    ? 'bg-primary-600 text-white shadow-md shadow-primary-500/30'
                    : isComplete
                      ? 'bg-primary-100 text-primary-700'
                      : 'bg-slate-100 text-slate-400'
                }`}
              >
                {isComplete ? '✓' : index + 1}
              </div>
              <span
                className={`text-xs font-semibold text-center leading-tight max-w-[7rem] sm:max-w-none sm:text-sm ${
                  isActive ? 'text-primary-700' : isUpcoming ? 'text-slate-400' : 'text-slate-600'
                }`}
              >
                {step.label}
              </span>
            </div>
            {index < STEPS.length - 1 ? (
              <div
                className={`h-0.5 flex-1 mx-3 sm:mx-5 mb-6 rounded-full ${
                  index < activeIndex ? 'bg-primary-300' : 'bg-slate-200'
                }`}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
