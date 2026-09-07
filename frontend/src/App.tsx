import { useHealth } from '@/hooks/useHealth';

/**
 * Application shell.
 *
 * At this stage it proves the frontend and API are wired together and reports
 * which upstream data sources are configured. An unconfigured upstream is shown
 * explicitly rather than hidden: a blank map because a key is missing must never
 * be mistaken for clean air.
 */
export function App(): React.JSX.Element {
  const { report, error, isLoading } = useHealth();

  return (
    <main className="mx-auto max-w-3xl p-8 font-sans">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">AirWatch</h1>
        <p className="mt-1 text-sm text-neutral-600">
          Federated hyperlocal air quality intelligence
        </p>
      </header>

      {isLoading && <p className="text-neutral-500">Checking API…</p>}

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-4">
          <p className="font-medium text-red-800">API unreachable</p>
          <p className="mt-1 text-sm text-red-700">{error.message}</p>
          {error.requestId && (
            <p className="mt-2 font-mono text-xs text-red-600">request {error.requestId}</p>
          )}
        </div>
      )}

      {report && (
        <section>
          <p className="text-sm text-neutral-700">
            API {report.version} · {report.environment} · H3 resolution {report.h3_resolution}
          </p>

          <h2 className="mt-6 mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Upstream data sources
          </h2>
          <ul className="divide-y divide-neutral-200 rounded border border-neutral-200">
            {report.upstreams.map((upstream) => (
              <li
                key={upstream.required_env_var}
                className="flex items-center justify-between p-3 text-sm"
              >
                <span>{upstream.provider}</span>
                {upstream.configured ? (
                  <span className="text-green-700">configured</span>
                ) : (
                  <span className="font-mono text-xs text-amber-700">
                    set {upstream.required_env_var}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
