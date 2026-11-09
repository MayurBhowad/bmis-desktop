import {
  addToHistory,
  executeBmisCommand,
  type CommandResult,
  type SendRequest,
} from './commandBuilder.ts';

export type HistoryCommandType = 'SET' | 'GET' | 'OTHER';

export type HistoryStatus = 'success' | 'failed';

export type HistorySort = 'newest' | 'oldest';

// Never holds the raw request: SET values are replaced before a record exists.
export type HistoryRecord = Readonly<{
  id: number;
  type: HistoryCommandType;
  command: string;
  status: HistoryStatus;
  summary: string;
  executedAt: number;
}>;

export type HistoryQuery = {
  search: string;
  type: HistoryCommandType | 'ALL';
  status: HistoryStatus | 'ALL';
  sort: HistorySort;
};

export const REDACTED = '<redacted>';
export const HISTORY_BROWSER_LIMIT = 100;
export const FAILURE_SUMMARY = 'Command failed';

export const DEFAULT_HISTORY_QUERY: HistoryQuery = {
  search: '',
  type: 'ALL',
  status: 'ALL',
  sort: 'newest',
};

// Unknown commands (AUTH, MSET, ...) may carry credentials or values, so only
// the arguments listed here are kept; everything after them is redacted.
const KEPT_ARGUMENTS: Record<HistoryCommandType, number> = { SET: 1, GET: Infinity, OTHER: 0 };

function tokenize(request: string): string[] {
  return request.split(/\s+/u).filter(Boolean);
}

function commandType(name: string): HistoryCommandType {
  return name === 'SET' || name === 'GET' ? name : 'OTHER';
}

export function redactCommand(request: string): { type: HistoryCommandType; command: string } {
  const [first = '', ...args] = tokenize(request);
  const name = first.toUpperCase();
  const type = commandType(name);
  const kept = args.slice(0, KEPT_ARGUMENTS[type]);
  const parts = kept.length < args.length ? [name, ...kept, REDACTED] : [name, ...kept];
  return { type, command: parts.join(' ') };
}

// Backend error text is not guaranteed free of user data, so failures never copy it.
function summarize(result: Pick<CommandResult, 'error' | 'noValue'>): string {
  if (result.error) {
    return FAILURE_SUMMARY;
  }
  return result.noValue ? 'No value found' : 'Response received';
}

export function createHistoryRecord(
  request: string,
  result: Pick<CommandResult, 'error' | 'noValue'>,
  id: number,
  executedAt: number,
): HistoryRecord {
  return {
    id,
    ...redactCommand(request),
    status: result.error ? 'failed' : 'success',
    summary: summarize(result),
    executedAt,
  };
}

export function addHistoryRecord(
  history: readonly HistoryRecord[],
  record: HistoryRecord,
): HistoryRecord[] {
  return [record, ...history].slice(0, HISTORY_BROWSER_LIMIT);
}

export function clearHistory(): HistoryRecord[] {
  return [];
}

export function searchHistory(history: readonly HistoryRecord[], search: string): HistoryRecord[] {
  const query = search.trim().toLowerCase();
  return history.filter((record) => record.command.toLowerCase().includes(query));
}

export function filterHistory(
  history: readonly HistoryRecord[],
  { type, status }: Pick<HistoryQuery, 'type' | 'status'>,
): HistoryRecord[] {
  return history.filter(
    (record) => (type === 'ALL' || record.type === type) && (status === 'ALL' || record.status === status),
  );
}

export function sortHistory(history: readonly HistoryRecord[], sort: HistorySort): HistoryRecord[] {
  const direction = sort === 'newest' ? -1 : 1;
  return [...history].sort(
    (left, right) => direction * (left.executedAt - right.executedAt || left.id - right.id),
  );
}

export function queryHistory(history: readonly HistoryRecord[], query: HistoryQuery): HistoryRecord[] {
  return sortHistory(filterHistory(searchHistory(history, query.search), query), query.sort);
}

// Redacted arguments are never restored; the kept prefix becomes a template to complete.
export function reuseCommand(record: HistoryRecord): string {
  const suffix = ` ${REDACTED}`;
  return record.type !== 'GET' && record.command.endsWith(suffix)
    ? record.command.slice(0, -REDACTED.length)
    : record.command;
}

export function isReuseTemplate(record: HistoryRecord): boolean {
  return reuseCommand(record) !== record.command;
}

export function recentCommands(history: readonly HistoryRecord[]): string[] {
  return history.reduceRight<string[]>(
    (recent, record) => addToHistory(recent, reuseCommand(record)),
    [],
  );
}

export type ExecuteAndRecordOptions = {
  nextId: () => number;
  send?: SendRequest;
  now?: () => number;
};

export async function executeAndRecord(
  request: string,
  record: (entry: HistoryRecord) => void,
  { nextId, send, now = Date.now }: ExecuteAndRecordOptions,
): Promise<CommandResult> {
  const result = await executeBmisCommand(request, send);
  record(createHistoryRecord(request, result, nextId(), now()));
  return result;
}
