import { ArrowRight, Cpu, Database, GitBranch, Route } from 'lucide-react';
import { Card } from '../../components/Card';

const STEPS = [
  {
    icon: Database,
    title: 'Dataset',
    description: 'Sample prompts run through the small/medium/strong tiers and get scored by the judge.',
  },
  {
    icon: GitBranch,
    title: 'Preference data',
    description: 'Scores become preference records: which tier was cheapest while still meeting the quality floor.',
  },
  {
    icon: Cpu,
    title: 'Training',
    description: 'A classifier (TF-IDF, embedding, or BERT-style) learns to predict that preference from the prompt.',
  },
  {
    icon: Route,
    title: 'Router',
    description: 'Set ROUTER_TYPE to the trained model and the gateway uses its predictions to route new requests.',
  },
];

export function TrainingPipeline() {
  return (
    <Card>
      <h3 className="mb-4 text-sm font-medium text-ink-primary">Dataset → Preference Data → Training → Router</h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((step, index) => (
          <div key={step.title} className="relative flex gap-3">
            <div className="flex h-9 w-9 flex-none items-center justify-center rounded-lg bg-brand-500/15 text-brand-300">
              <step.icon className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-medium text-ink-primary">{step.title}</p>
              <p className="mt-0.5 text-xs text-ink-muted">{step.description}</p>
            </div>
            {index < STEPS.length - 1 && (
              <ArrowRight className="absolute -right-3 top-2 hidden h-4 w-4 text-ink-disabled lg:block" />
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}
