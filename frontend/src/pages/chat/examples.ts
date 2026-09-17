export interface ExamplePrompt {
  id: string;
  label: string;
  description: string;
  prompt: string;
}

export const EXAMPLE_PROMPTS: ExamplePrompt[] = [
  {
    id: 'factual',
    label: 'Simple factual',
    description: 'Short lookup that usually stays on a cheaper tier',
    prompt: 'What is the capital of France, and roughly how many people live there?',
  },
  {
    id: 'coding',
    label: 'Coding',
    description: 'Implementation request with code-oriented routing features',
    prompt:
      'Write a Python function that merges two already-sorted lists into one sorted list in O(n) time. Include a short docstring and two unit-test style examples.',
  },
  {
    id: 'reasoning',
    label: 'Complex reasoning',
    description: 'Multi-step puzzle that typically needs a stronger model',
    prompt:
      'A farmer must cross a river with a wolf, a goat, and a cabbage. The boat holds the farmer plus one item. The wolf cannot be left alone with the goat, and the goat cannot be left alone with the cabbage. List the minimal sequence of crossings and explain why each illegal alternative fails.',
  },
];

/** Minimal tool payload: a non-empty `tools` list is how `/api/chat` marks the request as requiring function calling. */
export const CAPABILITY_TOOL_STUB: Array<Record<string, unknown>> = [
  {
    type: 'function',
    function: {
      name: 'capability_probe',
      description: 'Signals that this request requires a model with tool/function calling.',
      parameters: { type: 'object', properties: {} },
    },
  },
];
