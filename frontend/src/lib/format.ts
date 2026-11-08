export const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) + " UTC";

export const clock = (iso: string, now = Date.now()) => {
  const s = Math.max(0, Math.floor((Date.parse(iso) - now) / 1000));
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
};

export const cap = (s: string) => s[0].toUpperCase() + s.slice(1);
