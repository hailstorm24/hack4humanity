import type { Metadata, Viewport } from "next";
import { Golos_Text, IBM_Plex_Mono, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import { Masthead } from "@/components/Masthead";
import { ToastHost } from "@/components/Toast";

const serif = Source_Serif_4({ variable: "--font-serif", subsets: ["latin", "cyrillic"], style: ["normal", "italic"], display: "swap" });
const sans = Golos_Text({ variable: "--font-sans", subsets: ["latin", "cyrillic"], display: "swap" });
const mono = IBM_Plex_Mono({ variable: "--font-mono", subsets: ["latin", "cyrillic"], weight: ["400", "500"], display: "swap" });

export const metadata: Metadata = {
  title: "Narrative Bots",
  description: "Build a Telegram bot that recognizes propaganda narratives and answers with the replies you wrote.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable} ${mono.variable}`}>
      <body>
        <div className="page">
          <Masthead />
          <main id="main">{children}</main>
          <footer className="foot">
            <span>Narrative taxonomy: SemEval 2025 Task 10</span>
            <span>Hack4Humanity prototype</span>
          </footer>
        </div>
        <ToastHost />
      </body>
    </html>
  );
}
