import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Card } from '../../components/Card';
import { ChartCard } from '../../components/ChartCard';
import type { TrainedModelInfo } from '../../types';
import {
  CHART_AXIS_COLOR,
  CHART_GRID_COLOR,
  CHART_TOOLTIP_ITEM,
  CHART_TOOLTIP_LABEL,
  CHART_TOOLTIP_STYLE,
  formatPercent,
} from './format';

interface TrainingMetricsChartsProps {
  metrics: TrainedModelInfo['metrics'];
}

export function TrainingMetricsCharts({ metrics }: TrainingMetricsChartsProps) {
  const accuracyRows = [
    { name: 'Train', value: metrics.train_accuracy * 100 },
    { name: 'Validation', value: metrics.validation_accuracy * 100 },
    { name: 'Test', value: metrics.test_accuracy * 100 },
  ];
  const qualityRows = [
    { name: 'Precision', value: metrics.precision * 100 },
    { name: 'Recall', value: metrics.recall * 100 },
    { name: 'F1', value: metrics.f1 * 100 },
  ];
  const confusion = metrics.confusion_matrix;
  const confusionTotal =
    confusion.true_negative + confusion.false_positive + confusion.false_negative + confusion.true_positive;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ChartCard title="Accuracy by split">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={accuracyRows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} />
            <XAxis dataKey="name" stroke={CHART_AXIS_COLOR} fontSize={12} />
            <YAxis stroke={CHART_AXIS_COLOR} fontSize={12} unit="%" domain={[0, 100]} />
            <Tooltip
              contentStyle={CHART_TOOLTIP_STYLE}
              labelStyle={CHART_TOOLTIP_LABEL}
              itemStyle={CHART_TOOLTIP_ITEM}
              formatter={(value) => `${typeof value === 'number' ? value.toFixed(1) : value}%`}
            />
            <Bar dataKey="value" name="Accuracy" fill="#6366f1" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="Test-set precision / recall / F1">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={qualityRows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} />
            <XAxis dataKey="name" stroke={CHART_AXIS_COLOR} fontSize={12} />
            <YAxis stroke={CHART_AXIS_COLOR} fontSize={12} unit="%" domain={[0, 100]} />
            <Tooltip
              contentStyle={CHART_TOOLTIP_STYLE}
              labelStyle={CHART_TOOLTIP_LABEL}
              itemStyle={CHART_TOOLTIP_ITEM}
              formatter={(value) => `${typeof value === 'number' ? value.toFixed(1) : value}%`}
            />
            <Bar dataKey="value" name="Score" fill="#22c55e" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <div className="lg:col-span-2">
        <Card>
          <h3 className="mb-1 text-sm font-medium text-ink-primary">Test-set confusion matrix</h3>
          <p className="mb-4 text-xs text-ink-muted">
            Predicted vs. actual “strong tier preferred” across {confusionTotal.toLocaleString()} held-out examples.
          </p>
          <div className="grid grid-cols-2 gap-3 sm:max-w-md">
            <ConfusionCell
              label="True positive"
              hint="Predicted strong, actually strong"
              value={confusion.true_positive}
              tone="success"
            />
            <ConfusionCell
              label="False positive"
              hint="Predicted strong, actually not"
              value={confusion.false_positive}
              tone="danger"
            />
            <ConfusionCell
              label="False negative"
              hint="Predicted not strong, actually strong"
              value={confusion.false_negative}
              tone="danger"
            />
            <ConfusionCell
              label="True negative"
              hint="Predicted not strong, actually not"
              value={confusion.true_negative}
              tone="success"
            />
          </div>
          {metrics.probability_mean !== null && metrics.probability_mean !== undefined && (
            <p className="mt-4 text-xs text-ink-muted">
              Mean predicted probability of “strong preferred” on the test set:{' '}
              <span className="text-ink-secondary">{formatPercent(metrics.probability_mean)}</span>
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}

function ConfusionCell({
  label,
  hint,
  value,
  tone,
}: {
  label: string;
  hint: string;
  value: number;
  tone: 'success' | 'danger';
}) {
  const toneClass = tone === 'success' ? 'border-success-500/30 bg-success-500/10' : 'border-danger-500/30 bg-danger-500/10';
  return (
    <div className={`rounded-lg border px-3 py-2.5 ${toneClass}`}>
      <p className="text-lg font-semibold text-ink-primary">{value.toLocaleString()}</p>
      <p className="text-xs font-medium text-ink-primary">{label}</p>
      <p className="mt-0.5 text-[11px] text-ink-muted">{hint}</p>
    </div>
  );
}
