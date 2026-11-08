"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, IS_MOCK, api, simulate } from "@/lib/api";
import { clock, fmtDate } from "@/lib/format";
import { copyText, toast } from "@/components/Toast";
import type { Bot } from "@/types/api";

const FAIL: Record<string, string> = {
  username_occupied: "That username is already taken on Telegram. Create the bot again with a different one.",
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
  const nextRef = useRef(3);

  const load = useCallback(() => {
    api.getBot(id).then(
      (b) => { setBot(b); setErr(null); },
      (e: unknown) => setErr(e instanceof ApiError && e.status === 404 ? "not_found" : e instanceof Error && e.message === "not_found" ? "not_found" : "Couldn’t load this bot."),
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
      <div className="empty rise">
        <h1 className="h2">Bot not found</h1>
        <p className="soft">This bot doesn’t exist, or the sample data was cleared when the browser tab closed.</p>
        <Link href="/bots" className="btn" style={{ marginTop: 12 }}>Back to My bots</Link>
      </div>
    );
  }
  if (err) return <p className="empty" role="alert">{err} <button className="link-btn" onClick={load}>Try again</button></p>;
  if (!bot) return <p className="empty soft">Loading…</p>;

  const c = bot.config;
  const remove = async () => {
    try { await api.deleteBot(bot.bot_id); toast("Bot deleted"); router.push("/bots"); } catch { toast("Couldn’t delete the bot. Try again."); }
  };
  const act = async (o: "confirm" | "occupied" | "expire") => { await simulate(bot.bot_id, o); toast("Done. The next check picks it up."); };

  let headline = "";
  let sub = "";
  if (bot.status === "pending") { headline = "Confirm in Telegram"; sub = "Your bot exists on our side. Telegram needs you to approve it before it can answer messages."; }
  else if (bot.status === "active") { headline = "Your bot is live"; sub = "Share the link. Anyone who forwards it a message gets a reply."; }
  else if (bot.status === "failed") { headline = "Telegram couldn’t create it"; sub = FAIL[bot.failure_reason ?? ""] ?? "Something went wrong on Telegram’s side."; }
  else if (bot.status === "expired") { headline = "The link expired"; sub = "Confirmation links work for 24 hours. Your replies are kept, so you can create the bot again."; }
  else { headline = "Deleted"; sub = `This bot stopped answering on ${bot.deleted_at ? fmtDate(bot.deleted_at) : "an earlier date"}. The record stays readable.`; }

  return (
    <div className="rise">
      <div className="title-row">
        <div>
          <p className="cap" style={{ margin: 0 }}><Link href="/bots">← My bots</Link></p>
          <h1 className="display" style={{ fontSize: "clamp(2.2rem, 5vw, 3.6rem)", marginTop: 12 }}>{headline}</h1>
          <p>{sub}</p>
        </div>
        <span className={"status " + bot.status}>{bot.status}</span>
      </div>

      <div className="bot-grid">
        <section className="sec" aria-live="polite">
          {bot.status === "pending" && bot.creation_link && bot.expires_at && (
            <>
              <div className="row">
                {IS_MOCK ? (
                  <button type="button" className="btn solid" onClick={() => toast("With the real API this opens Telegram. Use the sample controls below to continue.")}>Open in Telegram <span aria-hidden="true">↗</span></button>
                ) : (
                  <a className="btn solid" href={bot.creation_link} target="_blank" rel="noopener noreferrer">Open in Telegram <span aria-hidden="true">↗</span></a>
                )}
                <button type="button" className="btn" onClick={() => copyText(bot.creation_link!)}>Copy link</button>
              </div>
              <p className="cap" style={{ margin: "28px 0 6px" }}>Link expires in</p>
              <div className="clock num">{clock(bot.expires_at, now)}</div>
              <p className="cap" style={{ marginTop: 6 }}>{fmtDate(bot.expires_at)}</p>
              <div className="live"><i aria-hidden="true" />Checking again in <span className="num">{next}</span> s</div>
              {IS_MOCK && (
                <details className="mockbox">
                  <summary>Sample controls: simulate Telegram and the server</summary>
                  <p style={{ margin: "8px 0 0" }}>With the real API these happen outside the page. Here they let you see each outcome.</p>
                  <div className="row">
                    <button type="button" className="btn sm" onClick={() => act("confirm")}>Organizer confirms</button>
                    <button type="button" className="btn sm" onClick={() => act("occupied")}>Username is taken</button>
                    <button type="button" className="btn sm" onClick={() => act("expire")}>Let the link expire</button>
                  </div>
                </details>
              )}
            </>
          )}
          {bot.status === "active" && bot.telegram_link && (
            <div className="row">
              <a className="btn solid" href={bot.telegram_link} target="_blank" rel="noopener noreferrer">{bot.telegram_link.replace("https://", "")} <span aria-hidden="true">↗</span></a>
              <button type="button" className="btn" onClick={() => copyText(bot.telegram_link!)}>Copy link</button>
            </div>
          )}
          {(bot.status === "failed" || bot.status === "expired") && (
            <Link className="btn solid" href={`/new?from=${bot.bot_id}`}>Create again with these replies</Link>
          )}

          <h2 className="h2" style={{ margin: "40px 0 12px" }}>Replies ({c.responses.length})</h2>
          {c.responses.length ? (
            <ul className="replies">
              {c.responses.map((r) => (
                <li key={r.narrative + (r.subnarrative ?? "")}>
                  <small>{r.narrative}{r.subnarrative ? ` › ${r.subnarrative}` : " (whole narrative)"}</small>
                  <p>{r.text}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="soft">No narrative replies. This bot only sends the “nothing matches” reply.</p>
          )}
        </section>

        <section className="sec">
          <h2 className="h2" style={{ marginBottom: 16 }}>{c.display_name}</h2>
          <dl className="facts">
            <dt>Username</dt><dd className="mono">@{c.username}</dd>
            <dt>Bot ID</dt><dd className="mono">{bot.bot_id}</dd>
            <dt>Created</dt><dd>{fmtDate(bot.created_at)}</dd>
            {bot.failure_reason && (<><dt>Failure</dt><dd className="mono">{bot.failure_reason}</dd></>)}
            <dt>Threshold</dt><dd className="mono num">{c.confidence_threshold.toFixed(2)}</dd>
            <dt>Taxonomy</dt><dd className="mono">{bot.taxonomy_version}</dd>
            <dt>No match</dt><dd>{c.other_response}</dd>
          </dl>
          <div className="row" style={{ marginTop: 28 }}>
            <Link href={`/new?from=${bot.bot_id}`} className="btn">Duplicate as new bot</Link>
            {bot.status !== "deleted" && !asking && (
              <button type="button" className="btn pen" onClick={() => setAsking(true)}>Delete</button>
            )}
          </div>
          {asking && (
            <div className="sure" role="alertdialog" aria-label="Confirm delete" style={{ marginTop: 16 }}>
              <span>Delete this bot? It stops answering. Its record stays readable.</span>
              <span className="row">
                <button type="button" className="btn sm" onClick={() => setAsking(false)}>Keep</button>
                <button type="button" className="btn sm solid" style={{ background: "var(--pen)", borderColor: "var(--pen)", color: "var(--paper)" }} onClick={remove}>Delete bot</button>
              </span>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
