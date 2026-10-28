import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QueryChat",
  description: "Chat with any database",
};

// Runs before paint so a saved or system dark preference never flashes light.
const THEME_SCRIPT = `try{var t=localStorage.getItem("querychat-theme");if(!t){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
