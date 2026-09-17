import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ChartCard } from '../../components/ChartCard';
import { Table, TableContainer, TBody, Td, Th, THead, Tr } from '../../components/Table';
import { formatCost, formatMs, formatPercent } from '../benchmark/format';
import { formatConfig } from './format';
import type { ExperimentSection } from '../../types';

interface SectionResultsProps {
  section: ExperimentSection;
}

export function SectionResults({ section }: SectionResultsProps) {
  const chartData = section.variants.map((variant) => ({
    name: variant.name,
    quality: Number((variant.metrics.average_quality * 100).toFixed(1)),
    costReduction: Number((variant.metrics.cost_reduction * 100).toFixed(1)),
  }));

  return (
    <div className="space-y-4">
      <h4 className="text-sm font-medium text-ink-primary">{section.name}</h4>

      <TableContainer>
        <Table>
          <THead>
            <Tr>
              <Th>Variant</Th>
              <Th>Config</Th>
              <Th>Requests</Th>
              <Th>Avg. Quality</Th>
              <Th>Avg. Cost</Th>
              <Th>Cost Reduction</Th>
              <Th>Quality Retention</Th>
              <Th>Avg. Latency</Th>
              <Th>P95 Latency</Th>
            </Tr>
          </THead>
          <TBody>
            {section.variants.map((variant) => (
              <Tr key={variant.name}>
                <Td className="font-medium text-ink-primary">{variant.name}</Td>
                <Td className="max-w-[220px] truncate font-mono text-xs text-ink-secondary" title={formatConfig(variant.config)}>
                  {formatConfig(variant.config)}
                </Td>
                <Td className="text-ink-secondary">{variant.metrics.total_requests}</Td>
                <Td className="text-ink-secondary">{formatPercent(variant.metrics.average_quality)}</Td>
                <Td className="text-ink-secondary">{formatCost(variant.metrics.average_cost)}</Td>
                <Td className="text-ink-secondary">{formatPercent(variant.metrics.cost_reduction)}</Td>
                <Td className="text-ink-secondary">{formatPercent(variant.metrics.quality_retention)}</Td>
                <Td className="text-ink-secondary">{formatMs(variant.metrics.average_latency_ms)}</Td>
                <Td className="text-ink-secondary">{formatMs(variant.metrics.p95_latency_ms)}</Td>
              </Tr>
            ))}
          </TBody>
        </Table>
      </TableContainer>

      <ChartCard title={`${section.name} — Quality vs. Cost Reduction`} isEmpty={chartData.length === 0}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2740" />
            <XAxis dataKey="name" stroke="#707b96" fontSize={11} interval={0} angle={-15} textAnchor="end" height={50} />
            <YAxis stroke="#707b96" fontSize={12} />
            <Tooltip contentStyle={{ background: '#121a2c', border: '1px solid #1f2740', borderRadius: 8 }} labelStyle={{ color: '#f4f6fb' }} />
            <Bar dataKey="quality" name="Quality %" fill="#6366f1" radius={[4, 4, 0, 0]} />
            <Bar dataKey="costReduction" name="Cost Reduction %" fill="#10b981" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}
