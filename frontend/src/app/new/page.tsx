"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ApiError, IS_MOCK, api } from "@/lib/api";
import { DEFAULT_MESSAGES as DEFAULTS, DEFAULT_REPLIES } from "@/lib/defaults";
import { describeError } from "@/lib/errors";
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
  replies: {},
  subs: [],
});

/** Fill every narrative that has no reply yet with its Russian default. Sub-narratives inherit the narrative reply. */
function withDefaults(d: Draft, tax: Taxonomy): Draft {
  const replies = { ...d.replies };
  tax.narratives.forEach((n, ni) => {
    if (!(replies[ni] ?? "").trim() && DEFAULT_REPLIES[n.name]) replies[ni] = DEFAULT_REPLIES[n.name];
  });
  return { ...d, replies };
}

const ISSUE: Record<string, string> = {
  required: "This field is required.",
  out_of_range: "The length is outside the allowed range.",
  pattern_mismatch: "Use 5–32 characters. Start with a letter, use letters, digits and underscores, and end in “bot”.",
  unknown_field: "This field isn’t recognized.",
  wrong_type: "This has the wrong type.",
  unknown_narrative: "This narrative isn’t in the current list.",
  unknown_subnarrative: "This sub-narrative isn’t in the current list.",
  duplicate_mapping: "Two replies target the same narrative.",
};
const LABEL: Record<string, string> = {
  display_name: "Display name",
  username: "Username",
  description: "Description",
  short_description: "Short description",
  confidence_threshold: "Confidence threshold",
  other_response: "Reply when nothing matches",
  start_message: "Greeting after Start",
  non_text_message: "Reply to photos and files",
  error_message: "Reply when checking fails",
};

/** Server paths like `responses[2].text` point into the list we sent; name the narrative instead. */
function labelFor(field: string, sent: BotConfig | null): string {
  const m = /^responses\[(\d+)\]/.exec(field);
  const r = m && sent ? sent.responses[Number(m[1])] : undefined;
  if (r) return `Reply for “${r.narrative}${r.subnarrative ? ` › ${r.subnarrative}` : ""}”`;
  return LABEL[field] ?? field;
}

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

/** Reply keys ("3" or "3.1") in the exact order toConfig puts them in `responses`, so a server path like responses[2] can be traced back to a text box. */
function mappingKeys(d: Draft, tax: Taxonomy): string[] {
  const keys: string[] = [];
  tax.narratives.forEach((n, ni) => {
    if ((d.replies[ni] ?? "").trim()) keys.push(String(ni));
    n.subnarratives.forEach((_, si) => {
      if ((d.replies[`${ni}.${si}`] ?? "").trim()) keys.push(`${ni}.${si}`);
    });
  });
  return keys;
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
      {hint && (
        <div className="hint" id={id + "-h"}>
          {hint}
        </div>
      )}
      {children}
      {count}
      {error && (
        <div className="err" id={id + "-e"}>
          {ISSUE[error] ?? error}
        </div>
      )}
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
  const [sent, setSent] = useState<BotConfig | null>(null);
  const [replyErrors, setReplyErrors] = useState<Record<string, string>>({});

  const loadTax = () => {
    api.taxonomy().then((t) => { setTax(t); setD((p) => withDefaults(p, t)); setTaxErr(null); }, (e: unknown) => setTaxErr(e instanceof ApiError && e.status === 503 ? "The narrative list is temporarily unavailable." : "Couldn’t load the narrative list."));
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

  const count = (ni: number) => Object.entries(d.replies).filter(([k, v]) => v.trim() && parseInt(k) === ni).length;

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!tax) return;
    const e = validate(d);
    setErrors(e);
    setReplyErrors({});
    setServerErr(null);
    if (Object.keys(e).length) {
      requestAnimationFrame(() => summaryRef.current?.focus());
      return;
    }
    setBusy(true);
    const keys = mappingKeys(d, tax);
    try {
      const cfg = toConfig(d, tax);
      setSent(cfg);
      const bot = await api.createBot(cfg);
      router.push(`/bots/${bot.bot_id}`);
    } catch (err) {
      setBusy(false);
      if (err instanceof ApiError && err.body?.error === "validation_failed" && err.body.details) {
        const local: Record<string, string> = {};
        for (const x of err.body.details) if (x.field in LABEL) local[x.field] = x.issue;
        const rep: Record<string, string> = {};
        for (const x of err.body.details) {
          const m = /^responses\[(\d+)\]/.exec(x.field);
          const key = m ? keys[Number(m[1])] : undefined;
          if (key) rep[key] = x.issue;
        }
        setErrors(local);
        setReplyErrors(rep);
        const first = Object.keys(rep)[0];
        if (first) setOpen(Number(first.split(".")[0]));
        setServerErr({ message: err.body.message ?? "Some fields need fixing.", details: err.body.details });
      } else {
        setServerErr({ message: describeError(err, "create the bot"), details: [] });
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
    <div className="wrap page fade">
      <div className="page-head">
        <div>
          <h1 className="h1">New bot</h1>
          <p>Every narrative starts with a ready-made reply in Russian. Edit any of them, or clear one to skip that narrative.</p>
        </div>
      </div>

      {taxErr && (
        <div className="alert" role="alert" style={{ marginBottom: 24 }}>
          <b>{taxErr}</b>{" "}
          <button className="linkbtn" type="button" onClick={loadTax}>
            Try again
          </button>
        </div>
      )}

      <form className="builder" onSubmit={submit} noValidate>
        <div className="stack" style={{ gap: 32 }}>
          <div ref={summaryRef} tabIndex={-1}>
            {showSummary && (
              <div className="alert" role="alert">
                <b>{serverErr ? serverErr.message : `${localList.length} ${localList.length === 1 ? "problem" : "problems"} to fix before creating the bot`}</b>
                <ul>
                  {localList.map(([f, issue]) => (
                    <li key={f}>
                      <button type="button" className="linkbtn" onClick={() => document.getElementById(f)?.focus()}>
                        {LABEL[f] ?? f}: {ISSUE[issue] ?? issue}
                      </button>
                    </li>
                  ))}
                  {serverErr?.details.filter((x) => !(x.field in LABEL)).map((x) => (
                    <li key={x.field + x.issue}>
                      {labelFor(x.field, sent)}: {ISSUE[x.issue] ?? x.issue}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <section className="panel" aria-labelledby="s-id">
            <div className="section-head">
              <h2 className="h2" id="s-id">1. Identity</h2>
              <p>How the bot appears in Telegram.</p>
            </div>
            <div className="stack-sm" style={{ gap: 20 }}>
              <div className="grid2">
                <Field id="display_name" label="Display name" error={errors.display_name}>
                  <input type="text" id="display_name" value={d.display_name} maxLength={LIM.name} onChange={(e) => set("display_name", e.target.value)} aria-invalid={!!errors.display_name} aria-describedby="display_name-e" />
                </Field>
                <Field id="username" label="Username" error={errors.username} hint="Must end in “bot”. This is a suggestion: Telegram lets you pick another name when you confirm.">
                  <div className="at">
                    <span aria-hidden="true">@</span>
                    <input type="text" id="username" value={d.username} maxLength={32} autoComplete="off" spellCheck={false} onChange={(e) => set("username", e.target.value)} aria-invalid={!!errors.username} aria-describedby="username-h username-e" />
                  </div>
                </Field>
              </div>
              <Field id="short_description" label="Short description (optional)" error={errors.short_description} hint="Shown on the bot’s profile and in shared links.">
                <Area id="short_description" value={d.short_description} max={LIM.short} rows={2} onChange={(v) => set("short_description", v)} />
              </Field>
              <Field id="description" label="Description (optional)" error={errors.description} hint="Shown in the empty chat before someone presses Start.">
                <Area id="description" value={d.description} max={LIM.desc} onChange={(v) => set("description", v)} />
              </Field>
            </div>
          </section>

          <section aria-labelledby="s-rep">
            <div className="section-head">
              <h2 className="h2" id="s-rep">2. Replies by narrative</h2>
              <p>Open a narrative to write its reply. Leave it empty to skip it.</p>
            </div>
            {tax ? (
              <div className="acc">
                {tax.narratives.map((n, ni) => {
                  const isOpen = open === ni;
                  const c = count(ni);
                  return (
                    <div className="acc-item" key={n.name} id={`narr-${ni}`}>
                      <button type="button" className="acc-btn" aria-expanded={isOpen} aria-controls={`narr-body-${ni}`} onClick={() => setOpen(isOpen ? null : ni)}>
                        <span className="acc-chev" aria-hidden="true">›</span>
                        <span className="acc-name">{n.name}</span>
                        <span className={"chip" + (c ? " on" : "")}>{c ? `${c} ${c === 1 ? "reply" : "replies"}` : "No reply"}</span>
                      </button>
                      {isOpen && (
                        <div className="acc-body" id={`narr-body-${ni}`}>
                          <Field id={`r-${ni}`} label="Reply for the whole narrative" error={replyErrors[String(ni)]}>
                            <Area id={`r-${ni}`} value={d.replies[ni] ?? ""} max={LIM.msg} placeholder="Write the reply in your audience’s language" onChange={(v) => setReply(String(ni), v)} />
                          </Field>
                          {n.subnarratives.length ? (
                            <div className="stack-sm">
                              <p className="small muted">A sub-narrative reply replaces the narrative reply for that sub-narrative only.</p>
                              {n.subnarratives.map((s, si) => {
                                const key = `${ni}.${si}`;
                                const on = d.subs.includes(key);
                                return (
                                  <div key={key} className="stack-sm">
                                    <div className="subrow">
                                      <span>{s}</span>
                                      <button type="button" className="btn sm" aria-expanded={on} onClick={() => toggleSub(key)}>
                                        {on ? "Remove" : "Add reply"}
                                      </button>
                                    </div>
                                    {on && (
                                      <Field id={`r-${ni}-${si}`} label={`Reply for “${s}”`} error={replyErrors[key]}>
                                        <Area id={`r-${ni}-${si}`} value={d.replies[key] ?? ""} max={LIM.msg} rows={2} onChange={(v) => setReply(key, v)} />
                                      </Field>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <p className="small muted">This narrative has no sub-narratives, so it can only be answered at narrative level.</p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="muted">{taxErr ? "" : "Loading the narrative list…"}</p>
            )}
          </section>

          <section className="panel" aria-labelledby="s-set">
            <div className="section-head">
              <h2 className="h2" id="s-set">3. Behavior</h2>
              <p>The bot replies only when the classifier’s score reaches your threshold.</p>
            </div>
            <div className="stack-sm" style={{ gap: 20 }}>
              <div className="field">
                <label htmlFor="thr">Confidence threshold</label>
                <div className="row" style={{ flexWrap: "nowrap" }}>
                  <input id="thr" type="range" min={0} max={1} step={0.05} value={d.confidence_threshold} onChange={(e) => set("confidence_threshold", +e.target.value)} aria-describedby="thr-h" />
                  <output htmlFor="thr" className="mono num" style={{ minWidth: "3.4ch", textAlign: "right", fontWeight: 600 }}>
                    {d.confidence_threshold.toFixed(2)}
                  </output>
                </div>
                <div className="hint" id="thr-h">Higher means fewer replies and fewer wrong ones. 0.60 is a sensible start.</div>
              </div>
              <Field id="other_response" label="Reply when nothing matches" error={errors.other_response} hint="Also sent when a match has no reply written for it.">
                <Area id="other_response" value={d.other_response} max={LIM.msg} rows={2} onChange={(v) => set("other_response", v)} />
              </Field>
              <details className="more">
                <summary>More messages</summary>
                <div className="stack-sm" style={{ gap: 20, marginTop: 8 }}>
                  <Field id="start_message" label="Greeting after Start" error={errors.start_message}>
                    <Area id="start_message" value={d.start_message} max={LIM.msg} rows={2} onChange={(v) => set("start_message", v)} />
                  </Field>
                  <div className="grid2">
                    <Field id="non_text_message" label="Reply to photos and files" error={errors.non_text_message}>
                      <Area id="non_text_message" value={d.non_text_message} max={LIM.msg} onChange={(v) => set("non_text_message", v)} />
                    </Field>
                    <Field id="error_message" label="Reply when checking fails" error={errors.error_message}>
                      <Area id="error_message" value={d.error_message} max={LIM.msg} onChange={(v) => set("error_message", v)} />
                    </Field>
                  </div>
                </div>
              </details>
            </div>
          </section>

          <div>
            <div className="row">
              <button className="btn primary" type="submit" disabled={busy || !tax}>
                {busy ? "Creating…" : "Create bot"}
              </button>
              <button className="btn" type="button" onClick={() => { setD(tax ? withDefaults(example(), tax) : example()); setErrors({}); setServerErr(null); }}>
                Reset to example
              </button>
            </div>
            <p className="small muted" style={{ marginTop: 12 }}>
              Settings can’t be edited after creation. To change a reply, create a new bot and delete the old one.
              {IS_MOCK && " This build uses sample data; nothing is sent to a server."}
            </p>
          </div>
        </div>

        <aside className="panel sticky stack-sm" aria-label="Reply preview">
          <h2 className="h2">Preview a reply</h2>
          <div className="field">
            <label htmlFor="pv">If the classifier finds</label>
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
          <p className="bubble" aria-live="polite">{preview}</p>
          <p className="small muted">
            {why} Matches scoring under <span className="mono num">{d.confidence_threshold.toFixed(2)}</span> are ignored.
          </p>
        </aside>
      </form>
    </div>
  );
}
