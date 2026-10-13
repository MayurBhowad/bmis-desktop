import { useRef, useState, type FormEvent } from 'react';
import './App.css';
import { ConnectionProfiles } from './ConnectionProfiles';
import {
  failureMessage,
  invokeErrorMessage,
  isRecord,
  parsePort,
  pythonRequest,
  type PythonCommand,
} from './pythonApi';
import type { ConnectionProfile } from './profiles';

type ConnectionState = {
  connected: boolean;
  host: string | null;
  port: number | null;
};

type ConnectionAction = 'connect' | 'status' | 'disconnect';

const DISCONNECTED: ConnectionState = {
  connected: false,
  host: null,
  port: null,
};

function formatResponse(body: unknown): string {
  return JSON.stringify(body, null, 2);
}

function isPortNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value);
}

function connectionStateFrom(body: unknown): ConnectionState | null {
  if (!isRecord(body) || typeof body.connected !== 'boolean') {
    return null;
  }
  if (body.connected) {
    if (typeof body.host !== 'string' || !isPortNumber(body.port)) {
      return null;
    }
    return { connected: true, host: body.host, port: body.port };
  }
  if (body.host !== null || body.port !== null) {
    return null;
  }
  return DISCONNECTED;
}

function connectionSummary(state: ConnectionState): string {
  if (state.connected && state.host !== null && state.port !== null) {
    return `Connected to ${state.host}:${state.port}`;
  }
  return 'Disconnected';
}

function App() {
  const [pingLoading, setPingLoading] = useState(false);
  const [pingResponse, setPingResponse] = useState('');
  const [pingError, setPingError] = useState('');

  const [host, setHost] = useState('127.0.0.1');
  const [port, setPort] = useState('6379');
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [connection, setConnection] = useState<ConnectionState>(DISCONNECTED);
  const [connectionLoading, setConnectionLoading] = useState<ConnectionAction | null>(null);
  const [connectionMessage, setConnectionMessage] = useState('');
  const [connectionError, setConnectionError] = useState('');

  const [command, setCommand] = useState('');
  const [commandLoading, setCommandLoading] = useState(false);
  const [commandOutput, setCommandOutput] = useState('');
  const [commandError, setCommandError] = useState('');

  const pingRequest = useRef(false);
  const connectionRequest = useRef(false);
  const commandRequest = useRef(false);

  const inputsDisabled = connection.connected || connectionLoading !== null;
  const commandEnabled = connection.connected && connectionLoading === null && !commandLoading;

  const sendPing = async () => {
    if (pingRequest.current) {
      return;
    }
    pingRequest.current = true;
    setPingLoading(true);
    setPingError('');
    try {
      const parsed = await pythonRequest({ command: 'ping' });
      const failure = failureMessage(parsed.body);
      setPingResponse(formatResponse(parsed.body));
      setPingError(failure ?? '');
    } catch (error) {
      setPingResponse('');
      setPingError(error instanceof Error ? error.message : invokeErrorMessage(error));
    } finally {
      pingRequest.current = false;
      setPingLoading(false);
    }
  };

  const runConnection = async (action: ConnectionAction, payload: PythonCommand) => {
    if (connectionRequest.current) {
      return;
    }
    connectionRequest.current = true;
    setConnectionLoading(action);
    setConnectionError('');
    setConnectionMessage('');
    try {
      const parsed = await pythonRequest(payload);
      const failure = failureMessage(parsed.body);
      if (failure) {
        setConnectionError(failure);
        return;
      }
      const next = connectionStateFrom(parsed.body);
      if (!next) {
        setConnectionError('Backend returned an unexpected response');
        return;
      }
      setConnection(next);
      setConnectionMessage(connectionSummary(next));
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : invokeErrorMessage(error));
    } finally {
      connectionRequest.current = false;
      setConnectionLoading(null);
    }
  };

  const refreshConnectionAfterExecuteFailure = async () => {
    try {
      const parsed = await pythonRequest({ command: 'status' });
      if (failureMessage(parsed.body)) {
        return;
      }
      const next = connectionStateFrom(parsed.body);
      if (!next) {
        return;
      }
      setConnection(next);
      setConnectionMessage(connectionSummary(next));
    } catch {
      // Keep the execute error already shown. A failed status query must not replace it.
    }
  };

  const handleSelectProfile = (profile: ConnectionProfile) => {
    setSelectedProfileId(profile.id);
    setHost(profile.host);
    setPort(String(profile.port));
    setConnectionError('');
  };

  const handleProfileDeleted = (id: string) => {
    setSelectedProfileId((current) => (current === id ? null : current));
  };

  const handleConnect = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (connectionRequest.current || connection.connected) {
      return;
    }
    const parsedHost = host.trim();
    if (!parsedHost) {
      setConnectionMessage('');
      setConnectionError('Host must be a non-empty hostname or IP address');
      return;
    }
    const parsedPort = parsePort(port);
    if (parsedPort === null) {
      setConnectionMessage('');
      setConnectionError('Port must be an integer between 1 and 65535');
      return;
    }
    void runConnection('connect', {
      command: 'connect',
      host: parsedHost,
      port: parsedPort,
    });
  };

  const handleExecute = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (commandRequest.current || !connection.connected) {
      return;
    }
    if (!command.trim()) {
      setCommandError('Enter a command before executing.');
      return;
    }
    commandRequest.current = true;
    setCommandLoading(true);
    setCommandError('');
    void (async () => {
      try {
        const parsed = await pythonRequest({
          command: 'execute',
          request: command,
        });
        setCommandOutput(formatResponse(parsed.body));
        const failure = failureMessage(parsed.body);
        setCommandError(failure ?? '');
        if (failure) {
          await refreshConnectionAfterExecuteFailure();
        }
      } catch (error) {
        setCommandOutput('');
        setCommandError(error instanceof Error ? error.message : invokeErrorMessage(error));
      } finally {
        commandRequest.current = false;
        setCommandLoading(false);
      }
    })();
  };

  return (
    <main className="app">
      <header className="header">
        <h1>BMis Desktop</h1>
        <p>Connect to a BMis server and run commands through the local Python backend.</p>
      </header>

      <section className="panel" aria-labelledby="python-heading">
        <div className="panel-heading">
          <h2 id="python-heading">Python backend</h2>
          <p className="hint">Health check for the desktop Python process.</p>
        </div>
        <button type="button" onClick={() => void sendPing()} disabled={pingLoading} aria-busy={pingLoading}>
          {pingLoading ? 'Pinging...' : 'Ping Python'}
        </button>
        {pingError && (
          <p className="error" role="alert">
            {pingError}
          </p>
        )}
        {pingResponse && (
          <pre className="output" aria-label="Python backend response">
            {pingResponse}
          </pre>
        )}
      </section>

      <ConnectionProfiles
        selectedId={selectedProfileId}
        suggestedHost={host}
        suggestedPort={port}
        onSelect={handleSelectProfile}
        onDeleted={handleProfileDeleted}
      />

      <section className="panel" aria-labelledby="connection-heading">
        <div className="panel-heading">
          <h2 id="connection-heading">BMis server</h2>
          <p
            className={connection.connected ? 'status status-connected' : 'status status-disconnected'}
            role="status"
            aria-live="polite"
          >
            {connection.connected ? 'Connected' : 'Disconnected'}
          </p>
        </div>

        <form className="connection-form" onSubmit={handleConnect}>
          <label htmlFor="bmis-host">
            Hostname or IP
            <input
              id="bmis-host"
              name="host"
              type="text"
              value={host}
              autoComplete="off"
              spellCheck={false}
              disabled={inputsDisabled}
              onChange={(event) => {
                setHost(event.target.value);
                setSelectedProfileId(null);
              }}
            />
          </label>
          <label htmlFor="bmis-port">
            Port
            <input
              id="bmis-port"
              name="port"
              type="text"
              inputMode="numeric"
              value={port}
              autoComplete="off"
              spellCheck={false}
              disabled={inputsDisabled}
              onChange={(event) => {
                setPort(event.target.value);
                setSelectedProfileId(null);
              }}
            />
          </label>
          <button type="submit" disabled={inputsDisabled} aria-busy={connectionLoading === 'connect'}>
            {connectionLoading === 'connect' ? 'Connecting...' : 'Connect'}
          </button>
        </form>

        <div className="actions">
          <button
            type="button"
            onClick={() => void runConnection('status', { command: 'status' })}
            disabled={connectionLoading !== null}
            aria-busy={connectionLoading === 'status'}
          >
            {connectionLoading === 'status' ? 'Refreshing...' : 'Refresh Status'}
          </button>
          <button
            type="button"
            onClick={() => void runConnection('disconnect', { command: 'disconnect' })}
            disabled={connectionLoading !== null}
            aria-busy={connectionLoading === 'disconnect'}
          >
            {connectionLoading === 'disconnect' ? 'Disconnecting...' : 'Disconnect'}
          </button>
        </div>

        {connectionMessage && <p className="notice">{connectionMessage}</p>}
        {connectionError && (
          <p className="error" id="connection-error" role="alert">
            {connectionError}
          </p>
        )}
      </section>

      <section className="panel" aria-labelledby="console-heading">
        <div className="panel-heading">
          <h2 id="console-heading">Command console</h2>
          <p className="hint">Try SET demo Mayur, then GET demo.</p>
        </div>
        <form className="command-form" onSubmit={handleExecute}>
          <label htmlFor="bmis-command">
            Command
            <input
              id="bmis-command"
              name="command"
              type="text"
              value={command}
              autoComplete="off"
              spellCheck={false}
              placeholder="SET demo Mayur"
              disabled={!commandEnabled}
              onChange={(event) => setCommand(event.target.value)}
            />
          </label>
          <button type="submit" disabled={!commandEnabled} aria-busy={commandLoading}>
            {commandLoading ? 'Executing...' : 'Execute'}
          </button>
        </form>
        {commandError && (
          <p className="error" role="alert">
            {commandError}
          </p>
        )}
        <pre className="output" aria-label="Command output" aria-live="polite">
          {commandOutput || 'Command output will appear here.'}
        </pre>
      </section>
    </main>
  );
}

export default App;
