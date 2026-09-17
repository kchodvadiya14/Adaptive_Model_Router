import { Play } from 'lucide-react';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { Input } from '../../components/Input';

interface GenerateDatasetCardProps {
  sourcePath: string;
  onSourcePathChange: (value: string) => void;
  qualityFloor: number;
  onQualityFloorChange: (value: number) => void;
  maxPrompts: number;
  onMaxPromptsChange: (value: number) => void;
  running: boolean;
  onGenerate: () => void;
}

export function GenerateDatasetCard({
  sourcePath,
  onSourcePathChange,
  qualityFloor,
  onQualityFloorChange,
  maxPrompts,
  onMaxPromptsChange,
  running,
  onGenerate,
}: GenerateDatasetCardProps) {
  return (
    <Card>
      <h3 className="mb-1 text-sm font-medium text-ink-primary">Generate a new dataset</h3>
      <p className="mb-4 text-xs text-ink-muted">
        Collects a small/medium/strong response for each prompt in the source file, scores every response with the
        judge, and saves the results as a new preference dataset.
      </p>
      <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-4">
        <label className="text-xs text-ink-muted md:col-span-2">
          Source path
          <Input
            value={sourcePath}
            disabled={running}
            onChange={(event) => onSourcePathChange(event.target.value)}
            className="mt-1.5"
          />
        </label>
        <label className="text-xs text-ink-muted">
          Quality floor
          <Input
            type="number"
            min={0.5}
            max={1}
            step={0.05}
            value={qualityFloor}
            disabled={running}
            onChange={(event) => onQualityFloorChange(Number(event.target.value))}
            className="mt-1.5"
          />
        </label>
        <label className="text-xs text-ink-muted">
          Max prompts
          <Input
            type="number"
            min={1}
            max={500}
            value={maxPrompts}
            disabled={running}
            onChange={(event) => onMaxPromptsChange(Number(event.target.value))}
            className="mt-1.5"
          />
        </label>
      </div>
      <Button onClick={onGenerate} loading={running} disabled={running}>
        {!running && <Play className="h-4 w-4" />}
        {running ? 'Generating…' : 'Generate dataset'}
      </Button>
    </Card>
  );
}
