"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { api, streamChatMessage } from "@/lib/api-client";
import type { ResearchSourceItem } from "@/lib/types";

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking: string;
}

export function TickerResearchChat({ ticker }: { ticker: string }) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [sources, setSources] = useState<ResearchSourceItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [manualThinkingOpen, setManualThinkingOpen] = useState<Record<string, boolean>>({});
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoaded(false);
    setMessages([]);
    setSources([]);
    api
      .getChatThread(ticker)
      .then((thread) => {
        if (cancelled) return;
        setLoaded(true);
        if (thread.messages.length === 0) {
          return; // wait for the user to explicitly ask a question or start the default analysis
        }
        setMessages(thread.messages.map((m) => ({ id: m.id, role: m.role, content: m.content, thinking: m.thinking ?? "" })));
        setSources(thread.sources);
        // If the last turn is a user question with no assistant reply, the previous run was
        // interrupted mid-stream (tab closed, navigated away) before it could persist — the
        // server only saves the reply once generation finishes, so it's lost. Resume it: the
        // question is already in the persisted history, so ask for a reply (message=null) rather
        // than resubmitting the question as a new turn, which would duplicate it.
        if (thread.messages[thread.messages.length - 1]!.role === "user") {
          runStream(null);
        }
      })
      .catch(() => cancelled || setLoaded(true));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, streaming]);

  async function runStream(userMessage: string | null) {
    setStreaming(true);
    const assistantId = `pending-${Date.now()}`;
    setMessages((prev) => {
      const next = userMessage
        ? [...prev, { id: `user-${Date.now()}`, role: "user" as const, content: userMessage, thinking: "" }]
        : [...prev];
      return [...next, { id: assistantId, role: "assistant" as const, content: "", thinking: "" }];
    });

    let contentStarted = false;
    try {
      const result = await streamChatMessage(
        ticker,
        userMessage,
        (delta) =>
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1]!;
            next[next.length - 1] = { ...last, thinking: last.thinking + delta };
            return next;
          }),
        (delta) => {
          if (!contentStarted) {
            // Collapse the reasoning trace the moment the answer starts, Claude-style — done here
            // (not as a side effect of the `open` prop toggling closed) because the *first*
            // native `toggle` event, fired when React mounts the element with open=true, is
            // indistinguishable from a real user click, so treating every toggle as "manual"
            // would permanently pin the trace open.
            contentStarted = true;
            setManualThinkingOpen((prev) => ({ ...prev, [assistantId]: false }));
          }
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1]!;
            next[next.length - 1] = { ...last, content: last.content + delta };
            return next;
          });
        }
      );
      setSources(result.sources);
    } catch {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1]!;
        if (!last.content) next[next.length - 1] = { ...last, content: "_Something went wrong generating this response._" };
        return next;
      });
    } finally {
      setStreaming(false);
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || streaming) return;
    setDraft("");
    runStream(text);
  }

  async function onNewAnalysis() {
    if (streaming) return;
    await api.resetChatThread(ticker);
    setMessages([]);
    setSources([]);
    runStream(null);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-900">Research</h2>
        <button
          onClick={onNewAnalysis}
          disabled={streaming}
          className="text-xs font-semibold text-gray-400 hover:text-brand disabled:opacity-40"
        >
          New analysis
        </button>
      </div>

      {!loaded && <p className="text-sm text-gray-500">Loading…</p>}

      {loaded && messages.length === 0 && !streaming && (
        <div className="flex flex-col items-start gap-2 rounded-lg border border-dashed border-gray-300 px-4 py-3">
          <p className="text-sm text-gray-500">
            No research yet for {ticker.toUpperCase()}. Ask a question below, or run a general analysis.
          </p>
          <button
            onClick={() => runStream(null)}
            className="rounded-full bg-brand px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-dark"
          >
            Run comprehensive analysis
          </button>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {messages.map((m, i) => {
          const isLast = i === messages.length - 1;
          const autoOpen = streaming && isLast && !m.content;
          const isOpen = manualThinkingOpen[m.id] ?? autoOpen;

          return m.role === "user" ? (
            <div key={m.id} className="ml-auto max-w-[85%] rounded-lg bg-brand px-3 py-2 text-sm text-white">
              {m.content}
            </div>
          ) : (
            <div key={m.id} className="flex flex-col gap-1.5">
              {m.thinking && (
                <details
                  open={isOpen}
                  onToggle={(e) => {
                    const nowOpen = e.currentTarget.open;
                    setManualThinkingOpen((prev) => ({ ...prev, [m.id]: nowOpen }));
                  }}
                  className="rounded-md border border-gray-200 bg-gray-50 px-3 py-1.5"
                >
                  <summary className="cursor-pointer text-xs font-medium text-gray-400">
                    {autoOpen ? "Thinking…" : "Reasoning"}
                  </summary>
                  <div className="mt-1.5 max-h-64 overflow-y-auto whitespace-pre-wrap text-xs text-gray-500">
                    {m.thinking}
                  </div>
                </details>
              )}
              {m.content ? (
                <div className="prose prose-sm max-w-none rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-700">
                  <ReactMarkdown>{m.content}</ReactMarkdown>
                </div>
              ) : (
                streaming &&
                isLast && (
                  <div className="flex items-center gap-2 px-1 text-sm text-gray-400">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-brand" /> Writing…
                  </div>
                )
              )}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Ask anything about ${ticker.toUpperCase()}…`}
          disabled={streaming}
          className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={streaming || !draft.trim()}
          className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50"
        >
          Ask
        </button>
      </form>

      {sources.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold text-gray-500">Sources</h3>
          <ul className="flex flex-col gap-1">
            {sources.map((s, i) => (
              <li key={i} className="text-xs">
                <span className="mr-2 uppercase text-gray-400">{s.source_type}</span>
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline">
                  {s.title}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
