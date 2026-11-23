import { useEffect, useRef, useState } from 'react';
import { fetchKeyPage } from './keyBrowser.ts';

type KeyBrowserProps = {
  connectionId: string | null;
};

export function KeyBrowser({ connectionId }: KeyBrowserProps) {
  const [keys, setKeys] = useState<string[]>([]);
  const [nextCursor, setNextCursor] = useState('0');
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const requestLock = useRef(false);
  const generation = useRef(0);
  const initialRequest = useRef<{
    connectionId: string;
    promise: ReturnType<typeof fetchKeyPage>;
  } | null>(null);

  useEffect(() => {
    const currentGeneration = ++generation.current;
    let active = true;

    setKeys([]);
    setNextCursor('0');
    setHasMore(false);
    setError('');

    if (!connectionId) {
      initialRequest.current = null;
      setLoading(false);

      return () => {
        active = false;
      };
    }

    setLoading(true);

    let request = initialRequest.current;

    if (!request || request.connectionId !== connectionId) {
      request = {
        connectionId,
        promise: fetchKeyPage(),
      };

      initialRequest.current = request;
    }

    request.promise
      .then((page) => {
        if (!active || generation.current !== currentGeneration) {
          return;
        }

        setKeys(page.keys);
        setNextCursor(page.nextCursor);
        setHasMore(page.hasMore);
      })
      .catch((cause: unknown) => {
        if (!active || generation.current !== currentGeneration) {
          return;
        }

        setError(
          cause instanceof Error
            ? cause.message
            : 'Unable to load keys',
        );
      })
      .finally(() => {
        if (initialRequest.current?.promise === request.promise) {
          initialRequest.current = null;
        }

        if (active && generation.current === currentGeneration) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [connectionId]);

  const loadMore = async () => {
    if (
      !connectionId ||
      !hasMore ||
      loading ||
      requestLock.current
    ) {
      return;
    }

    requestLock.current = true;
    const currentGeneration = generation.current;

    setLoading(true);
    setError('');

    try {
      const page = await fetchKeyPage(nextCursor);

      if (generation.current !== currentGeneration) {
        return;
      }

      setKeys((current) => {
        const existing = new Set(current);
        const additions = page.keys.filter((key) => !existing.has(key));
        return [...current, ...additions];
      });

      setNextCursor(page.nextCursor);
      setHasMore(page.hasMore);
    } catch (cause) {
      if (generation.current === currentGeneration) {
        setError(
          cause instanceof Error
            ? cause.message
            : 'Unable to load more keys',
        );
      }
    } finally {
      requestLock.current = false;

      if (generation.current === currentGeneration) {
        setLoading(false);
      }
    }
  };

  const refresh = async () => {
    if (!connectionId || loading || requestLock.current) {
      return;
    }

    requestLock.current = true;
    const currentGeneration = generation.current;

    setLoading(true);
    setError('');
    setKeys([]);
    setNextCursor('0');
    setHasMore(false);

    try {
      const page = await fetchKeyPage();

      if (generation.current !== currentGeneration) {
        return;
      }

      setKeys(page.keys);
      setNextCursor(page.nextCursor);
      setHasMore(page.hasMore);
    } catch (cause) {
      if (generation.current === currentGeneration) {
        setError(
          cause instanceof Error
            ? cause.message
            : 'Unable to refresh keys',
        );
      }
    } finally {
      requestLock.current = false;

      if (generation.current === currentGeneration) {
        setLoading(false);
      }
    }
  };

  return (
    <section className="panel key-browser" aria-labelledby="key-browser-heading">
      <div className="panel-heading">
        <div className="panel-title">
          <h2 id="key-browser-heading">Key Browser</h2>
          <p className="hint">
            {connectionId
              ? `${keys.length} keys loaded`
              : 'Connect to a BMis server to browse keys.'}
          </p>
        </div>

        <div className="actions">
          <button
            type="button"
            className="secondary"
            onClick={() => void refresh()}
            disabled={!connectionId || loading}
            aria-busy={loading}
          >
            {loading && keys.length === 0 ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {!connectionId && (
        <p className="hint">Key listing is unavailable while disconnected.</p>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {connectionId && keys.length === 0 && !loading && !error && (
        <p className="hint">No keys found.</p>
      )}

      {keys.length > 0 && (
        <div className="key-list" role="list" aria-label="Stored keys">
          {keys.map((key) => (
            <div className="key-row" role="listitem" key={key}>
              <span className="key-name">{key}</span>
            </div>
          ))}
        </div>
      )}

      {loading && keys.length > 0 && (
        <p className="hint" role="status">Loading keys...</p>
      )}

      {connectionId && hasMore && (
        <div className="key-browser-footer">
          <span className="hint">More keys available</span>
          <button
            type="button"
            className="secondary"
            onClick={() => void loadMore()}
            disabled={loading}
            aria-busy={loading}
          >
            Load more
          </button>
        </div>
      )}

      {connectionId && !hasMore && keys.length > 0 && !loading && (
        <p className="hint">End of key listing.</p>
      )}
    </section>
  );
}
