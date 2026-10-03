// Thin wrapper around fetch that adds the login token, refreshes it when it
// expires, and turns error responses into ApiError objects.

const TOKEN_STORAGE_KEY = "medislot.tokens";

export class ApiError extends Error {
  constructor(status, code, message, retryAfterSeconds) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

let sessionExpiredHandler = null;

export function onSessionExpired(handler) {
  sessionExpiredHandler = handler;
}

export function saveTokens(tokens) {
  // localStorage keeps the user logged in across tabs and reloads. The trade-off is
  // that any script on the page can read it, so the access token is kept short-lived.
  localStorage.setItem(
    TOKEN_STORAGE_KEY,
    JSON.stringify({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token }),
  );
}

export function loadTokens() {
  const stored = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (!stored) {
    return null;
  }
  return JSON.parse(stored);
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

async function readError(response) {
  let code = "UNKNOWN_ERROR";
  let message = "Something went wrong. Please try again.";
  try {
    const body = await response.json();
    if (body.error) {
      code = body.error.code;
      message = body.error.message;
    }
  } catch {
    // The body was not JSON (for example a proxy error page); keep the defaults.
  }
  const retryAfter = response.headers.get("Retry-After");
  const retryAfterSeconds = retryAfter ? Number(retryAfter) : null;
  return new ApiError(response.status, code, message, retryAfterSeconds);
}

let refreshInProgress = null;

async function refreshAccessToken() {
  const tokens = loadTokens();
  if (!tokens) {
    return false;
  }
  const response = await fetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: tokens.refreshToken }),
  });
  if (!response.ok) {
    return false;
  }
  saveTokens(await response.json());
  return true;
}

function refreshOnce() {
  // Several requests can fail at the same moment; they all wait for one refresh call.
  if (!refreshInProgress) {
    refreshInProgress = refreshAccessToken().finally(() => {
      refreshInProgress = null;
    });
  }
  return refreshInProgress;
}

export async function apiRequest(path, options = {}) {
  const { method = "GET", body, headers = {}, retryAfterRefresh = true } = options;
  const requestHeaders = { ...headers };
  const tokens = loadTokens();
  if (tokens) {
    requestHeaders.Authorization = `Bearer ${tokens.accessToken}`;
  }
  if (body !== undefined) {
    requestHeaders["Content-Type"] = "application/json";
  }

  let response;
  try {
    response = await fetch(path, {
      method,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Could not reach MediSlot. Check your connection and try again.");
  }

  if (response.status === 401 && tokens && retryAfterRefresh) {
    const refreshed = await refreshOnce();
    if (refreshed) {
      return apiRequest(path, { ...options, retryAfterRefresh: false });
    }
    clearTokens();
    if (sessionExpiredHandler) {
      sessionExpiredHandler();
    }
  }

  if (!response.ok) {
    throw await readError(response);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}
