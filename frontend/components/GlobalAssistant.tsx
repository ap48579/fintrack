"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { api, streamAssistantChat } from "@/lib/api-client";

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking: string;
}

export function GlobalAssistant() {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [manualThinkingOpen, setManualThinkingOpen] = useState<Record<string, boolean>>({});
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .getAssistantThread()
      .then((thread) => {
        setMessages(thread.map((m) => ({ id: m.id, role: m.role, content: m.content, thinking: m.thinking ?? "" })));
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, streaming, open]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || streaming) return;
    setDraft("");
    setStreaming(true);

    const assistantId = `pending-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: "user", content: text, thinking: "" },
      { id: assistantId, role: "assistant", content: "", thinking: "" },
    ]);

    let contentStarted = false;
    try {
      await streamAssistantChat(
        text,
        (delta) =>
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1]!;
            next[next.length - 1] = { ...last, thinking: last.thinking + delta };
            return next;
          }),
        (delta) => {
          if (!contentStarted) {
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
    } catch {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1]!;
        if (!last.content) next[next.length - 1] = { ...last, content: "_Something went wrong answering that._" };
        return next;
      });
    } finally {
      setStreaming(false);
    }
  }

  async function onReset() {
    if (streaming) return;
    await api.resetAssistantThread();
    setMessages([]);
  }

  return (
    <>
      <button
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-brand text-2xl text-white shadow-lg hover:bg-brand-dark"
        title="FinTrack research assistant"
      >
        {open ? "✕" : "💬"}
      </button>

      <div
        className={`fixed right-0 top-0 z-30 flex h-full w-full max-w-md transform flex-col border-l border-gray-200 bg-gray-50 shadow-xl transition-transform duration-200 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3">
          <div>
            <h2 className="text-sm font-bold text-gray-900">FinTrack Assistant</h2>
            <p className="text-xs text-gray-500">Answers from everything this tool has ingested — not per-ticker news.</p>
          </div>
          <button onClick={onReset} disabled={streaming} className="text-xs font-semibold text-gray-400 hover:text-brand disabled:opacity-40">
            Reset
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {!loaded && <p className="text-sm text-gray-500">Loading…</p>}
          {loaded && messages.length === 0 && (
            <p className="text-sm text-gray-500">
              Ask about domain-cloud concentration, hypothesis backtest results, or data coverage — e.g. "which
              hypotheses actually show a signal?" or "what sectors have the most buyer clustering right now?"
            </p>
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
                      className="rounded-md border border-gray-200 bg-white px-3 py-1.5"
                    >
                      <summary className="cursor-pointer text-xs font-medium text-gray-400">
                        {autoOpen ? "Thinking…" : "Reasoning"}
                      </summary>
                      <div className="mt-1.5 max-h-48 overflow-y-auto whitespace-pre-wrap text-xs text-gray-500">
                        {m.thinking}
                      </div>
                    </details>
                  )}
                  {m.content ? (
                    <div className="prose prose-sm max-w-none rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700">
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
        </div>

        <form onSubmit={onSubmit} className="flex gap-2 border-t border-gray-200 bg-white p-3">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask about the data…"
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
      </div>
    </>
  );
}
