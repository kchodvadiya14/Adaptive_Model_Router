import { Search } from 'lucide-react';
import { Badge } from '../../components/Badge';
import { Button } from '../../components/Button';
import { Input } from '../../components/Input';
import { Select } from '../../components/Select';
import { Table, TableContainer, TBody, Td, Th, THead, Tr } from '../../components/Table';
import type { PreferenceRecord } from '../../types';
import { EVAL_SOURCE_BADGE, EVAL_SOURCE_LABEL, formatTaskType, TIER_BADGE } from './format';

interface RecordsTableProps {
  records: PreferenceRecord[];
  taskTypes: string[];
  search: string;
  onSearchChange: (value: string) => void;
  taskFilter: string;
  onTaskFilterChange: (value: string) => void;
  page: number;
  pageSize: number;
  totalFiltered: number;
  onPageChange: (page: number) => void;
  onReview: (record: PreferenceRecord) => void;
}

export function RecordsTable({
  records,
  taskTypes,
  search,
  onSearchChange,
  taskFilter,
  onTaskFilterChange,
  page,
  pageSize,
  totalFiltered,
  onPageChange,
  onReview,
}: RecordsTableProps) {
  const totalPages = Math.max(1, Math.ceil(totalFiltered / pageSize));

  return (
    <div>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
          <Input
            placeholder="Search prompts…"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            className="pl-9"
          />
        </div>
        <Select
          value={taskFilter}
          onChange={(event) => onTaskFilterChange(event.target.value)}
          className="sm:w-56"
        >
          <option value="">All task types</option>
          {taskTypes.map((type) => (
            <option key={type} value={type}>
              {formatTaskType(type)}
            </option>
          ))}
        </Select>
      </div>

      {records.length === 0 ? (
        <div className="rounded-card border border-dashed border-line-strong bg-surface-1/60 px-4 py-8 text-center text-sm text-ink-muted">
          No records match your filters.
        </div>
      ) : (
        <>
          <TableContainer>
            <Table className="min-w-[860px]">
              <THead>
                <Tr>
                  <Th>Prompt</Th>
                  <Th>Task type</Th>
                  <Th>Scores (S / M / St)</Th>
                  <Th>Preferred</Th>
                  <Th>Evaluation</Th>
                  <Th />
                </Tr>
              </THead>
              <TBody>
                {records.map((record) => (
                  <Tr key={record.id}>
                    <Td className="max-w-sm">
                      <span className="line-clamp-2 text-ink-secondary" title={record.prompt}>
                        {record.prompt}
                      </span>
                    </Td>
                    <Td>
                      <Badge variant="neutral">{formatTaskType(record.task_type)}</Badge>
                    </Td>
                    <Td className="whitespace-nowrap font-mono text-xs text-ink-secondary">
                      {(record.small_score * 100).toFixed(0)}% / {(record.medium_score * 100).toFixed(0)}% /{' '}
                      {(record.strong_score * 100).toFixed(0)}%
                    </Td>
                    <Td>
                      <Badge variant={TIER_BADGE[record.preferred_model]}>{record.preferred_model}</Badge>
                    </Td>
                    <Td>
                      <Badge variant={EVAL_SOURCE_BADGE[record.evaluation_source] ?? 'neutral'}>
                        {EVAL_SOURCE_LABEL[record.evaluation_source] ?? record.evaluation_source}
                      </Badge>
                    </Td>
                    <Td>
                      <Button variant="ghost" size="sm" onClick={() => onReview(record)}>
                        Review
                      </Button>
                    </Td>
                  </Tr>
                ))}
              </TBody>
            </Table>
          </TableContainer>

          <div className="mt-4 flex flex-col gap-2 text-sm text-ink-secondary sm:flex-row sm:items-center sm:justify-between">
            <span>
              Page {page + 1} of {totalPages} · {totalFiltered.toLocaleString()} record{totalFiltered === 1 ? '' : 's'}
            </span>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" disabled={page === 0} onClick={() => onPageChange(page - 1)}>
                Previous
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page + 1 >= totalPages}
                onClick={() => onPageChange(page + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
