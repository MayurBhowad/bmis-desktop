import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import {
  DEFAULT_HISTORY_QUERY,
  isReuseTemplate,
  queryHistory,
  reuseCommand,
  type HistoryCommandType,
  type HistoryQuery,
  type HistoryRecord,
  type HistorySort,
  type HistoryStatus,
} from './commandHistory';

type HistoryBrowserProps = {
  open: boolean;
  history: readonly HistoryRecord[];
  canReuse: boolean;
  onReuse: (command: string) => void;
  onClear: () => void;
  onClose: () => void;
};

const TYPE_OPTIONS: readonly (HistoryCommandType | 'ALL')[] = ['ALL', 'SET', 'GET', 'OTHER'];
const STATUS_OPTIONS: readonly (HistoryStatus | 'ALL')[] = ['ALL', 'success', 'failed'];
const SORT_OPTIONS: readonly HistorySort[] = ['newest', 'oldest'];

const TYPE_LABELS: Record<HistoryCommandType, string> = { SET: 'SET', GET: 'GET', OTHER: 'Other' };
const STATUS_LABELS: Record<HistoryStatus, string> = { success: 'Success', failed: 'Failed' };

const timestampFormat = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'medium',
});

function pick<T extends string>(options: readonly T[], value: string, fallback: T): T {
  return options.find((option) => option === value) ?? fallback;
}

export function HistoryBrowser({
  open,
  history,
  canReuse,
  onReuse,
  onClear,
  onClose,
}: HistoryBrowserProps) {
  const [query, setQuery] = useState<HistoryQuery>(DEFAULT_HISTORY_QUERY);
  const dialog = useRef<HTMLDialogElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);

  const results = queryHistory(history, query);
  const filtered =
    query.search.trim() !== '' || query.type !== 'ALL' || query.status !== 'ALL';

  useEffect(() => {
    const element = dialog.current;
    if (!element) {
      return;
    }
    if (open && !element.open) {
      element.showModal();
    } else if (!open && element.open) {
      element.close();
    }
  }, [open]);

  const updateQuery = (next: Partial<HistoryQuery>) => {
    setQuery((current) => ({ ...current, ...next }));
  };

  const resetFilters = () => {
    updateQuery({ search: '', type: 'ALL', status: 'ALL' });
  };

  // The modal must close before the console input can take focus.
  const reuse = (record: HistoryRecord) => {
    dialog.current?.close();
    onReuse(reuseCommand(record));
  };

  const clear = () => {
    onClear();
    closeButton.current?.focus();
  };

  const moveFocus = (event: KeyboardEvent<HTMLUListElement>) => {
    const buttons = Array.from(
      list.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [],
    );
    const index = buttons.findIndex((button) => button === document.activeElement);
    if (index === -1) {
      return;
    }
    const targets: Partial<Record<string, number>> = {
      ArrowDown: Math.min(index + 1, buttons.length - 1),
      ArrowUp: Math.max(index - 1, 0),
      Home: 0,
      End: buttons.length - 1,
    };
    const target = targets[event.key];
    if (target === undefined) {
      return;
    }
    event.preventDefault();
    buttons[target]?.focus();
  };

  return (
    <dialog
      ref={dialog}
      className="history-dialog"
      aria-labelledby="history-heading"
      aria-describedby="history-privacy"
      onClose={onClose}
    >
      <div className="panel-heading">
        <div className="panel-title">
          <h2 id="history-heading">Command history</h2>
          <p className="hint" id="history-privacy">
            Kept in memory for this session only. SET values and arguments of other commands are
            never shown or restored.
          </p>
        </div>
        <button
          ref={closeButton}
          type="button"
          className="secondary"
          aria-label="Close command history"
          onClick={() => dialog.current?.close()}
        >
          Close
        </button>
      </div>

      <div className="history-filters" role="search" aria-label="Filter command history">
        <label htmlFor="history-search">
          Search
          <input
            id="history-search"
            name="history-search"
            type="text"
            value={query.search}
            autoComplete="off"
            spellCheck={false}
            placeholder="GET demo"
            onChange={(event) => updateQuery({ search: event.target.value })}
          />
        </label>
        <label htmlFor="history-type">
          Type
          <select
            id="history-type"
            value={query.type}
            onChange={(event) => updateQuery({ type: pick(TYPE_OPTIONS, event.target.value, 'ALL') })}
          >
            <option value="ALL">All types</option>
            <option value="SET">SET</option>
            <option value="GET">GET</option>
            <option value="OTHER">Other</option>
          </select>
        </label>
        <label htmlFor="history-status">
          Status
          <select
            id="history-status"
            value={query.status}
            onChange={(event) =>
              updateQuery({ status: pick(STATUS_OPTIONS, event.target.value, 'ALL') })
            }
          >
            <option value="ALL">All statuses</option>
            <option value="success">Success</option>
            <option value="failed">Failed</option>
          </select>
        </label>
        <label htmlFor="history-sort">
          Sort
          <select
            id="history-sort"
            value={query.sort}
            onChange={(event) => updateQuery({ sort: pick(SORT_OPTIONS, event.target.value, 'newest') })}
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </select>
        </label>
      </div>

      <p className="hint" role="status" aria-live="polite">
        {history.length === 0
          ? 'No commands recorded.'
          : `Showing ${results.length} of ${history.length} commands.`}
      </p>

      {history.length === 0 ? (
        <p className="history-empty">
          No commands yet. Commands run from the console or quick actions appear here.
        </p>
      ) : results.length === 0 ? (
        <div className="history-empty">
          <p>No commands match the current search or filters.</p>
          {filtered && (
            <button type="button" className="secondary" onClick={resetFilters}>
              Reset filters
            </button>
          )}
        </div>
      ) : (
        <ul
          ref={list}
          className="history-list"
          aria-label="Command history entries"
          onKeyDown={moveFocus}
        >
          {results.map((record) => {
            const template = isReuseTemplate(record);
            return (
              <li key={record.id} className="history-row">
                <div className="history-meta">
                  <span className="pill pill-idle history-type">{TYPE_LABELS[record.type]}</span>
                  <span className={record.status === 'success' ? 'pill pill-ok' : 'pill pill-error'}>
                    {STATUS_LABELS[record.status]}
                  </span>
                  <time className="history-time" dateTime={new Date(record.executedAt).toISOString()}>
                    {timestampFormat.format(record.executedAt)}
                  </time>
                </div>
                <code className="history-command">{record.command}</code>
                <p className="history-summary">{record.summary}</p>
                <button
                  type="button"
                  className="secondary"
                  disabled={!canReuse}
                  aria-label={
                    template
                      ? `Use ${reuseCommand(record).trim()} template in the console. Redacted arguments are not restored.`
                      : `Use ${record.command} in the console`
                  }
                  onClick={() => reuse(record)}
                >
                  {template ? 'Use as template' : 'Use command'}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <div className="history-footer">
        {!canReuse && history.length > 0 && (
          <p className="hint">Reuse is available while connected and no command is running.</p>
        )}
        <button type="button" className="danger" disabled={history.length === 0} onClick={clear}>
          Clear history
        </button>
      </div>
    </dialog>
  );
}
