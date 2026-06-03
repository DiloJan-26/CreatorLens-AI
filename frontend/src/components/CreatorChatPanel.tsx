"use client";

import { FormEvent, useState } from "react";

import { streamChatResponse } from "@/lib/api";
import type { ChatCitation, ChatMessage } from "@/types/project";

const SUGGESTED_QUESTIONS = [
  "What is the engagement rate of each content item?",
  "Compare the hooks in the first 5 seconds.",
  "Which content has stronger confirmed public engagement?",
  "What metadata is missing or unavailable?",
  "Suggest improvements for Content 2 based on Content 1.",
];

type CreatorChatPanelProps = {
  projectId: string | null;
  indexReady: boolean;
};

export function CreatorChatPanel({
  projectId,
  indexReady,
}: CreatorChatPanelProps) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentAssistantText, setCurrentAssistantText] = useState("");
  const [currentCitations, setCurrentCitations] = useState<ChatCitation[]>([]);
  const canChat = Boolean(projectId && indexReady);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!projectId) {
      setError("Analyze videos before starting the chat.");
      return;
    }

    if (!indexReady) {
      setError("Build the search index before starting the cited chat.");
      return;
    }

    const question = input.trim();

    if (!question || isStreaming) {
      return;
    }

    setInput("");
    setError(null);
    setIsStreaming(true);
    setCurrentAssistantText("");
    setCurrentCitations([]);
    setMessages((previousMessages) => [
      ...previousMessages,
      {
        role: "user",
        content: question,
      },
      {
        role: "assistant",
        content: "",
        citations: [],
      },
    ]);

    try {
      await streamChatResponse(
        projectId,
        {
          message: question,
          session_id: sessionId,
        },
        {
          onSession: setSessionId,
          onToken: (text) => {
            setCurrentAssistantText((currentText) => currentText + text);
            setMessages((previousMessages) =>
              updateLastAssistantMessage(previousMessages, {
                appendText: text,
              }),
            );
          },
          onCitations: (citations) => {
            setCurrentCitations(citations);
            setMessages((previousMessages) =>
              updateLastAssistantMessage(previousMessages, {
                citations,
              }),
            );
          },
          onError: (message) => {
            setError(message);
          },
        },
      );
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setIsStreaming(false);
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            Cited Creator Insights
          </p>
          <h2 className="mt-2 text-base font-semibold text-slate-950">
            Streaming Creator Chat
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Ask performance, hook, and improvement questions grounded in
            retrieved sources from both content items.
          </p>
        </div>
        {sessionId ? (
          <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-medium text-slate-600">
            Memory-aware chat
          </span>
        ) : null}
      </div>

      {!projectId ? (
        <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          Analyze videos before starting the chat.
        </p>
      ) : !indexReady ? (
        <p className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Build the search index before starting the cited chat.
        </p>
      ) : null}

      <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-600">
        Metric and follower questions use confirmed public metrics first to
        avoid estimating unavailable values.
      </p>

      <div className="mt-5 flex flex-wrap gap-2">
        {SUGGESTED_QUESTIONS.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => setInput(question)}
            disabled={!canChat || isStreaming}
            className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs font-medium text-slate-700 transition hover:border-teal-300 hover:bg-teal-50 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
          >
            {question}
          </button>
        ))}
      </div>

      <div className="mt-5 grid max-h-[520px] gap-3 overflow-y-auto rounded-md border border-slate-200 bg-slate-50 p-3">
        {messages.length === 0 ? (
          <p className="rounded-md border border-slate-200 bg-white px-3 py-3 text-sm leading-6 text-slate-600">
            Answers are grounded in retrieved sources and extracted metadata.
            Unavailable public metrics are not estimated.
          </p>
        ) : (
          messages.map((message, index) => (
            <ChatMessageBubble
              key={`${message.role}-${index}`}
              message={message}
              isStreaming={isStreaming && index === messages.length - 1}
            />
          ))
        )}
      </div>

      {currentAssistantText && isStreaming ? (
        <p className="mt-3 text-xs text-slate-500">
          Streaming response... {currentCitations.length} sources ready
        </p>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {error}
        </p>
      ) : null}

      <form onSubmit={handleSubmit} className="mt-4 grid gap-3">
        <label className="text-sm font-medium text-slate-900">
          Ask a question
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            disabled={!canChat || isStreaming}
            rows={3}
            className="mt-2 w-full resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm leading-6 text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-teal-600 focus:ring-2 focus:ring-teal-100 disabled:cursor-not-allowed disabled:bg-slate-100"
            placeholder="Ask about performance, hooks, story, or improvements."
          />
        </label>
        <button
          type="submit"
          disabled={!canChat || isStreaming || !input.trim()}
          className="inline-flex h-10 w-fit items-center justify-center rounded-md bg-teal-700 px-4 text-sm font-medium text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {isStreaming ? "Streaming..." : "Send"}
        </button>
      </form>
    </section>
  );
}

function ChatMessageBubble({
  message,
  isStreaming,
}: {
  message: ChatMessage;
  isStreaming: boolean;
}) {
  const isUser = message.role === "user";

  return (
    <article
      className={`rounded-md border px-3 py-3 ${
        isUser
          ? "ml-auto max-w-[86%] border-teal-200 bg-teal-50"
          : "mr-auto max-w-[92%] border-slate-200 bg-white"
      }`}
    >
      <p className="text-xs font-semibold uppercase text-slate-500">
        {isUser ? "You" : "CreatorLens AI"}
      </p>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-800">
        {message.content || (isStreaming ? "Thinking..." : "")}
      </p>
      {!isUser && message.citations && message.citations.length > 0 ? (
        <CitationList citations={message.citations} />
      ) : null}
    </article>
  );
}

function CitationList({ citations }: { citations: ChatCitation[] }) {
  return (
    <div className="mt-4 border-t border-slate-200 pt-3">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
        Sources
      </p>
      <ol className="mt-2 grid gap-2">
        {citations.map((citation, index) => (
          <li
            key={`${citation.citation_label}-${index}`}
            className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
          >
            <p className="text-sm font-semibold text-slate-900">
              {index + 1}. {citation.citation_label}
            </p>
            <p className="mt-1 text-xs font-medium uppercase text-slate-500">
              {platformLabel(citation.platform)} /{" "}
              {sourceTypeLabel(citation.source_type)}
              {typeof citation.score === "number"
                ? ` / ${citation.score.toFixed(4)}`
                : ""}
            </p>
            <p className="mt-2 line-clamp-4 whitespace-pre-wrap text-sm leading-6 text-slate-700">
              {citation.text}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}

function updateLastAssistantMessage(
  messages: ChatMessage[],
  update: {
    appendText?: string;
    citations?: ChatCitation[];
  },
): ChatMessage[] {
  const nextMessages = [...messages];

  for (let index = nextMessages.length - 1; index >= 0; index -= 1) {
    const message = nextMessages[index];

    if (message.role !== "assistant") {
      continue;
    }

    nextMessages[index] = {
      ...message,
      content: `${message.content}${update.appendText ?? ""}`,
      citations: update.citations ?? message.citations,
    };
    break;
  }

  return nextMessages;
}

function platformLabel(platform: string): string {
  const normalizedPlatform = platform.toLowerCase();

  if (normalizedPlatform === "youtube") {
    return "YouTube";
  }

  if (normalizedPlatform === "instagram") {
    return "Instagram";
  }

  if (normalizedPlatform === "facebook") {
    return "Facebook";
  }

  return platform;
}

function sourceTypeLabel(sourceType: string): string {
  if (sourceType === "metadata") {
    return "Metadata";
  }

  if (sourceType === "description") {
    return "Description/Caption";
  }

  if (sourceType === "hook") {
    return "Hook";
  }

  if (sourceType === "transcript") {
    return "Transcript";
  }

  return sourceType;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Could not stream chat response.";
}
