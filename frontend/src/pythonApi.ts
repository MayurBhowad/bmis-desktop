import { invoke } from '@tauri-apps/api/core';

export type PythonCommand =
  | { command: 'ping' }
  | { command: 'connect'; host: string; port: number }
  | { command: 'status' }
  | { command: 'execute'; request: string }
  | { command: 'disconnect' }
  | { command: 'list_profiles' }
  | { command: 'create_profile'; name: string; host: string; port: number }
  | { command: 'update_profile'; id: string; name: string; host: string; port: number }
  | { command: 'delete_profile'; id: string };

export type ParsedPythonResponse = {
  raw: string;
  body: unknown;
};

export const MIN_PORT = 1;
export const MAX_PORT = 65535;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function invokeErrorMessage(error: unknown): string {
  if (typeof error === 'string' && error.trim()) {
    return error;
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return 'Unable to reach the Python backend';
}

function backendErrorMessage(body: Record<string, unknown>): string {
  const message = body.error;
  if (typeof message === 'string' && message.trim()) {
    return message;
  }
  return 'Backend request failed';
}

export function failureMessage(body: unknown): string | null {
  if (!isRecord(body)) {
    return 'Backend returned an unexpected response';
  }
  if (body.status === false) {
    return backendErrorMessage(body);
  }
  if (body.status !== true) {
    return 'Backend returned an unexpected response';
  }
  return null;
}

export function parsePort(value: string): number | null {
  const trimmed = value.trim();
  if (!/^[0-9]+$/.test(trimmed)) {
    return null;
  }
  const port = Number(trimmed);
  if (!Number.isInteger(port) || port < MIN_PORT || port > MAX_PORT) {
    return null;
  }
  return port;
}

export async function pythonRequest(payload: PythonCommand): Promise<ParsedPythonResponse> {
  let raw: string;
  try {
    raw = await invoke<string>('python_request', {
      request: JSON.stringify(payload),
    });
  } catch (error) {
    throw new Error(invokeErrorMessage(error));
  }

  if (typeof raw !== 'string') {
    throw new Error('Backend returned an unexpected response');
  }

  try {
    return { raw, body: JSON.parse(raw) as unknown };
  } catch {
    throw new Error('Backend returned malformed JSON');
  }
}
