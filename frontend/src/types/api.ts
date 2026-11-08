// Types mirror ../../frontend-openapi.yaml (Bot Management API, frontend bundle).

export type BotStatus = "pending" | "active" | "failed" | "expired" | "deleted";

export interface Taxonomy {
  taxonomy_version: string;
  narratives: { name: string; subnarratives: string[] }[];
}

export interface ResponseMapping {
  narrative: string;
  /** null = reply covers the whole narrative */
  subnarrative: string | null;
  text: string;
}

export interface BotConfig {
  display_name: string;
  username: string;
  description?: string;
  short_description?: string;
  start_message?: string;
  non_text_message?: string;
  error_message?: string;
  confidence_threshold: number;
  responses: ResponseMapping[];
  other_response: string;
}

export interface Bot {
  bot_id: string;
  status: BotStatus;
  config: BotConfig;
  taxonomy_version: string;
  created_at: string;
  creation_link?: string;
  expires_at?: string;
  telegram_link?: string;
  failure_reason?: string;
  deleted_at?: string;
}

export interface BotList {
  bots: Bot[];
  next_cursor: string | null;
}

export interface ApiErrorBody {
  error: string;
  message: string;
  details?: { field: string; issue: string }[];
}
