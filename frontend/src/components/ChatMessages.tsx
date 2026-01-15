import { useEffect, useRef } from "react";
import type { ChatMessage } from "./ChatWidget";

type Props = {
  messages: ChatMessage[];
  isStreaming?: boolean;
};

export function ChatMessages({ messages, isStreaming = false }: Props) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Smooth auto-scroll to bottom when messages change
  const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
    messagesEndRef.current?.scrollIntoView({ behavior, block: "end" });
  };

  // Auto-scroll when new messages arrive
  useEffect(() => {
    // Small delay to ensure DOM is updated
    const timeoutId = setTimeout(() => {
      scrollToBottom("smooth");
    }, 100);

    return () => clearTimeout(timeoutId);
  }, [messages]);

  // Initial scroll (instant, not smooth)
  useEffect(() => {
    scrollToBottom("auto");
  }, []);

  return (
    <div
      ref={containerRef}
      className="flex-1 space-y-4 overflow-y-auto px-4 py-4 bg-gray-50 scroll-smooth"
      style={{ scrollBehavior: "smooth" }}
    >
      {messages.map((msg, index) => {
        const isTyping = msg.text === "thinking...";
        const isLastMessage = index === messages.length - 1;
        const isWaitingForStream = msg.role === "assistant" && msg.text === "" && isLastMessage && isStreaming;
        const showStreamingCursor = msg.role === "assistant" && msg.text !== "" && isLastMessage && isStreaming;

        return (
          <div
            key={msg.id}
            className={`flex ${
              msg.role === "user" ? "justify-end" : "justify-start"
            } animate-in fade-in slide-in-from-bottom-2 duration-300`}
          >
            <div
              className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-3 text-sm shadow-sm transition-all duration-200 ${
                msg.role === "user"
                  ? "bg-chat-primary text-white rounded-br-sm"
                  : "bg-white text-chat-text border border-chat-border rounded-bl-sm"
              }`}
            >
              {isTyping || isWaitingForStream ? (
                <div className="flex items-center gap-2">
                  <div className="flex gap-1">
                    <span className="inline-block w-2 h-2 bg-chat-accent rounded-full animate-bounce" style={{ animationDelay: "0ms" }}></span>
                    <span className="inline-block w-2 h-2 bg-chat-accent rounded-full animate-bounce" style={{ animationDelay: "150ms" }}></span>
                    <span className="inline-block w-2 h-2 bg-chat-accent rounded-full animate-bounce" style={{ animationDelay: "300ms" }}></span>
                  </div>
                  <span className="text-xs text-chat-muted">AI is thinking...</span>
                </div>
              ) : (
                <>
                  {msg.text}
                  {showStreamingCursor && (
                    <span className="inline-block w-0.5 h-4 bg-chat-accent ml-0.5 animate-pulse" />
                  )}
                </>
              )}
            </div>
          </div>
        );
      })}
      {/* Invisible element at the end for auto-scroll */}
      <div ref={messagesEndRef} className="h-0" />
    </div>
  );
}
