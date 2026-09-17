import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ChartCard } from '../../components/ChartCard';
import type { ChartRow } from './format';
import { formatCost, formatMs } from './format';

const tooltipStyle = {
  background: '#121a2c',
  border: '1px solid #1f2740',
  borderRadius: 8,
};
const tooltipLabel = { color: '#f4f6fb' };
const tooltipItem = { color: '#9aa4bd' };

interface ComparisonChartsProps {
  rows: ChartRow[];
}

export function ComparisonCharts({ rows }: ComparisonChartsProps) {
  const isEmpty = rows.length === 0;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ChartCard
        title="Cost / quality tradeoff"
        isEmpty={isEmpty}
        emptyMessage="Run a benchmark to plot average cost against average quality."
      >
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 16, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2740" />
            <XAxis
              type="number"
              dataKey="averageCost"
              name="Avg. cost"
              stroke="#707b96"
              fontSize={12}
              tickFormatter={(value: number) => formatCost(value)}
            />
            <YAxis
              type="number"
              dataKey="quality"
              name="Avg. quality"
              unit="%"
              stroke="#707b96"
              fontSize={12}
              domain={[0, 100]}
            />
            <Tooltip
              cursor={{ strokeDasharray: '3 3' }}
              contentStyle={tooltipStyle}
              labelStyle={tooltipLabel}
              itemStyle={tooltipItem}
              formatter={(value, name) => {
                const numeric = typeof value === 'number' ? value : Number(value);
                if (name === 'Avg. cost') return [formatCost(numeric), 'Avg. cost'];
                if (name === 'Avg. quality') return [`${numeric.toFixed(1)}%`, 'Avg. quality'];
                return [value, name];
              }}
            />
            <Scatter data={rows} name="Strategy">
              {rows.map((row) => (
                <Cell key={row.strategy} fill={row.color} />
              ))}
              <LabelList dataKey="name" position="top" fill="#9aa4bd" fontSize={11} />
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard
        title="Latency"
        isEmpty={isEmpty}
        emptyMessage="Run a benchmark to compare average and P95 latency."
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2740" />
            <XAxis dataKey="name" stroke="#707b96" fontSize={12} />
            <YAxis stroke="#707b96" fontSize={12} tickFormatter={(value: number) => formatMs(value)} />
            <Tooltip
              contentStyle={tooltipStyle}
              labelStyle={tooltipLabel}
              itemStyle={tooltipItem}
              formatter={(value) => formatMs(typeof value === 'number' ? value : Number(value))}
            />
            <Legend />
            <Bar dataKey="averageLatency" name="Avg. latency" fill="#6366f1" radius={[4, 4, 0, 0]} />
            <Bar dataKey="p95Latency" name="P95 latency" fill="#f59e0b" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <div className="lg:col-span-2">
        <ChartCard
          title="Quality retention vs cost reduction"
          isEmpty={isEmpty}
          emptyMessage="Run a benchmark to compare retention and cost reduction."
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2740" />
              <XAxis dataKey="name" stroke="#707b96" fontSize={12} />
              <YAxis stroke="#707b96" fontSize={12} unit="%" />
              <Tooltip
                contentStyle={tooltipStyle}
                labelStyle={tooltipLabel}
                itemStyle={tooltipItem}
                formatter={(value) => `${typeof value === 'number' ? value.toFixed(1) : value}%`}
              />
              <Legend />
              <Bar dataKey="qualityRetention" name="Quality retention %" fill="#22c55e" radius={[4, 4, 0, 0]} />
              <Bar dataKey="costReduction" name="Cost reduction %" fill="#6366f1" radius={[4, 4, 0, 0]} />
              <Bar dataKey="strongUsage" name="Strong-model usage %" fill="#f43f5e" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
