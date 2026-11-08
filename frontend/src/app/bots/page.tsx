"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { IS_MOCK, api } from "@/lib/api";
import { cap, fmtDate } from "@/lib/format";
import { toast } from "@/components/Toast";
import { describeError } from "@/lib/errors";
import type { Bot, BotStatus } from "@/types/api";

const TABS: ("all" | BotStatus)[] = ["all", "pending", "active", "failed", "expired", "deleted"];

export default function Bots() {
  const [bots, setBots] = useState<Bot[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("all");
  const [asking, setAsking] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(() => {
    api.listBots().then((r) => { setBots(r.bots); setErr(null); }, (e: unknown) => setErr(describeError(e, "load your bots")));
  }, []);
  useEffect(load, [load]);

  // Pending bots flip to active a few seconds after the organizer confirms in Telegram:
  // re-read only those, every 3 s, and stop when none are left.
  const pendingIds = (bots ?? []).filter((b) => b.status === "pending").map((b) => b.bot_id).join(",");
  useEffect(() => {
    if (!pendingIds) return;
    const ids = pendingIds.split(",");
    let live = true; // drop answers that arrive after this effect was torn down (e.g. after a delete)
    const t = setInterval(() => {
      Promise.all(ids.map((id) => api.getBot(id).catch(() => null))).then((fresh) => {
        if (!live) return;
        setBots((prev) => prev && prev.map((b) => fresh.find((f) => f?.bot_id === b.bot_id) ?? b));
      });
    }, 3000);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, [pendingIds]);

  const remove = async (b: Bot) => {
    setDeleting(true);
    try {
      await api.deleteBot(b.bot_id);
      setBots((prev) => prev && prev.map((x) => (x.bot_id === b.bot_id ? { ...x, status: "deleted" } : x)));
      setAsking(null);
      toast("Bot deleted");
      load();
    } catch (e) {
      toast(describeError(e, "delete the bot"));
    } finally {
      setDeleting(false);
    }
  };

  const shown = (bots ?? []).filter((b) => tab === "all" || b.status === tab);
  const n = (t: (typeof TABS)[number]) => (bots ?? []).filter((b) => t === "all" || b.status === t).length;

  return (
    <div className="wrap page fade">
      <div className="page-head">
        <div>
          <h1 className="h1">My bots</h1>
          <p>{IS_MOCK ? "Sample bots are shown here. Connected to the API, this lists the bots you created." : "Every bot created through this service, newest first."}</p>
        </div>
        <Link href="/new" className="btn primary">New bot</Link>
      </div>

      <div className="seg" role="group" aria-label="Filter by status" style={{ marginBottom: 20 }}>
        {TABS.map((t) => (
          <button key={t} type="button" aria-pressed={tab === t} onClick={() => setTab(t)}>
            {cap(t)} <span className="num">{n(t)}</span>
          </button>
        ))}
      </div>

      {err && (
        <p role="alert" className="alert">
          {err} <button className="linkbtn" onClick={load}>Try again</button>
        </p>
      )}
      {!err && bots === null && <p className="muted" role="status">Loading…</p>}
      {bots && bots.length === 0 && (
        <div className="empty">
          <h2 className="h2">No bots yet</h2>
          <p className="muted">Create your first bot to start answering narratives.</p>
          <Link href="/new" className="btn primary">New bot</Link>
        </div>
      )}
      {bots && bots.length > 0 && shown.length === 0 && <p className="muted">No {tab} bots.</p>}

      {shown.length > 0 && (
        <div className="list">
          {shown.map((b) => (
            <div key={b.bot_id} className={"item" + (b.status === "deleted" ? " dead" : "")}>
              <div style={{ minWidth: 0 }}>
                <Link className="name" href={`/bots/${b.bot_id}`}>{b.config.display_name}</Link>
                <div className="small muted">@{b.telegram_username ?? b.config.username} · {fmtDate(b.created_at)}</div>
              </div>
              <span className={"status " + b.status}>{cap(b.status)}</span>
              <div className="row" style={{ gap: 8 }}>
                <Link href={`/bots/${b.bot_id}`} className="btn sm">Open</Link>
                {b.status !== "deleted" && (
                  <button type="button" className="btn sm danger" aria-label={`Delete ${b.config.display_name}`} onClick={() => setAsking(b.bot_id)}>
                    Delete
                  </button>
                )}
              </div>
              {asking === b.bot_id && (
                <div className="confirm" role="alertdialog" aria-label="Confirm delete">
                  <span>Delete this bot? It stops answering. Its record stays readable.</span>
                  <span className="row" style={{ gap: 8 }}>
                    <button type="button" className="btn sm" disabled={deleting} onClick={() => setAsking(null)}>Keep</button>
                    <button type="button" className="btn sm danger solid" disabled={deleting} onClick={() => remove(b)}>{deleting ? "Deleting…" : "Delete bot"}</button>
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
