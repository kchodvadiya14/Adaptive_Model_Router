import { Line, LineChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge } from '../../components/Badge';
import { ChartCard } from '../../components/ChartCard';
import { Table, TableContainer, TBody, Td, Th, THead, Tr } from '../../components/Table';
import type { DatasetManifest, TrainedModelInfo } from '../../types';
import {
  CHART_AXIS_COLOR,
  CHART_GRID_COLOR,
  CHART_TOOLTIP_ITEM,
  CHART_TOOLTIP_LABEL,
  CHART_TOOLTIP_STYLE,
  formatPercent,
  formatTimestamp,
  ROUTER_TYPE_BADGE,
} from './format';

interface TrainingHistoryTableProps {
  models: TrainedModelInfo[];
  datasetsById: Map<string, DatasetManifest>;
}

const ROUTER_LINE_COLOR: Record<TrainedModelInfo['router_type'], string> = {
  tfidf: '#38bdf8',
  embedding: '#fbbf24',
  bert: '#f43f5e',
};

export function TrainingHistoryTable({ models, datasetsById }: TrainingHistoryTableProps) {
  const sorted = [...models].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  const trendRows = [...models]
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    .map((model, index) => ({
      run: `#${index + 1}`,
      created_at: model.created_at,
      [model.router_type]: Math.round(model.metrics.test_accuracy * 1000) / 10,
    }));

  return (
    <div className="space-y-4">
      {models.length > 1 && (
        <ChartCard title="Test accuracy across training runs">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trendRows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} />
              <XAxis dataKey="run" stroke={CHART_AXIS_COLOR} fontSize={12} />
              <YAxis stroke={CHART_AXIS_COLOR} fontSize={12} unit="%" domain={[0, 100]} />
              <Tooltip
                contentStyle={CHART_TOOLTIP_STYLE}
                labelStyle={CHART_TOOLTIP_LABEL}
                itemStyle={CHART_TOOLTIP_ITEM}
                formatter={(value) => `${value}%`}
                labelFormatter={(_label, payload) =>
                  payload?.[0]?.payload ? formatTimestamp(payload[0].payload.created_at) : ''
                }
              />
              <Legend />
              {(['tfidf', 'embedding', 'bert'] as const).map((type) => (
                <Line
                  key={type}
                  type="monotone"
                  dataKey={type}
                  name={type}
                  stroke={ROUTER_LINE_COLOR[type]}
                  connectNulls
                  dot={{ r: 3 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      <TableContainer>
        <Table>
          <THead>
            <Tr>
              <Th>Router type</Th>
              <Th>Dataset</Th>
              <Th>Test accuracy</Th>
              <Th>F1</Th>
              <Th>Threshold</Th>
              <Th>Samples</Th>
              <Th>Created</Th>
            </Tr>
          </THead>
          <TBody>
            {sorted.slice(0, 20).map((model) => {
              const dataset = datasetsById.get(model.dataset_id);
              return (
                <Tr key={model.id}>
                  <Td>
                    <Badge variant={ROUTER_TYPE_BADGE[model.router_type]}>{model.router_type}</Badge>
                  </Td>
                  <Td className="max-w-[200px] truncate text-ink-secondary" title={dataset?.name ?? model.dataset_id}>
                    {dataset?.name ?? <span className="font-mono text-xs">{model.dataset_id}</span>}
                  </Td>
                  <Td className="text-ink-secondary">{formatPercent(model.metrics.test_accuracy)}</Td>
                  <Td className="text-ink-secondary">{model.metrics.f1.toFixed(3)}</Td>
                  <Td className="text-ink-secondary">{model.threshold}</Td>
                  <Td className="text-ink-secondary">{model.samples.toLocaleString()}</Td>
                  <Td className="whitespace-nowrap text-ink-secondary">{formatTimestamp(model.created_at)}</Td>
                </Tr>
              );
            })}
          </TBody>
        </Table>
      </TableContainer>
    </div>
  );
}
