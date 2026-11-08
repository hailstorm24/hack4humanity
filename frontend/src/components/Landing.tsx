"use client";
import Link from "next/link";
import { useEffect, useState } from "react";

const MOMENTS = [
  {
    title: "Forward a message to the bot",
    body: "Someone sends your bot a claim they doubt: a forward, a caption, text copied from a channel. The bot reads the words and nothing else.",
    tags: ["Input", "Any Telegram chat"],
  },
  {
    title: "The classifier finds the narrative",
    body: "A shared classifier scores the message against the narrative list. You never train anything and you never see anyone’s data.",
    tags: ["Shared classifier", "SemEval 2025"],
  },
  {
    title: "Your reply goes out",
    body: "The bot answers with the reply you wrote for that narrative, or a more specific one you wrote for the sub-narrative.",
    tags: ["Your reply", "Per narrative"],
  },
  {
    title: "Below the threshold, the fallback reply",
    body: "Set a confidence threshold. Below it, the bot sends your fallback reply instead of guessing.",
    tags: ["Threshold", "Fallback reply"],
  },
  {
    title: "Confirm the bot in Telegram, then share it",
    body: "Create the bot here, approve it in Telegram, share the link. Confirmation links last 24 hours.",
    tags: ["24 hours", "One approval"],
  },
] as const;

const CLAIM = "НАТО спровоцировало эту войну, Россия лишь защищает себя.";
const REPLY = "Утверждения о «провокации НАТО» — частый приём.";

type ChatMsg = { id: string; dir: "in" | "out"; time: string; text: string; fwd?: string; lang?: string };
const claim: ChatMsg = { id: "claim", dir: "out", time: "9:41", fwd: "Новости дня", lang: "ru", text: CLAIM };
// What is on screen in each scene. A message that stays across scenes keeps its key, so it never re-animates.
const CHAT: ChatMsg[][] = [
  [claim],
  [claim],
  [claim, { id: "reply", dir: "in", time: "9:41", lang: "ru", text: REPLY }],
  [
    { id: "rain", dir: "out", time: "9:42", lang: "ru", text: "Сегодня в Одессе дождь." },
    { id: "fallback", dir: "in", time: "9:42", text: "I couldn’t recognize a known narrative in this message." },
  ],
  [
    { id: "start", dir: "out", time: "9:41", text: "/start" },
    { id: "greet", dir: "in", time: "9:41", text: "Forward me a message and I’ll reply if I recognize a known narrative." },
  ],
];

const Ticks = () => (
  <svg width="16" height="10" viewBox="0 0 16 10" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M1 5.5 4 8.5 9.5 1.5M6 8.5l.7.5L12.2 1.5" />
  </svg>
);

function Msg({ dir, time, fwd, lang, children }: { dir: "in" | "out"; time: string; fwd?: string; lang?: string; children: React.ReactNode }) {
  return (
    <div className={"tgm " + dir} lang={lang}>
      {fwd && (
        <span className="fwd">
          Forwarded from <b>{fwd}</b>
        </span>
      )}
      {children}
      <span className="meta">
        {time}
        {dir === "out" && <Ticks />}
      </span>
    </div>
  );
}

// A Telegram chat (iOS look). The bot only ever shows messages; what the classifier saw is annotated outside the phone.
function Phone({ scene }: { scene: number }) {
  const typing = scene === 0 || scene === 1;
  return (
    <div className="phone" role="img" aria-label={`Phone showing a Telegram chat with the bot. Scene: ${MOMENTS[scene].title}.`}>
      <div className="phone-notch" aria-hidden="true" />
      <div className="tgp" aria-hidden="true">
        <div className="tgp-status">
          <span>9:41</span>
          <span>
            <svg width="17" height="11" viewBox="0 0 17 11" fill="currentColor"><rect x="0" y="7" width="3" height="4" rx="0.8" /><rect x="4.5" y="5" width="3" height="6" rx="0.8" /><rect x="9" y="2.5" width="3" height="8.5" rx="0.8" /><rect x="13.5" y="0" width="3" height="11" rx="0.8" /></svg>
            <svg width="24" height="11" viewBox="0 0 24 11" fill="none"><rect x="0.5" y="0.5" width="20" height="10" rx="3" stroke="currentColor" opacity="0.5" /><rect x="2" y="2" width="17" height="7" rx="1.8" fill="currentColor" /><rect x="21.5" y="3.5" width="1.6" height="4" rx="0.8" fill="currentColor" opacity="0.5" /></svg>
          </span>
        </div>
        <div className="tgp-head">
          <span className="tgp-back">
            <svg width="12" height="20" viewBox="0 0 12 20" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M10 2 2 10l8 8" /></svg>
            <i>3</i>
          </span>
          <div className="tgp-title">
            <b>Odesa Fact Check</b>
            <span className={typing ? "typing-s" : undefined}>{typing ? "typing…" : "bot"}</span>
          </div>
          <span className="tgp-ava">O</span>
        </div>
        <div className="tgp-chat">
          <span className="tgp-date">Today</span>
          {CHAT[scene].map((m) => (
            <Msg key={m.id} dir={m.dir} time={m.time} fwd={m.fwd} lang={m.lang}>
              {m.text}
            </Msg>
          ))}
        </div>
        <div className="tgp-bar">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m21 11-8.6 8.6a5.5 5.5 0 0 1-7.8-7.8l8.6-8.6a3.7 3.7 0 0 1 5.2 5.2l-8.6 8.6a1.8 1.8 0 0 1-2.6-2.6L15 6.5" /></svg>
          <span className="tgp-field">
            Message
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="9" /><path d="M8.5 14.5a4.5 4.5 0 0 0 7 0M9 9.5h.01M15 9.5h.01" /></svg>
          </span>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
        </div>
      </div>
    </div>
  );
}

const ASIDE: Record<number, { label: string; line: string; meter?: number; foot?: string }> = {
  1: { label: "The classifier found", line: "Russia is the Victim › only self-defence", meter: 82, foot: "score 0.82 · threshold 0.60" },
  3: { label: "The classifier found", line: "Nothing above your threshold", meter: 21, foot: "score 0.21 · threshold 0.60" },
  4: { label: "Your bot is live", line: "t.me/odesa_factcheck_bot", foot: "Confirmation link expires in 23:59:41" },
};

function Aside({ scene }: { scene: number }) {
  const a = ASIDE[scene];
  return (
    <div className="aside-card" aria-live="polite">
      {a && (
        <div className="found">
          <span className="label">{a.label}</span>
          <span>{a.line}</span>
          {a.meter !== undefined && (
            <div className="meter" role="presentation">
              <i style={{ width: `${a.meter}%` }} />
              <u style={{ left: "60%" }} />
            </div>
          )}
          {a.foot && <span className="num" style={{ color: "var(--muted)" }}>{a.foot}</span>}
        </div>
      )}
    </div>
  );
}

export function Landing() {
  const [scene, setScene] = useState(0);

  // Scroll drives the phone: whichever moment crosses the middle of the viewport is "playing".
  useEffect(() => {
    const els = document.querySelectorAll<HTMLElement>("[data-moment]");
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setScene(Number((e.target as HTMLElement).dataset.moment));
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);


  return (
    <div className="wrap fade">
      <div className="land">
        <div className="story">
          <section className="hero-copy">
            <p className="eyebrow">A Telegram bot builder · Hack4Humanity</p>
            <h1 className="h1">
              A bot that answers propaganda with <span className="hl">your community.</span>
            </h1>
            <p className="lede">
              Forward it a message. It spots the narrative behind it and replies with the response you wrote in advance. <b style={{ color: "var(--text)", fontWeight: 500 }}>You decide what it says.</b>
            </p>
            <div className="row">
              <Link href="/new" className="btn primary">Create a bot</Link>
              <a href="#moments" className="btn">See how it works ↓</a>
            </div>
          </section>

          <section id="idea" aria-labelledby="idea-h">
            <p className="sec-no"><b>01</b> The idea</p>
            <h2 className="big" id="idea-h">A bot for the narratives you keep answering.</h2>
            <p className="body">
              The same few narratives come back again and again. Write a good reply to each once, and let a bot hand it to anyone who asks, in their own chat, in their own language.
            </p>
          </section>

          <section id="moments" aria-labelledby="moments-h" style={{ minHeight: 0, paddingBottom: 0 }}>
            <p className="sec-no"><b>02</b> Five moments</p>
            <h2 className="big" id="moments-h">Five moments of a Telegram bot, played on the phone.</h2>
            <p className="body">Each moment drives the phone beside it.</p>
          </section>

          {MOMENTS.map((m, i) => (
            <section key={m.title} className="moment" data-moment={i} data-on={scene === i} aria-labelledby={`m-${i}`}>
              <div className="numeral" aria-hidden="true">{String(i + 1).padStart(2, "0")}</div>
              <h3 className="big" id={`m-${i}`} style={{ font: "600 clamp(1.25rem,2.2vw,1.625rem)/1.2 var(--display)", letterSpacing: "-0.03em" }}>{m.title}.</h3>
              <p className="body">{m.body}</p>
              <div className="tags">{m.tags.map((t) => <span className="tag" key={t}>{t}</span>)}</div>
            </section>
          ))}

          <section className="closer" aria-labelledby="close-h">
            <h2 className="big" id="close-h">Write the replies once. The bot does the rest.</h2>
            <p className="body">Setting up takes a few minutes.</p>
            <div className="row">
              <Link href="/new" className="btn primary">Create a bot</Link>
              <Link href="/bots" className="btn">My bots</Link>
            </div>
          </section>
        </div>

        <div className="phone-col">
          <Phone scene={scene} />
          <Aside scene={scene} />
          <p className="now" aria-live="polite"><span className="live" aria-hidden="true" />Now playing · <b>{String(scene + 1).padStart(2, "0")} {MOMENTS[scene].title}</b></p>
        </div>
      </div>
    </div>
  );
}
