import { Info } from 'lucide-react';
import { Card } from '../../components/Card';

export function HowTrainingWorks() {
  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        <Info className="h-4 w-4 text-ink-secondary" />
        <h3 className="text-sm font-medium text-ink-primary">How training works</h3>
      </div>
      <div className="space-y-2 text-sm text-ink-secondary">
        <p>
          Each preference record already says which tier (small, medium, or strong) was the cheapest one that still
          met the dataset's quality floor. Training fits a binary classifier — TF-IDF + logistic regression,
          sentence-embedding features, or a BERT-style MLP — to predict <em>strong vs. not-strong</em> directly from
          the prompt text, using that label.
        </p>
        <p>
          The dataset is split into train / validation / test sets. <strong>Train accuracy</strong> and{' '}
          <strong>validation accuracy</strong> are measured during fitting; <strong>test accuracy</strong>,{' '}
          <strong>precision</strong>, <strong>recall</strong>, <strong>F1</strong>, and the confusion matrix come from
          a held-out split the model never saw during training.
        </p>
        <p>
          These metrics describe how well the trained model reproduces the judge's preference labels — not the
          quality of the responses a routed model will produce. A high test accuracy means the router's
          strong/not-strong predictions usually agree with the dataset it was trained on.
        </p>
        <p>
          Once training completes, set <code className="rounded bg-surface-3 px-1 py-0.5 text-xs text-brand-300">ROUTER_TYPE</code> to
          the trained type in the backend's <code className="rounded bg-surface-3 px-1 py-0.5 text-xs text-brand-300">.env</code> and
          restart it — the gateway then loads the most recently trained artifact of that type at startup.
        </p>
      </div>
    </Card>
  );
}
