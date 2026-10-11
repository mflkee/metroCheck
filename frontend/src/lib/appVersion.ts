/**
 * Version of the running web build, injected at build time from `frontend/package.json`
 * (see `vite.config.ts`).
 */
export const APP_VERSION = __APP_VERSION__

/**
 * Release channel. metroCheck is below `1.0.0`, so it always advertises `beta`.
 */
export const APP_STAGE = "beta"
