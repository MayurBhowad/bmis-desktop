import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import {
  buildGetCommand,
  buildSetCommand,
  commandSuggestions,
  HISTORY_LIMIT,
  type SendRequest,
} from '../src/commandBuilder.ts';
import {
  addHistoryRecord,
  clearHistory,
  createHistoryRecord,
  DEFAULT_HISTORY_QUERY,
  executeAndRecord,
  filterHistory,
  HISTORY_BROWSER_LIMIT,
  isReuseTemplate,
  queryHistory,
  recentCommands,
  redactCommand,
  reuseCommand,
  FAILURE_SUMMARY,
  searchHistory,
  sortHistory,
  type HistoryRecord,
} from '../src/commandHistory.ts';
import type { PythonCommand } from '../src/pythonApi.ts';

const OK = { error: '', noValue: false };
const SECRET = 's3cr3t-value';

function respondWith(body: unknown, sent: PythonCommand[] = []): SendRequest {
  return async (payload) => {
    sent.push(payload);
    return { raw: JSON.stringify(body), body };
  };
}

function record(
  request: string,
  id: number,
  executedAt: number,
  result: { error: string; noValue: boolean } = OK,
): HistoryRecord {
  return createHistoryRecord(request, result, id, executedAt);
}

function sampleHistory(): HistoryRecord[] {
  return [
    record('SET demo Mayur', 1, 1_000),
    record('GET demo', 2, 2_000),
    record('INCR counter', 3, 3_000, { error: 'Not connected to BMis', noValue: false }),
    record('GET missing', 4, 4_000, { error: '', noValue: true }),
  ].reduce<HistoryRecord[]>(addHistoryRecord, []);
}

function counter() {
  let id = 0;
  return () => (id += 1);
}

describe('redactCommand', () => {
  test('hides the SET value behind the key', () => {
    assert.deepEqual(redactCommand('SET demo Mayur'), { type: 'SET', command: 'SET demo <redacted>' });
  });

  test('redacts every value token, case-insensitively and with extra whitespace', () => {
    for (const request of [`set demo ${SECRET}`, `  SeT   demo  ${SECRET} EX 10 `, `SET\tdemo\t${SECRET}`]) {
      const redacted = redactCommand(request);
      assert.equal(redacted.type, 'SET');
      assert.equal(redacted.command, 'SET demo <redacted>');
      assert.doesNotMatch(redacted.command, new RegExp(SECRET));
    }
  });

  test('keeps SET commands without a value', () => {
    assert.deepEqual(redactCommand('SET demo'), { type: 'SET', command: 'SET demo' });
    assert.deepEqual(redactCommand('SET'), { type: 'SET', command: 'SET' });
  });

  test('keeps GET keys and normalizes the command name and whitespace', () => {
    assert.deepEqual(redactCommand(' get  demo '), { type: 'GET', command: 'GET demo' });
  });

  test('redacts every argument of other commands', () => {
    const requests = [
      `AUTH ${SECRET}`,
      `auth admin ${SECRET}`,
      `MSET a ${SECRET} b ${SECRET}`,
      `SETEX demo 10 ${SECRET}`,
      '  INCR counter ',
    ];
    for (const request of requests) {
      const redacted = redactCommand(request);
      assert.equal(redacted.type, 'OTHER');
      assert.match(redacted.command, /^[A-Z]+ <redacted>$/);
      assert.doesNotMatch(redacted.command, new RegExp(SECRET));
    }
    assert.deepEqual(redactCommand('auth admin pw'), { type: 'OTHER', command: 'AUTH <redacted>' });
  });

  test('keeps other commands without arguments', () => {
    assert.deepEqual(redactCommand(' ping '), { type: 'OTHER', command: 'PING' });
    assert.deepEqual(redactCommand('   '), { type: 'OTHER', command: '' });
  });
});

describe('createHistoryRecord', () => {
  test('stores only safe fields for a successful SET', () => {
    const entry = createHistoryRecord(`SET demo ${SECRET}`, OK, 7, 1_700_000_000_000);

    assert.deepEqual(entry, {
      id: 7,
      type: 'SET',
      command: 'SET demo <redacted>',
      status: 'success',
      summary: 'Response received',
      executedAt: 1_700_000_000_000,
    });
    assert.doesNotMatch(JSON.stringify(entry), new RegExp(SECRET));
  });

  test('records failed executions with a fixed summary', () => {
    const entry = createHistoryRecord('GET demo', { error: 'Not connected to BMis', noValue: false }, 1, 5);

    assert.equal(entry.status, 'failed');
    assert.equal(entry.summary, FAILURE_SUMMARY);
  });

  test('never copies backend error text into the summary', () => {
    for (const request of [`SET demo ${SECRET}`, `GET ${SECRET}`, `ECHO ${SECRET}`]) {
      const entry = createHistoryRecord(request, { error: `Rejected ${SECRET}`, noValue: false }, 1, 5);

      assert.equal(entry.summary, FAILURE_SUMMARY);
      assert.doesNotMatch(entry.summary, new RegExp(SECRET));
    }
  });

  test('summarizes an empty GET without exposing response bodies', () => {
    assert.equal(createHistoryRecord('GET missing', { error: '', noValue: true }, 1, 5).summary, 'No value found');
    assert.equal(createHistoryRecord('GET demo', OK, 1, 5).summary, 'Response received');
  });
});

describe('addHistoryRecord and clearHistory', () => {
  test('keeps the newest record first without mutating the input', () => {
    const first = [record('GET a', 1, 1)];
    const next = addHistoryRecord(first, record('GET b', 2, 2));

    assert.deepEqual(next.map(({ command }) => command), ['GET b', 'GET a']);
    assert.equal(first.length, 1);
  });

  test(`keeps at most ${HISTORY_BROWSER_LIMIT} records`, () => {
    let history: HistoryRecord[] = [];
    for (let index = 1; index <= HISTORY_BROWSER_LIMIT + 5; index += 1) {
      history = addHistoryRecord(history, record(`GET key${index}`, index, index));
    }

    assert.equal(history.length, HISTORY_BROWSER_LIMIT);
    assert.equal(history[0]?.command, `GET key${HISTORY_BROWSER_LIMIT + 5}`);
  });

  test('clearing removes every entry and recent suggestion', () => {
    assert.ok(sampleHistory().length > 0);
    const cleared = clearHistory();

    assert.deepEqual(cleared, []);
    assert.deepEqual(queryHistory(cleared, DEFAULT_HISTORY_QUERY), []);
    assert.deepEqual(recentCommands(cleared), []);
  });
});

describe('searchHistory', () => {
  test('matches safe command text case-insensitively', () => {
    assert.deepEqual(searchHistory(sampleHistory(), 'demo').map(({ id }) => id), [2, 1]);
    assert.deepEqual(searchHistory(sampleHistory(), '  incr ').map(({ id }) => id), [3]);
  });

  test('returns everything for a blank search and nothing for unknown text', () => {
    assert.equal(searchHistory(sampleHistory(), '   ').length, 4);
    assert.deepEqual(searchHistory(sampleHistory(), 'DEL'), []);
  });

  test('cannot find redacted SET values or other command arguments', () => {
    const history = [record(`SET demo ${SECRET}`, 1, 1), record(`AUTH ${SECRET}`, 2, 2)];

    assert.deepEqual(searchHistory(history, SECRET), []);
    assert.deepEqual(searchHistory(history, 'redacted').map(({ id }) => id), [1, 2]);
    assert.deepEqual(searchHistory(history, 'auth').map(({ id }) => id), [2]);
  });
});

describe('filterHistory', () => {
  test('filters by command type', () => {
    const history = sampleHistory();

    assert.deepEqual(filterHistory(history, { type: 'SET', status: 'ALL' }).map(({ id }) => id), [1]);
    assert.deepEqual(filterHistory(history, { type: 'GET', status: 'ALL' }).map(({ id }) => id), [4, 2]);
    assert.deepEqual(filterHistory(history, { type: 'OTHER', status: 'ALL' }).map(({ id }) => id), [3]);
    assert.equal(filterHistory(history, { type: 'ALL', status: 'ALL' }).length, 4);
  });

  test('filters by execution status', () => {
    const history = sampleHistory();

    assert.deepEqual(filterHistory(history, { type: 'ALL', status: 'failed' }).map(({ id }) => id), [3]);
    assert.deepEqual(
      filterHistory(history, { type: 'ALL', status: 'success' }).map(({ id }) => id),
      [4, 2, 1],
    );
    assert.deepEqual(filterHistory(history, { type: 'SET', status: 'failed' }), []);
  });
});

describe('sortHistory and queryHistory', () => {
  test('sorts newest-first or oldest-first without mutating the input', () => {
    const history = sampleHistory();
    const snapshot = history.map(({ id }) => id);

    assert.deepEqual(sortHistory(history, 'newest').map(({ id }) => id), [4, 3, 2, 1]);
    assert.deepEqual(sortHistory(history, 'oldest').map(({ id }) => id), [1, 2, 3, 4]);
    assert.deepEqual(history.map(({ id }) => id), snapshot);
  });

  test('breaks timestamp ties by record order', () => {
    const history = [record('GET a', 1, 10), record('GET b', 2, 10)];

    assert.deepEqual(sortHistory(history, 'newest').map(({ id }) => id), [2, 1]);
    assert.deepEqual(sortHistory(history, 'oldest').map(({ id }) => id), [1, 2]);
  });

  test('combines search, filters, and sort', () => {
    assert.deepEqual(
      queryHistory(sampleHistory(), { search: 'get', type: 'GET', status: 'success', sort: 'oldest' }).map(
        ({ id }) => id,
      ),
      [2, 4],
    );
  });
});

describe('reuseCommand', () => {
  test('returns GET and argument-free commands unchanged for editing', () => {
    for (const request of ['GET demo', 'PING', 'SET demo']) {
      const entry = record(request, 1, 1);
      assert.equal(reuseCommand(entry), request);
      assert.equal(isReuseTemplate(entry), false);
    }
  });

  test('turns SET into a key template without the original value', () => {
    const entry = record(`SET demo ${SECRET}`, 1, 1);

    assert.equal(reuseCommand(entry), 'SET demo ');
    assert.equal(isReuseTemplate(entry), true);
  });

  test('turns other commands into a name-only template', () => {
    for (const [request, template] of [
      [`AUTH ${SECRET}`, 'AUTH '],
      [`MSET a ${SECRET}`, 'MSET '],
      ['INCR counter', 'INCR '],
    ] as const) {
      const entry = record(request, 1, 1);
      assert.equal(reuseCommand(entry), template);
      assert.equal(isReuseTemplate(entry), true);
    }
  });
});

describe('recentCommands', () => {
  test('feeds safe, de-duplicated commands into existing suggestions', () => {
    const history = [
      record('GET demo', 1, 1),
      record(`SET demo ${SECRET}`, 2, 2),
      record('GET demo', 3, 3),
    ].reduce<HistoryRecord[]>(addHistoryRecord, []);

    assert.deepEqual(recentCommands(history), ['GET demo', 'SET demo ']);
    assert.deepEqual(commandSuggestions('', recentCommands(history)), [
      { kind: 'recent', label: 'GET demo', value: 'GET demo' },
      { kind: 'recent', label: 'SET demo ', value: 'SET demo ' },
      { kind: 'template', label: 'SET <key> <value>', value: 'SET ' },
      { kind: 'template', label: 'GET <key>', value: 'GET ' },
    ]);
    assert.deepEqual(
      commandSuggestions('g', recentCommands(history)).map(({ value }) => value),
      ['GET demo', 'GET '],
    );
  });

  test(`keeps at most ${HISTORY_LIMIT} suggestions`, () => {
    let history: HistoryRecord[] = [];
    for (let index = 1; index <= HISTORY_LIMIT + 5; index += 1) {
      history = addHistoryRecord(history, record(`GET key${index}`, index, index));
    }

    assert.equal(recentCommands(history).length, HISTORY_LIMIT);
    assert.equal(recentCommands(history)[0], `GET key${HISTORY_LIMIT + 5}`);
  });
});

describe('executeAndRecord', () => {
  test('records after the command completes and returns the unchanged result', async () => {
    const sent: PythonCommand[] = [];
    const recorded: HistoryRecord[] = [];
    const result = await executeAndRecord('GET demo', (entry) => recorded.push(entry), {
      nextId: counter(),
      send: respondWith({ status: true, result: 'Mayur' }, sent),
      now: () => 42,
    });

    assert.deepEqual(sent, [{ command: 'execute', request: 'GET demo' }]);
    assert.match(result.output, /"result": "Mayur"/);
    assert.deepEqual(recorded, [
      { id: 1, type: 'GET', command: 'GET demo', status: 'success', summary: 'Response received', executedAt: 42 },
    ]);
    assert.doesNotMatch(JSON.stringify(recorded), /Mayur/);
  });

  test('records backend and transport failures', async () => {
    const recorded: HistoryRecord[] = [];
    const nextId = counter();
    const result = await executeAndRecord('GET demo', (entry) => recorded.push(entry), {
      nextId,
      send: respondWith({ status: false, error: 'Not connected to BMis' }),
    });
    assert.equal(result.error, 'Not connected to BMis');
    await executeAndRecord(`SET demo ${SECRET}`, (entry) => recorded.push(entry), {
      nextId,
      send: () => Promise.reject(new Error('Python backend closed the connection')),
    });

    assert.deepEqual(
      recorded.map(({ id, type, command, status, summary }) => ({ id, type, command, status, summary })),
      [
        { id: 1, type: 'GET', command: 'GET demo', status: 'failed', summary: FAILURE_SUMMARY },
        { id: 2, type: 'SET', command: 'SET demo <redacted>', status: 'failed', summary: FAILURE_SUMMARY },
      ],
    );
  });

  test('console and quick actions share one redacted history', async () => {
    let history: HistoryRecord[] = [];
    const store = (entry: HistoryRecord) => {
      history = addHistoryRecord(history, entry);
    };
    const options = { nextId: counter(), send: respondWith({ status: true, result: 'OK' }) };
    const quickSet = buildSetCommand('demo', SECRET);
    const quickGet = buildGetCommand('missing');
    assert.ok(quickSet.ok && quickGet.ok);

    await executeAndRecord(`SET demo ${SECRET}`, store, options);
    await executeAndRecord(quickSet.command, store, options);
    const getResult = await executeAndRecord(quickGet.command, store, {
      ...options,
      send: respondWith({ status: true, result: null }),
    });

    assert.equal(getResult.noValue, true);
    assert.deepEqual(
      history.map(({ type, command, summary }) => ({ type, command, summary })),
      [
        { type: 'GET', command: 'GET missing', summary: 'No value found' },
        { type: 'SET', command: 'SET demo <redacted>', summary: 'Response received' },
        { type: 'SET', command: 'SET demo <redacted>', summary: 'Response received' },
      ],
    );
    assert.doesNotMatch(JSON.stringify(history), new RegExp(SECRET));
  });
});
