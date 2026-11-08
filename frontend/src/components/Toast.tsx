"use client";
import { useEffect, useRef, useState } from "react";

export function toast(message: string) {
  window.dispatchEvent(new CustomEvent("nb-toast", { detail: message }));
}

export function ToastHost() {
  const [msg, setMsg] = useState("");
  const [on, setOn] = useState(false);
  const t = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => {
    const h = (e: Event) => {
      setMsg((e as CustomEvent<string>).detail);
      setOn(true);
      clearTimeout(t.current);
      t.current = setTimeout(() => setOn(false), 2800);
    };
    window.addEventListener("nb-toast", h);
    return () => window.removeEventListener("nb-toast", h);
  }, []);
  return (
    <div className={"toast" + (on ? " on" : "")} role="status" aria-live="polite">
      {msg}
    </div>
  );
}

export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copied");
  } catch {
    toast("Copy was blocked. Select the text and copy it.");
  }
}
