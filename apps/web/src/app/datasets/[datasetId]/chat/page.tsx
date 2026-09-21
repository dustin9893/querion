"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useI18n } from "@/components/providers/I18nProvider";
import {
  ConversationResponse,
  MessageResponse,
  createConversation,
  listConversations,
  deleteConversation,
  getMessages,
  sendMessageStream,
} from "@/lib/api/chat";

export default function ChatPage() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useParams();
  const datasetId = params.datasetId as string;

  const [conversations, setConversations] = useState<ConversationResponse[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingSources, setStreamingSources] = useState<any[] | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => { scrollToBottom(); }, [messages, streamingContent]);

  // Fetch conversations
  const fetchConversations = useCallback(async () => {
    try {
      const data = await listConversations(datasetId);
      setConversations(data);
    } catch { /* silent */ }
  }, [datasetId]);

  useEffect(() => { fetchConversations(); }, [fetchConversations]);

  // Fetch messages when active conversation changes
  useEffect(() => {
    if (!activeConvId) { setMessages([]); return; }
    (async () => {
      try {
        const msgs = await getMessages(activeConvId);
        setMessages(msgs);
      } catch { /* silent */ }
    })();
  }, [activeConvId]);

  // Start new chat — just reset state, conversation created on first message
  const handleNewChat = () => {
    setActiveConvId(null);
    setMessages([]);
  };

  // Delete conversation
  const handleDeleteConv = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConvId === id) { setActiveConvId(null); setMessages([]); }
    } catch { /* silent */ }
  };

  // Send message
  const handleSend = async () => {
    if (!input.trim() || streaming) return;

    let convId = activeConvId;

    // Auto-create conversation if none selected
    if (!convId) {
      try {
        const conv = await createConversation(datasetId);
        setConversations((prev) => [conv, ...prev]);
        convId = conv.id;
        setActiveConvId(conv.id);
      } catch { return; }
    }

    const userMessage: MessageResponse = {
      id: crypto.randomUUID(),
      role: "user",
      content: input,
      sources: null,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setStreaming(true);
    setStreamingContent("");
    setStreamingSources(null);

    try {
      const response = await sendMessageStream(convId, userMessage.content);
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let sources: any[] | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6);
          if (data === "[DONE]") break;

          try {
            const parsed = JSON.parse(data);
            if (parsed.type === "token") {
              fullContent += parsed.content;
              setStreamingContent(fullContent);
            } else if (parsed.type === "sources") {
              sources = parsed.sources;
              setStreamingSources(sources);
            } else if (parsed.type === "error") {
              fullContent += `\n\n⚠️ ${parsed.content}`;
              setStreamingContent(fullContent);
            }
          } catch { /* skip parse errors */ }
        }
      }

      // Add final assistant message
      if (fullContent) {
        const assistantMsg: MessageResponse = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: fullContent,
          sources: sources,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      }

      // Refresh conversation list (title may have changed)
      fetchConversations();
    } catch (err: any) {
      const errorMsg: MessageResponse = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `⚠️ Error: ${err.message}`,
        sources: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setStreaming(false);
      setStreamingContent("");
      setStreamingSources(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <div className="flex h-[calc(100vh-64px)]" style={{ background: "var(--background)" }}>
      {/* Sidebar — Conversations */}
      <div
        className={`flex flex-col transition-all duration-300 ${sidebarOpen ? "w-72" : "w-0"} overflow-hidden`}
        style={{ borderRight: "1px solid var(--border)", background: "var(--card)" }}
      >
        <div className="flex items-center justify-between p-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <button
            onClick={() => router.push(`/datasets/${datasetId}`)}
            className="rounded-lg p-1.5 transition-colors"
            style={{ color: "var(--muted)" }}
            onMouseEnter={(e) => { e.currentTarget.style.color = "var(--foreground)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = "var(--muted)"; }}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M12 3L6 9L12 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
          <button
            onClick={handleNewChat}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all"
            style={{ background: "var(--accent)", color: "#fff" }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M7 3V11M3 7H11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {conversations.length === 0 ? (
            <p className="text-center text-xs py-8" style={{ color: "var(--muted)" }}>
              No conversations yet
            </p>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => setActiveConvId(conv.id)}
                className={`w-full text-left rounded-lg px-3 py-2.5 mb-1 text-sm transition-all group flex items-center`}
                style={{
                  background: activeConvId === conv.id ? "var(--accent-glow)" : "transparent",
                  color: activeConvId === conv.id ? "var(--accent)" : "var(--foreground)",
                }}
                onMouseEnter={(e) => { if (activeConvId !== conv.id) e.currentTarget.style.background = "var(--card-hover)"; }}
                onMouseLeave={(e) => { if (activeConvId !== conv.id) e.currentTarget.style.background = "transparent"; }}
              >
                <span className="truncate flex-1">{conv.title}</span>
                <span
                  className="opacity-0 group-hover:opacity-100 ml-1 p-1 rounded transition-opacity"
                  onClick={(e) => handleDeleteConv(conv.id, e)}
                  style={{ color: "var(--muted)" }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = "#ef4444"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = "var(--muted)"; }}
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M3 3L9 9M3 9L9 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                  </svg>
                </span>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toggle sidebar + header */}
        <div className="flex items-center gap-2 px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="rounded-lg p-1.5"
            style={{ color: "var(--muted)" }}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M3 5H15M3 9H15M3 13H15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
          <h3 className="text-sm font-medium truncate" style={{ color: "var(--foreground)" }}>
            {activeConvId
              ? conversations.find((c) => c.id === activeConvId)?.title || "Chat"
              : "Start a new chat"}
          </h3>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {messages.length === 0 && !streaming ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="rounded-full p-4 mb-4" style={{ background: "var(--accent-glow)" }}>
                <svg width="32" height="32" viewBox="0 0 32 32" fill="none" style={{ color: "var(--accent)" }}>
                  <path d="M16 4C9.37 4 4 8.95 4 15C4 18.06 5.5 20.82 7.88 22.75L6 28L12.12 25.5C13.35 25.82 14.65 26 16 26C22.63 26 28 21.05 28 15C28 8.95 22.63 4 16 4Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold mb-1" style={{ color: "var(--foreground)" }}>Chat with your documents</h3>
              <p className="text-sm" style={{ color: "var(--muted)" }}>Ask a question about your indexed documents</p>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto flex flex-col gap-4">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className="rounded-2xl px-4 py-3 max-w-[85%] text-sm leading-relaxed"
                    style={{
                      background: msg.role === "user" ? "var(--accent)" : "var(--card)",
                      color: msg.role === "user" ? "#fff" : "var(--foreground)",
                      border: msg.role === "assistant" ? "1px solid var(--border)" : "none",
                    }}
                  >
                    <p style={{ whiteSpace: "pre-wrap" }}>{msg.content}</p>
                    {/* Sources */}
                    {msg.sources && msg.sources.length > 0 && (() => {
                      // Group sources by filename
                      const grouped: Record<string, typeof msg.sources> = {};
                      for (const src of msg.sources!) {
                        const name = src.filename || "doc";
                        if (!grouped[name]) grouped[name] = [];
                        grouped[name]!.push(src);
                      }
                      return (
                        <div className="mt-3 pt-2" style={{ borderTop: "1px solid var(--border)" }}>
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                            <span className="text-xs" style={{ color: "var(--muted)" }}>📎</span>
                            {Object.entries(grouped).map(([filename, chunks]) => (
                              <span
                                key={filename}
                                className="text-xs px-2 py-0.5 rounded-md cursor-default inline-flex items-center gap-1"
                                style={{ background: "var(--accent-glow)", color: "var(--accent)" }}
                                title={chunks!.map(c => `#${c.chunk_index}: ${c.content_preview}`).join("\n\n")}
                              >
                                <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{ flexShrink: 0 }}>
                                  <path d="M2 1H6L8 3V9H2V1Z" stroke="currentColor" strokeWidth="0.8" />
                                  <path d="M6 1V3H8" stroke="currentColor" strokeWidth="0.8" />
                                </svg>
                                {filename.length > 25 ? filename.slice(0, 22) + "…" : filename}
                                <span style={{ opacity: 0.6 }}>
                                  §{chunks!.map(c => c.chunk_index).join(",")}
                                </span>
                              </span>
                            ))}
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                </div>
              ))}

              {/* Streaming message */}
              {streaming && (
                <div className="flex justify-start">
                  <div
                    className="rounded-2xl px-4 py-3 max-w-[85%] text-sm leading-relaxed"
                    style={{ background: "var(--card)", border: "1px solid var(--border)", color: "var(--foreground)" }}
                  >
                    {streamingSources && streamingSources.length > 0 && !streamingContent && (
                      <div className="flex items-center gap-2 mb-2">
                        <div className="animate-spin rounded-full h-3 w-3 border border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
                        <span className="text-xs" style={{ color: "var(--muted)" }}>
                          Found {streamingSources.length} relevant chunks, generating answer...
                        </span>
                      </div>
                    )}
                    {streamingContent ? (
                      <p style={{ whiteSpace: "pre-wrap" }}>
                        {streamingContent}
                        <span className="animate-pulse">▊</span>
                      </p>
                    ) : !streamingSources ? (
                      <div className="flex items-center gap-2">
                        <div className="animate-spin rounded-full h-3 w-3 border border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
                        <span className="text-xs" style={{ color: "var(--muted)" }}>Searching documents...</span>
                      </div>
                    ) : null}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="px-4 py-3" style={{ borderTop: "1px solid var(--border)" }}>
          <div className="max-w-3xl mx-auto">
            <div
              className="flex items-end gap-2 rounded-xl p-2"
              style={{ background: "var(--card)", border: "1px solid var(--border)" }}
            >
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question about your documents..."
                className="flex-1 resize-none bg-transparent text-sm outline-none px-2 py-1.5"
                style={{ color: "var(--foreground)", minHeight: 24, maxHeight: 120 }}
                rows={1}
                disabled={streaming}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || streaming}
                className="rounded-lg p-2 transition-all disabled:opacity-30"
                style={{ background: "var(--accent)", color: "#fff" }}
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M14 2L7 9M14 2L10 14L7 9M14 2L2 6L7 9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
