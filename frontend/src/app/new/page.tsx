"use client";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ApiError, IS_MOCK, api } from "@/lib/api";
import { DEFAULTS } from "@/lib/mock";
import { Mosaic } from "@/components/Mosaic";
import type { Bot, BotConfig, Taxonomy } from "@/types/api";

const LIM = { name: 64, desc: 512, short: 120, msg: 4096 };
const USER_RE = /^[A-Za-z][A-Za-z0-9_]{1,28}[Bb][Oo][Tt]$/;

interface Draft {
  display_name: string;
  username: string;
  description: string;
  short_description: string;
  start_message: string;
  non_text_message: string;
  error_message: string;
  confidence_threshold: number;
  other_response: string;
  /** keys: "3" = whole narrative 3, "3.1" = its second sub-narrative */
  replies: Record<string, string>;
  subs: string[];
}

const example = (): Draft => ({
  display_name: "Odesa Fact Check",
  username: "odesa_factcheck_bot",
  description: "",
  short_description: "",
  start_message: DEFAULTS.start_message,
  non_text_message: DEFAULTS.non_text_message,
  error_message: DEFAULTS.error_message,
  confidence_threshold: 0.6,
  other_response: DEFAULTS.other_response,
  replies: { "0.1": "Утверждения о «провокации НАТО» — частый приём.", "2": "Утверждение выставляет агрессора жертвой." },
  subs: ["0.1"],
});

const ISSUE: Record<string, string> = {
  required: "This field is required.",
  out_of_range: "The length is outside the allowed range.",
  pattern_mismatch: "Use 5–32 characters. Start with a letter, use letters, digits and underscores, and end in “bot”.",
  unknown_field: "This field isn’t recognized.",
};
const LABEL: Record<string, string> = { display_name: "Display name", username: "Username", other_response: "Reply when nothing matches" };

function validate(d: Draft): Record<string, string> {
  const e: Record<string, string> = {};
  const name = d.display_name.trim();
  if (!name) e.display_name = "required";
  else if (name.length > LIM.name) e.display_name = "out_of_range";
  const u = d.username.trim();
  if (!u) e.username = "required";
  else if (!USER_RE.test(u) || u.length < 5 || u.length > 32) e.username = "pattern_mismatch";
  if (!d.other_response.trim()) e.other_response = "required";
  return e;
}

function toConfig(d: Draft, tax: Taxonomy): BotConfig {
  const responses: BotConfig["responses"] = [];
  tax.narratives.forEach((n, ni) => {
    const t = (d.replies[ni] ?? "").trim();
    if (t) responses.push({ narrative: n.name, subnarrative: null, text: t });
    n.subnarratives.forEach((s, si) => {
      const st = (d.replies[`${ni}.${si}`] ?? "").trim();
      if (st) responses.push({ narrative: n.name, subnarrative: s, text: st });
    });
  });
  const c: BotConfig = {
    display_name: d.display_name.trim(),
    username: d.username.trim(),
    confidence_threshold: d.confidence_threshold,
    other_response: d.other_response.trim(),
    responses,
  };
  for (const k of ["description", "short_description", "start_message", "non_text_message", "error_message"] as const) {
    if (d[k].trim()) c[k] = d[k].trim();
  }
  return c;
}

function fromBot(b: Bot, tax: Taxonomy): Draft {
  const c = b.config;
  const d: Draft = {
    display_name: c.display_name,
    username: "",
    description: c.description ?? "",
    short_description: c.short_description ?? "",
    start_message: c.start_message ?? DEFAULTS.start_message,
    non_text_message: c.non_text_message ?? DEFAULTS.non_text_message,
    error_message: c.error_message ?? DEFAULTS.error_message,
    confidence_threshold: c.confidence_threshold,
    other_response: c.other_response,
    replies: {},
    subs: [],
  };
  for (const r of c.responses) {
    const ni = tax.narratives.findIndex((n) => n.name === r.narrative);
    if (ni < 0) continue;
    const si = r.subnarrative === null ? -1 : tax.narratives[ni].subnarratives.indexOf(r.subnarrative);
    const key = si < 0 ? String(ni) : `${ni}.${si}`;
    d.replies[key] = r.text;
    if (si >= 0) d.subs.push(key);
  }
  return d;
}

function Field({ id, label, hint, error, count, children }: { id: string; label: string; hint?: string; error?: string; count?: ReactNode; children: ReactNode }) {
  return (
    <div className={"field" + (error ? " bad" : "")} data-field={id}>
      <label htmlFor={id}>{label}</label>
      {children}
      {count}
      {hint && (
        <div className="hint" id={id + "-h"}>
          {hint}
        </div>
      )}
      <div className="err" id={id + "-e"}>
        {error ? (ISSUE[error] ?? error) : ""}
      </div>
    </div>
  );
}

function Area({ id, value, onChange, max, rows = 3, placeholder }: { id: string; value: string; onChange: (v: string) => void; max: number; rows?: number; placeholder?: string }) {
  return (
    <>
      <textarea id={id} value={value} rows={rows} maxLength={max} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} aria-describedby={`${id}-h ${id}-e`} />
      <span className="count num">
        {value.length} / {max}
      </span>
    </>
  );
}

export default function NewBot() {
  const router = useRouter();
  const [tax, setTax] = useState<Taxonomy | null>(null);
  const [taxErr, setTaxErr] = useState<string | null>(null);
  const [d, setD] = useState<Draft>(example);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverErr, setServerErr] = useState<{ message: string; details: { field: string; issue: string }[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<number | null>(0);
  const [pv, setPv] = useState("0.1");
  const summaryRef = useRef<HTMLDivElement>(null);

  const loadTax = () => {
    api.taxonomy().then((t) => { setTax(t); setTaxErr(null); }, (e: unknown) => setTaxErr(e instanceof ApiError && e.status === 503 ? "The narrative list is temporarily unavailable." : "Couldn’t load the narrative list."));
  };
  useEffect(loadTax, []);

  // "Duplicate as new bot" arrives as /new?from=<bot id>
  useEffect(() => {
    const from = new URLSearchParams(window.location.search).get("from");
    if (!from || !tax) return;
    api.getBot(from).then((b) => setD(fromBot(b, tax)), () => {});
  }, [tax]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => {
    setD((p) => ({ ...p, [k]: v }));
    if (errors[k as string]) setErrors((e) => Object.fromEntries(Object.entries(e).filter(([f]) => f !== k)));
  };
  const setReply = (key: string, v: string) => setD((p) => ({ ...p, replies: { ...p.replies, [key]: v } }));
  const toggleSub = (key: string) =>
    setD((p) => {
      if (p.subs.includes(key)) {
        const replies = Object.fromEntries(Object.entries(p.replies).filter(([k]) => k !== key));
        return { ...p, subs: p.subs.filter((k) => k !== key), replies };
      }
      return { ...p, subs: [...p.subs, key] };
    });

  const answered = useMemo(() => {
    const s = new Set<number>();
    for (const [k, v] of Object.entries(d.replies)) if (v.trim()) s.add(parseInt(k));
    return s;
  }, [d.replies]);

  const count = (ni: number) => Object.entries(d.replies).filter(([k, v]) => v.trim() && parseInt(k) === ni).length;

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!tax) return;
    const e = validate(d);
    setErrors(e);
    setServerErr(null);
    if (Object.keys(e).length) {
      requestAnimationFrame(() => summaryRef.current?.focus());
      return;
    }
    setBusy(true);
    try {
      const bot = await api.createBot(toConfig(d, tax));
      router.push(`/bots/${bot.bot_id}`);
    } catch (err) {
      setBusy(false);
      if (err instanceof ApiError && err.status === 422 && err.body?.details) {
        const local: Record<string, string> = {};
        for (const x of err.body.details) if (x.field in LABEL) local[x.field] = x.issue;
        setErrors(local);
        setServerErr({ message: err.body.message, details: err.body.details });
      } else {
        setServerErr({ message: err instanceof ApiError && err.status === 503 ? "The service can’t check your bot right now. Try again in a moment." : err instanceof Error ? err.message : "Something went wrong.", details: [] });
      }
      requestAnimationFrame(() => summaryRef.current?.focus());
    }
  };

  const localList = Object.entries(errors);
  const showSummary = localList.length > 0 || serverErr;

  // reply preview resolves sub-narrative reply, then narrative reply, then the fallback
  const [pni, psi] = pv.split(".").map(Number);
  const subReply = pv.includes(".") ? (d.replies[pv] ?? "").trim() : "";
  const narReply = (d.replies[pni] ?? "").trim();
  const preview = subReply || narReply || d.other_response.trim() || "(empty)";
  const why = subReply
    ? "Uses the reply written for this sub-narrative."
    : narReply
      ? pv.includes(".") ? "No sub-narrative reply, so it falls back to the narrative reply." : "Uses the reply written for this narrative."
      : "No reply written for this one, so the bot sends the “nothing matches” reply.";
  void psi;

  return (
    <div className="rise">
      <div className="title-row">
        <div>
          <h1 className="display" style={{ fontSize: "clamp(2.2rem, 5vw, 3.6rem)" }}>
            New bot
          </h1>
          <p>The values below are an example so you can see how it works. Replace them with your own.</p>
        </div>
      </div>

      {taxErr && (
        <div className="errsum" role="alert">
          <b>{taxErr}</b> <button className="link-btn" type="button" onClick={loadTax}>Try again</button>
        </div>
      )}

      <form className="builder" onSubmit={submit} noValidate>
        <div>
          <div ref={summaryRef} tabIndex={-1}>
            {showSummary && (
              <div className="errsum" role="alert">
                <b>{serverErr ? serverErr.message : `${localList.length} ${localList.length === 1 ? "problem" : "problems"} to fix before creating the bot`}</b>
                <ul>
                  {localList.map(([f, issue]) => (
                    <li key={f}>
                      <button type="button" className="link-btn" onClick={() => document.getElementById(f)?.focus()}>
                        {LABEL[f] ?? f}: {ISSUE[issue] ?? issue}
                      </button>
                    </li>
                  ))}
                  {serverErr?.details.filter((x) => !(x.field in LABEL)).map((x) => (
                    <li key={x.field + x.issue}>
                      {x.field}: {ISSUE[x.issue] ?? x.issue}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <section className="sec" style={{ marginTop: 28 }}>
            <h2 className="h2">Identity</h2>
            <p className="lead">How the bot appears in Telegram.</p>
            <div className="two">
              <Field id="display_name" label="Display name" error={errors.display_name}>
                <input type="text" id="display_name" value={d.display_name} maxLength={LIM.name} onChange={(e) => set("display_name", e.target.value)} aria-invalid={!!errors.display_name} aria-describedby="display_name-e" />
              </Field>
              <Field id="username" label="Username" error={errors.username} hint="Must end in “bot”. Whether a name is taken is only known after you confirm in Telegram.">
                <div className="handle">
                  <span aria-hidden="true">@</span>
                  <input type="text" id="username" value={d.username} maxLength={32} autoComplete="off" spellCheck={false} onChange={(e) => set("username", e.target.value)} aria-invalid={!!errors.username} aria-describedby="username-h username-e" />
                </div>
              </Field>
            </div>
            <Field id="short_description" label="Short description (optional)" hint="Shown on the bot’s profile and in shared links.">
              <Area id="short_description" value={d.short_description} max={LIM.short} rows={2} onChange={(v) => set("short_description", v)} />
            </Field>
            <Field id="description" label="Description (optional)" hint="Shown in the empty chat before someone presses Start.">
              <Area id="description" value={d.description} max={LIM.desc} onChange={(v) => set("description", v)} />
            </Field>
          </section>

          <section className="sec">
            <h2 className="h2">When the bot answers</h2>
            <p className="lead">The bot replies only when the classifier’s score reaches your threshold.</p>
            <div className="field">
              <label htmlFor="thr">Confidence threshold</label>
              <div className="row" style={{ flexWrap: "nowrap" }}>
                <input id="thr" type="range" min={0} max={1} step={0.05} value={d.confidence_threshold} onChange={(e) => set("confidence_threshold", +e.target.value)} aria-describedby="thr-h" />
                <output htmlFor="thr" className="mono num" style={{ minWidth: "3.4ch", textAlign: "right", fontWeight: 500 }}>
                  {d.confidence_threshold.toFixed(2)}
                </output>
              </div>
              <div className="hint" id="thr-h">Higher means fewer replies and fewer wrong ones. 0.60 is a sensible start.</div>
            </div>
            <Field id="other_response" label="Reply when nothing matches" error={errors.other_response} hint="Also sent when a match has no reply written for it.">
              <Area id="other_response" value={d.other_response} max={LIM.msg} rows={2} onChange={(v) => set("other_response", v)} />
            </Field>
            <Field id="start_message" label="Greeting after Start">
              <Area id="start_message" value={d.start_message} max={LIM.msg} rows={2} onChange={(v) => set("start_message", v)} />
            </Field>
            <div className="two">
              <Field id="non_text_message" label="Reply to photos and files">
                <Area id="non_text_message" value={d.non_text_message} max={LIM.msg} onChange={(v) => set("non_text_message", v)} />
              </Field>
              <Field id="error_message" label="Reply when checking fails">
                <Area id="error_message" value={d.error_message} max={LIM.msg} onChange={(v) => set("error_message", v)} />
              </Field>
            </div>
          </section>

          <section className="sec">
            <h2 className="h2">Replies by narrative</h2>
            <p className="lead">Filled tiles have a reply. Pick a tile or a row to write one. Leave a narrative empty to skip it.</p>
            {tax ? (
              <>
                <Mosaic narratives={tax.narratives} answered={answered} picked={open} onPick={(i) => { setOpen(i); requestAnimationFrame(() => document.getElementById(`narr-${i}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" })); }} />
                <div style={{ marginTop: 28 }}>
                  {tax.narratives.map((n, ni) => {
                    const isOpen = open === ni;
                    const c = count(ni);
                    return (
                      <div className="narr" key={n.name} id={`narr-${ni}`}>
                        <button type="button" aria-expanded={isOpen} aria-controls={`narr-body-${ni}`} onClick={() => setOpen(isOpen ? null : ni)}>
                          <span className="nm">{n.name}</span>
                          <span className={"st" + (c ? " on" : "")}>{c ? `${c} ${c === 1 ? "reply" : "replies"}` : "no reply"}</span>
                          <span aria-hidden="true">{isOpen ? "−" : "+"}</span>
                        </button>
                        {isOpen && (
                          <div className="body" id={`narr-body-${ni}`}>
                            <Field id={`r-${ni}`} label={`Reply for every “${n.name}” message`}>
                              <Area id={`r-${ni}`} value={d.replies[ni] ?? ""} max={LIM.msg} placeholder="Write the reply in your audience’s language" onChange={(v) => setReply(String(ni), v)} />
                            </Field>
                            {n.subnarratives.length ? (
                              <div className="subs">
                                <div className="hint">A sub-narrative reply replaces the narrative reply for that sub-narrative only.</div>
                                {n.subnarratives.map((s, si) => {
                                  const key = `${ni}.${si}`;
                                  const on = d.subs.includes(key);
                                  return (
                                    <div key={key}>
                                      <div className="sub-h">
                                        <span>{s}</span>
                                        <button type="button" className="btn sm" aria-expanded={on} onClick={() => toggleSub(key)}>
                                          {on ? "Remove" : "Add reply"}
                                        </button>
                                      </div>
                                      {on && (
                                        <Field id={`r-${ni}-${si}`} label={`Reply for “${s}”`}>
                                          <Area id={`r-${ni}-${si}`} value={d.replies[key] ?? ""} max={LIM.msg} rows={2} onChange={(v) => setReply(key, v)} />
                                        </Field>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <div className="hint">This narrative has no sub-narratives, so it can only be answered at narrative level.</div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            ) : (
              <p className="soft">{taxErr ? "" : "Loading the narrative list…"}</p>
            )}
          </section>

          <div className="row" style={{ marginTop: 36 }}>
            <button className="btn solid" type="submit" disabled={busy || !tax}>
              {busy ? "Creating…" : "Create bot"}
              {!busy && <span aria-hidden="true">→</span>}
            </button>
            <button className="btn" type="button" onClick={() => { setD(example()); setErrors({}); setServerErr(null); }}>
              Reset to example
            </button>
          </div>
          <p className="cap" style={{ marginTop: 14 }}>
            Settings can’t be edited after creation. To change a reply, create a new bot and delete the old one.
            {IS_MOCK && " This build uses sample data; nothing is sent to a server."}
          </p>
        </div>

        <aside className="aside" aria-label="Reply preview">
          <h2 className="h2" style={{ fontSize: "1.35rem" }}>Preview a reply</h2>
          <p className="cap" style={{ margin: "6px 0 16px" }}>Pick what the classifier might find to see what the bot would send.</p>
          <div className="field">
            <label htmlFor="pv">Classifier finds</label>
            <select id="pv" value={pv} onChange={(e) => setPv(e.target.value)}>
              {(tax?.narratives ?? []).map((n, ni) => (
                <optgroup key={n.name} label={n.name}>
                  <option value={String(ni)}>Whole narrative</option>
                  {n.subnarratives.map((s, si) => (
                    <option key={s} value={`${ni}.${si}`}>{s}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="proof" style={{ padding: 16 }}>
            <div className="reply" style={{ borderTop: 0, paddingTop: 0 }}>
              <small>Your bot replies</small>
              <p>{preview}</p>
            </div>
          </div>
          <p className="cap" style={{ marginTop: 12 }}>
            {why} Matches scoring under <span className="mono num">{d.confidence_threshold.toFixed(2)}</span> are ignored.
          </p>
        </aside>
      </form>
    </div>
  );
}
