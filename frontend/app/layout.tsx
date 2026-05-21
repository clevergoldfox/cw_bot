import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Job Watcher",
  description: "Real-time Crowdworks & Lancers new-assignment feed",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
