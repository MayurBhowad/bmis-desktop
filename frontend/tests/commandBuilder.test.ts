import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import {
  addToHistory,
  buildGetCommand,
  buildSetCommand,
  commandSuggestions,
  executeBmisCommand,
  HISTORY_LIMIT,
  runExclusive,
  SUGGESTION_LIMIT,
  type SendRequest,
} from '../src/commandBuilder.ts';
import type { PythonCommand } from '../src/pythonApi.ts';

function respondWith(body: unknown, sent: PythonCommand[] = []): SendRequest {
  return async (payload) => {
    sent.push(payload);
    return { raw: JSON.stringify(body), body };
  };
}

describe('buildSetCommand', () => {
  test('generates the verified SET syntax', () => {
    assert.deepEqual(buildSetCommand('desktop_test', 'Mayur'), {
      ok: true,
      command: 'SET desktop_test Mayur',
    });
  });

  test('trims surrounding whitespace', () => {
    assert.deepEqual(buildSetCommand('  demo ', '\tMayur  '), {
      ok: true,
      command: 'SET demo Mayur',
    });
  });

  test('requires a key before checking the value', () => {
    assert.deepEqual(buildSetCommand('', ''), {
      ok: false,
      field: 'key',
      message: 'Key is required.',
    });
    assert.deepEqual(buildSetCommand('   ', 'Mayur'), {
      ok: false,
      field: 'key',
      message: 'Key is required.',
    });
  });

  test('requires a value', () => {
    for (const value of ['', '   ', '\n']) {
      assert.deepEqual(buildSetCommand('demo', value), {
        ok: false,
        field: 'value',
        message: 'Value is required.',
      });
    }
  });

  test('rejects tokens that would split or inject commands', () => {
    const unsafe = ['two words', 'demo\nDEL demo', 'demo\r\nDEL demo', 'a\tb', 'a\u0000b', 'a\u00a0b'];
    for (const token of unsafe) {
      assert.deepEqual(buildSetCommand(token, 'Mayur'), {
        ok: false,
        field: 'key',
        message: 'Key cannot contain spaces or control characters.',
      });
      assert.deepEqual(buildSetCommand('demo', token), {
        ok: false,
        field: 'value',
        message: 'Value cannot contain spaces or control characters.',
      });
    }
  });

  test('keeps printable non-ASCII tokens unchanged', () => {
    assert.deepEqual(buildSetCommand('user:1', 'नमस्ते'), {
      ok: true,
      command: 'SET user:1 नमस्ते',
    });
  });
});

describe('buildGetCommand', () => {
  test('generates the verified GET syntax', () => {
    assert.deepEqual(buildGetCommand(' desktop_test '), { ok: true, command: 'GET desktop_test' });
  });

  test('requires a key', () => {
    for (const key of ['', '  ']) {
      assert.deepEqual(buildGetCommand(key), {
        ok: false,
        field: 'key',
        message: 'Key is required.',
      });
    }
  });

  test('rejects unsafe keys', () => {
    assert.deepEqual(buildGetCommand('demo\nDEL demo'), {
      ok: false,
      field: 'key',
      message: 'Key cannot contain spaces or control characters.',
    });
  });
});

describe('executeBmisCommand', () => {
  test('sends the request through the execute IPC command', async () => {
    const sent: PythonCommand[] = [];
    const result = await executeBmisCommand(
      'SET demo Mayur',
      respondWith({ status: true, result: 'OK' }, sent),
    );

    assert.deepEqual(sent, [{ command: 'execute', request: 'SET demo Mayur' }]);
    assert.deepEqual(result, {
      output: JSON.stringify({ status: true, result: 'OK' }, null, 2),
      error: '',
      backendFailure: false,
      noValue: false,
    });
  });

  test('forwards direct console text unchanged', async () => {
    const sent: PythonCommand[] = [];
    await executeBmisCommand('  INCR counter ', respondWith({ status: true, result: 1 }, sent));

    assert.deepEqual(sent, [{ command: 'execute', request: '  INCR counter ' }]);
  });

  test('returns the retrieved GET value', async () => {
    const result = await executeBmisCommand(
      'GET demo',
      respondWith({ status: true, result: 'Mayur' }),
    );

    assert.equal(result.error, '');
    assert.equal(result.noValue, false);
    assert.match(result.output, /"result": "Mayur"/);
  });

  test('flags an empty GET result', async () => {
    const result = await executeBmisCommand('GET missing', respondWith({ status: true, result: null }));

    assert.equal(result.error, '');
    assert.equal(result.backendFailure, false);
    assert.equal(result.noValue, true);
    assert.match(result.output, /"result": null/);
  });

  test('reports backend failures and keeps the response visible', async () => {
    const body = { status: false, error: 'Not connected to BMis' };
    const result = await executeBmisCommand('GET demo', respondWith(body));

    assert.deepEqual(result, {
      output: JSON.stringify(body, null, 2),
      error: 'Not connected to BMis',
      backendFailure: true,
      noValue: false,
    });
  });

  test('treats unexpected bodies as backend failures', async () => {
    for (const body of [{}, 'OK', null, { status: 'yes' }]) {
      const result = await executeBmisCommand('GET demo', respondWith(body));
      assert.equal(result.error, 'Backend returned an unexpected response');
      assert.equal(result.backendFailure, true);
      assert.equal(result.noValue, false);
    }
  });

  test('reports transport errors without output', async () => {
    const rejectWithError: SendRequest = async () => {
      throw new Error('Backend returned malformed JSON');
    };
    const rejectWithString: SendRequest = () => Promise.reject('Python process exited');

    assert.deepEqual(await executeBmisCommand('GET demo', rejectWithError), {
      output: '',
      error: 'Backend returned malformed JSON',
      backendFailure: false,
      noValue: false,
    });
    assert.equal((await executeBmisCommand('GET demo', rejectWithString)).error, 'Python process exited');
  });
});

describe('addToHistory', () => {
  test('puts the newest command first without duplicates', () => {
    const history = addToHistory(addToHistory(addToHistory([], 'SET a 1'), 'GET a'), 'SET a 1');

    assert.deepEqual(history, ['SET a 1', 'GET a']);
  });

  test('ignores blank commands and keeps the input unchanged', () => {
    const history = ['GET a'];

    assert.deepEqual(addToHistory(history, '   '), ['GET a']);
    assert.notEqual(addToHistory(history, 'GET b'), history);
    assert.deepEqual(history, ['GET a']);
  });

  test(`keeps at most ${HISTORY_LIMIT} entries`, () => {
    let history: string[] = [];
    for (let index = 0; index < HISTORY_LIMIT + 5; index += 1) {
      history = addToHistory(history, `GET key${index}`);
    }

    assert.equal(history.length, HISTORY_LIMIT);
    assert.equal(history[0], `GET key${HISTORY_LIMIT + 4}`);
  });
});

describe('commandSuggestions', () => {
  test('offers recent commands and SET/GET templates for empty input', () => {
    assert.deepEqual(commandSuggestions('', ['GET demo', 'SET demo Mayur']), [
      { kind: 'recent', label: 'GET demo', value: 'GET demo' },
      { kind: 'recent', label: 'SET demo Mayur', value: 'SET demo Mayur' },
      { kind: 'template', label: 'SET <key> <value>', value: 'SET ' },
      { kind: 'template', label: 'GET <key>', value: 'GET ' },
    ]);
  });

  test('filters by case-insensitive prefix', () => {
    assert.deepEqual(
      commandSuggestions('s', ['GET demo', 'SET demo Mayur']).map(({ value }) => value),
      ['SET demo Mayur', 'SET '],
    );
    assert.deepEqual(
      commandSuggestions('get d', ['GET demo', 'GET other']).map(({ value }) => value),
      ['GET demo'],
    );
  });

  test('hides a template once it has been typed and skips the exact current input', () => {
    assert.deepEqual(
      commandSuggestions('GET ', ['GET demo']).map(({ value }) => value),
      ['GET demo'],
    );
    assert.deepEqual(commandSuggestions('GET demo', ['GET demo']), []);
  });

  test('only suggests verified SET and GET templates', () => {
    assert.deepEqual(commandSuggestions('INCR', []), []);
    assert.deepEqual(commandSuggestions('d', []), []);
  });

  test(`returns at most ${SUGGESTION_LIMIT} suggestions and keeps templates visible`, () => {
    const history = Array.from({ length: HISTORY_LIMIT }, (_, index) => `GET key${index}`);
    const suggestions = commandSuggestions('', history);

    assert.equal(suggestions.length, SUGGESTION_LIMIT);
    assert.deepEqual(
      suggestions.filter(({ kind }) => kind === 'template').map(({ value }) => value),
      ['SET ', 'GET '],
    );
  });
});

describe('runExclusive', () => {
  test('holds the lock while running and ignores duplicate submissions', async () => {
    const lock = { current: false };
    let release: (value: string) => void = () => {};
    let calls = 0;
    const task = () => {
      calls += 1;
      return new Promise<string>((resolve) => {
        release = resolve;
      });
    };

    const first = runExclusive(lock, task);
    assert.equal(lock.current, true);
    assert.equal(await runExclusive(lock, task), null);
    assert.equal(calls, 1);

    release('done');
    assert.equal(await first, 'done');
    assert.equal(lock.current, false);
  });

  test('releases the lock when the task fails', async () => {
    const lock = { current: false };

    await assert.rejects(
      runExclusive(lock, () => Promise.reject(new Error('boom'))),
      /boom/,
    );
    assert.equal(lock.current, false);
    assert.equal(await runExclusive(lock, async () => 'next'), 'next');
  });
});
