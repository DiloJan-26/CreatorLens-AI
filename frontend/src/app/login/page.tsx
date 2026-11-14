import { GoogleSignIn } from "@/components/GoogleSignIn";
export default async function Login({searchParams}:{searchParams:Promise<{error?:string}>}){
  const query=await searchParams;
  return <main className="page-container">{query.error&&<p role="alert" className="mx-auto max-w-lg mb-4">Google sign-in could not be completed. Try again; no workspace session was established by this callback.</p>}<GoogleSignIn/></main>;
}
