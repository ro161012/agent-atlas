/* Frontend configuration.
 *
 * apiBase: where the Agent Atlas API lives.
 *   - "" (default): same origin as this page — the normal case when the
 *     dashboard is served by the FastAPI app itself (local dev, Cloud Run).
 *   - Cross-origin: to host this static dashboard somewhere else (e.g. GitHub
 *     Pages) and point it at a deployed backend, set the backend origin, e.g.
 *       window.ATLAS_CONFIG = { apiBase: "https://atlas-xxxx.run.app" };
 */
window.ATLAS_CONFIG = { apiBase: "" };
