"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, IS_MOCK, api } from "@/lib/api";
import { cap, fmtDate } from "@/lib/format";
import { toast } from "@/components/Toast";
import type { Bot, BotStatus } from "@/types/api";

const TABS: ("all" | BotStatus)[] = ["all", "pending", "active", "failed", "expired", "deleted"];

export default function Bots() {
  const [bots, setBots] = useState<Bot[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("all");
  const [asking, setAsking] = useState<string | null>(null);

  const load = useCallback(() => {
    api.listBots().then((r) => { setBots(r.bots); setErr(null); }, (e: unknown) => setErr(e instanceof ApiError ? e.message : "Couldn’t load your bots."));
  }, []);
  useEffect(load, [load]);

  const remove = async (b: Bot) => {
    try {
      await api.deleteBot(b.bot_id);
      setAsking(null);
      toast("Bot deleted");
      load();
    } catch {
      toast("Couldn’t delete the bot. Try again.");
    }
  };

  const shown = (bots ?? []).filter((b) => tab === "all" || b.status === tab);
  const n = (t: (typeof TABS)[number]) => (bots ?? []).filter((b) => t === "all" || b.status === t).length;

  return (
    <div className="rise">
      <div className="title-row">
        <div>
          <h1 className="display" style={{ fontSize: "clamp(2.2rem, 5vw, 3.6rem)" }}>My bots</h1>
          <p>{IS_MOCK ? "Sample bots are shown here. Connected to the API, this lists the bots you created." : "Every bot created through this service, newest first."}</p>
        </div>
        <Link href="/new" className="btn solid">New bot <span aria-hidden="true">→</span></Link>
      </div>

      <div className="tabs" role="group" aria-label="Filter by status">
        {TABS.map((t) => (
          <button key={t} type="button" aria-pressed={tab === t} onClick={() => setTab(t)}>
            {cap(t)} <small className="num">{n(t)}</small>
          </button>
        ))}
      </div>

      {err && (
        <p role="alert" className="empty">
          {err} <button className="link-btn" onClick={load}>Try again</button>
        </p>
      )}
      {!err && bots === null && <p className="empty soft">Loading…</p>}
      {bots && bots.length === 0 && (
        <div className="empty">
          <h2 className="h2">No bots yet</h2>
          <p className="soft">Create your first bot to start answering narratives.</p>
          <Link href="/new" className="btn solid" style={{ marginTop: 12 }}>New bot</Link>
        </div>
      )}
      {bots && bots.length > 0 && shown.length === 0 && <p className="empty soft">No {tab} bots.</p>}

      {shown.map((b) => (
        <div key={b.bot_id} className={"line" + (b.status === "deleted" ? " dead" : "")}>
          <div className="who">
            <Link href={`/bots/${b.bot_id}`}>{b.config.display_name}</Link>
            <div className="meta">@{b.config.username} · {fmtDate(b.created_at)}</div>
          </div>
          <span className={"status " + b.status}>{b.status}</span>
          <div className="acts">
            <Link href={`/bots/${b.bot_id}`} className="btn sm">Open</Link>
            {b.status !== "deleted" && (
              <button type="button" className="btn sm pen" aria-label={`Delete ${b.config.display_name}`} onClick={() => setAsking(b.bot_id)}>
                Delete
              </button>
            )}
          </div>
          {asking === b.bot_id && (
            <div className="sure" role="alertdialog" aria-label="Confirm delete">
              <span>Delete this bot? It stops answering. Its record stays readable.</span>
              <span className="row">
                <button type="button" className="btn sm" onClick={() => setAsking(null)}>Keep</button>
                <button type="button" className="btn sm solid" style={{ background: "var(--pen)", borderColor: "var(--pen)", color: "var(--paper)" }} onClick={() => remove(b)}>Delete bot</button>
              </span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
