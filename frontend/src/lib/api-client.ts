/**
 * The only place the frontend talks to the API.
 *
 * No component may call `fetch` directly. Centralising it means the error
 * envelope is parsed once, the correlation ID is threaded once, and a change to
 * the transport does not ripple through the feature folders.
 */

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

  constructor(
    code: string,
    message: string,
    status: number,
    details: Record<string, unknown> = {},
    requestId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
    this.requestId = requestId;
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
  readonly signal?: AbortSignal;
  readonly searchParams?: Record<string, string | number | boolean | undefined>;
}

function buildUrl(path: string, searchParams: RequestOptions['searchParams']): string {
  const url = `${API_BASE}${path}`;
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
  return typeof error === 'object' && error !== null && 'code' in error && typeof error.code === 'string';
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
  const { method = 'GET', body, signal, searchParams } = options;

  // Held as a plain record rather than HeadersInit: the union also admits an
  // array and a Headers instance, neither of which can be spread into an object.
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  const init: RequestInit = {
    method,
    headers,
    ...(signal ? { signal } : {}),
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
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
      );
    }
    throw new ApiError('unknown_error', 'The API returned an unrecognised error.', response.status, {}, requestId);
  }

  return payload as T;
}

/** Shorthand for a GET request. */
export function get<T>(path: string, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
  return request<T>(path, { ...options, method: 'GET' });
}

/** Shorthand for a POST request. */
export function post<T>(path: string, body: unknown, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
  return request<T>(path, { ...options, method: 'POST', body });
}
