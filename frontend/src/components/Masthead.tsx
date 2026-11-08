"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/bots", label: "My bots" },
  { href: "/new", label: "New bot" },
];

export function Masthead() {
  const path = usePathname();
  return (
    <header className="mast">
      <div className="mast-top">
        <span>Telegram bots for Russian-language narratives</span>
        <span>taxonomy semeval2025-t10-urw</span>
      </div>
      <div className="mast-bar">
        <Link href="/" className="wordmark">
          Narrative&nbsp;<i>Bots</i>
        </Link>
        <nav aria-label="Main">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} aria-current={path === l.href || path.startsWith(l.href + "/") ? "page" : undefined}>
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
