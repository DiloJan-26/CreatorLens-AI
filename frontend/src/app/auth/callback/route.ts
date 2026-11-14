import { NextRequest,NextResponse } from "next/server";
import { serverAuth,siteOrigin } from "@/lib/supabase/server";
export async function GET(request:NextRequest) {
  let origin:string;
  try { origin=siteOrigin(); } catch { return new NextResponse("Authentication configuration is incomplete.",{status:503}); }
  const code=request.nextUrl.searchParams.get("code");
  if (code && !request.nextUrl.searchParams.has("error")) {
    const supabase=await serverAuth();
    const {error}=await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(origin+"/workspace",{headers:{"Cache-Control":"private, no-store"}});
  }
  return NextResponse.redirect(origin+"/login?error=oauth",{headers:{"Cache-Control":"private, no-store"}});
}
