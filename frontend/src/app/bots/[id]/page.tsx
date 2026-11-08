"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, IS_MOCK, api, simulate } from "@/lib/api";
import { cap, clock, fmtDate } from "@/lib/format";
import { copyText, toast } from "@/components/Toast";
import { describeError } from "@/lib/errors";
import type { Bot } from "@/types/api";

const FAIL: Record<string, string> = {
  bot_limit_exceeded: "Your Telegram account has reached its limit of bots. Delete one in Telegram, then try again.",
};

export default function BotPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [bot, setBot] = useState<Bot | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [next, setNext] = useState(3);
  const [asking, setAsking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const nextRef = useRef(3);

  const load = useCallback(() => {
    api.getBot(id).then(
      (b) => { setBot(b); setErr(null); },
      (e: unknown) => setErr(e instanceof ApiError && e.status === 404 ? "not_found" : e instanceof Error && e.message === "not_found" ? "not_found" : describeError(e, "load this bot")),
    );
  }, [id]);
  useEffect(load, [load]);

  // while pending: tick the countdown every second and re-read the bot every 3 s
  const pending = bot?.status === "pending";
  useEffect(() => {
    if (!pending) return;
    nextRef.current = 3;
    const t = setInterval(() => {
      setNow(Date.now());
      nextRef.current -= 1;
      if (nextRef.current <= 0) { nextRef.current = 3; load(); }
      setNext(nextRef.current);
    }, 1000);
    return () => clearInterval(t);
  }, [pending, load]);

  if (err === "not_found") {
    return (
      <div className="wrap empty fade">
        <h1 className="h1">Bot not found</h1>
        <p className="muted">This bot doesn’t exist, or the sample data was cleared when the browser tab closed.</p>
        <Link href="/bots" className="btn">Back to My bots</Link>
      </div>
    );
  }
  if (err) return <p className="wrap page alert" role="alert">{err} <button className="linkbtn" onClick={load}>Try again</button></p>;
  if (!bot) return <p className="wrap page muted" role="status">Loading…</p>;

  const c = bot.config;
  const remove = async () => {
    setDeleting(true);
    try { await api.deleteBot(bot.bot_id); toast("Bot deleted"); router.push("/bots"); } catch (e) { toast(describeError(e, "delete the bot")); setDeleting(false); }
  };
  const act = async (o: "confirm" | "limit" | "expire") => { await simulate(bot.bot_id, o); toast("Done. The next check picks it up."); };

  let headline = "";
  let sub = "";
  if (bot.status === "pending") { headline = "Confirm in Telegram"; sub = "Telegram needs you to approve the bot before it can answer messages."; }
  else if (bot.status === "active") { headline = "Your bot is live"; sub = "Share the link. Anyone who forwards it a message gets a reply."; }
  else if (bot.status === "failed") { headline = "Telegram couldn’t create it"; sub = FAIL[bot.failure_reason ?? ""] ?? "Something went wrong on Telegram’s side. Create the bot again."; }
  else if (bot.status === "expired") { headline = "The link expired"; sub = "The link expired after 24 hours. Your replies are kept, so you can create the bot again."; }
  else { headline = "Deleted"; sub = `This bot stopped answering on ${bot.deleted_at ? fmtDate(bot.deleted_at) : "an earlier date"}. The record stays readable.`; }

  return (
    <div className="narrow page fade">
      <Link href="/bots" className="back">← My bots</Link>
      <div className="page-head" style={{ marginTop: 8 }}>
        <div>
          <h1 className="h1">{headline}</h1>
          <p>{sub}</p>
        </div>
        <span className={"status " + bot.status}>{cap(bot.status)}</span>
      </div>

      <div className="stack">
        {(bot.status !== "deleted") && (
          <section className="panel stack-sm" aria-live="polite" aria-label="Next step">
            {bot.status === "pending" && bot.creation_link && bot.expires_at && (
              <>
                <div className="row">
                  {IS_MOCK ? (
                    <button type="button" className="btn primary" onClick={() => toast("With the real API this opens Telegram. Use the sample controls below to continue.")}>Open in Telegram</button>
                  ) : (
                    <a className="btn primary" href={bot.creation_link} target="_blank" rel="noopener noreferrer">Open in Telegram</a>
                  )}
                  <button type="button" className="btn" onClick={() => copyText(bot.creation_link!)}>Copy link</button>
                </div>
                <ol className="tg-steps">
                  <li>Open the link in <b>Telegram Desktop</b>.</li>
                  <li>Tap <b>«Создать бота»</b>.</li>
                  <li>Confirm. This page switches to live within a few seconds.</li>
                </ol>
                <p className="small muted">Use Telegram Desktop: the iOS app doesn’t support the create button yet and opens an empty “Forward” screen.</p>
                <div style={{ marginTop: 12 }}>
                  <p className="small muted">Link expires in</p>
                  <div className="clock num">{clock(bot.expires_at, now)}</div>
                  <p className="small muted" style={{ marginTop: 4 }}>{fmtDate(bot.expires_at)}</p>
                </div>
                <p className="small muted"><span className="pulse" aria-hidden="true" /> Checking again in <span className="num">{next}</span> s</p>
                {IS_MOCK && (
                  <details className="sample">
                    <summary>Sample controls: simulate Telegram and the server</summary>
                    <p style={{ margin: "8px 0" }}>With the real API these happen outside the page. Here they let you see each outcome.</p>
                    <div className="row" style={{ gap: 8 }}>
                      <button type="button" className="btn sm" onClick={() => act("confirm")}>Organizer confirms</button>
                      <button type="button" className="btn sm" onClick={() => act("limit")}>Telegram refuses (bot limit)</button>
                      <button type="button" className="btn sm" onClick={() => act("expire")}>Let the link expire</button>
                    </div>
                  </details>
                )}
              </>
            )}
            {bot.status === "active" && bot.telegram_link && (
              <>
                <p><span className="small muted">Your bot’s username</span><br /><b className="mono">@{bot.telegram_username ?? c.username}</b></p>
                <div className="row">
                  <a className="btn primary" href={bot.telegram_link} target="_blank" rel="noopener noreferrer">Open bot</a>
                  <button type="button" className="btn" onClick={() => copyText(bot.telegram_link!)}>Copy link</button>
                </div>
              </>
            )}
            {(bot.status === "failed" || bot.status === "expired") && (
              <div><Link className="btn primary" href={`/new?from=${bot.bot_id}`}>Create again with these replies</Link></div>
            )}
          </section>
        )}

        <section className="panel" aria-labelledby="details">
          <h2 className="h2" id="details" style={{ marginBottom: 16 }}>{c.display_name}</h2>
          <dl className="facts">
            <dt>{bot.telegram_username ? "Username" : "Suggested username"}</dt><dd className="mono">@{bot.telegram_username ?? c.username}</dd>
            {bot.telegram_username && bot.telegram_username !== c.username && (<><dt>You suggested</dt><dd className="mono">@{c.username}</dd></>)}
            <dt>Bot ID</dt><dd className="mono">{bot.bot_id}</dd>
            <dt>Created</dt><dd>{fmtDate(bot.created_at)}</dd>
            {bot.failure_reason && (<><dt>Failure</dt><dd className="mono">{bot.failure_reason}</dd></>)}
            <dt>Threshold</dt><dd className="mono num">{c.confidence_threshold.toFixed(2)}</dd>
            <dt>Taxonomy</dt><dd className="mono">{bot.taxonomy_version}</dd>
            <dt>No match</dt><dd>{c.other_response}</dd>
          </dl>
          <div className="row" style={{ marginTop: 24 }}>
            <Link href={`/new?from=${bot.bot_id}`} className="btn">Duplicate as new bot</Link>
            {bot.status !== "deleted" && !asking && (
              <button type="button" className="btn danger" onClick={() => setAsking(true)}>Delete</button>
            )}
          </div>
          {asking && (
            <div className="confirm" role="alertdialog" aria-label="Confirm delete" style={{ marginTop: 16 }}>
              <span>Delete this bot? It stops answering. Its record stays readable.</span>
              <span className="row" style={{ gap: 8 }}>
                <button type="button" className="btn sm" onClick={() => setAsking(false)}>Keep</button>
                <button type="button" className="btn sm danger solid" disabled={deleting} onClick={remove}>{deleting ? "Deleting…" : "Delete bot"}</button>
              </span>
            </div>
          )}
        </section>

        <section aria-labelledby="replies">
          <h2 className="h2" id="replies" style={{ marginBottom: 16 }}>Replies ({c.responses.length})</h2>
          {c.responses.length ? (
            <ul className="panel reply-list">
              {c.responses.map((r) => (
                <li key={r.narrative + (r.subnarrative ?? "")}>
                  <small>{r.narrative}{r.subnarrative ? ` › ${r.subnarrative}` : " (whole narrative)"}</small>
                  <p className="bubble">{r.text}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No narrative replies. This bot only sends the “nothing matches” reply.</p>
          )}
        </section>
      </div>
    </div>
  );
}
