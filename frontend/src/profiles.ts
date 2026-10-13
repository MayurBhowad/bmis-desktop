import { failureMessage, isRecord, parsePort, pythonRequest } from './pythonApi';

export type ConnectionProfile = {
  id: string;
  name: string;
  host: string;
  port: number;
  created_at: string;
  updated_at: string;
};

export type ProfileDraft = {
  name: string;
  host: string;
  port: string;
};

export type ValidProfileFields = {
  name: string;
  host: string;
  port: number;
};

const PROFILE_TIMESTAMP =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{6})[+-](\d{2}):(\d{2})$/;

function isProfileText(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.trim().length > 0 &&
    !value.includes('\n') &&
    !value.includes('\r')
  );
}

function isProfilePort(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 65535;
}

function isProfileTimestamp(value: unknown): value is string {
  if (typeof value !== 'string') {
    return false;
  }
  const match = PROFILE_TIMESTAMP.exec(value);
  if (!match) {
    return false;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const offsetHour = Number(match[8]);
  const offsetMinute = Number(match[9]);
  if (
    month < 1 ||
    month > 12 ||
    hour > 23 ||
    minute > 59 ||
    second > 59 ||
    offsetHour > 23 ||
    offsetMinute > 59
  ) {
    return false;
  }
  const utc = new Date(Date.UTC(year, month - 1, day));
  return utc.getUTCFullYear() === year && utc.getUTCMonth() === month - 1 && utc.getUTCDate() === day;
}

export function parseProfile(value: unknown): ConnectionProfile | null {
  if (!isRecord(value)) {
    return null;
  }
  if (!isProfileText(value.id) || !isProfileText(value.name) || !isProfileText(value.host)) {
    return null;
  }
  if (!isProfilePort(value.port)) {
    return null;
  }
  if (!isProfileTimestamp(value.created_at) || !isProfileTimestamp(value.updated_at)) {
    return null;
  }
  return {
    id: value.id,
    name: value.name,
    host: value.host,
    port: value.port,
    created_at: value.created_at,
    updated_at: value.updated_at,
  };
}

export function parseProfileList(body: unknown): ConnectionProfile[] | null {
  if (!isRecord(body) || body.status !== true || !Array.isArray(body.profiles)) {
    return null;
  }
  const profiles: ConnectionProfile[] = [];
  const ids = new Set<string>();
  for (const item of body.profiles) {
    const profile = parseProfile(item);
    if (!profile || ids.has(profile.id)) {
      return null;
    }
    ids.add(profile.id);
    profiles.push(profile);
  }
  return profiles;
}

export function parseSavedProfile(body: unknown): ConnectionProfile | null {
  if (!isRecord(body) || body.status !== true) {
    return null;
  }
  return parseProfile(body.profile);
}

export function validatedProfileFields(draft: ProfileDraft): ValidProfileFields | string {
  if (draft.name.includes('\n') || draft.name.includes('\r')) {
    return 'Name cannot contain newline characters';
  }
  const name = draft.name.trim();
  if (!name) {
    return 'Name must be a non-empty string';
  }
  if (draft.host.includes('\n') || draft.host.includes('\r')) {
    return 'Host cannot contain newline characters';
  }
  const host = draft.host.trim();
  if (!host) {
    return 'Host must be a non-empty string';
  }
  const port = parsePort(draft.port);
  if (port === null) {
    return 'Port must be an integer between 1 and 65535';
  }
  return { name, host, port };
}

export function orderProfiles(profiles: readonly ConnectionProfile[]): ConnectionProfile[] {
  return [...profiles].sort((left, right) => {
    if (left.name < right.name) {
      return -1;
    }
    if (left.name > right.name) {
      return 1;
    }
    if (left.id < right.id) {
      return -1;
    }
    if (left.id > right.id) {
      return 1;
    }
    return 0;
  });
}

function rejectProfileFailure(body: unknown): void {
  const failure = failureMessage(body);
  if (failure) {
    throw new Error(failure);
  }
}

export async function requestProfileList(): Promise<ConnectionProfile[]> {
  const parsed = await pythonRequest({ command: 'list_profiles' });
  rejectProfileFailure(parsed.body);
  const profiles = parseProfileList(parsed.body);
  if (!profiles) {
    throw new Error('Backend returned an unexpected response');
  }
  return profiles;
}

export async function requestCreateProfile(fields: ValidProfileFields): Promise<ConnectionProfile> {
  const parsed = await pythonRequest({
    command: 'create_profile',
    name: fields.name,
    host: fields.host,
    port: fields.port,
  });
  rejectProfileFailure(parsed.body);
  const profile = parseSavedProfile(parsed.body);
  if (!profile) {
    throw new Error('Backend returned an unexpected response');
  }
  return profile;
}

export async function requestUpdateProfile(
  id: string,
  fields: ValidProfileFields,
): Promise<ConnectionProfile> {
  const parsed = await pythonRequest({
    command: 'update_profile',
    id,
    name: fields.name,
    host: fields.host,
    port: fields.port,
  });
  rejectProfileFailure(parsed.body);
  const profile = parseSavedProfile(parsed.body);
  if (!profile) {
    throw new Error('Backend returned an unexpected response');
  }
  return profile;
}

export async function requestDeleteProfile(id: string): Promise<void> {
  const parsed = await pythonRequest({ command: 'delete_profile', id });
  rejectProfileFailure(parsed.body);
}
