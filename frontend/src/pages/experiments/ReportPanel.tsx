import { Badge } from '../../components/Badge';
import { Card } from '../../components/Card';
import { formatTimestamp } from '../benchmark/format';
import { experimentTypeBadge, experimentTypeLabel } from './format';
import { SectionResults } from './SectionResults';
import type { ExperimentReport } from '../../types';

interface ReportPanelProps {
  report: ExperimentReport;
  heading?: string;
}

export function ReportPanel({ report, heading }: ReportPanelProps) {
  const observations = report.summary
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

  return (
    <div className="space-y-6">
      {heading && <h3 className="text-sm font-medium text-ink-primary">{heading}</h3>}

      {/* Configuration + Execution: what was requested vs. what actually ran */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink-disabled">Configuration</h4>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-ink-muted">Experiment Type</dt>
              <dd>
                <Badge variant={experimentTypeBadge(report.experiment_type)}>
                  {experimentTypeLabel(report.experiment_type)}
                </Badge>
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-muted">Dataset</dt>
              <dd className="max-w-[220px] truncate font-mono text-xs text-ink-primary" title={report.dataset_path}>
                {report.dataset_path}
              </dd>
            </div>
          </dl>
          <p className="mt-3 text-xs text-ink-muted">
            Per-variant configuration (quality floor, strategy, or router type) is listed in each result table&rsquo;s
            Config column below.
          </p>
        </Card>

        <Card>
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink-disabled">Execution</h4>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-ink-muted">Run Name</dt>
              <dd className="text-ink-primary">{report.name}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-muted">Completed</dt>
              <dd className="text-ink-primary">{formatTimestamp(report.created_at)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-muted">Sections Run</dt>
              <dd className="text-ink-primary">{report.sections.length}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-muted">Report ID</dt>
              <dd className="max-w-[160px] truncate font-mono text-xs text-ink-primary" title={report.id}>
                {report.id}
              </dd>
            </div>
          </dl>
        </Card>
      </div>

      {/* Results: what was measured */}
      <div className="space-y-6">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-disabled">Results</h4>
        {report.sections.length === 0 ? (
          <p className="text-sm text-ink-muted">This run produced no sections.</p>
        ) : (
          report.sections.map((section) => <SectionResults key={section.name} section={section} />)
        )}
      </div>

      {observations.length > 0 && (
        <Card>
          <h4 className="mb-3 text-sm font-medium text-ink-primary">Experiment Observations</h4>
          <ul className="space-y-1.5 text-sm text-ink-secondary">
            {observations.map((line) => (
              <li key={line} className="flex gap-2">
                <span className="text-brand-400">•</span>
                <span>{line}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11px] text-ink-disabled">
            Generated directly from this run&rsquo;s measured metrics — not a general claim about routing strategies.
          </p>
        </Card>
      )}
    </div>
  );
}
