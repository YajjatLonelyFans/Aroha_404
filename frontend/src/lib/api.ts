// Typed client for the Aroha backend. The frontend talks only to this backend, never to
// third-party APIs, and holds no keys. Types come from src/types/api.ts (npm run gen:api).
import type { components, paths } from "@/types/api";

export type Schemas = components["schemas"];

// NEXT_PUBLIC_API_BASE_URL may end in /api; the generated paths already start with /api.
const ORIGIN = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "").replace(/\/api$/, "");

const DEFAULT_TIMEOUT_MS = 30_000;

type Method = "get" | "post" | "patch";
type PathsFor<M extends Method> = { [P in keyof paths]: paths[P][M] extends undefined ? never : P }[keyof paths];
type Op<P extends keyof paths, M extends Method> = NonNullable<paths[P][M]>;

type JsonOf<R> = R extends { content: { "application/json": infer T } } ? T : never;
type Success<O> = O extends { responses: infer R }
  ? R extends { 200: infer Ok } ? JsonOf<Ok> : R extends { 201: infer Created } ? JsonOf<Created> : never
  : never;

export type RequestOptions<O> = {
  path?: O extends { parameters: { path?: infer T } } ? T : never;
  query?: O extends { parameters: { query?: infer T } } ? T : never;
  body?: O extends { requestBody?: { content: { "application/json": infer B } } } ? B : never;
  signal?: AbortSignal;
  timeoutMs?: number;
};

/** The backend's error envelope: {"error": {code, message, retryable, details?}}. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryable: boolean,
    readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function buildUrl(path: string, params?: object, query?: object): string {
  const filled = path.replace(/\{(\w+)\}/g, (_, key: string) =>
    encodeURIComponent(String((params as Record<string, unknown> | undefined)?.[key] ?? "")),
  );
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null) qs.set(k, String(v));
  }
  const q = qs.toString();
  return `${ORIGIN}${filled}${q ? `?${q}` : ""}`;
}

async function toApiError(res: Response): Promise<ApiError> {
  try {
    const { error } = (await res.json()) as { error?: Partial<ApiError> & { details?: Record<string, unknown> } };
    if (error?.code && error.message) {
      return new ApiError(res.status, error.code, error.message, Boolean(error.retryable), error.details);
    }
  } catch {
    // not JSON; fall through
  }
  return new ApiError(res.status, "http_error", `The server answered ${res.status}.`, res.status >= 500);
}

export async function api<M extends Method, P extends PathsFor<M>>(
  method: M,
  path: P,
  options: RequestOptions<Op<P, M>> = {},
): Promise<Success<Op<P, M>>> {
  const timeout = AbortSignal.timeout(options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout;
  let res: Response;
  try {
    res = await fetch(buildUrl(path as string, options.path, options.query), {
      method: method.toUpperCase(),
      headers: options.body === undefined ? undefined : { "Content-Type": "application/json" },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal,
    });
  } catch (err) {
    if (options.signal?.aborted) throw err; // the caller cancelled; not an error to show
    if (timeout.aborted) {
      throw new ApiError(0, "timeout", "The server took too long to answer. Try again.", true);
    }
    throw new ApiError(0, "network_error", "Can't reach the Aroha server. Is the backend running?", true);
  }
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as Success<Op<P, M>>;
}
