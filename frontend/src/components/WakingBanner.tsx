"use client";
import { useEffect, useState } from "react";

// Shown while a request to the hosted API takes more than a few seconds (cold start).
export function WakingBanner() {
  const [waking, setWaking] = useState(false);
  useEffect(() => {
    const h = (e: Event) => setWaking((e as CustomEvent<boolean>).detail);
    window.addEventListener("nb-waking", h);
    return () => window.removeEventListener("nb-waking", h);
  }, []);
  if (!waking) return null;
  return (
    <div className="waking" role="status">
      <span className="pulse" aria-hidden="true" /> Waking the server… the first request can take up to a minute.
    </div>
  );
}
