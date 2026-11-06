import {
  failureMessage,
  invokeErrorMessage,
  isRecord,
  pythonRequest,
  type ParsedPythonResponse,
  type PythonCommand,
} from './pythonApi.ts';

export type CommandField = 'key' | 'value';

export type BuiltCommand =
  | { ok: true; command: string }
  | { ok: false; field: CommandField; message: string };

export type CommandResult = {
  output: string;
  error: string;
  backendFailure: boolean;
  noValue: boolean;
};

export type SendRequest = (payload: PythonCommand) => Promise<ParsedPythonResponse>;

export type CommandSuggestion = {
  kind: 'recent' | 'template';
  label: string;
  value: string;
};

export const HISTORY_LIMIT = 10;
export const SUGGESTION_LIMIT = 6;

const COMMAND_TEMPLATES: readonly CommandSuggestion[] = [
  { kind: 'template', label: 'SET <key> <value>', value: 'SET ' },
  { kind: 'template', label: 'GET <key>', value: 'GET ' },
];

// BMis receives one space-separated text line; whitespace or control characters
// inside a token would split it or smuggle a second command.
const UNSAFE_TOKEN = /[\s\p{Cc}]/u;

const FIELD_LABELS: Record<CommandField, string> = { key: 'Key', value: 'Value' };

function tokenError(field: CommandField, token: string): BuiltCommand | null {
  if (!token) {
    return { ok: false, field, message: `${FIELD_LABELS[field]} is required.` };
  }
  if (UNSAFE_TOKEN.test(token)) {
    return {
      ok: false,
      field,
      message: `${FIELD_LABELS[field]} cannot contain spaces or control characters.`,
    };
  }
  return null;
}

export function buildSetCommand(key: string, value: string): BuiltCommand {
  const parsedKey = key.trim();
  const parsedValue = value.trim();
  return (
    tokenError('key', parsedKey) ??
    tokenError('value', parsedValue) ?? { ok: true, command: `SET ${parsedKey} ${parsedValue}` }
  );
}

export function buildGetCommand(key: string): BuiltCommand {
  const parsedKey = key.trim();
  return tokenError('key', parsedKey) ?? { ok: true, command: `GET ${parsedKey}` };
}

export function addToHistory(history: readonly string[], command: string): string[] {
  if (!command.trim()) {
    return [...history];
  }
  return [command, ...history.filter((entry) => entry !== command)].slice(0, HISTORY_LIMIT);
}

export function commandSuggestions(
  input: string,
  history: readonly string[],
): CommandSuggestion[] {
  const query = input.trimStart().toLowerCase();
  const recent: CommandSuggestion[] = history
    .filter((entry) => entry !== input && entry.toLowerCase().startsWith(query))
    .map((entry) => ({ kind: 'recent', label: entry, value: entry }));
  const templates = COMMAND_TEMPLATES.filter(({ value }) => {
    const template = value.toLowerCase();
    return template !== query && template.startsWith(query);
  });
  return [...recent.slice(0, SUGGESTION_LIMIT - templates.length), ...templates];
}

export function formatResponse(body: unknown): string {
  return JSON.stringify(body, null, 2);
}

export async function executeBmisCommand(
  request: string,
  send: SendRequest = pythonRequest,
): Promise<CommandResult> {
  try {
    const parsed = await send({ command: 'execute', request });
    const failure = failureMessage(parsed.body);
    return {
      output: formatResponse(parsed.body),
      error: failure ?? '',
      backendFailure: failure !== null,
      noValue: failure === null && isRecord(parsed.body) && parsed.body.result === null,
    };
  } catch (error) {
    return {
      output: '',
      error: error instanceof Error ? error.message : invokeErrorMessage(error),
      backendFailure: false,
      noValue: false,
    };
  }
}

export async function runExclusive<T>(
  lock: { current: boolean },
  task: () => Promise<T>,
): Promise<T | null> {
  if (lock.current) {
    return null;
  }
  lock.current = true;
  try {
    return await task();
  } finally {
    lock.current = false;
  }
}
