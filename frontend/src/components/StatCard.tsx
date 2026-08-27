interface StatCardProps {
  label: string;
  value: string | number;
  subtext?: string;
}

export function StatCard({ label, value, subtext }: StatCardProps) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
      {subtext && <p className="mt-1 text-xs text-slate-500">{subtext}</p>}
    </div>
  );
}
