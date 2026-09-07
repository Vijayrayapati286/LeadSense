export default function WorkflowStepper({ steps, activeStepId }) {
  const activeIndex = steps.findIndex((s) => s.id === activeStepId);

  return (
    <nav aria-label="Progress" className="w-full max-w-3xl mx-auto">
      <ol className="flex">
        {steps.map((step, index) => {
          const isComplete = index < activeIndex;
          const isActive = index === activeIndex;
          const isUpcoming = index > activeIndex;

          return (
            <li
              key={step.id}
              className={`flex flex-col items-center ${index < steps.length - 1 ? 'flex-1' : 'shrink-0'}`}
            >
              <div className="flex w-full items-center">
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

                {index < steps.length - 1 ? (
                  <div
                    className={`mx-2 h-0.5 min-w-[1rem] flex-1 rounded-full sm:mx-3 ${
                      index < activeIndex ? 'bg-primary-300' : 'bg-slate-200'
                    }`}
                    aria-hidden
                  />
                ) : null}
              </div>

              <span
                className={`mt-2 w-full max-w-[7.5rem] px-1 text-center text-xs font-semibold leading-tight sm:max-w-[9rem] sm:text-sm ${
                  isActive ? 'text-primary-700' : isUpcoming ? 'text-slate-400' : 'text-slate-600'
                }`}
              >
                {step.label}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
