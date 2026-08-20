import axios from "axios";

/**
 * Base URL of the backend.
 *
 * The deployment serves the React build and the API from the same origin
 * (browser -> Nginx -> FastAPI), so the correct value is normally an empty
 * string and requests go to a relative `/api/...` path.
 *
 * `process.env.REACT_APP_BACKEND_URL` used to be read straight into a template
 * literal. When the variable was not defined at build time the result was the
 * string "undefined", so every request went to `/undefined/api/...` and the
 * whole app looked like it could not load any data. Anything falsy now
 * collapses to a relative URL, and a trailing slash is trimmed so
 * `https://host/` and `https://host` behave the same.
 */
const rawBackendUrl = process.env.REACT_APP_BACKEND_URL;

export const BACKEND_URL =
  typeof rawBackendUrl === "string" && rawBackendUrl.trim() && rawBackendUrl.trim() !== "undefined"
    ? rawBackendUrl.trim().replace(/\/+$/, "")
    : "";

export const API = `${BACKEND_URL}/api`;

/** Default request timeout (ms). Imports and PDF exports set their own. */
export const DEFAULT_TIMEOUT = 30000;

// Session cookies are HttpOnly, so every request has to carry credentials.
// Setting it on the shared defaults means a call site cannot forget it — the
// public QR forms and a few authenticated calls previously did, which made
// them fail as soon as the backend required a session.
axios.defaults.withCredentials = true;
axios.defaults.timeout = DEFAULT_TIMEOUT;

/** Pre-configured client: relative base URL, credentials, timeout. */
export const api = axios.create({
  baseURL: API,
  withCredentials: true,
  timeout: DEFAULT_TIMEOUT,
});

/** Routes that are reachable without a session; a 401 here is not a redirect. */
const PUBLIC_PATH_PREFIXES = ["/login", "/fuel/", "/damage/", "/handover/"];

const isOnPublicRoute = () =>
  PUBLIC_PATH_PREFIXES.some((prefix) => window.location.pathname.startsWith(prefix));

let onUnauthorized = null;

/** Register what should happen when the backend reports an expired session. */
export const setUnauthorizedHandler = (handler) => {
  onUnauthorized = handler;
};

const handleResponseError = (error) => {
  if (error.response?.status === 401 && !isOnPublicRoute()) {
    onUnauthorized?.();
  }
  return Promise.reject(error);
};

api.interceptors.response.use((response) => response, handleResponseError);
axios.interceptors.response.use((response) => response, handleResponseError);

/**
 * Human-readable message for a failed request.
 *
 * Distinguishes "the server said no" from "the server was never reached",
 * which is the difference between a validation problem and a deployment
 * problem — and the one thing the old `catch { toast.error("...") }` handlers
 * threw away.
 */
export const errorMessage = (error, fallback = "Operace se nezdařila") => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => d.msg || d.detail).filter(Boolean).join("; ") || fallback;
  }
  if (error?.code === "ECONNABORTED") return "Požadavek vypršel. Zkuste to prosím znovu.";
  if (error?.response?.status === 401) return "Přihlášení vypršelo. Přihlaste se prosím znovu.";
  if (error?.response?.status === 403) return "K této akci nemáte oprávnění.";
  if (error?.response?.status === 429) return "Příliš mnoho pokusů. Zkuste to prosím za chvíli.";
  if (!error?.response) return "Server je nedostupný. Zkontrolujte připojení.";
  return fallback;
};

export default api;
