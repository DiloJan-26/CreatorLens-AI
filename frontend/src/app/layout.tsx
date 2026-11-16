import type { Metadata } from "next";
import localFont from "next/font/local";
import { AccountProvider } from "@/components/AccountProvider";
import { AppNavbar } from "@/components/AppNavbar";
import "./globals.css";
const geist = localFont({
  src: "../../node_modules/next/dist/next-devtools/server/font/geist-latin.woff2",
  variable: "--font-geist",
  display: "swap",
});

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
    <html lang="en" className="h-full antialiased">
      <body className={`${geist.variable} min-h-full`}>
        <AccountProvider><AppNavbar>{children}</AppNavbar></AccountProvider>
      </body>
    </html>
  );
}
