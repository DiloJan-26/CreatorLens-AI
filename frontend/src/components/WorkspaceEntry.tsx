"use client";
import Link from "next/link";
import type { ReactNode } from "react";
import { useAccount } from "./AccountProvider";
import { GoogleSignInButton } from "./GoogleSignIn";

export function WorkspaceEntry({children,className="button-primary",href="/workspace"}:{children:ReactNode;className?:string;href?:string}){
  const {account,loading}=useAccount();
  return account?<Link className={className} href={href}>{children}</Link>:<GoogleSignInButton className={className} disabled={loading}>{children}</GoogleSignInButton>;
}
