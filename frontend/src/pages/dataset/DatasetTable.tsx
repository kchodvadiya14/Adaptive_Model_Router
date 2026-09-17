import { Button } from '../../components/Button';
import { Badge } from '../../components/Badge';
import { Table, TableContainer, TBody, Td, Th, THead, Tr } from '../../components/Table';
import type { DatasetManifest } from '../../types';
import { formatPercent, formatTimestamp, shortPath } from './format';

interface DatasetTableProps {
  datasets: DatasetManifest[];
  selectedId: string;
  onSelect: (id: string) => void;
}

export function DatasetTable({ datasets, selectedId, onSelect }: DatasetTableProps) {
  return (
    <TableContainer>
      <Table>
        <THead>
          <Tr>
            <Th>Name</Th>
            <Th>Records</Th>
            <Th>Source</Th>
            <Th>Judge</Th>
            <Th>Quality floor</Th>
            <Th>Created</Th>
            <Th />
          </Tr>
        </THead>
        <TBody>
          {datasets.map((dataset) => {
            const selected = dataset.id === selectedId;
            return (
              <Tr key={dataset.id} className={selected ? 'bg-brand-500/10' : undefined}>
                <Td>
                  <div className="font-medium text-ink-primary">{dataset.name}</div>
                  {dataset.description && (
                    <div className="mt-0.5 max-w-xs truncate text-xs text-ink-muted" title={dataset.description}>
                      {dataset.description}
                    </div>
                  )}
                </Td>
                <Td className="text-ink-secondary">{dataset.record_count.toLocaleString()}</Td>
                <Td className="max-w-[200px] truncate font-mono text-xs text-ink-secondary" title={dataset.source_path}>
                  {shortPath(dataset.source_path)}
                </Td>
                <Td>
                  <Badge variant="neutral">{dataset.judge_provider}</Badge>
                </Td>
                <Td className="text-ink-secondary">{formatPercent(dataset.quality_floor, 0)}</Td>
                <Td className="whitespace-nowrap text-ink-secondary">{formatTimestamp(dataset.created_at)}</Td>
                <Td>
                  <Button variant="ghost" size="sm" onClick={() => onSelect(dataset.id)}>
                    {selected ? 'Viewing' : 'Browse'}
                  </Button>
                </Td>
              </Tr>
            );
          })}
        </TBody>
      </Table>
    </TableContainer>
  );
}
