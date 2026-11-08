"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

const APP_LINKS = [
  { href: "/bots", label: "My bots" },
  { href: "/new", label: "New bot" },
];
const HOME_LINKS = [
  { href: "/#idea", label: "The idea" },
  { href: "/#moments", label: "Moments" },
  { href: "/bots", label: "My bots" },
];

const MQ = "(prefers-color-scheme: dark)";
const subscribe = (cb: () => void) => {
  const mq = window.matchMedia(MQ);
  window.addEventListener("nb-theme", cb);
  mq.addEventListener("change", cb);
  return () => {
    window.removeEventListener("nb-theme", cb);
    mq.removeEventListener("change", cb);
  };
};
const snapshot = () => {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : window.matchMedia(MQ).matches;
};

function ThemeToggle() {
  const dark = useSyncExternalStore(subscribe, snapshot, () => true);
  const flip = () => {
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("nb-theme", next);
    } catch {}
    window.dispatchEvent(new Event("nb-theme"));
  };
  return (
    <button type="button" className="iconbtn" onClick={flip} aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}>
      {dark ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
        </svg>
      )}
    </button>
  );
}

export function Masthead() {
  const path = usePathname();
  const links = path === "/" ? HOME_LINKS : APP_LINKS;
  return (
    <header className="top">
      <div className="wrap">
        <Link href="/" className="brand">
          Narrative Bots
        </Link>
        <nav aria-label="Main">
          {links.map((l) => (
            <Link key={l.href} href={l.href} aria-current={l.href.startsWith("/#") ? undefined : path === l.href || path.startsWith(l.href + "/") ? "page" : undefined}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="tools">
          <ThemeToggle />
          {path !== "/new" && (
            <Link href="/new" className="btn primary">
              Create a bot
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
