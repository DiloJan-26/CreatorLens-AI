import type { Metadata } from "next";
import { AppNavbar } from "@/components/AppNavbar";
import "./globals.css";

export const metadata: Metadata = {
  title: "CreatorLens AI",
  description: "Compare Shorts and Reels with cited creator intelligence.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full flex flex-col">
        <ThemeScript />
        <AppNavbar />
        {children}
      </body>
    </html>
  );
}

function ThemeScript() {
  const script = `
    (function () {
      try {
        var storedTheme = localStorage.getItem('creatorlens_theme');
        var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        var theme = storedTheme === 'dark' || storedTheme === 'light'
          ? storedTheme
          : prefersDark ? 'dark' : 'light';
        document.documentElement.classList.toggle('dark', theme === 'dark');
      } catch (error) {}
    })();
  `;

  return <script dangerouslySetInnerHTML={{ __html: script }} />;
}
