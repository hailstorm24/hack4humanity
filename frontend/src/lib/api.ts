// One module the UI talks to. Set NEXT_PUBLIC_API_BASE_URL (e.g.
// https://h4h-narrative-stubs.onrender.com/v1) to use the real Bot Management API;
// leave it unset to use the in-browser mock.
import { mock } from "./mock";
import type { ApiErrorBody, Bot, BotConfig, BotList, BotStatus, Taxonomy } from "@/types/api";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
export const IS_MOCK = !BASE;

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ApiErrorBody | null,
  ) {
    super(body?.message ?? `HTTP ${status}`);
  }
}

// The hosted API sleeps when idle, so the first request can take about a minute.
const TIMEOUT_MS = 90_000;
const WAKING_AFTER_MS = 4_000;
let inflightSlow = 0;
const setWaking = (delta: number) => {
  inflightSlow += delta;
  window.dispatchEvent(new CustomEvent("nb-waking", { detail: inflightSlow > 0 }));
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const ctl = new AbortController();
  const killer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  let slow = false;
  const slowTimer = setTimeout(() => {
    slow = true;
    setWaking(1);
  }, WAKING_AFTER_MS);
  const done = () => {
    clearTimeout(killer);
    clearTimeout(slowTimer);
    if (slow) setWaking(-1);
  };
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      ...init,
      signal: ctl.signal,
      headers: { ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    });
  } catch {
    done();
    throw new ApiError(0, ctl.signal.aborted
      ? { error: "internal", message: "The server took too long to answer. Try again." }
      : { error: "internal", message: "Can’t reach the server. Check your connection and try again." });
  }
  done();
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let json: unknown = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {}
  if (!res.ok) {
    const body = (json as ApiErrorBody) ?? null;
    // invalid_request means the page sent something the contract forbids: a bug on our side.
    if (body?.error === "invalid_request") console.error("API invalid_request", path, body);
    throw new ApiError(res.status, body);
  }
  return json as T;
}

export const api = {
  taxonomy: (): Promise<Taxonomy> => (IS_MOCK ? mock.taxonomy() : call("/taxonomy")),
  listBots: (status?: BotStatus): Promise<BotList> =>
    IS_MOCK ? mock.list() : call(`/bots?limit=200${status ? `&status=${status}` : ""}`),
  getBot: (id: string): Promise<Bot> => (IS_MOCK ? mock.get(id) : call(`/bots/${encodeURIComponent(id)}`)),
  createBot: (config: BotConfig): Promise<Bot> =>
    IS_MOCK ? mock.create(config) : call("/bots", { method: "POST", body: JSON.stringify(config) }),
  deleteBot: (id: string): Promise<void> =>
    IS_MOCK ? mock.remove(id) : call(`/bots/${encodeURIComponent(id)}`, { method: "DELETE" }),
};

export const simulate = mock.simulate;
