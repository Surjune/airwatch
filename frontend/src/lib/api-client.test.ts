import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, get, post, request } from './api-client';

function mockFetch(response: Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(response),
  );
}

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('successful requests', () => {
  it('returns the parsed body', async () => {
    mockFetch(jsonResponse({ status: 'ok' }));
    await expect(get('/health')).resolves.toEqual({ status: 'ok' });
  });

  it('prefixes the versioned API path', async () => {
    const spy = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal('fetch', spy);

    await get('/health');

    expect(spy).toHaveBeenCalledWith('/v1/health', expect.anything());
  });

  it('serialises query parameters and drops undefined ones', async () => {
    const spy = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal('fetch', spy);

    await get('/grid', { searchParams: { h3: 'abc', hours: 24, unused: undefined } });

    expect(spy).toHaveBeenCalledWith('/v1/grid?h3=abc&hours=24', expect.anything());
  });

  it('sends a JSON body on POST', async () => {
    const spy = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal('fetch', spy);

    await post('/reports', { pm25: 42 });

    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(init.body).toBe(JSON.stringify({ pm25: 42 }));
  });
});

describe('error handling', () => {
  it('parses the API error envelope into an ApiError', async () => {
    mockFetch(
      jsonResponse(
        {
          error: {
            code: 'missing_credential',
            message: 'No credential configured for NASA FIRMS.',
            details: { env_var: 'FIRMS_MAP_KEY' },
            request_id: 'abc123',
          },
        },
        503,
      ),
    );

    const error = await get('/hotspots').catch((cause: unknown) => cause);

    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.code).toBe('missing_credential');
    expect(apiError.status).toBe(503);
    expect(apiError.details).toEqual({ env_var: 'FIRMS_MAP_KEY' });
    expect(apiError.requestId).toBe('abc123');
  });

  it('flags a configuration failure so the UI does not read it as clean air', async () => {
    // The distinction that matters: an empty map because a key is missing is a
    // deployment fault, not a report that the air is fine.
    mockFetch(
      jsonResponse({ error: { code: 'missing_credential', message: 'absent' } }, 503),
    );

    const error = (await get('/hotspots').catch((cause: unknown) => cause)) as ApiError;

    expect(error.isConfigurationFailure).toBe(true);
  });

  it('does not flag an ordinary upstream outage as a configuration failure', async () => {
    mockFetch(jsonResponse({ error: { code: 'upstream_timeout', message: 'slow' } }, 504));

    const error = (await get('/hotspots').catch((cause: unknown) => cause)) as ApiError;

    expect(error.isConfigurationFailure).toBe(false);
  });

  it('reports a network failure that never reached the API', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connection refused')));

    const error = (await get('/health').catch((cause: unknown) => cause)) as ApiError;

    expect(error.code).toBe('network_error');
    expect(error.status).toBe(0);
  });

  it('treats a non-JSON body as an error rather than an empty result', async () => {
    // An empty result would render as "nothing to see", which is the exact
    // failure this project exists to remove.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('<html>gateway error</html>', { status: 502 })),
    );

    const error = (await get('/health').catch((cause: unknown) => cause)) as ApiError;

    expect(error.code).toBe('invalid_response');
  });

  it('falls back when an error body is not the expected envelope', async () => {
    mockFetch(jsonResponse({ detail: 'something else' }, 500));

    const error = (await get('/health').catch((cause: unknown) => cause)) as ApiError;

    expect(error.code).toBe('unknown_error');
  });
});


describe('multipart uploads', () => {
  it('sends the form data untouched', async () => {
    const spy = vi.fn().mockResolvedValue(jsonResponse({ report_id: 1 }));
    vi.stubGlobal('fetch', spy);

    const form = new FormData();
    form.append('longitude', '77.2');

    await request('/citizen/reports', { method: 'POST', formData: form });

    const init = spy.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(init?.body).toBe(form);
  });

  it('does not set a content type, so the browser can add the boundary', async () => {
    // Setting it here would produce a multipart body with no boundary, which
    // the server cannot parse -- and the failure would look like a bad photo
    // rather than a bad request.
    const spy = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal('fetch', spy);

    await request('/citizen/reports', { method: 'POST', formData: new FormData() });

    const init = spy.mock.calls[0]?.[1] as RequestInit | undefined;
    const headers = init?.headers as Record<string, string> | undefined;
    expect(headers?.['Content-Type']).toBeUndefined();
  });
});

describe('non-envelope error bodies', () => {
  it('keeps the raw body so a typed rejection can be read', async () => {
    // A photograph the server declines to score returns its reason rather than
    // the standard envelope. Discarding the body would throw away the only
    // part of that response worth showing the submitter.
    mockFetch(
      jsonResponse({ accepted: false, reason: 'out_of_focus', detail: 'The image is blurred.' }, 422),
    );

    const error = (await post('/citizen/reports', {}).catch((cause: unknown) => cause)) as ApiError;

    expect(error.body).toEqual({
      accepted: false,
      reason: 'out_of_focus',
      detail: 'The image is blurred.',
    });
  });

  it('keeps the body for a standard envelope too', async () => {
    mockFetch(jsonResponse({ error: { code: 'not_found', message: 'gone' } }, 404));

    const error = (await get('/alerts/9').catch((cause: unknown) => cause)) as ApiError;

    expect(error.code).toBe('not_found');
    expect(error.body).toBeDefined();
  });
});
