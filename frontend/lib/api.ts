export interface ApiErrorBody {
  code: string;
  message: string;
  detail?: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail?: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.detail = body.detail;
  }
}

type ApiErrorListener = (err: ApiError, path: string) => void;

const listeners = new Set<ApiErrorListener>();

export function onApiError(listener: ApiErrorListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function notify(err: ApiError, path: string): void {
  for (const listener of listeners) {
    try {
      listener(err, path);
    } catch {
      /* listeners must not break the request */
    }
  }
}

const baseUrl = () => process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${baseUrl()}/api/v1${path}`, {
    method,
    credentials: "include",
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });

  if (!res.ok) {
    let parsed: { error?: ApiErrorBody } = {};
    try {
      parsed = (await res.json()) as { error?: ApiErrorBody };
    } catch {
      /* non-JSON error body */
    }
    const body = parsed.error ?? { code: "unknown_error", message: res.statusText };
    const err = new ApiError(res.status, body);
    notify(err, path);
    throw err;
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const apiGet = <T>(path: string) => request<T>("GET", path);
export const apiPost = <T>(path: string, body?: unknown) => request<T>("POST", path, body);
export const apiPatch = <T>(path: string, body: unknown) => request<T>("PATCH", path, body);
export const apiPut = <T>(path: string, body: unknown) => request<T>("PUT", path, body);
export const apiDelete = <T>(path: string) => request<T>("DELETE", path);
