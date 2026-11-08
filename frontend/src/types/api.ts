// Types come from the Bot Management API contract. Regenerate with `npm run types`
// (reads ../frontend-openapi.yaml); never hand-write request shapes here.
import type { components } from "./api.gen";

type S = components["schemas"];

export type BotStatus = S["BotStatus"];
export type Bot = S["Bot"];
export type BotConfig = S["BotConfig"];
export type ResponseMapping = S["ResponseMapping"];
export type Taxonomy = S["Taxonomy"];
export type ApiErrorBody = S["Error"];

export interface BotList {
  bots: Bot[];
  next_cursor: string | null;
}
