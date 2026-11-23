import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import {
  DEFAULT_SCAN_COUNT,
  fetchKeyPage,
  type KeyBrowserRequest,
} from '../src/keyBrowser.ts';
import type { PythonCommand } from '../src/pythonApi.ts';

function respondWith(
  body: unknown,
  sent: PythonCommand[] = [],
): KeyBrowserRequest {
  return async (payload) => {
    sent.push(payload);
    return { raw: JSON.stringify(body), body };
  };
}

describe('fetchKeyPage', () => {
  test('requests the first page with the default cursor and count', async () => {
    const sent: PythonCommand[] = [];
    const response = {
      status: true,
      keys: ['user:1', 'user:2'],
      nextCursor: '12',
      hasMore: true,
    };

    const result = await fetchKeyPage('0', DEFAULT_SCAN_COUNT, respondWith(response, sent));

    assert.deepEqual(sent, [
      { command: 'list_keys', cursor: '0', count: 50 },
    ]);
    assert.deepEqual(result, response);
  });

  test('forwards the next cursor for subsequent pages', async () => {
    const sent: PythonCommand[] = [];
    const response = {
      status: true,
      keys: ['user:3'],
      nextCursor: '0',
      hasMore: false,
    };

    const result = await fetchKeyPage('12', 25, respondWith(response, sent));

    assert.deepEqual(sent, [
      { command: 'list_keys', cursor: '12', count: 25 },
    ]);
    assert.deepEqual(result, response);
  });

  test('rejects invalid cursors without sending a request', async () => {
    const sent: PythonCommand[] = [];
    const invalidCursors = ['', '-1', '1.5', '01', 'abc', '1\\n'];

    for (const cursor of invalidCursors) {
      await assert.rejects(
        fetchKeyPage(cursor, 50, respondWith({}, sent)),
        { message: 'Invalid scan cursor' },
      );
    }

    assert.equal(sent.length, 0);
  });

  test('rejects invalid counts without sending a request', async () => {
    const sent: PythonCommand[] = [];

    for (const count of [0, -1, 101, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
      await assert.rejects(
        fetchKeyPage('0', count, respondWith({}, sent)),
        { message: 'Count must be an integer between 1 and 100' },
      );
    }

    assert.equal(sent.length, 0);
  });

  test('rejects malformed backend responses', async () => {
    const invalidResponses = [
      null,
      {},
      { status: false, error: 'Not connected to BMis' },
      { status: true, keys: 'user:1', nextCursor: '0', hasMore: false },
      { status: true, keys: [1], nextCursor: '0', hasMore: false },
      { status: true, keys: [], nextCursor: 'invalid', hasMore: true },
      { status: true, keys: [], nextCursor: '12', hasMore: false },
      { status: true, keys: [], nextCursor: '9007199254740992', hasMore: true },
    ];

    for (const body of invalidResponses) {
      await assert.rejects(
        fetchKeyPage('0', 50, respondWith(body)),
      );
    }
  });

  test('preserves backend error messages', async () => {
    const request: KeyBrowserRequest = async () => ({
      raw: '',
      body: { status: false, error: 'Not connected to BMis' },
    });

    await assert.rejects(
      fetchKeyPage('0', 50, request),
      { message: 'Not connected to BMis' },
    );
  });

  test('accepts an empty page with a nonzero cursor', async () => {
    const response = {
      status: true,
      keys: [],
      nextCursor: '24',
      hasMore: true,
    };

    const result = await fetchKeyPage('12', 50, respondWith(response));

    assert.deepEqual(result, response);
  });

  test('accepts an empty completed scan', async () => {
    const response = {
      status: true,
      keys: [],
      nextCursor: '0',
      hasMore: false,
    };

    const result = await fetchKeyPage('24', 50, respondWith(response));

    assert.deepEqual(result, response);
  });

  test('propagates transport errors', async () => {
    const request: KeyBrowserRequest = async () => {
      throw new Error('Connection timed out');
    };

    await assert.rejects(
      fetchKeyPage('0', 50, request),
      { message: 'Connection timed out' },
    );
  });

  test('rejects cursors above the JavaScript safe integer limit', async () => {
    const sent: PythonCommand[] = [];

    await assert.rejects(
      fetchKeyPage('9007199254740992', 50, respondWith({}, sent)),
      { message: 'Invalid scan cursor' },
    );

    assert.equal(sent.length, 0);
  });
});
