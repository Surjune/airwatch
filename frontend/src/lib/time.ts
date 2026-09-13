/**
 * Render a UTC timestamp in IST, the only timezone a reader here works in.
 *
 * Storage and the API are UTC throughout; this is the single presentation
 * boundary where that changes, so every screen shows the same wall-clock time
 * for the same instant.
 */
export function istDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** How long ago an instant was, coarsely, for "updated 3 h ago" labels. */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const minutes = Math.round((now.getTime() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${String(minutes)} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${String(hours)} h ago`;
  return `${String(Math.round(hours / 24))} days ago`;
}
