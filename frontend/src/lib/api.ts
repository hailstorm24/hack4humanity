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

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers: { ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    });
  } catch {
    throw new ApiError(0, { error: "network", message: "Can’t reach the server. Check your connection and try again." });
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let json: unknown = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {}
  if (!res.ok) throw new ApiError(res.status, (json as ApiErrorBody) ?? null);
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
