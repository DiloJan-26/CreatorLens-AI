"use client";
import Link from "next/link";
import type { ReactNode } from "react";
import { useAccount } from "./AccountProvider";
import { GoogleSignInButton } from "./GoogleSignIn";

export function WorkspaceEntry({children, signedInLabel, className="button-primary", href="/workspace"}: {
  children: ReactNode;
  signedInLabel?: ReactNode;
  className?: string;
  href?: string;
}) {
  const {account, loading} = useAccount();
  if (account) return <Link className={className} href={href}>{signedInLabel ?? children}</Link>;
  return <GoogleSignInButton className={className} disabled={loading}>{loading ? "Restoring session..." : children}</GoogleSignInButton>;
}
