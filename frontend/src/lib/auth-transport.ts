import { authEnabled,browserAuth } from "./supabase/browser";
import { clearAccountWorkspace } from "./app-session";
export class ApiError extends Error { constructor(public status:number,message:string,public retryAfter:string|null=null){super(message);} }
export async function authorizedHeaders(init?:HeadersInit) {
  const headers=new Headers(init);
  if(authEnabled()) {
    // Session supplies only the transport credential. FastAPI verifies identity and ownership.
    const {data,error}=await browserAuth().auth.getSession();
    if(error || !data.session?.access_token) throw new ApiError(401,"Sign in with Google to continue.");
    headers.set("Authorization",`Bearer ${data.session.access_token}`);
  }
  return headers;
}
export function sessionExpired() {
  clearAccountWorkspace();
  if(typeof window!=="undefined") window.dispatchEvent(new Event("creatorlens_session_expired"));
}
