import { Badge } from '../../components/Badge';
import { Table, TableContainer, TBody, Td, Th, THead, Tr } from '../../components/Table';
import type { BenchmarkReport } from '../../types';
import {
  formatCost,
  formatMs,
  formatPercent,
  parseSample,
  strategyBadge,
  strategyLabel,
} from './format';

interface ComparisonTableProps {
  report: BenchmarkReport;
}

export function ComparisonTable({ report }: ComparisonTableProps) {
  return (
    <TableContainer>
      <Table className="min-w-[960px]">
        <THead>
          <Tr>
            <Th>Strategy</Th>
            <Th>Requests</Th>
            <Th>Avg. quality</Th>
            <Th>Avg. cost</Th>
            <Th>Total cost</Th>
            <Th>Avg. latency</Th>
            <Th>P50</Th>
            <Th>P95</Th>
            <Th>Cost reduction</Th>
            <Th>Quality retention</Th>
            <Th>Strong usage</Th>
            <Th>Routing accuracy</Th>
          </Tr>
        </THead>
        <TBody>
          {report.strategies.map((item) => (
            <Tr key={item.strategy}>
              <Td>
                <Badge variant={strategyBadge(item.strategy)}>{strategyLabel(item.strategy)}</Badge>
              </Td>
              <Td className="text-ink-secondary">{item.metrics.total_requests}</Td>
              <Td className="text-ink-secondary">{formatPercent(item.metrics.average_quality)}</Td>
              <Td className="text-ink-secondary">{formatCost(item.metrics.average_cost)}</Td>
              <Td className="text-ink-secondary">{formatCost(item.metrics.total_cost)}</Td>
              <Td className="text-ink-secondary">{formatMs(item.metrics.average_latency_ms)}</Td>
              <Td className="text-ink-secondary">{formatMs(item.metrics.p50_latency_ms)}</Td>
              <Td className="text-ink-secondary">{formatMs(item.metrics.p95_latency_ms)}</Td>
              <Td className="text-ink-secondary">{formatPercent(item.metrics.cost_reduction)}</Td>
              <Td className="text-ink-secondary">{formatPercent(item.metrics.quality_retention)}</Td>
              <Td className="text-ink-secondary">{formatPercent(item.metrics.strong_model_usage)}</Td>
              <Td className="text-ink-secondary">{formatPercent(item.metrics.routing_accuracy)}</Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    </TableContainer>
  );
}

interface SampleTableProps {
  report: BenchmarkReport;
}

export function SampleTable({ report }: SampleTableProps) {
  const rows = report.strategies.flatMap((item) =>
    (item.samples ?? []).map((raw) => ({
      strategy: item.strategy,
      ...parseSample(raw),
    })),
  );

  if (rows.length === 0) return null;

  return (
    <div>
      <h3 className="mb-3 text-sm font-medium text-ink-primary">Prompt samples</h3>
      <TableContainer>
        <Table className="min-w-[800px]">
          <THead>
            <Tr>
              <Th>Strategy</Th>
              <Th>Prompt</Th>
              <Th>Model</Th>
              <Th>Tier</Th>
              <Th>Quality</Th>
              <Th>Cost</Th>
              <Th>Latency</Th>
            </Tr>
          </THead>
          <TBody>
            {rows.map((row, index) => (
              <Tr key={`${row.strategy}-${row.prompt_id}-${index}`}>
                <Td>
                  <Badge variant={strategyBadge(row.strategy)}>{strategyLabel(row.strategy)}</Badge>
                </Td>
                <Td className="max-w-[280px] truncate text-ink-secondary" title={row.prompt || row.prompt_id}>
                  {row.prompt || row.prompt_id}
                </Td>
                <Td className="font-mono text-xs text-ink-secondary">{row.selected_model}</Td>
                <Td>
                  {row.tier !== '—' ? (
                    <Badge variant={row.tier === 'strong' || row.tier === 'small' || row.tier === 'medium' ? row.tier : 'neutral'}>
                      {row.tier}
                    </Badge>
                  ) : (
                    <span className="text-ink-muted">—</span>
                  )}
                </Td>
                <Td className="text-ink-secondary">{formatPercent(row.quality)}</Td>
                <Td className="text-ink-secondary">{formatCost(row.cost)}</Td>
                <Td className="text-ink-secondary">{formatMs(row.latency_ms)}</Td>
              </Tr>
            ))}
          </TBody>
        </Table>
      </TableContainer>
    </div>
  );
}
