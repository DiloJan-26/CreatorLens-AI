"use client";

import { FormEvent, useEffect, useState, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { StructuredAnswerCard } from "@/components/StructuredAnswerCard";
import { getChatHistory, streamChatResponse } from "@/lib/api";
import {
  clearChatSessionId,
  getChatDraft,
  getChatSessionId,
  setChatDraft,
  setChatSessionId,
} from "@/lib/app-session";
import type {
  ChatCitation,
  ChatMessage,
  StoredChatMessage,
  StructuredAnswerPayload,
} from "@/types/project";

const SUGGESTED_QUESTIONS = [
  "What is the engagement rate of each content item?",
  "Compare the hooks in the first 5 seconds.",
  "Give me the Creator Insight Summary.",
  "Which content has stronger confirmed public engagement?",
  "What metadata is missing?",
  "Suggest improvements for Content 2 based on Content 1.",
  "Rewrite the opening for Content 2.",
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
  const [isRestoringSession, setIsRestoringSession] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [, setCurrentAssistantText] = useState("");
  const [, setCurrentCitations] = useState<ChatCitation[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const followRef = useRef(true);
  const [showLatest, setShowLatest] = useState(false);
  useEffect(() => {
    if (followRef.current && scrollRef.current)
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, isStreaming]);
  const canChat = Boolean(projectId && indexReady && !isRestoringSession);

  useEffect(() => {
    let isActive = true;
    const restoreTimer = window.setTimeout(() => {
      setSessionId(null);
      setMessages([]);
      setCurrentAssistantText("");
      setCurrentCitations([]);
      setError(null);

      if (!projectId) {
        setInput("");
        setIsRestoringSession(false);
        return;
      }

      const restoredDraft = getChatDraft(projectId);
      const restoredSessionId = getChatSessionId(projectId);

      setInput(restoredDraft ?? "");

      if (!restoredSessionId) {
        setIsRestoringSession(false);
        return;
      }

      setIsRestoringSession(true);

      getChatHistory(projectId, restoredSessionId)
        .then((history) => {
          if (!isActive) {
            return;
          }

          setSessionId(history.session_id);
          setMessages(
            history.messages
              .filter((message) => message.role !== "system")
              .map(chatHistoryMessage),
          );
        })
        .catch(() => {
          if (!isActive) {
            return;
          }

          setError(
            "Previous messages could not be restored. A new conversation will start when you send a question.",
          );
          clearChatSessionId(projectId);
          setSessionId(null);
          setMessages([]);
        })
        .finally(() => {
          if (isActive) {
            setIsRestoringSession(false);
          }
        });
    }, 0);

    return () => {
      isActive = false;
      window.clearTimeout(restoreTimer);
    };
  }, [projectId]);

  useEffect(() => {
    if (!projectId) {
      return;
    }

    setChatDraft(projectId, input);
  }, [input, projectId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!projectId) {
      setError("Analyze content before starting the chat.");
      return;
    }

    if (!indexReady) {
      setError("The evidence index must be ready before starting cited chat.");
      return;
    }

    const question = input.trim();

    if (!question || isStreaming) {
      return;
    }

    followRef.current = true;
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

    let streamCompleted = false;
    try {
      await streamChatResponse(
        projectId,
        {
          message: question,
          session_id: sessionId,
        },
        {
          onDone: () => {
            streamCompleted = true;
          },
          onSession: (nextSessionId) => {
            setSessionId(nextSessionId);
            setChatSessionId(projectId, nextSessionId);
          },
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
          onStructuredAnswer: (structuredAnswer) => {
            setMessages((previousMessages) =>
              updateLastAssistantMessage(previousMessages, {
                structuredAnswer,
              }),
            );
          },
          onError: (message) => {
            setError(message);
          },
        },
      );
      if (!streamCompleted)
        setError(
          (current) =>
            current ??
            "The response ended before completion. Review the partial answer or retry.",
        );
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setIsStreaming(false);
    }
  }

  return (
    <section className="chat-panel" aria-label="Evidence-grounded conversation">
      <div className="chat-top">
        <span className="font-semibold">CreatorLens AI</span>
        <span className="muted text-xs">
          {isStreaming
            ? "Responding..."
            : sessionId
              ? "Current session"
              : "New conversation"}
        </span>
      </div>
      <div
        className="chat-messages"
        ref={scrollRef}
        tabIndex={0}
        aria-label="Conversation messages"
        onScroll={() => {
          const el = scrollRef.current;
          if (el) {
            followRef.current =
              el.scrollHeight - el.scrollTop - el.clientHeight < 100;
            setShowLatest(!followRef.current);
          }
        }}
      >
        {isRestoringSession ? (
          <p role="status">Restoring this session...</p>
        ) : messages.length === 0 ? (
          <div className="chat-welcome">
            <p className="eyebrow">Start with the evidence</p>
            <h2 className="text-2xl">What would you like to understand?</h2>
            <p className="muted text-sm mt-3 mb-6">
              Explore this comparison&apos;s performance, opening hooks and creative
              choices.
            </p>
            <div className="chat-starters">
              {SUGGESTED_QUESTIONS.slice(0, 4).map((q) => (
                <button
                  className="button-secondary"
                  key={q}
                  disabled={!canChat || isStreaming}
                  onClick={() => {
                    setInput(q);
                    inputRef.current?.focus();
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message, index) => (
            <ChatMessageBubble
              key={index}
              message={message}
              isStreaming={isStreaming && index === messages.length - 1}
            />
          ))
        )}
      </div>
      {showLatest && (
        <button
          className="button-quiet latest-button"
          onClick={() => {
            followRef.current = true;
            scrollRef.current?.scrollTo({
              top: scrollRef.current.scrollHeight,
              behavior: "instant",
            });
            setShowLatest(false);
          }}
        >
          Jump to latest
        </button>
      )}
      <div className="chat-composer">
        <p className="sr-only" role="status">
          {isStreaming
            ? "Response streaming"
            : error
              ? "Response failed"
              : messages.length
                ? "Response ready"
                : "Ready for a question"}
        </p>
        {!canChat && !isRestoringSession && (
          <p className="muted text-sm">
            Analyze content and prepare its evidence index before chatting.
          </p>
        )}
        {error && (
          <div role="alert" className="notice notice-error mb-3">
            {error}
            <button
              className="button-quiet"
              onClick={() => {
                const last = [...messages]
                  .reverse()
                  .find((m) => m.role === "user");
                setInput(last?.content ?? "");
                inputRef.current?.focus();
              }}
            >
              Edit and retry
            </button>
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <label htmlFor="chat-question" className="sr-only">
            Ask about this comparison
          </label>
          <textarea
            ref={inputRef}
            id="chat-question"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={!canChat || isStreaming}
            rows={2}
            placeholder="Ask about this comparison..."
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <div className="flex gap-3 items-center justify-between mt-3">
            <span className="muted text-xs">Ctrl / Cmd + Enter to send</span>
            <button
              type="submit"
              className="button-primary"
              disabled={!canChat || isStreaming || !input.trim()}
            >
              {isStreaming ? "Responding..." : "Send question"}
            </button>
          </div>
        </form>
        <details className="text-xs muted mt-2">
          <summary>About this session</summary>Context is retained while
          navigating in this browser session. Reloading can start a new
          conversation. Restored message history may not include structured
          cards or source details.
        </details>
      </div>
    </section>
  );
}

function AssistantMarkdown({ content }: { content: string }) {
  return (
    <div className="answer-prose mt-2 text-sm leading-6">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ children }) => (
            <div className="table-scroll">
              <table>{children}</table>
            </div>
          ),
          // Headings
          h1: ({ children }) => (
            <h1 className="mt-4 mb-1 text-base font-bold text-slate-950 first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="mt-4 mb-1 text-base font-semibold text-slate-950 first:mt-0">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mt-3 mb-1 text-sm font-semibold text-slate-900 first:mt-0">
              {children}
            </h3>
          ),
          // Paragraphs
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          // Unordered lists
          ul: ({ children }) => (
            <ul className="mb-2 ml-4 list-disc space-y-0.5 last:mb-0">
              {children}
            </ul>
          ),
          // Ordered lists
          ol: ({ children }) => (
            <ol className="mb-2 ml-4 list-decimal space-y-0.5 last:mb-0">
              {children}
            </ol>
          ),
          li: ({ children }) => <li className="leading-6">{children}</li>,
          // Bold / italic
          strong: ({ children }) => (
            <strong className="font-semibold text-slate-950">
              {children}
            </strong>
          ),
          em: ({ children }) => (
            <em className="italic text-slate-700">
              {children}
            </em>
          ),
          // Horizontal rule (--- separators)
          hr: () => (
            <hr className="my-3 border-slate-200" />
          ),
          // Inline code
          code: ({ children, className }) => {
            const isBlock = Boolean(className);
            return isBlock ? (
              <code className="block rounded-md bg-slate-100 px-3 py-2 font-mono text-xs text-slate-800">
                {children}
              </code>
            ) : (
              <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs text-slate-800">
                {children}
              </code>
            );
          },
          // Block quote
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-4 border-teal-400 pl-3 text-slate-600">
              {children}
            </blockquote>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
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
      className={`chat-message ${isUser ? "message-user" : "message-assistant"}`}
    >
      <p className="text-xs font-semibold uppercase text-slate-500">
        {isUser ? "You" : "CreatorLens AI"}
      </p>
      {isUser ? (
        <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-800">
          {message.content}
        </p>
      ) : message.structuredAnswer ? (
        <StructuredAnswerCard payload={message.structuredAnswer} />
      ) : message.content ? (
        <AssistantMarkdown content={message.content} />
      ) : isStreaming ? (
        <p className="mt-2 text-sm leading-6 text-slate-400">
          Thinking...
        </p>
      ) : null}
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
              {index + 1}. {citationDisplayLabel(citation.citation_label)}
            </p>
            <p className="mt-1 text-xs font-medium uppercase text-slate-500">
              {platformLabel(citation.platform)} /{" "}
              {sourceTypeLabel(citation.source_type)}
            </p>
            <details className="mt-2">
              <summary className="cursor-pointer text-xs font-semibold text-teal-700">
                View source text
              </summary>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">
                {citation.text}
              </p>
            </details>
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
    structuredAnswer?: StructuredAnswerPayload;
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
      structuredAnswer: update.structuredAnswer ?? message.structuredAnswer,
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

  if (sourceType === "insight") {
    return "Creator Insight Summary";
  }

  return sourceType;
}

function citationDisplayLabel(label: string): string {
  return label.replace(/\s-\s/g, " / ");
}

function chatHistoryMessage(message: StoredChatMessage): ChatMessage {
  return {
    role: message.role === "assistant" ? "assistant" : "user",
    content: message.content,
    citations: [],
  };
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Could not stream chat response.";
}
