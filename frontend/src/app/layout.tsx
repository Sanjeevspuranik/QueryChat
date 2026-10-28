import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QueryChat",
  description: "Chat with any database",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
