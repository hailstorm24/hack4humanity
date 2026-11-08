import type { Metadata, Viewport } from "next";
import { Geologica, Onest } from "next/font/google";
import "./globals.css";
import { Masthead } from "@/components/Masthead";
import { ToastHost } from "@/components/Toast";
import { WakingBanner } from "@/components/WakingBanner";

const display = Geologica({ variable: "--font-display", subsets: ["latin", "cyrillic"], display: "swap" });
const text = Onest({ variable: "--font-text", subsets: ["latin", "cyrillic"], display: "swap" });

export const metadata: Metadata = {
  title: "Narrative Bots",
  description: "Build a Telegram bot that recognizes propaganda narratives and answers with the replies you wrote.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning className={`${display.variable} ${text.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: "try{var t=localStorage.getItem('nb-theme');if(t)document.documentElement.dataset.theme=t}catch(e){}" }} />
      </head>
      <body suppressHydrationWarning>
        <a className="skip-link" href="#main">Skip to content</a>
        <Masthead />
        <WakingBanner />
        <main id="main">{children}</main>
        <footer className="foot">
          <div className="wrap">
            <span>Narrative taxonomy: SemEval 2025 Task 10</span>
            <span>Hack4Humanity prototype</span>
          </div>
        </footer>
        <ToastHost />
      </body>
    </html>
  );
}
