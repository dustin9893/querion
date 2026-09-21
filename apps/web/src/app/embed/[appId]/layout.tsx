import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Trợ lý",
  robots: { index: false, follow: false },
};

/** The embed route renders inside a third-party iframe: no shell, no admin providers. */
export default function EmbedLayout({ children }: { children: React.ReactNode }) {
  return <div style={{ height: "100vh", overflow: "hidden" }}>{children}</div>;
}
