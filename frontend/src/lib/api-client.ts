/**
 * The only place the frontend talks to the API.
 *
 * No component may call `fetch` directly. Centralising it means the error
 * envelope is parsed once, the correlation ID is threaded once, and a change to
 * the transport does not ripple through the feature folders.
 */

import { getOperatorToken } from './operator-token';

/** Base path for the versioned API. Vite proxies this to the backend in dev. */
const API_BASE = '/v1';

/** Header carrying the request correlation ID, matching the backend constant. */
const REQUEST_ID_HEADER = 'X-Request-ID';

/** The error envelope every failing API response returns. */
export interface ApiErrorBody {
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly details?: Record<string, unknown>;
    readonly request_id?: string;
  };
}

/**
 * A failed API call, carrying the machine-readable code the backend assigned.
 *
 * Callers branch on `code`, never on the message text, which is written for
 * humans and may be reworded.
 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;
  readonly requestId: string | undefined;

  /**
   * The parsed response body, whatever shape it had.
   *
   * Kept because not every failure is the standard envelope. A photograph the
   * server declines to score comes back as a typed rejection carrying the
   * reason the submitter needs, and discarding the body would throw away the
   * only part of that response worth reading.
   */
  readonly body: unknown;

  constructor(
    code: string,
    message: string,
    status: number,
    details: Record<string, unknown> = {},
    requestId?: string,
    body?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
    this.requestId = requestId;
    this.body = body;
  }

  /**
   * Whether the failure is a missing upstream credential.
   *
   * Worth distinguishing in the UI: it means the deployment is misconfigured,
   * not that the air is clean. Showing an empty map for this would be exactly
   * the failure mode the project exists to remove.
   */
  get isConfigurationFailure(): boolean {
    return this.code === 'missing_credential' || this.code === 'configuration_error';
  }
}

/** Options accepted by {@link request}. */
export interface RequestOptions {
  readonly method?: 'GET' | 'POST' | 'PATCH';
  readonly body?: unknown;
  /**
   * Multipart payload, for a request carrying a file.
   *
   * Passed through untouched and without a Content-Type header: the browser has
   * to set that itself so it can include the multipart boundary, and setting it
   * here would produce a body the server cannot parse.
   */
  readonly formData?: FormData;
  readonly signal?: AbortSignal;
  readonly searchParams?: Record<string, string | number | boolean | undefined>;
  /** Extra headers, such as the anonymous device identifier a resident's own records need. */
  readonly headers?: Record<string, string>;
}

/**
 * The browser-facing address of an API path, for an element that loads it itself.
 *
 * An audio element fetches and streams its own source, which is what lets a
 * phone start speaking before the whole clip has arrived -- so it is given an
 * address rather than a body, and the base path still lives only here.
 */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

function buildUrl(path: string, searchParams: RequestOptions['searchParams']): string {
  const url = apiUrl(path);
  if (!searchParams) {
    return url;
  }
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (value !== undefined) {
      query.set(key, String(value));
    }
  }
  const serialised = query.toString();
  return serialised ? `${url}?${serialised}` : url;
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) {
    return false;
  }
  const { error } = value;
  return (
    typeof error === 'object' && error !== null && 'code' in error && typeof error.code === 'string'
  );
}

/**
 * Perform an API request and parse the response.
 *
 * @param path - Path below the version prefix, for example `/health`.
 * @param options - Method, body, query parameters and abort signal.
 * @throws {ApiError} When the response is not successful, or the body is not
 *   the JSON the caller expects. A malformed body is an error rather than a
 *   silently empty result, because an empty result reads as "nothing to see".
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, formData, signal, searchParams } = options;

  // Held as a plain record rather than HeadersInit: the union also admits an
  // array and a Headers instance, neither of which can be spread into an object.
  const headers: Record<string, string> = { Accept: 'application/json', ...options.headers };
  if (body !== undefined && formData === undefined) {
    headers['Content-Type'] = 'application/json';
  }
  // Presented on every request once an operator has signed in; read endpoints
  // ignore it, and write endpoints refuse without it.
  const operatorToken = getOperatorToken();
  if (operatorToken) {
    headers.Authorization = `Bearer ${operatorToken}`;
  }

  const init: RequestInit = {
    method,
    headers,
    ...(signal ? { signal } : {}),
    ...(formData !== undefined
      ? { body: formData }
      : body !== undefined
        ? { body: JSON.stringify(body) }
        : {}),
  };

  let response: Response;
  try {
    response = await fetch(buildUrl(path, searchParams), init);
  } catch (cause) {
    // A network-level failure never reached the API, so there is no envelope.
    throw new ApiError(
      'network_error',
      cause instanceof Error ? cause.message : 'The request could not be sent.',
      0,
    );
  }

  const requestId = response.headers.get(REQUEST_ID_HEADER) ?? undefined;

  if (response.status === 204) {
    return undefined as T;
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(
      'invalid_response',
      'The API returned a response that was not valid JSON.',
      response.status,
      {},
      requestId,
    );
  }

  if (!response.ok) {
    if (isApiErrorBody(payload)) {
      throw new ApiError(
        payload.error.code,
        payload.error.message,
        response.status,
        payload.error.details ?? {},
        payload.error.request_id ?? requestId,
        payload,
      );
    }
    throw new ApiError(
      'unknown_error',
      'The API returned an unrecognised error.',
      response.status,
      {},
      requestId,
      payload,
    );
  }

  return payload as T;
}

/** A file the API returned, with the name it suggested. */
export interface DownloadedFile {
  readonly blob: Blob;
  readonly filename: string;
}

/**
 * Fetch a file, such as a PDF report, rather than JSON.
 *
 * A failure still arrives as the JSON error envelope and is raised as an
 * {@link ApiError}, so a refused download is reported like any other failure
 * instead of saving an error page under a `.pdf` name.
 */
export async function download(
  path: string,
  options: Pick<RequestOptions, 'headers' | 'signal'> & { readonly fallbackName: string },
): Promise<DownloadedFile> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, undefined), {
      headers: { Accept: 'application/pdf, application/json', ...options.headers },
      ...(options.signal ? { signal: options.signal } : {}),
    });
  } catch (cause) {
    throw new ApiError(
      'network_error',
      cause instanceof Error ? cause.message : 'The download could not be started.',
      0,
    );
  }

  if (!response.ok) {
    const requestId = response.headers.get(REQUEST_ID_HEADER) ?? undefined;
    const payload: unknown = await response.json().catch(() => null);
    if (isApiErrorBody(payload)) {
      throw new ApiError(
        payload.error.code,
        payload.error.message,
        response.status,
        payload.error.details ?? {},
        payload.error.request_id ?? requestId,
        payload,
      );
    }
    throw new ApiError('unknown_error', 'The download failed.', response.status, {}, requestId);
  }

  const disposition = response.headers.get('Content-Disposition') ?? '';
  const named = /filename="([^"]+)"/.exec(disposition)?.[1];
  return { blob: await response.blob(), filename: named ?? options.fallbackName };
}

/** Shorthand for a GET request. */
export function get<T>(
  path: string,
  options: Omit<RequestOptions, 'method' | 'body'> = {},
): Promise<T> {
  return request<T>(path, { ...options, method: 'GET' });
}

/** Shorthand for a POST request. */
export function post<T>(
  path: string,
  body: unknown,
  options: Omit<RequestOptions, 'method' | 'body'> = {},
): Promise<T> {
  return request<T>(path, { ...options, method: 'POST', body });
}
