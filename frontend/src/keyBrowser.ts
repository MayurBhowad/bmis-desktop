import {
  parseListKeysResponse,
  pythonRequest,
  type ListKeysResponse,
  type ParsedPythonResponse,
  type PythonCommand,
} from './pythonApi.ts';

export type KeyBrowserRequest = (
  payload: PythonCommand,
) => Promise<ParsedPythonResponse>;

export const DEFAULT_SCAN_COUNT = 50;

export async function fetchKeyPage(
  cursor = '0',
  count = DEFAULT_SCAN_COUNT,
  send: KeyBrowserRequest = pythonRequest,
): Promise<ListKeysResponse> {
  if (
    !/^(0|[1-9][0-9]*)$/.test(cursor) ||
    !Number.isSafeInteger(Number(cursor))
  ) {
    throw new Error('Invalid scan cursor');
  }

  if (!Number.isInteger(count) || count < 1 || count > 100) {
    throw new Error('Count must be an integer between 1 and 100');
  }

  const parsed = await send({
    command: 'list_keys',
    cursor,
    count,
  });

  if (typeof parsed !== 'object' || parsed === null || !('body' in parsed)) {
    throw new Error('Backend returned an unexpected response');
  }

  return parseListKeysResponse(parsed.body);
}