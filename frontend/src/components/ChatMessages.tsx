import { useEffect, useRef, useState, useCallback } from "react";
import type { ReactNode } from "react";
import type { ChatMessage } from "./ChatWidget";

// Credit exhaustion card component
function CreditExhaustionCard({
  message,
  actions,
  onAction,
  onOpenWhatsAppDropdown
}: {
  message: string;
  actions: ChatMessage["actions"];
  onAction: (type: string) => void;
  onOpenWhatsAppDropdown?: (anchorEl: HTMLElement, originalQuery?: string) => void;
}) {
  return (
    <div className="credit-exhaustion-card bg-gradient-to-br from-orange-50 to-amber-50 rounded-2xl border border-orange-200 p-5 my-3 mx-2">
      <div className="flex items-start gap-3 mb-4">
        <div className="flex-shrink-0">
          <div className="h-10 w-10 rounded-full bg-orange-100 flex items-center justify-center">
            <svg className="h-5 w-5 text-orange-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gray-800 mb-1">Ready to unlock more?</h3>
          <p className="text-sm text-gray-600">{message}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {actions?.map((action, idx) => {
          let buttonStyle = "";
          let icon = null;

          if (action.type === "schedule_demo") {
            buttonStyle = "bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white";
            icon = (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            );
          } else if (action.type === "whatsapp") {
            buttonStyle = "bg-gradient-to-r from-green-500 to-green-600 hover:from-green-600 hover:to-green-700 text-white";
            icon = (
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/>
              </svg>
            );
          } else if (action.type === "chat_with_us") {
            buttonStyle = "bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white";
            icon = (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            );
          } else if (action.type === "continue_chat") {
            buttonStyle = "bg-white border-2 border-orange-300 text-orange-700 hover:bg-orange-50 hover:border-orange-500";
            icon = (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            );
          }

          return (
            <button
              key={idx}
              onClick={(e) => {
                if (action.type === 'whatsapp') {
                  e.stopPropagation();
                  onOpenWhatsAppDropdown?.(e.currentTarget as HTMLElement);
                } else {
                  onAction(action.type);
                }
              }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 transform hover:scale-105 shadow-sm cursor-pointer ${buttonStyle}`}
            >
              {icon}
              <span>{action.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// Explore More button component
function ExploreMoreButton({ url }: { url: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="explore-more-button group relative inline-flex items-center gap-2.5 mt-4 px-6 py-3 rounded-xl text-sm font-bold
        bg-gradient-to-br from-orange-50 via-orange-100 to-orange-200
        hover:from-orange-100 hover:via-orange-200 hover:to-orange-300
        text-orange-900
        shadow-[0_2px_8px_0_rgba(249,115,22,0.2),inset_0_1px_0_0_rgba(255,255,255,0.5)] 
        hover:shadow-[0_4px_16px_0_rgba(249,115,22,0.3),inset_0_1px_0_0_rgba(255,255,255,0.6)]
        transition-all duration-300 transform hover:scale-[1.02] hover:-translate-y-0.5
        border-2 border-orange-300/60 hover:border-orange-400/80
        overflow-hidden"
      onClick={(e) => e.stopPropagation()}
    >
      {/* Animated gradient background on hover */}
      <span className="absolute inset-0 bg-gradient-to-r from-orange-200/0 via-orange-300/40 to-orange-200/0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700" />
      
      {/* Content wrapper */}
      <span className="relative z-10 flex items-center gap-2.5">
        {/* Icon */}
        <svg 
          className="h-4 w-4 text-orange-700 transition-transform duration-300 group-hover:rotate-12" 
          fill="none" 
          viewBox="0 0 24 24" 
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
        </svg>
        
        {/* Text */}
        <span className="text-orange-900 tracking-wide">Explore More Details</span>
        
        {/* Animated arrow */}
        <svg 
          className="h-4 w-4 text-orange-700 transition-transform duration-300 group-hover:translate-x-1.5" 
          fill="none" 
          viewBox="0 0 24 24" 
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 7l5 5m0 0l-5 5m5-5H6" />
        </svg>
      </span>
    </a>
  );
}

type Props = {
  messages: ChatMessage[];
  isStreaming?: boolean;
  onActionClick?: (actionType: string, originalQuery?: string) => void;
  onOpenWhatsAppDropdown?: (anchorEl: HTMLElement, originalQuery?: string) => void;
  onFeedbackSubmit?: (feedbackData: FeedbackSubmitData) => Promise<void>;
  onDelayedFeedbackSubmit?: (feedbackData: DelayedFeedbackData) => Promise<void>;
  sessionId?: string;
  pageUrl?: string;
  onClose?: () => void;
};

export type FeedbackSubmitData = {
  sessionId: string;
  feedbackType: 'thumbs_up' | 'thumbs_down';
  messageId: string;
  assistantMessage: string;
  userQuery?: string;
  reason?: string;
  pageUrl?: string;
  conversation: { role: string; content: string; message_id?: string }[];
};

export type DelayedFeedbackData = {
  sessionId: string;
  feedbackType: 'rating';
  rating: number;
  workedWell: string[];
  comment?: string;
  pageUrl?: string;
  conversation: { role: string; content: string; message_id?: string }[];
};

type FeedbackState = {
  [messageId: string]: {
    type: 'up' | 'down' | null;
    reason?: string;
    submitted: boolean;
    submitting?: boolean;
  };
};

type FeedbackModalState = {
  isOpen: boolean;
  messageId: string | null;
  assistantMessage?: string;
  userQuery?: string;
};

type DelayedFeedbackState = {
  show: boolean;
  rating: number;
  workedWell: string[];
  comment: string;
  submitting: boolean;
  submitted: boolean;
};

const FEEDBACK_REASONS = [
  { id: 'inaccurate', label: 'Inaccurate information', icon: '❌' },
  { id: 'unhelpful', label: 'Not helpful', icon: '🤷' },
  { id: 'incomplete', label: 'Incomplete response', icon: '📝' },
  { id: 'confusing', label: 'Hard to understand', icon: '😕' },
  { id: 'other', label: 'Other', icon: '💬' },
];

const WORKED_WELL_OPTIONS = [
  { id: 'clarity', label: 'Clarity' },
  { id: 'language', label: 'Language used' },
  { id: 'accuracy', label: 'Accuracy' },
  { id: 'relevance', label: 'Relevance' },
  { id: 'speed', label: 'Response speed' },
];

// Inactivity timeout in milliseconds (40 seconds for feedback, 30 seconds for support buttons)
const INACTIVITY_TIMEOUT = 40000;
const SUPPORT_BUTTONS_TIMEOUT = 30000;

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

export function ChatMessages({
  messages,
  isStreaming = false,
  onActionClick,
  onOpenWhatsAppDropdown,
  onFeedbackSubmit,
  onDelayedFeedbackSubmit,
  sessionId = '',
  pageUrl = '',
  onClose
}: Props) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [feedbackState, setFeedbackState] = useState<FeedbackState>({});
  const [feedbackModal, setFeedbackModal] = useState<FeedbackModalState>({
    isOpen: false,
    messageId: null,
    assistantMessage: undefined,
    userQuery: undefined
  });

  // Delayed feedback state
  const [delayedFeedback, setDelayedFeedback] = useState<DelayedFeedbackState>({
    show: false,
    rating: 0,
    workedWell: [],
    comment: '',
    submitting: false,
    submitted: false
  });
  const inactivityTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastActivityRef = useRef<number>(Date.now());
  const hasShownDelayedFeedbackRef = useRef<boolean>(false);

  // Support buttons state
  const [supportButtons, setSupportButtons] = useState<{ show: boolean; dismissed: boolean }>({
    show: false,
    dismissed: false
  });
  const supportButtonsTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasShownSupportButtonsRef = useRef<boolean>(false);

  // Find the user query that preceded an assistant message
  const findUserQuery = (messageIndex: number): string | undefined => {
    for (let i = messageIndex - 1; i >= 0; i--) {
      if (messages[i]?.role === 'user') {
        return messages[i].text;
      }
    }
    return undefined;
  };

  // Submit feedback to backend
  const submitFeedbackToBackend = async (
    messageId: string,
    type: 'up' | 'down',
    assistantMessage: string,
    userQuery?: string,
    reason?: string
  ) => {
    if (!onFeedbackSubmit) return;

    // Build conversation history
    const conversation = messages.map(msg => ({
      role: msg.role,
      content: msg.text,
      message_id: msg.id
    }));

    const feedbackData: FeedbackSubmitData = {
      sessionId,
      feedbackType: type === 'up' ? 'thumbs_up' : 'thumbs_down',
      messageId,
      assistantMessage,
      userQuery,
      reason,
      pageUrl,
      conversation
    };

    try {
      await onFeedbackSubmit(feedbackData);
    } catch (error) {
      console.error('[Feedback] Failed to submit:', error);
    }
  };

  const handleFeedback = async (messageId: string, type: 'up' | 'down', messageIndex: number) => {
    const message = messages.find(m => m.id === messageId);
    const userQuery = findUserQuery(messageIndex);

    if (type === 'up') {
      // Positive feedback - submit immediately with animation
      setFeedbackState(prev => ({
        ...prev,
        [messageId]: { type: 'up', submitted: false, submitting: true }
      }));

      // Submit to backend
      await submitFeedbackToBackend(messageId, 'up', message?.text || '', userQuery);

      setFeedbackState(prev => ({
        ...prev,
        [messageId]: { type: 'up', submitted: true, submitting: false }
      }));
    } else {
      // Negative feedback - show modal for reason selection
      setFeedbackModal({
        isOpen: true,
        messageId,
        assistantMessage: message?.text,
        userQuery
      });
    }
  };

  const handleFeedbackReasonSelect = async (reason: string) => {
    if (feedbackModal.messageId) {
      setFeedbackState(prev => ({
        ...prev,
        [feedbackModal.messageId!]: { type: 'down', reason, submitted: false, submitting: true }
      }));

      // Submit to backend with reason
      await submitFeedbackToBackend(
        feedbackModal.messageId,
        'down',
        feedbackModal.assistantMessage || '',
        feedbackModal.userQuery,
        reason
      );

      setFeedbackState(prev => ({
        ...prev,
        [feedbackModal.messageId!]: { type: 'down', reason, submitted: true, submitting: false }
      }));
    }
    setFeedbackModal({ isOpen: false, messageId: null, assistantMessage: undefined, userQuery: undefined });
  };

  const closeFeedbackModal = () => {
    setFeedbackModal({ isOpen: false, messageId: null, assistantMessage: undefined, userQuery: undefined });
  };

  // =========================================================================
  // DELAYED FEEDBACK (AWS-style "idle" feedback form)
  // =========================================================================

  // Reset inactivity timer for delayed feedback
  const resetInactivityTimer = useCallback(() => {
    lastActivityRef.current = Date.now();

    if (inactivityTimerRef.current) {
      clearTimeout(inactivityTimerRef.current);
    }

    // Don't show if already shown or submitted, or if there are no messages
    if (hasShownDelayedFeedbackRef.current || delayedFeedback.submitted || messages.length < 2) {
      return;
    }

    inactivityTimerRef.current = setTimeout(() => {
      // Only show if user has had at least one exchange
      const hasAssistantResponse = messages.some(m => m.role === 'assistant' && m.text && m.text !== 'thinking...');
      if (hasAssistantResponse && !hasShownDelayedFeedbackRef.current) {
        setDelayedFeedback(prev => ({ ...prev, show: true }));
        hasShownDelayedFeedbackRef.current = true;
      }
    }, INACTIVITY_TIMEOUT);
  }, [messages, delayedFeedback.submitted]);

  // Reset inactivity timer for support buttons
  const resetSupportButtonsTimer = useCallback(() => {
    if (supportButtonsTimerRef.current) {
      clearTimeout(supportButtonsTimerRef.current);
    }

    // Don't show if already shown, dismissed, or if there are no messages
    if (hasShownSupportButtonsRef.current || supportButtons.dismissed || messages.length < 2) {
      return;
    }

    supportButtonsTimerRef.current = setTimeout(() => {
      // Only show if user has had at least one exchange
      const hasAssistantResponse = messages.some(m => m.role === 'assistant' && m.text && m.text !== 'thinking...');
      if (hasAssistantResponse && !hasShownSupportButtonsRef.current) {
        setSupportButtons({ show: true, dismissed: false });
        hasShownSupportButtonsRef.current = true;
      }
    }, SUPPORT_BUTTONS_TIMEOUT);
  }, [messages, supportButtons.dismissed]);

  // Track user activity
  useEffect(() => {
    resetInactivityTimer();
    resetSupportButtonsTimer();

    // Listen for user interactions
    const handleActivity = () => {
      resetInactivityTimer();
      resetSupportButtonsTimer();
    };
    const container = containerRef.current;

    if (container) {
      container.addEventListener('scroll', handleActivity);
      container.addEventListener('click', handleActivity);
      container.addEventListener('mousemove', handleActivity);
    }

    return () => {
      if (inactivityTimerRef.current) {
        clearTimeout(inactivityTimerRef.current);
      }
      if (supportButtonsTimerRef.current) {
        clearTimeout(supportButtonsTimerRef.current);
      }
      if (container) {
        container.removeEventListener('scroll', handleActivity);
        container.removeEventListener('click', handleActivity);
        container.removeEventListener('mousemove', handleActivity);
      }
    };
  }, [resetInactivityTimer, resetSupportButtonsTimer]);

  // Reset timers when messages change (user is active)
  // Also hide support buttons and feedback form when user sends a new message
  useEffect(() => {
    resetInactivityTimer();
    resetSupportButtonsTimer();

    // Hide support buttons and feedback form when user starts chatting again
    if (messages.length > 0) {
      const lastMessage = messages[messages.length - 1];

      // If the last message is from the user, hide both UI elements
      if (lastMessage?.role === 'user') {
        // Hide support buttons
        if (supportButtons.show) {
          setSupportButtons(prev => ({ ...prev, show: false }));
        }

        // Hide delayed feedback form (but keep it as "dismissed" so it won't show again)
        if (delayedFeedback.show) {
          setDelayedFeedback(prev => ({ ...prev, show: false }));
        }
      }
    }
  }, [messages, resetInactivityTimer, resetSupportButtonsTimer]);

  // Handle star rating click
  const handleStarClick = (star: number) => {
    setDelayedFeedback(prev => ({ ...prev, rating: star }));
  };

  // Handle "what worked well" toggle
  const toggleWorkedWell = (id: string) => {
    setDelayedFeedback(prev => ({
      ...prev,
      workedWell: prev.workedWell.includes(id)
        ? prev.workedWell.filter(w => w !== id)
        : [...prev.workedWell, id]
    }));
  };

  // Handle comment change
  const handleCommentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setDelayedFeedback(prev => ({ ...prev, comment: e.target.value }));
  };

  // Cancel delayed feedback
  const cancelDelayedFeedback = () => {
    setDelayedFeedback(prev => ({ ...prev, show: false }));
  };

  // Submit delayed feedback
  const submitDelayedFeedback = async () => {
    if (delayedFeedback.rating === 0) return;

    setDelayedFeedback(prev => ({ ...prev, submitting: true }));

    if (onDelayedFeedbackSubmit) {
      const conversation = messages.map(msg => ({
        role: msg.role,
        content: msg.text,
        message_id: msg.id
      }));

      await onDelayedFeedbackSubmit({
        sessionId,
        feedbackType: 'rating',
        rating: delayedFeedback.rating,
        workedWell: delayedFeedback.workedWell,
        comment: delayedFeedback.comment || undefined,
        pageUrl,
        conversation
      });
    }

    setDelayedFeedback(prev => ({
      ...prev,
      show: false,
      submitting: false,
      submitted: true
    }));
  };

  // Handle support button clicks
  const handleSupportAction = (action: string) => {
    // Dismiss the support buttons card
    setSupportButtons({ show: false, dismissed: true });

    // Trigger the action
    if (action === 'contact_support') {
      // Open contact support (could be WhatsApp, email, or custom modal)
      window.open('https://api.whatsapp.com/send/?phone=4407727449124&text&type=phone_number&app_absent=0', '_blank');
    } else if (action === 'view_faq') {
      // Open FAQ page
      window.open('https://www.marketinside.io/faq', '_blank');
    } else if (action === 'get_help') {
      // Send a message to chatbot asking for help
      onActionClick?.('chat', 'I need help with something');
    } else if (action === 'schedule_demo') {
      // Close/minimize the chatbot first
      console.log('Closing chatbot...');
      onClose?.();

      // Then open schedule demo after a small delay
      setTimeout(() => {
        if (typeof window !== 'undefined' && typeof (window as any).openScheduleDemo === 'function') {
          console.log('Opening schedule demo...');
          (window as any).openScheduleDemo();
        } else {
          console.log('openScheduleDemo function not found on window');
        }
      }, 100);
    }
  };

  // Dismiss support buttons
  const dismissSupportButtons = () => {
    setSupportButtons({ show: false, dismissed: true });
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
      className="flex-1 space-y-3 overflow-y-auto px-4 py-4 bg-white cursor-default"
      style={{ scrollBehavior: "smooth" }}
    >
      {messages.map((msg, index) => {
        const isTyping = msg.text === "thinking...";
        const isLastMessage = index === messages.length - 1;
        const isWaitingForStream = msg.role === "assistant" && msg.text === "" && isLastMessage && isStreaming;
        const showStreamingCursor = msg.role === "assistant" && msg.text !== "" && isLastMessage && isStreaming;

        // Enhanced debug logging for thinking indicator
        if (msg.role === "assistant" && msg.text === "" && isLastMessage) {
          console.log('[ChatMessages] ⏳ Thinking indicator check:', {
            msgId: msg.id,
            isLastMessage,
            isStreaming,
            isWaitingForStream,
            messageCount: messages.length,
            status: isWaitingForStream ? '✅ SHOWING DOTS' : '❌ NOT SHOWING'
          });
        }

        // Log when streaming starts showing content
        if (msg.role === "assistant" && msg.text !== "" && isLastMessage && isStreaming && msg.text.length < 20) {
          console.log('[ChatMessages] 📝 Content streaming started:', {
            msgId: msg.id,
            textLength: msg.text.length,
            preview: msg.text.substring(0, 20)
          });
        }

        return (
          <div
            key={msg.id}
            className={`flex chat-bubble ${
              msg.role === "user" ? "justify-start" : "justify-end"
            }`}
          >
            {/* User avatar - shown on left for user messages */}
            {msg.role === "user" && (
              <div className="flex-shrink-0 mr-2 mt-1">
                <div className="h-7 w-7 rounded-full bg-gradient-to-br from-gray-500 to-gray-600 flex items-center justify-center">
                  <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </div>
              </div>
            )}

            <div className={`flex-1 ${msg.role === "assistant" ? "flex flex-col items-end" : ""}`}>
              {/* Don't show message bubble for credit exhaustion (CreditExhaustionCard handles it) */}
              {!msg.isCreditExhausted && (
                <div
                  className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed overflow-hidden cursor-text ${
                    msg.role === "user"
                      ? "text-white rounded-br-md"
                      : "text-gray-900 rounded-bl-md"
                  } ${isWaitingForStream ? 'animate-pulse-soft' : ''}`}
                  style={{
                    wordBreak: 'break-word',
                    overflowWrap: 'break-word',
                    backgroundColor: msg.role === "user" ? '#333333' : (isWaitingForStream ? '#ffedd5' : '#fff6ed')
                  }}
                >
                  {isTyping || isWaitingForStream ? (
                    <div className="flex flex-col gap-1.5 py-2 px-1" role="status" aria-label="Thinking">
                      <div className="flex items-center gap-1.5">
                        <span className={`typing-dot inline-block w-2.5 h-2.5 rounded-full ${msg.role === "user" ? "bg-white" : "bg-orange-500"}`}></span>
                        <span className={`typing-dot inline-block w-2.5 h-2.5 rounded-full ${msg.role === "user" ? "bg-white" : "bg-orange-500"}`}></span>
                        <span className={`typing-dot inline-block w-2.5 h-2.5 rounded-full ${msg.role === "user" ? "bg-white" : "bg-orange-500"}`}></span>
                      </div>
                      <span className={`text-xs ${msg.role === "user" ? "text-white/70" : "text-orange-600/70"}`}>
                        Analyzing your query...
                      </span>
                    </div>
                  ) : (
                    <>
                      {renderMessageWithLinks(msg.text)}
                      {showStreamingCursor && (
                        <span className={`inline-block w-0.5 h-4 ml-0.5 animate-pulse ${msg.role === "user" ? "bg-white" : "bg-orange-500"}`} />
                      )}
                    </>
                  )}
                </div>
              )}

              {/* Credit exhaustion card - special UI */}
              {msg.role === "assistant" && msg.isCreditExhausted && msg.actions && msg.actions.length > 0 && (
                <CreditExhaustionCard
                  message={msg.text}
                  actions={msg.actions}
                  onAction={(type) => onActionClick?.(type)}
                  onOpenWhatsAppDropdown={(el) => onOpenWhatsAppDropdown?.(el)}
                />
              )}

              {/* Action buttons for generic responses - below the message (not for credit exhaustion) */}
              {msg.role === "assistant" && msg.actions && msg.actions.length > 0 && !msg.isCreditExhausted && (
                <div className="flex flex-wrap gap-2 mt-3 justify-end">
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
                  } else if (action.type === "hubspot_chat" || action.type === "chat_with_us") {
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
                      onClick={(e) => {
                        if (action.type === 'whatsapp') {
                          e.stopPropagation();
                          onOpenWhatsAppDropdown?.(e.currentTarget as HTMLElement, userQuery);
                        } else {
                          onActionClick?.(action.type, userQuery);
                        }
                      }}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 transform hover:scale-105 cursor-pointer ${buttonStyle}`}
                    >
                      {icon}
                      <span>{action.label}</span>
                    </button>
                  );
                })}
              </div>
            )}

              {/* Suggestion pills from init response or clarifying questions */}
              {msg.role === "assistant" && msg.suggestions && msg.suggestions.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3 justify-end">
                  {msg.suggestions.map((suggestion, suggestionIdx) => (
                    <div
                      key={suggestionIdx}
                      className="rounded-full p-[2px] bg-gradient-to-r from-blue-400 via-purple-500 to-pink-500"
                      style={{
                        backgroundSize: '200% 200%',
                        animation: 'gradient-x 3s ease infinite'
                      }}
                    >
                      <button
                        onClick={() => onActionClick?.("chat", suggestion)}
                        className="flex items-center gap-2 px-4 py-2 rounded-full text-sm font-normal
                          bg-white text-gray-800
                          hover:bg-gray-50
                          transition-all duration-200 cursor-pointer"
                      >
                        {/* Sparkle/Diamond Icon */}
                        <svg className="w-4 h-4 flex-shrink-0 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
                        </svg>
                        <span>{suggestion}</span>
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Explore More button for data-specific responses */}
              {msg.role === "assistant" && msg.exploreUrl && (
                <div className="flex justify-end mt-2">
                  <ExploreMoreButton url={msg.exploreUrl} />
                </div>
              )}

              {/* Feedback section for assistant messages */}
              {msg.role === "assistant" && msg.text && !isTyping && !isWaitingForStream && (
                <div className="mt-2 flex justify-end">
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
                        onClick={() => handleFeedback(msg.id, 'up', index)}
                        disabled={feedbackState[msg.id]?.submitting}
                        className="feedback-btn group flex items-center gap-1 px-2 py-1 rounded-md transition-all duration-200 hover:bg-green-50 text-gray-400 hover:text-green-600 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Yes, this was helpful"
                      >
                        {feedbackState[msg.id]?.submitting && feedbackState[msg.id]?.type === 'up' ? (
                          <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                        ) : (
                          <svg className="w-3.5 h-3.5 transition-transform group-hover:scale-110" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M2 10.5a1.5 1.5 0 113 0v6a1.5 1.5 0 01-3 0v-6zM6 10.333v5.43a2 2 0 001.106 1.79l.05.025A4 4 0 008.943 18h5.416a2 2 0 001.962-1.608l1.2-6A2 2 0 0015.56 8H12V4a2 2 0 00-2-2 1 1 0 00-1 1v.667a4 4 0 01-.8 2.4L6.8 7.933a4 4 0 00-.8 2.4z" />
                          </svg>
                        )}
                        <span className="text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity">Yes</span>
                      </button>
                      <button
                        onClick={() => handleFeedback(msg.id, 'down', index)}
                        disabled={feedbackState[msg.id]?.submitting}
                        className="feedback-btn group flex items-center gap-1 px-2 py-1 rounded-md transition-all duration-200 hover:bg-red-50 text-gray-400 hover:text-red-500 disabled:opacity-50 disabled:cursor-not-allowed"
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

            {/* MI Assistant avatar - shown on right for assistant messages */}
            {msg.role === "assistant" && (
              <div className="flex-shrink-0 ml-2 mt-1">
                <div className="h-8 w-8 rounded-full bg-orange-500 flex items-center justify-center">
                  <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </div>
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
          <div className="feedback-modal relative bg-white rounded-2xl shadow-2xl w-[90%] max-w-sm max-h-[75vh] mx-4 overflow-y-auto">
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

      {/* Support Buttons Card (appears after 30 seconds of inactivity) */}
      {supportButtons.show && !supportButtons.dismissed && (
        <div className="support-buttons-card mx-2 my-4 animate-fade-in">
          {/* Idle message bubble */}
          <div className="flex items-center justify-center mb-3">
            <div className="bg-blue-100 px-4 py-2 rounded-full text-sm text-blue-700 flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 5.636l-3.536 3.536m0 5.656l3.536 3.536M9.172 9.172L5.636 5.636m3.536 9.192l-3.536 3.536M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-5 0a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
              Need assistance?
            </div>
          </div>

          {/* Support Card */}
          <div className="bg-white rounded-2xl shadow-lg border border-blue-200 overflow-hidden">
            <div className="bg-gradient-to-r from-blue-500 to-blue-600 px-5 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center">
                    <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="text-white font-semibold text-base">We're here to help!</h3>
                    <p className="text-blue-100 text-xs">Choose how you'd like assistance</p>
                  </div>
                </div>
                <button
                  onClick={dismissSupportButtons}
                  className="text-white/80 hover:text-white transition-colors p-1 hover:bg-white/10 rounded-full"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Support Options */}
            <div className="p-5 space-y-3">
              <button
                onClick={() => handleSupportAction('get_help')}
                className="w-full flex items-center gap-4 p-4 rounded-xl transition-all duration-200 hover:bg-orange-50 border-2 border-transparent hover:border-orange-200 group text-left"
              >
                <div className="flex-shrink-0 w-12 h-12 bg-orange-100 rounded-full flex items-center justify-center group-hover:bg-orange-200 transition-colors">
                  <svg className="w-6 h-6 text-orange-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <div className="flex-1">
                  <div className="font-semibold text-gray-800 group-hover:text-orange-700 transition-colors">Continue Chatting</div>
                  <div className="text-sm text-gray-500">Ask me anything about our services</div>
                </div>
                <svg className="w-5 h-5 text-gray-300 group-hover:text-orange-500 transition-all group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>

              <button
                onClick={() => handleSupportAction('contact_support')}
                className="w-full flex items-center gap-4 p-4 rounded-xl transition-all duration-200 hover:bg-green-50 border-2 border-transparent hover:border-green-200 group text-left"
              >
                <div className="flex-shrink-0 w-12 h-12 bg-green-100 rounded-full flex items-center justify-center group-hover:bg-green-200 transition-colors">
                  <svg className="w-6 h-6 text-green-600" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>
                  </svg>
                </div>
                <div className="flex-1">
                  <div className="font-semibold text-gray-800 group-hover:text-green-700 transition-colors">WhatsApp Support</div>
                  <div className="text-sm text-gray-500">Chat with our team directly</div>
                </div>
                <svg className="w-5 h-5 text-gray-300 group-hover:text-green-500 transition-all group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>

              <button
                onClick={() => handleSupportAction('schedule_demo')}
                className="w-full flex items-center gap-4 p-4 rounded-xl transition-all duration-200 hover:bg-purple-50 border-2 border-transparent hover:border-purple-200 group text-left"
              >
                <div className="flex-shrink-0 w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center group-hover:bg-purple-200 transition-colors">
                  <svg className="w-6 h-6 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </div>
                <div className="flex-1">
                  <div className="font-semibold text-gray-800 group-hover:text-purple-700 transition-colors">Schedule a Demo</div>
                  <div className="text-sm text-gray-500">See our platform in action</div>
                </div>
                <svg className="w-5 h-5 text-gray-300 group-hover:text-purple-500 transition-all group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>

              {/* <button
                onClick={() => handleSupportAction('view_faq')}
                className="w-full flex items-center gap-4 p-4 rounded-xl transition-all duration-200 hover:bg-blue-50 border-2 border-transparent hover:border-blue-200 group text-left"
              >
                <div className="flex-shrink-0 w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center group-hover:bg-blue-200 transition-colors">
                  <svg className="w-6 h-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div className="flex-1">
                  <div className="font-semibold text-gray-800 group-hover:text-blue-700 transition-colors">View FAQ</div>
                  <div className="text-sm text-gray-500">Find answers to common questions</div>
                </div>
                <svg className="w-5 h-5 text-gray-300 group-hover:text-blue-500 transition-all group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button> */}
            </div>
          </div>
        </div>
      )}

      {/* AWS-style Delayed Feedback Form */}
      {delayedFeedback.show && (
        <div className="delayed-feedback-card mx-2 my-4 animate-fade-in">
          {/* Idle message bubble */}
          <div className="flex items-center justify-center mb-3">
            <div className="bg-gray-100 px-4 py-2 rounded-full text-sm text-gray-500 flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              You've been idle for a while.
            </div>
          </div>

          {/* Feedback Card */}
          <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
            <div className="p-5 space-y-5">
              {/* Star Rating */}
              <div>
                <p className="text-sm font-medium text-gray-700 mb-3">How would you rate this chat so far?</p>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((star) => (
                    <button
                      key={star}
                      onClick={() => handleStarClick(star)}
                      className="p-1 transition-all duration-200 hover:scale-110 focus:outline-none"
                      aria-label={`Rate ${star} stars`}
                    >
                      <svg
                        className={`w-8 h-8 transition-colors duration-200 ${
                          star <= delayedFeedback.rating
                            ? 'text-yellow-400 fill-current'
                            : 'text-gray-300 hover:text-yellow-300'
                        }`}
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={1.5}
                        fill={star <= delayedFeedback.rating ? 'currentColor' : 'none'}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                      </svg>
                    </button>
                  ))}
                </div>
              </div>

              {/* What worked well */}
              <div>
                <p className="text-sm font-medium text-gray-700 mb-3">What worked well?</p>
                <div className="flex flex-wrap gap-2">
                  {WORKED_WELL_OPTIONS.map((option) => (
                    <button
                      key={option.id}
                      onClick={() => toggleWorkedWell(option.id)}
                      className={`px-3 py-1.5 rounded-full text-sm font-medium border-2 transition-all duration-200 ${
                        delayedFeedback.workedWell.includes(option.id)
                          ? 'bg-orange-50 border-orange-400 text-orange-700'
                          : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300 hover:bg-gray-50'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Comment textarea */}
              <div>
                <p className="text-sm font-medium text-gray-700 mb-2">Want to add any details?</p>
                <textarea
                  value={delayedFeedback.comment}
                  onChange={handleCommentChange}
                  placeholder="Please add details (avoid including personal info)"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                  rows={3}
                />
              </div>
            </div>

            {/* Action buttons */}
            <div className="px-5 py-3 bg-gray-50 border-t border-gray-100 flex justify-end gap-3">
              <button
                onClick={cancelDelayedFeedback}
                className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-800 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={submitDelayedFeedback}
                disabled={delayedFeedback.rating === 0 || delayedFeedback.submitting}
                className={`px-5 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  delayedFeedback.rating === 0
                    ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    : 'bg-orange-500 text-white hover:bg-orange-600 shadow-md hover:shadow-lg'
                }`}
              >
                {delayedFeedback.submitting ? (
                  <span className="flex items-center gap-2">
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Submitting...
                  </span>
                ) : (
                  'Submit'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
