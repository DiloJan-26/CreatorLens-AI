"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import {
  getActiveProjectId,
  subscribeToActiveProject,
} from "@/lib/app-session";

import { AiReasoningStatus } from "./AiReasoningStatus";
import { ThemeToggle } from "./ThemeToggle";

export function AppNavbar() {
  const pathname = usePathname();
  const [latestProjectId, setLatestProjectId] = useState(() =>
    getActiveProjectId(),
  );
  const navLinks = [
    { label: "Home", href: "/" },
    { label: "Analyze", href: "/analyze" },
    { label: "Insights", href: "/analyze#insights" },
    { label: "Chat", href: "/chat" },
    { label: "Evidence", href: "/analyze#evidence" },
  ];

  useEffect(() => {
    return subscribeToActiveProject(setLatestProjectId);
  }, []);

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/85 shadow-sm shadow-slate-950/[0.03] backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950/85 dark:shadow-black/20">
      <div className="mx-auto flex h-[76px] max-w-7xl items-center justify-between gap-4 px-6 sm:px-8 lg:px-10">
        <Link href="/" className="flex shrink-0 items-center gap-2 text-base font-semibold text-slate-950 dark:text-slate-50">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-slate-950 text-xs font-bold text-white shadow-sm dark:bg-teal-400 dark:text-slate-950">
            CL
          </span>
          <span>CreatorLens AI</span>
        </Link>

        <nav className="hidden items-center gap-1 rounded-full border border-slate-200 bg-slate-50 p-1 text-sm font-medium text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 md:flex">
          {navLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className={`rounded-full px-3 py-1.5 transition hover:bg-white hover:text-slate-950 dark:hover:bg-slate-800 dark:hover:text-white ${
                isActive(pathname, link.href)
                  ? "bg-white text-slate-950 shadow-sm dark:bg-slate-800 dark:text-white"
                  : ""
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <AiReasoningStatus />
          <ThemeToggle />
          <Link
            href={latestProjectId ? "/analyze" : "/analyze?new=1"}
            className="hidden h-10 items-center justify-center rounded-full bg-slate-950 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 dark:bg-teal-400 dark:text-slate-950 dark:hover:bg-teal-300 sm:inline-flex"
          >
            Start Analysis
          </Link>
        </div>
      </div>
    </header>
  );
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }

  return href.startsWith(pathname) && pathname !== "/";
}
