"use client";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { Dialog, Icon } from "./ui";
const creatorLinks = [
  { href: "/analyze", label: "Compare videos", icon: "compare" },
  { href: "/chat", label: "AI Assistant", icon: "chat" },
];
const engineerLinks = [
  { href: "/evaluations", label: "RAG Evaluation", icon: "shield" },
  { href: "/dashboard", label: "LLM Observability", icon: "chart" },
];
function Brand() {
  return (
    <Link href="/" className="brand" aria-label="CreatorLens AI home">
      <Image
        src="/Logo/Logo.png"
        alt=""
        width={33}
        height={33}
        className="brand-mark"
        priority
      />
      <span>
        CreatorLens<span className="brand-ai"> AI</span>
      </span>
    </Link>
  );
}
export function AppNavbar({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [drawer, setDrawer] = useState(false);
  const [auth, setAuth] = useState(false);
  const publicPage = pathname === "/";
  const navigation = (
    <nav aria-label="Workspace navigation">
      <p className="nav-group-label">Creator workspace</p>
      {creatorLinks.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className="rail-link"
          aria-current={pathname === l.href ? "page" : undefined}
          onClick={() => setDrawer(false)}
        >
          <Icon name={l.icon} />
          {l.label}
        </Link>
      ))}
      <p className="nav-group-label engineering-label">Engineering</p>
      {engineerLinks.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className="rail-link"
          aria-current={pathname === l.href ? "page" : undefined}
          onClick={() => setDrawer(false)}
        >
          <Icon name={l.icon} />
          {l.label}
        </Link>
      ))}
      <Link
        className="rail-link product-link"
        href="/"
        onClick={() => setDrawer(false)}
      >
        <Icon name="home" />
        About CreatorLens
      </Link>
    </nav>
  );
  const active = [...creatorLinks, ...engineerLinks].find(
    (l) => l.href === pathname,
  );
  return (
    <>
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      {publicPage ? (
        <header className="public-header">
          <div className="public-header-inner">
            <Brand />
            <nav className="public-links" aria-label="Public navigation">
              <Link href="/#product">Product</Link>
              <Link href="/#how-it-works">How it works</Link>
              <Link href="/#features">Features</Link>
              <Link href="/evaluations">Engineering</Link>
            </nav>
            <div className="header-actions">
              <button
                className="button-secondary public-signin"
                onClick={() => setAuth(true)}
              >
                Sign in
              </button>
              <Link className="button-primary public-demo" href="/analyze">
                Get started <Icon name="arrow" size={16} />
              </Link>
              <button
                className="icon-button public-menu"
                onClick={() => setDrawer(true)}
                aria-label="Open navigation"
                aria-expanded={drawer}
              >
                <Icon name="menu" />
              </button>
            </div>
          </div>
        </header>
      ) : (
        <>
          <aside className="application-rail">
            <Brand />
            {navigation}
            <div className="rail-footer">
              <span className="status-dot" />
              Demo workspace<p>Public evidence. No account required.</p>
            </div>
          </aside>
          <header className="workspace-header">
            <div className="flex items-center gap-3 min-w-0">
              <button
                className="icon-button workspace-menu"
                onClick={() => setDrawer(true)}
                aria-label="Open navigation"
                aria-expanded={drawer}
              >
                <Icon name="menu" />
              </button>
              <span className="breadcrumb-group">
                {pathname === "/evaluations" || pathname === "/dashboard"
                  ? "Engineering"
                  : "Workspace"}
              </span>
              <span className="muted" aria-hidden="true">
                /
              </span>
              <span className="truncate">{active?.label ?? "CreatorLens"}</span>
            </div>
            <div className="header-actions">
              <span className="demo-label">Demo mode</span>
            </div>
          </header>
        </>
      )}
      <div
        id="main-content"
        tabIndex={-1}
        className={publicPage ? "public-content" : "application-content"}
      >
        {children}
      </div>
      <Dialog
        open={drawer}
        onClose={() => setDrawer(false)}
        title="CreatorLens AI"
        drawer
      >
        {navigation}
        {publicPage && (
          <div className="drawer-actions">
            <button
              className="button-secondary"
              onClick={() => {
                setDrawer(false);
                setAuth(true);
              }}
            >
              Sign in
            </button>
            <Link
              href="/analyze"
              className="button-primary"
              onClick={() => setDrawer(false)}
            >
              Explore demo
            </Link>
          </div>
        )}
        <p className="muted text-sm mt-8">Demo mode · No sign-in required</p>
      </Dialog>
      <Dialog
        open={auth}
        onClose={() => setAuth(false)}
        title="Explore without an account"
      >
        <p className="muted">
          CreatorLens is currently an open demo. You can use the existing
          workspace without signing in.
        </p>
        <Link
          href="/analyze"
          className="button-primary mt-6"
          onClick={() => setAuth(false)}
        >
          Continue to demo <Icon name="arrow" size={16} />
        </Link>
      </Dialog>
    </>
  );
}
