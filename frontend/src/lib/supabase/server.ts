import "server-only";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
export async function serverAuth() {
  const store = await cookies();
  const url=process.env.NEXT_PUBLIC_SUPABASE_URL, key=process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) throw new Error("Authentication is not configured.");
  return createServerClient(url,key,{cookies:{getAll:()=>store.getAll(),setAll(values){
    for (const {name,value,options} of values) store.set(name,value,{...options,sameSite:"lax",secure:process.env.NODE_ENV==="production"});
  }}});
}
export function siteOrigin() {
  const origin=process.env.NEXT_PUBLIC_SITE_URL ?? (process.env.NODE_ENV==="development" ? "http://localhost:3000" : "");
  if (!origin) throw new Error("The trusted site origin is missing.");
  const url=new URL(origin);
  if (url.origin !== origin || url.protocol!=="https:" && !(process.env.NODE_ENV==="development" && url.hostname==="localhost")) throw new Error("Invalid trusted site origin.");
  return origin;
}
