// In-browser stand-in for the Bot Management API. Used only when
// NEXT_PUBLIC_API_BASE_URL is not set. State lives in sessionStorage.
import taxonomy from "./taxonomy.json";
import type { Bot, BotConfig, BotList, Taxonomy } from "@/types/api";

const KEY = "narrative-bots:mock:v1";
const HOUR = 3_600_000;

export const DEFAULTS = {
  start_message: "Перешлите мне сообщение, и я проверю его.",
  non_text_message: "Пожалуйста, перешлите текстовое сообщение или пост с подписью.",
  error_message: "Сейчас не удаётся проверить сообщение. Попробуйте позже.",
  other_response: "Мы не нашли известного нарратива.",
};

const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d+Z$/, "Z");
const uuid = () =>
  "xxxxxxxx-xxxx-4xxx-8xxx-xxxxxxxxxxxx".replace(/x/g, () => ((Math.random() * 16) | 0).toString(16));

function make(created: number, status: Bot["status"], config: Partial<BotConfig>, extra: Partial<Bot> = {}): Bot {
  const id = uuid();
  const cfg: BotConfig = {
    start_message: DEFAULTS.start_message,
    non_text_message: DEFAULTS.non_text_message,
    error_message: DEFAULTS.error_message,
    display_name: "",
    username: "",
    confidence_threshold: 0.6,
    other_response: DEFAULTS.other_response,
    responses: [],
    ...config,
  };
  const bot: Bot = {
    bot_id: id,
    status,
    config: cfg,
    taxonomy_version: taxonomy.taxonomy_version,
    created_at: iso(created),
    ...extra,
  };
  if (status === "pending") {
    bot.creation_link = `https://t.me/newbot/STUB_MANAGER_bot/${cfg.username}?name=${id}`;
    bot.expires_at = iso(created + 24 * HOUR);
  }
  if (status === "active") bot.telegram_link = `https://t.me/${cfg.username}`;
  return bot;
}

function seed(): Bot[] {
  const now = Date.now();
  const N = taxonomy.narratives;
  const r = (ni: number, si: number | null, text: string) => ({
    narrative: N[ni].name,
    subnarrative: si === null ? null : N[ni].subnarratives[si],
    text,
  });
  return [
    make(now - 5 * HOUR, "pending", {
      display_name: "Харьков: проверка",
      username: "kharkiv_check_bot",
      confidence_threshold: 0.7,
      responses: [r(1, null, "Это обобщение без источников. Проверьте данные на сайтах независимых СМИ.")],
    }),
    make(now - 30 * HOUR, "active", {
      display_name: "Odesa Fact Check",
      username: "odesa_factcheck_bot",
      responses: [
        r(0, 1, "Утверждения о «провокации НАТО» — частый приём."),
        r(2, null, "Утверждение выставляет агрессора жертвой."),
        r(1, 4, "Это переписанная история: вот проверенные факты."),
      ],
    }),
    make(now - 72 * HOUR, "failed", { display_name: "Lviv Check", username: "lviv_check_bot" }, { failure_reason: "username_occupied" }),
    make(
      now - 120 * HOUR,
      "deleted",
      { display_name: "Test bot", username: "test_sayid_bot", confidence_threshold: 0.5, responses: [r(3, null, "Пример ответа.")] },
      { deleted_at: iso(now - 90 * HOUR) },
    ),
  ];
}

function load(): Bot[] {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw) return JSON.parse(raw) as Bot[];
  } catch {}
  const s = seed();
  save(s);
  return s;
}
function save(bots: Bot[]) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(bots));
  } catch {}
}
/** The server expires a pending bot 24 h after creation. */
function age(bots: Bot[]) {
  for (const b of bots) {
    if (b.status === "pending" && b.expires_at && Date.now() >= Date.parse(b.expires_at)) {
      b.status = "expired";
      delete b.creation_link;
    }
  }
}

export const mock = {
  taxonomy: async (): Promise<Taxonomy> => taxonomy as Taxonomy,
  list: async (): Promise<BotList> => {
    const bots = load();
    age(bots);
    save(bots);
    return { bots: [...bots].sort((a, b) => b.created_at.localeCompare(a.created_at)), next_cursor: null };
  },
  get: async (id: string): Promise<Bot> => {
    const bots = load();
    age(bots);
    save(bots);
    const b = bots.find((x) => x.bot_id === id);
    if (!b) throw new Error("not_found");
    return b;
  },
  create: async (config: BotConfig): Promise<Bot> => {
    const bots = load();
    const bot = make(Date.now(), "pending", config);
    save([bot, ...bots]);
    return bot;
  },
  remove: async (id: string): Promise<void> => {
    const bots = load();
    const b = bots.find((x) => x.bot_id === id);
    if (b && b.status !== "deleted") {
      b.status = "deleted";
      b.deleted_at = iso(Date.now());
      delete b.creation_link;
      delete b.expires_at;
      delete b.telegram_link;
      save(bots);
    }
  },
  /** Stand-ins for what Telegram and the server do. Mock mode only. */
  simulate: async (id: string, outcome: "confirm" | "occupied" | "expire") => {
    const bots = load();
    const b = bots.find((x) => x.bot_id === id);
    if (!b || b.status !== "pending") return;
    if (outcome === "confirm") {
      b.status = "active";
      b.telegram_link = `https://t.me/${b.config.username}`;
      delete b.creation_link;
      delete b.expires_at;
    } else if (outcome === "occupied") {
      b.status = "failed";
      b.failure_reason = "username_occupied";
      delete b.creation_link;
      delete b.expires_at;
    } else {
      b.expires_at = iso(Date.now() - 1000);
    }
    save(bots);
  },
};
