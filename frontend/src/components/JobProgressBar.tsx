interface JobProgressBarProps {
  progress: number;
  label?: string;
}

export function JobProgressBar({ progress, label = 'Running...' }: JobProgressBarProps) {
  const pct = Math.round(Math.min(1, Math.max(0, progress)) * 100);

  return (
    <div className="mb-4 rounded-lg border border-brand-500/30 bg-brand-500/10 px-4 py-3">
      <div className="mb-2 flex items-center justify-between text-sm text-brand-100">
        <span>{label}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-800">
        <div
          className="h-full rounded-full bg-brand-500 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
