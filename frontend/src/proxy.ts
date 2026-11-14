import { createServerClient } from "@supabase/ssr";
import { NextRequest, NextResponse } from "next/server";
export async function proxy(request: NextRequest) {
  if (process.env.APPLICATION_ACCESS_MODE!=="authenticated") return NextResponse.next();
  const url=process.env.NEXT_PUBLIC_SUPABASE_URL,key=process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key || process.env.NEXT_PUBLIC_APPLICATION_ACCESS_MODE!=="authenticated") return new NextResponse("Authentication configuration is incomplete.",{status:503});
  let origin:string;
  try {
    const configured=process.env.NEXT_PUBLIC_SITE_URL;
    if(!configured)throw new Error("Missing trusted origin");
    const parsed=new URL(configured);
    if(parsed.origin!==configured || parsed.protocol!=="https:" && !(process.env.NODE_ENV==="development" && parsed.hostname==="localhost"))throw new Error("Invalid trusted origin");
    origin=parsed.origin;
  } catch {return new NextResponse("The trusted site origin is not configured.",{status:503});}
  let response=NextResponse.next({request});
  const supabase=createServerClient(url,key,{cookies:{getAll:()=>request.cookies.getAll(),setAll(values){
    for (const {name,value} of values) request.cookies.set(name,value);
    response=NextResponse.next({request});
    for (const {name,value,options} of values) response.cookies.set(name,value,{...options,sameSite:"lax",secure:process.env.NODE_ENV==="production"});
  }}});
  const {data,error}=await supabase.auth.getClaims();
  if (error || !data?.claims) {
    const destination=new URL("/login",origin);
    const redirect=NextResponse.redirect(destination);
    for (const cookie of response.cookies.getAll()) redirect.cookies.set(cookie);
    redirect.headers.set("Cache-Control","private, no-store");return redirect;
  }
  response.headers.set("Cache-Control","private, no-store");
  return response;
}
export const config={matcher:["/analyze/:path*","/chat/:path*","/dashboard/:path*","/evaluations/:path*","/workspace/:path*"]};
