import { AppShell } from '@/components/layout/AppShell';
import { ScopeProvider } from '@/components/layout/ScopeProvider';
import { SCREEN_KEYS } from '@/components/layout/navigation';
import { AlertConsole } from '@/features/alerts/AlertConsole';
import { CitizenSubmit } from '@/features/citizen/CitizenSubmit';
import { CorridorView } from '@/features/corridor/CorridorView';
import { FederationView } from '@/features/federation/FederationView';
import { MapScreen } from '@/features/map/MapScreen';
import { OverviewScreen } from '@/features/overview/OverviewScreen';
import { useHashRoute } from '@/hooks/useHashRoute';

/**
 * Application root: reads the screen from the URL and renders it in the shell.
 *
 * Owns nothing else; each screen loads its own data.
 */
export function App(): React.JSX.Element {
  const [screen, navigate] = useHashRoute(SCREEN_KEYS, 'overview');

  return (
    <ScopeProvider>
      <AppShell active={screen} onNavigate={navigate}>
        {screen === 'overview' && <OverviewScreen onNavigate={navigate} />}
        {screen === 'map' && <MapScreen />}
        {screen === 'corridor' && <CorridorView />}
        {screen === 'alerts' && <AlertConsole />}
        {screen === 'federation' && <FederationView />}
        {screen === 'citizen' && <CitizenSubmit />}
      </AppShell>
    </ScopeProvider>
  );
}
