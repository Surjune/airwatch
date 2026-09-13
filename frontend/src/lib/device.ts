/**
 * A stable per-device identifier, held in this browser only.
 *
 * Not an account. Both citizen tiers are anonymous; this exists so one device can
 * be rate-limited, and so a device that submits unusable photographs can stop
 * counting towards the calibration without anyone being identified. It is
 * generated locally and never derived from anything about the person.
 */
const DEVICE_STORAGE_KEY = 'airwatch.device-id';

export function deviceId(): string {
  try {
    const stored = localStorage.getItem(DEVICE_STORAGE_KEY);
    if (stored) return stored;
    const created = `device-${crypto.randomUUID()}`;
    localStorage.setItem(DEVICE_STORAGE_KEY, created);
    return created;
  } catch {
    // Private browsing, or storage blocked. A per-session identifier still
    // rate-limits a single tab, which is the behaviour that matters most.
    return `device-${crypto.randomUUID()}`;
  }
}
