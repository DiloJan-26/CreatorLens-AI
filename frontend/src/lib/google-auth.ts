import { browserAuth } from "@/lib/supabase/browser";

let redirectPending=false;
/** A user-initiated OAuth redirect; registration and return sign-in share this path. */
export async function startGoogleSignIn() {
  if(redirectPending)return;
  redirectPending=true;
  try {
    const origin=process.env.NEXT_PUBLIC_SITE_URL??(process.env.NODE_ENV==="development"?"http://localhost:3000":"");
    if(!origin || new URL(origin).origin!==origin || origin!==window.location.origin)throw new Error("The trusted sign-in origin is not configured for this site.");
    const {error}=await browserAuth().auth.signInWithOAuth({provider:"google",options:{redirectTo:origin+"/auth/callback",scopes:"openid email profile",queryParams:{prompt:"select_account"}}});
    if(error)throw new Error("Google sign-in could not be started. Please try again.");
  } catch(error) {
    redirectPending=false;
    throw error;
  }
}
