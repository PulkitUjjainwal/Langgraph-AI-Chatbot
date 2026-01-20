import { useEffect, useRef } from "react";
import type { ChatMessage } from "./ChatWidget";

type Props = {
  messages: ChatMessage[];
  isStreaming?: boolean;
  onActionClick?: (actionType: string, originalQuery?: string) => void;
};

/**
 * Parse message text and convert URLs and markdown links to clickable elements
 */
function renderMessageWithLinks(text: string) {
  if (!text) return null;

  // Patterns to match:
  // 1. Markdown links: [text](url)
  // 2. Plain URLs: https://... or http://...
  const markdownLinkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
  const urlRegex = /(https?:\/\/[^\s<>\[\]"']+)/g;

  // First, handle markdown links
  let processedText = text;
  const markdownLinks: { placeholder: string; label: string; url: string }[] = [];

  let match;
  let index = 0;
  while ((match = markdownLinkRegex.exec(text)) !== null) {
    const placeholder = `__MDLINK_${index}__`;
    markdownLinks.push({
      placeholder,
      label: match[1],
      url: match[2]
    });
    processedText = processedText.replace(match[0], placeholder);
    index++;
  }

  // Then split by plain URLs
  const parts: (string | JSX.Element)[] = [];
  const segments = processedText.split(urlRegex);

  segments.forEach((segment, idx) => {
    // Check if this segment is a markdown link placeholder
    const mdLink = markdownLinks.find(l => segment.includes(l.placeholder));
    if (mdLink) {
      // Replace placeholder with actual link
      const subParts = segment.split(mdLink.placeholder);
      subParts.forEach((subPart, subIdx) => {
        if (subPart) parts.push(subPart);
        if (subIdx < subParts.length - 1) {
          parts.push(
            <a
              key={`md-${idx}-${subIdx}`}
              href={mdLink.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-orange-600 hover:text-orange-700 underline underline-offset-2 font-medium break-all"
              onClick={(e) => e.stopPropagation()}
            >
              <span>{mdLink.label}</span>
              <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          );
        }
      });
    } else if (segment.match(urlRegex)) {
      // This is a plain URL
      parts.push(
        <a
          key={`url-${idx}`}
          href={segment}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-orange-600 hover:text-orange-700 underline underline-offset-2 font-medium break-all"
          onClick={(e) => e.stopPropagation()}
        >
          <span className="break-all">{segment.length > 50 ? segment.substring(0, 50) + '...' : segment}</span>
          <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </a>
      );
    } else if (segment) {
      parts.push(segment);
    }
  });

  return parts;
}

export function ChatMessages({ messages, isStreaming = false, onActionClick }: Props) {
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
            className={` ${
              msg.role === "user" ? "justify-end flex" : "justify-start block"
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
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed overflow-hidden ${
                msg.role === "user"
                  ? "bg-chat-primary text-white rounded-br-md"
                  : "bg-gray-100 text-chat-text rounded-bl-md"
              }`}
              style={{ wordBreak: 'break-word', overflowWrap: 'break-word' }}
            >
              {isTyping || isWaitingForStream ? (
                <div className="flex items-center gap-1 py-1">
                  <span className="typing-dot inline-block w-2 h-2 bg-orange-500 rounded-full"></span>
                  <span className="typing-dot inline-block w-2 h-2 bg-orange-500 rounded-full"></span>
                  <span className="typing-dot inline-block w-2 h-2 bg-orange-500 rounded-full"></span>
                </div>
              ) : (
                <>
                  {renderMessageWithLinks(msg.text)}
                  {showStreamingCursor && (
                    <span className="inline-block w-0.5 h-4 bg-orange-500 ml-0.5 animate-pulse" />
                  )}
                </>
              )}
            </div>

            {/* Action buttons for generic responses */}
            {msg.role === "assistant" && msg.actions && msg.actions.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {msg.actions.map((action, actionIdx) => {
                  // Find the original user query (previous message)
                  const userQuery = index > 0 ? messages[index - 1]?.text : undefined;
                  
                  // Button styling based on action type
                  let buttonStyle = "";
                  let icon = null;
                  
                  if (action.type === "schedule_demo") {
                    buttonStyle = "bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white shadow-md hover:shadow-lg";
                    icon = (
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                    );
                  } else if (action.type === "whatsapp") {
                    buttonStyle = "bg-gradient-to-r from-green-500 to-green-600 hover:from-green-600 hover:to-green-700 text-white shadow-md hover:shadow-lg";
                    icon = (
                      <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>
                      </svg>
                    );
                  } else if (action.type === "chat") {
                    buttonStyle = "bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white shadow-md hover:shadow-lg";
                    icon = (
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>
                    );
                  } else if (action.type === "refresh") {
                    buttonStyle = "bg-gradient-to-r from-gray-500 to-gray-600 hover:from-gray-600 hover:to-gray-700 text-white shadow-md hover:shadow-lg";
                    icon = (
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                    );
                  }

                  return (
                    <button
                      key={actionIdx}
                      onClick={() => onActionClick?.(action.type, userQuery)}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 transform hover:scale-105 ${buttonStyle}`}
                    >
                      {icon}
                      <span>{action.label}</span>
                    </button>
                  );
                })}
              </div>
            )}

            {/* Suggestion pills from init response */}
            {msg.role === "assistant" && msg.suggestions && msg.suggestions.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3 ml-9">
                {msg.suggestions.map((suggestion, suggestionIdx) => (
                  <button
                    key={suggestionIdx}
                    onClick={() => onActionClick?.("chat", suggestion)}
                    className="px-3 py-1 rounded-2xl rounded-br-md text-sm font-medium
                      bg-white border-2 border-orange-300 text-orange-700
                      hover:bg-orange-50 hover:border-orange-500
                      transition-all duration-200 transform hover:scale-105
                      shadow-sm hover:shadow-md"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
      <div ref={messagesEndRef} className="h-0" />
    </div>
  );
}
