import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { ChatMessage } from "./ChatWidget";

type Props = {
  messages: ChatMessage[];
  isStreaming?: boolean;
  onActionClick?: (actionType: string, originalQuery?: string) => void;
};

type FeedbackState = {
  [messageId: string]: {
    type: 'up' | 'down' | null;
    reason?: string;
    submitted: boolean;
  };
};

type FeedbackModalState = {
  isOpen: boolean;
  messageId: string | null;
};

const FEEDBACK_REASONS = [
  { id: 'inaccurate', label: 'Inaccurate information', icon: '❌' },
  { id: 'unhelpful', label: 'Not helpful', icon: '🤷' },
  { id: 'incomplete', label: 'Incomplete response', icon: '📝' },
  { id: 'confusing', label: 'Hard to understand', icon: '😕' },
  { id: 'other', label: 'Other', icon: '💬' },
];

/**
 * Parse message text and convert URLs and markdown links to clickable elements
 */
function renderMessageWithLinks(text: string): ReactNode {
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
  const parts: ReactNode[] = [];
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

  return <>{parts}</>;
}

export function ChatMessages({ messages, isStreaming = false, onActionClick }: Props) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [feedbackState, setFeedbackState] = useState<FeedbackState>({});
  const [feedbackModal, setFeedbackModal] = useState<FeedbackModalState>({ isOpen: false, messageId: null });

  const handleFeedback = (messageId: string, type: 'up' | 'down') => {
    if (type === 'up') {
      // Positive feedback - submit immediately with animation
      setFeedbackState(prev => ({
        ...prev,
        [messageId]: { type: 'up', submitted: true }
      }));
    } else {
      // Negative feedback - show modal for reason selection
      setFeedbackModal({ isOpen: true, messageId });
    }
  };

  const handleFeedbackReasonSelect = (reason: string) => {
    if (feedbackModal.messageId) {
      setFeedbackState(prev => ({
        ...prev,
        [feedbackModal.messageId!]: { type: 'down', reason, submitted: true }
      }));
    }
    setFeedbackModal({ isOpen: false, messageId: null });
  };

  const closeFeedbackModal = () => {
    setFeedbackModal({ isOpen: false, messageId: null });
  };

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

        // Debug logging for loader
        if (msg.role === "assistant" && msg.text === "" && isLastMessage) {
          console.log('[ChatMessages] Loader check:', { 
            msgId: msg.id, 
            isLastMessage, 
            isStreaming, 
            isWaitingForStream,
            messageCount: messages.length 
          });
        }

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

            <div className="flex-1">
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

              {/* Feedback section for assistant messages */}
              {msg.role === "assistant" && msg.text && !isTyping && !isWaitingForStream && (
                <div className="mt-2 ml-1">
                  {feedbackState[msg.id]?.submitted ? (
                    // Thank you message after feedback
                    <div className="feedback-thank-you flex items-center gap-2 py-1.5 px-3 rounded-lg bg-gradient-to-r from-gray-50 to-gray-100 border border-gray-200">
                      <span className="text-lg">
                        {feedbackState[msg.id]?.type === 'up' ? '🎉' : '🙏'}
                      </span>
                      <span className="text-xs text-gray-600 font-medium">
                        Thanks for your feedback!
                      </span>
                    </div>
                  ) : (
                    // Feedback buttons
                    <div className="flex items-center gap-1">
                      <span className="text-xs text-gray-400 mr-1">Was this helpful?</span>
                      <button
                        onClick={() => handleFeedback(msg.id, 'up')}
                        className="feedback-btn group flex items-center gap-1 px-2 py-1 rounded-md transition-all duration-200 hover:bg-green-50 text-gray-400 hover:text-green-600"
                        title="Yes, this was helpful"
                      >
                        <svg className="w-3.5 h-3.5 transition-transform group-hover:scale-110" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
                        </svg>
                        <span className="text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity">Yes</span>
                      </button>
                      <button
                        onClick={() => handleFeedback(msg.id, 'down')}
                        className="feedback-btn group flex items-center gap-1 px-2 py-1 rounded-md transition-all duration-200 hover:bg-red-50 text-gray-400 hover:text-red-500"
                        title="No, this needs improvement"
                      >
                        <svg className="w-3.5 h-3.5 transition-transform group-hover:scale-110" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M18 9.5a1.5 1.5 0 11-3 0v-6a1.5 1.5 0 013 0v6zM14 9.667v-5.43a2 2 0 00-1.105-1.79l-.05-.025A4 4 0 0011.055 2H5.64a2 2 0 00-1.962 1.608l-1.2 6A2 2 0 004.44 12H8v4a2 2 0 002 2 1 1 0 001-1v-.667a4 4 0 01.8-2.4l1.4-1.866a4 4 0 00.8-2.4z" />
                        </svg>
                        <span className="text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity">No</span>
                      </button>
                    </div>
                  )}
                </div>
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
                  } else if (action.type === "call") {
                    buttonStyle = "bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white shadow-md hover:shadow-lg";
                    icon = (
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                      </svg>
                    );
                  } else if (action.type === "hubspot_chat") {
                    buttonStyle = "bg-gradient-to-r from-purple-500 to-purple-600 hover:from-purple-600 hover:to-purple-700 text-white shadow-md hover:shadow-lg";
                    icon = (
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>
                    );
                  } else if (action.type === "chat") {
                  buttonStyle =
                    "bg-gradient-to-r from-[#FD853A] to-[#E67529] hover:from-[#E67529] hover:to-[#C96520] text-white shadow-md hover:shadow-lg";

                  icon = (
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                      />
                    </svg>
                  );
                }
                else if (action.type === "refresh") {
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
              <div className="flex flex-wrap gap-2 mt-3 ml-9 justify-end">
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

      {/* Feedback Reason Modal */}
      {feedbackModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/30 backdrop-blur-sm feedback-modal-backdrop"
            onClick={closeFeedbackModal}
          />

          {/* Modal */}
          <div className="feedback-modal relative bg-white rounded-2xl shadow-2xl w-[90%] max-w-sm mx-4 overflow-hidden">
            {/* Header */}
            <div className="bg-gradient-to-r from-orange-500 to-orange-600 px-5 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center">
                    <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="text-white font-semibold text-base">Help us improve</h3>
                    <p className="text-orange-100 text-xs">What went wrong?</p>
                  </div>
                </div>
                <button
                  onClick={closeFeedbackModal}
                  className="text-white/80 hover:text-white transition-colors p-1 hover:bg-white/10 rounded-full"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Reason Options */}
            <div className="p-4 space-y-2">
              {FEEDBACK_REASONS.map((reason) => (
                <button
                  key={reason.id}
                  onClick={() => handleFeedbackReasonSelect(reason.id)}
                  className="feedback-reason-btn w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-all duration-200 hover:bg-orange-50 border border-transparent hover:border-orange-200 group"
                >
                  <span className="text-xl group-hover:scale-110 transition-transform">{reason.icon}</span>
                  <span className="text-sm font-medium text-gray-700 group-hover:text-orange-700">{reason.label}</span>
                  <svg className="w-4 h-4 text-gray-300 group-hover:text-orange-500 ml-auto transition-all group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              ))}
            </div>

            {/* Footer */}
            <div className="px-5 py-3 bg-gray-50 border-t border-gray-100">
              <p className="text-xs text-gray-400 text-center">Your feedback helps us serve you better</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
