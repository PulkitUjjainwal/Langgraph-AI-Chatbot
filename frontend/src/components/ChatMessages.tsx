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
    const timeoutId = setTimeout(() => {
      scrollToBottom("smooth");
    }, 100);
    return () => clearTimeout(timeoutId);
  }, [messages]);

  // Initial scroll
  useEffect(() => {
    scrollToBottom("auto");
  }, []);

  return (
    <div
      ref={containerRef}
      className="flex-1 space-y-3 overflow-y-auto px-4 py-4 bg-white"
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
            } chat-bubble`}
          >
            {/* Assistant avatar */}
            {msg.role === "assistant" && (
              <div className="flex-shrink-0 mr-2 mt-1">
                <div className="h-7 w-7 rounded-full bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
                  <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
              </div>
            )}

            <div
              className={`max-w-[75%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-chat-primary text-white rounded-br-md"
                  : "bg-gray-100 text-chat-text rounded-bl-md"
              }`}
            >
              {isTyping || isWaitingForStream ? (
                <div className="flex items-center gap-1 py-1">
                  <span className="typing-dot inline-block w-2 h-2 bg-orange-500 rounded-full"></span>
                  <span className="typing-dot inline-block w-2 h-2 bg-orange-500 rounded-full"></span>
                  <span className="typing-dot inline-block w-2 h-2 bg-orange-500 rounded-full"></span>
                </div>
              ) : (
                <>
                  {msg.text}
                  {showStreamingCursor && (
                    <span className="inline-block w-0.5 h-4 bg-orange-500 ml-0.5 animate-pulse" />
                  )}
                </>
              )}
            </div>
          </div>
        );
      })}
      <div ref={messagesEndRef} className="h-0" />
    </div>
  );
}
