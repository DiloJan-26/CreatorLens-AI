"use client";
import { AccountMenu,useAccount } from "./AccountProvider";
import { GoogleSignIn } from "./GoogleSignIn";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Dialog, Icon } from "./ui";
const creatorLinks = [
  { href: "/analyze", label: "Compare", icon: "compare" },
  { href: "/analyze#insights", label: "Insights", icon: "chart" },
  { href: "/analyze#evidence", label: "Evidence", icon: "evidence" },
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
  const { enabled,account } = useAccount();
  const [drawer, setDrawer] = useState(false);
  const [auth, setAuth] = useState(false);
  const [section, setSection] = useState("");
  useEffect(() => {
    const sync = () => setSection(window.location.hash);
    const timer = window.setTimeout(sync, 0);
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, [pathname]);
  const isCurrent = (href: string) => {
    if (href.includes("#"))
      return (
        pathname === "/analyze" && section === href.slice(href.indexOf("#"))
      );
    return (
      pathname === href &&
      !(href === "/analyze" && ["#insights", "#evidence"].includes(section))
    );
  };
  const publicPage = pathname === "/" || pathname === "/login" || pathname.startsWith("/auth/");
  const homeLink = (
    <Link
      href="/"
      className="rail-link rail-home"
      aria-current={publicPage ? "page" : undefined}
      onClick={() => setDrawer(false)}
    >
      <Icon name="home" /> Home
    </Link>
  );
  const navigation = (
    <nav aria-label="Workspace navigation">
      {enabled&&<Link href="/workspace" className="rail-link">Your analyses</Link>}
      <p className="nav-group-label">Workspace</p>
      {creatorLinks.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className="rail-link"
          aria-current={isCurrent(l.href) ? "page" : undefined}
          onClick={(event) => {
            setDrawer(false);
            if (
              pathname === "/analyze" &&
              l.href.startsWith("/analyze") &&
              !event.ctrlKey &&
              !event.metaKey &&
              !event.shiftKey &&
              !event.altKey
            ) {
              event.preventDefault();
              window.history.pushState(null, "", l.href);
              window.dispatchEvent(new HashChangeEvent("hashchange"));
            }
          }}
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
    </nav>
  );
  const active = [...creatorLinks, ...engineerLinks].find((l) =>
    isCurrent(l.href),
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
                {account ? "Your account" : "Sign in"}
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
            {homeLink}
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
              <AccountMenu />
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
        <div className="drawer-navigation">
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
                {account ? "Your account" : "Sign in"}
              </button>
              <Link
                href="/analyze"
                className="button-primary"
                onClick={() => setDrawer(false)}
              >
                {enabled ? "Open workspace" : "Explore demo"}
              </Link>
            </div>
          )}
          {homeLink}
        </div>
      </Dialog>
      <Dialog
        open={auth}
        onClose={() => setAuth(false)}
        title={enabled ? "Sign in to CreatorLens" : "Restricted demonstration"}
      >
        {enabled ? (account ? <AccountMenu/> : <GoogleSignIn/>) : <>
        <p className="muted">
          CreatorLens is currently a restricted demonstration. No account is
          required for the isolated local experience. Public project access and
          provider generation are disabled by default.
        </p>
        <Link
          href="/analyze"
          className="button-primary mt-6"
          onClick={() => setAuth(false)}
        >
          Continue to demo <Icon name="arrow" size={16} />
        </Link>
        </>}
      </Dialog>
    </>
  );
}
