import { Suspense } from "react";

import { CreatorChatPage } from "@/components/CreatorChatPage";

export default function ChatPage() {
  return (
    <Suspense fallback={<ChatLoading />}>
      <CreatorChatPage />
    </Suspense>
  );
}

function ChatLoading() {
  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12 text-slate-950 dark:bg-slate-950 dark:text-slate-50">
      <p className="mx-auto max-w-7xl rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-100">
        Loading CreatorLens AI chat...
      </p>
    </main>
  );
}
