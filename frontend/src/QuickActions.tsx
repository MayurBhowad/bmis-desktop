import { useRef, useState, type FormEvent, type RefObject } from 'react';
import {
  buildGetCommand,
  buildSetCommand,
  type BuiltCommand,
  type CommandField,
  type CommandResult,
} from './commandBuilder';

type QuickAction = 'set' | 'get';

type FieldError = { field: CommandField; message: string };

type QuickActionsProps = {
  enabled: boolean;
  onRun: (request: string) => Promise<CommandResult | null>;
};

const NO_ERRORS: Record<QuickAction, FieldError | null> = { set: null, get: null };

export function QuickActions({ enabled, onRun }: QuickActionsProps) {
  const [setKey, updateSetKey] = useState('');
  const [setValue, updateSetValue] = useState('');
  const [getKey, updateGetKey] = useState('');
  const [errors, setErrors] = useState(NO_ERRORS);
  const [running, setRunning] = useState<QuickAction | null>(null);
  const [getNotice, setGetNotice] = useState('');

  const requestLock = useRef(false);
  const setKeyInput = useRef<HTMLInputElement>(null);
  const setValueInput = useRef<HTMLInputElement>(null);
  const getKeyInput = useRef<HTMLInputElement>(null);

  const setPreview = buildSetCommand(setKey, setValue);
  const getPreview = buildGetCommand(getKey);

  const clearError = (action: QuickAction) => {
    setErrors((current) => (current[action] ? { ...current, [action]: null } : current));
  };

  const submit = (
    action: QuickAction,
    built: BuiltCommand,
    inputs: Partial<Record<CommandField, RefObject<HTMLInputElement | null>>>,
  ) => {
    if (!enabled || requestLock.current) {
      return;
    }
    if (!built.ok) {
      setErrors((current) => ({ ...current, [action]: built }));
      inputs[built.field]?.current?.focus();
      return;
    }
    requestLock.current = true;
    setRunning(action);
    clearError(action);
    if (action === 'get') {
      setGetNotice('');
    }
    void (async () => {
      try {
        const result = await onRun(built.command);
        if (action === 'get' && result?.noValue) {
          setGetNotice(`No value found for key "${getKey.trim()}".`);
        }
      } finally {
        requestLock.current = false;
        setRunning(null);
      }
    })();
  };

  const handleSet = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submit('set', setPreview, { key: setKeyInput, value: setValueInput });
  };

  const handleGet = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submit('get', getPreview, { key: getKeyInput });
  };

  const fieldProps = (action: QuickAction, field: CommandField) => {
    const invalid = errors[action]?.field === field;
    return {
      'aria-invalid': invalid,
      'aria-describedby': invalid ? `quick-${action}-error` : undefined,
    };
  };

  return (
    <section className="panel" aria-labelledby="quick-actions-heading">
      <div className="panel-heading">
        <div className="panel-title">
          <h2 id="quick-actions-heading">Quick actions</h2>
          <p className="hint">
            Build a SET or GET command without typing it. The result appears in the console
            response.
          </p>
        </div>
      </div>

      <div className="quick-actions">
        <form className="quick-form" onSubmit={handleSet} aria-labelledby="quick-set-heading" noValidate>
          <h3 id="quick-set-heading">SET value</h3>
          <div className="quick-fields">
            <label htmlFor="quick-set-key">
              Key
              <input
                ref={setKeyInput}
                id="quick-set-key"
                name="key"
                type="text"
                value={setKey}
                required
                autoComplete="off"
                spellCheck={false}
                placeholder="demo"
                disabled={!enabled}
                {...fieldProps('set', 'key')}
                onChange={(event) => {
                  updateSetKey(event.target.value);
                  clearError('set');
                }}
              />
            </label>
            <label htmlFor="quick-set-value">
              Value
              <input
                ref={setValueInput}
                id="quick-set-value"
                name="value"
                type="text"
                value={setValue}
                required
                autoComplete="off"
                spellCheck={false}
                placeholder="Mayur"
                disabled={!enabled}
                {...fieldProps('set', 'value')}
                onChange={(event) => {
                  updateSetValue(event.target.value);
                  clearError('set');
                }}
              />
            </label>
          </div>
          {errors.set && (
            <p className="error" id="quick-set-error" role="alert">
              {errors.set.message}
            </p>
          )}
          <div className="quick-footer">
            <button type="submit" className="primary" disabled={!enabled} aria-busy={running === 'set'}>
              {running === 'set' ? 'Executing...' : 'Execute SET'}
            </button>
            {setPreview.ok && <code className="command-preview">{setPreview.command}</code>}
          </div>
        </form>

        <form className="quick-form" onSubmit={handleGet} aria-labelledby="quick-get-heading" noValidate>
          <h3 id="quick-get-heading">GET value</h3>
          <div className="quick-fields">
            <label htmlFor="quick-get-key">
              Key
              <input
                ref={getKeyInput}
                id="quick-get-key"
                name="key"
                type="text"
                value={getKey}
                required
                autoComplete="off"
                spellCheck={false}
                placeholder="demo"
                disabled={!enabled}
                {...fieldProps('get', 'key')}
                onChange={(event) => {
                  updateGetKey(event.target.value);
                  clearError('get');
                  setGetNotice('');
                }}
              />
            </label>
          </div>
          {errors.get && (
            <p className="error" id="quick-get-error" role="alert">
              {errors.get.message}
            </p>
          )}
          {getNotice && (
            <p className="notice" role="status">
              {getNotice}
            </p>
          )}
          <div className="quick-footer">
            <button type="submit" className="primary" disabled={!enabled} aria-busy={running === 'get'}>
              {running === 'get' ? 'Executing...' : 'Execute GET'}
            </button>
            {getPreview.ok && <code className="command-preview">{getPreview.command}</code>}
          </div>
        </form>
      </div>
    </section>
  );
}
