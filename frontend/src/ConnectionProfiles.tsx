import { useEffect, useRef, useState, type FormEvent } from 'react';
import { invokeErrorMessage } from './pythonApi';
import {
  orderProfiles,
  requestCreateProfile,
  requestDeleteProfile,
  requestProfileList,
  requestUpdateProfile,
  validatedProfileFields,
  type ConnectionProfile,
  type ProfileDraft,
} from './profiles';

type ProfileMode =
  | { type: 'idle' }
  | { type: 'create' }
  | { type: 'edit'; id: string }
  | { type: 'confirmDelete'; id: string };

type ProfileOperation = 'create' | 'update' | 'delete';

type ConnectionProfilesProps = {
  selectedId: string | null;
  suggestedHost: string;
  suggestedPort: string;
  onSelect: (profile: ConnectionProfile) => void;
  onDeleted: (id: string) => void;
};

const NOT_FOUND = 'Connection profile not found';

function emptyDraft(host: string, port: string): ProfileDraft {
  return { name: '', host, port };
}

function draftFromProfile(profile: ConnectionProfile): ProfileDraft {
  return {
    name: profile.name,
    host: profile.host,
    port: String(profile.port),
  };
}

function upsertProfile(
  profiles: readonly ConnectionProfile[],
  profile: ConnectionProfile,
): ConnectionProfile[] {
  return orderProfiles([...profiles.filter((item) => item.id !== profile.id), profile]);
}

export function ConnectionProfiles({
  selectedId,
  suggestedHost,
  suggestedPort,
  onSelect,
  onDeleted,
}: ConnectionProfilesProps) {
  const [profiles, setProfiles] = useState<ConnectionProfile[]>([]);
  const [listState, setListState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [listError, setListError] = useState('');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [mode, setMode] = useState<ProfileMode>({ type: 'idle' });
  const [draft, setDraft] = useState<ProfileDraft>(emptyDraft(suggestedHost, suggestedPort));
  const [formError, setFormError] = useState('');
  const [operation, setOperation] = useState<ProfileOperation | null>(null);

  const requestLock = useRef(false);
  const listLock = useRef(false);

  const busy = operation !== null || listState === 'loading';

  useEffect(() => {
    let ignore = false;
    listLock.current = true;

    void (async () => {
      try {
        const next = await requestProfileList();
        if (ignore) {
          return;
        }
        setProfiles(orderProfiles(next));
        setListState('ready');
      } catch (error) {
        if (ignore) {
          return;
        }
        setListError(invokeErrorMessage(error));
        setListState('error');
      } finally {
        if (!ignore) {
          listLock.current = false;
        }
      }
    })();

    return () => {
      ignore = true;
    };
  }, [loadAttempt]);

  const retryLoad = () => {
    if (listLock.current || requestLock.current) {
      return;
    }
    listLock.current = true;
    setListState('loading');
    setListError('');
    setLoadAttempt((current) => current + 1);
  };

  const beginMutation = (next: ProfileOperation): boolean => {
    if (requestLock.current || listLock.current || listState === 'loading') {
      return false;
    }
    requestLock.current = true;
    setOperation(next);
    setFormError('');
    return true;
  };

  const finishMutation = () => {
    requestLock.current = false;
    setOperation(null);
  };

  const startCreate = () => {
    if (busy || mode.type !== 'idle') {
      return;
    }
    setDraft(emptyDraft(suggestedHost, suggestedPort));
    setFormError('');
    setMode({ type: 'create' });
  };

  const startEdit = (profile: ConnectionProfile) => {
    if (busy || mode.type !== 'idle') {
      return;
    }
    setDraft(draftFromProfile(profile));
    setFormError('');
    setMode({ type: 'edit', id: profile.id });
  };

  const startDelete = (profile: ConnectionProfile) => {
    if (busy || mode.type !== 'idle') {
      return;
    }
    setFormError('');
    setMode({ type: 'confirmDelete', id: profile.id });
  };

  const cancelMode = () => {
    if (operation !== null) {
      return;
    }
    setFormError('');
    setMode({ type: 'idle' });
  };

  const handleSave = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode.type !== 'create' && mode.type !== 'edit') {
      return;
    }
    const fields = validatedProfileFields(draft);
    if (typeof fields === 'string') {
      setFormError(fields);
      return;
    }
    const saving = mode;
    if (!beginMutation(saving.type === 'create' ? 'create' : 'update')) {
      return;
    }

    void (async () => {
      try {
        const saved =
          saving.type === 'create'
            ? await requestCreateProfile(fields)
            : await requestUpdateProfile(saving.id, fields);
        setProfiles((current) => upsertProfile(current, saved));
        if (selectedId === saved.id) {
          onSelect(saved);
        }
        setMode({ type: 'idle' });
      } catch (error) {
        const message = invokeErrorMessage(error);
        setFormError(message);
        if (saving.type === 'edit' && message === NOT_FOUND) {
          setProfiles((current) => current.filter((item) => item.id !== saving.id));
          onDeleted(saving.id);
          setMode({ type: 'idle' });
        }
      } finally {
        finishMutation();
      }
    })();
  };

  const confirmDelete = (profile: ConnectionProfile) => {
    if (mode.type !== 'confirmDelete' || mode.id !== profile.id) {
      return;
    }
    if (!beginMutation('delete')) {
      return;
    }

    void (async () => {
      try {
        await requestDeleteProfile(profile.id);
        setProfiles((current) => current.filter((item) => item.id !== profile.id));
        onDeleted(profile.id);
        setMode({ type: 'idle' });
      } catch (error) {
        const message = invokeErrorMessage(error);
        setFormError(message);
        if (message === NOT_FOUND) {
          setProfiles((current) => current.filter((item) => item.id !== profile.id));
          onDeleted(profile.id);
          setMode({ type: 'idle' });
        }
      } finally {
        finishMutation();
      }
    })();
  };

  const pendingDelete =
    mode.type === 'confirmDelete'
      ? (profiles.find((profile) => profile.id === mode.id) ?? null)
      : null;
  const actionsLocked = busy || mode.type !== 'idle';

  return (
    <section className="panel" aria-labelledby="profiles-heading" aria-busy={busy}>
      <div className="panel-heading">
        <h2 id="profiles-heading">Saved profiles</h2>
        <p className="hint">Choosing a profile fills the host and port below. It does not connect.</p>
      </div>

      {listState === 'loading' && (
        <p className="notice" role="status">
          Loading saved profiles...
        </p>
      )}
      {listError && (
        <p className="error" role="alert">
          {listError}
        </p>
      )}
      {listState === 'error' && mode.type === 'idle' && (
        <div className="actions">
          <button type="button" onClick={retryLoad} disabled={busy}>
            Retry
          </button>
        </div>
      )}
      {listState === 'ready' && profiles.length === 0 && mode.type === 'idle' && (
        <p className="hint">No saved profiles.</p>
      )}

      {profiles.length > 0 && (
        <ul className="profile-list" aria-label="Saved connection profiles">
          {profiles.map((profile) => {
            const selected = profile.id === selectedId;
            return (
              <li
                key={profile.id}
                className={selected ? 'profile-row profile-row-selected' : 'profile-row'}
              >
                <button
                  type="button"
                  className="profile-choice"
                  aria-pressed={selected}
                  disabled={busy}
                  onClick={() => onSelect(profile)}
                >
                  <span className="profile-name">{profile.name}</span>
                  <span className="profile-endpoint">
                    <span>Host {profile.host}</span>
                    <span>Port {profile.port}</span>
                  </span>
                </button>
                <div className="profile-actions">
                  <button
                    type="button"
                    className="secondary"
                    disabled={actionsLocked}
                    aria-label={`Edit ${profile.name}`}
                    onClick={() => startEdit(profile)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="danger"
                    disabled={actionsLocked}
                    aria-label={`Delete ${profile.name}`}
                    onClick={() => startDelete(profile)}
                  >
                    Delete
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {mode.type === 'idle' && listState !== 'loading' && (
        <div className="actions">
          <button type="button" onClick={startCreate} disabled={busy}>
            New profile
          </button>
        </div>
      )}

      {(mode.type === 'create' || mode.type === 'edit') && (
        <form className="profile-form" onSubmit={handleSave}>
          <h3>{mode.type === 'create' ? 'New profile' : 'Edit profile'}</h3>
          <div className="profile-fields">
            <label htmlFor="profile-name">
              Name
              <input
                id="profile-name"
                name="name"
                type="text"
                value={draft.name}
                autoComplete="off"
                spellCheck={false}
                disabled={busy}
                onChange={(event) => {
                  setFormError('');
                  setDraft((current) => ({ ...current, name: event.target.value }));
                }}
              />
            </label>
            <label htmlFor="profile-host">
              Hostname or IP
              <input
                id="profile-host"
                name="host"
                type="text"
                value={draft.host}
                autoComplete="off"
                spellCheck={false}
                disabled={busy}
                onChange={(event) => {
                  setFormError('');
                  setDraft((current) => ({ ...current, host: event.target.value }));
                }}
              />
            </label>
            <label htmlFor="profile-port">
              Port
              <input
                id="profile-port"
                name="port"
                type="text"
                inputMode="numeric"
                value={draft.port}
                autoComplete="off"
                spellCheck={false}
                disabled={busy}
                onChange={(event) => {
                  setFormError('');
                  setDraft((current) => ({ ...current, port: event.target.value }));
                }}
              />
            </label>
          </div>
          {formError && (
            <p className="error" role="alert">
              {formError}
            </p>
          )}
          <div className="actions">
            <button
              type="submit"
              disabled={busy}
              aria-busy={operation === 'create' || operation === 'update'}
            >
              {operation === 'create' || operation === 'update' ? 'Saving...' : 'Save profile'}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={cancelMode}
              disabled={operation !== null}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {pendingDelete && (
        <div className="confirm" role="region" aria-label="Confirm profile deletion">
          <p>
            Delete the saved profile "{pendingDelete.name}" for host {pendingDelete.host} and port{' '}
            {pendingDelete.port}? This removes the saved profile and does not change the current
            connection.
          </p>
          {formError && (
            <p className="error" role="alert">
              {formError}
            </p>
          )}
          <div className="actions">
            <button
              type="button"
              className="danger"
              onClick={() => confirmDelete(pendingDelete)}
              disabled={busy}
              aria-busy={operation === 'delete'}
            >
              {operation === 'delete' ? 'Deleting...' : 'Delete profile'}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={cancelMode}
              disabled={operation !== null}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
