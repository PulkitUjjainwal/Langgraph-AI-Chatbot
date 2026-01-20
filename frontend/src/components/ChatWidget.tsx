import { useEffect, useMemo, useRef, useState } from "react";
import { ChatHeader } from "./ChatHeader";
import { ChatMessages } from "./ChatMessages";
import { ChatFooter } from "./ChatFooter";
import genericQA from "../data/genericQA.json";

export type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
  actions?: {
    type: "schedule_demo" | "whatsapp" | "chat" | "refresh";
    label: string;
  }[];
  suggestions?: string[]; // For pill buttons from init
};

type SlotValues = Record<string, string>;

type SuggestionsState = {
  status?: string;
  missing_fields?: string[];
  draft_payload?: unknown;
  suggestions?: any;
};

// Lead capture types (keeping logic but removing UI)
type LeadFormField = {
  name: string;
  type: string;
  label: string;
  placeholder: string;
  required: boolean;
};

type LeadPrompt = {
  show_form: boolean;
  prompt_type: string;
  message: string;
  fields: LeadFormField[];
  buttons: {
    submit: string;
    skip: string;
  };
};

type LeadFormData = {
  email: string;
  phone: string;
  company_name: string;
};

// Question card type for Google-style display
type QuestionCard = {
  title: string;
  description: string;
};

const SESSION_STORAGE_KEY = "chat_session_id";

function createSessionId(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof (crypto as Crypto & { randomUUID?: () => string }).randomUUID === "function"
  ) {
    return (crypto as Crypto & { randomUUID: () => string }).randomUUID();
  }
  return `sid-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// Generate description for questions
function generateQuestionDescription(question: string): string {
  const q = question.toLowerCase();
  if (q.includes('buyer') || q.includes('importer')) {
    return "Find active importers and their shipment details";
  }
  if (q.includes('supplier') || q.includes('exporter')) {
    return "Discover suppliers and export patterns";
  }
  if (q.includes('hs code') || q.includes('product')) {
    return "Explore product categories and trade volumes";
  }
  if (q.includes('country') || q.includes('market')) {
    return "Analyze market trends and opportunities";
  }
  if (q.includes('trend') || q.includes('analysis')) {
    return "Get insights on trade patterns and changes";
  }
  return "Get detailed trade intelligence data";
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [suggestionsState, setSuggestionsState] = useState<SuggestionsState | null>(null);
  const [showTooltip, setShowTooltip] = useState(false);
  const [tooltipDismissed, setTooltipDismissed] = useState(false);

  const [sessionId, setSessionId] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(SESSION_STORAGE_KEY) ?? "";
  });

  const [countryInput, setCountryInput] = useState("");
  const [productInput, setProductInput] = useState("");
  const [currentUrl, setCurrentUrl] = useState("");
  const [isInitializing, setIsInitializing] = useState(false);

  // Initialize with generic questions from JSON
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>(() => {
    return Object.keys(genericQA);
  });

  // Lead capture state (keeping logic for future use)
  const [_showLeadForm, setShowLeadForm] = useState(false);
  const [_leadPrompt, setLeadPrompt] = useState<LeadPrompt | null>(null);
  const [leadFormData, setLeadFormData] = useState<LeadFormData>({
    email: "",
    phone: "",
    company_name: "",
  });
  const [_leadFormError, setLeadFormError] = useState("");
  const [_isSubmittingLead, setIsSubmittingLead] = useState(false);
  const [leadCaptured, setLeadCaptured] = useState(false);
  // Suppress unused warnings
  void _showLeadForm; void _leadPrompt; void _leadFormError; void _isSubmittingLead;

  // Refs
  const currentUrlRef = useRef<string>("");
  const sessionIdRef = useRef<string>(sessionId);
  const isInitializingRef = useRef<boolean>(false);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // Show tooltip after 3 seconds if not dismissed
  useEffect(() => {
    if (!open && !tooltipDismissed && suggestedQuestions.length > 0) {
      const timer = setTimeout(() => {
        setShowTooltip(true);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [open, tooltipDismissed, suggestedQuestions]);

  // Convert questions to cards with descriptions
  const questionCards: QuestionCard[] = useMemo(() => {
    return suggestedQuestions.slice(0, 5).map(q => ({
      title: q,
      description: generateQuestionDescription(q)
    }));
  }, [suggestedQuestions]);

  // Track current URL for init calls
  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = window.location.href;
    currentUrlRef.current = url;
    setCurrentUrl(url);
  }, []);

  // Show initial welcome message
  useEffect(() => {
    if (open && messages.length === 0) {
      if (!sessionIdRef.current) {
        const storedSid = typeof window !== "undefined"
          ? window.localStorage.getItem(SESSION_STORAGE_KEY) ?? ""
          : "";
        const sid = storedSid || createSessionId();

        sessionIdRef.current = sid;
        setSessionId(sid);
        try {
          window.localStorage.setItem(SESSION_STORAGE_KEY, sid);
        } catch {}
      }

      // setMessages([
      //   {
      //     id: "welcome-1",
      //     role: "assistant",
      //     text: "Hi! I'm your trade intelligence assistant. Ask me anything about markets, products, or companies.",
      //   },
      // ]);
    }
  }, [open, messages.length, sessionId]);

  const {
    dataTypeButtonOptions,
    countryOptions,
    isCollecting,
    missingFields,
  } = useMemo(() => {
    const missing_fields = suggestionsState?.missing_fields ?? [];
    const suggestionsRaw = suggestionsState?.suggestions;

    type ButtonOption = { label: string; value: string };

    const normalizeButtonOptions = (options: unknown): ButtonOption[] => {
      if (!Array.isArray(options)) return [];
      return options
        .map((o) => {
          if (typeof o === "string") return { label: o, value: o };
          if (o && typeof o === "object") {
            const label = (o as any).label;
            const value = (o as any).value;
            if (typeof value === "string") {
              return { label: typeof label === "string" ? label : value, value };
            }
          }
          return null;
        })
        .filter((x): x is ButtonOption => Boolean(x));
    };

    const normalizeStringOptions = (options: unknown): string[] => {
      if (!Array.isArray(options)) return [];
      return options
        .map((o) => {
          if (typeof o === "string") return o;
          if (o && typeof o === "object") {
            const value = (o as any).value;
            const label = (o as any).label;
            if (typeof value === "string") return value;
            if (typeof label === "string") return label;
          }
          return null;
        })
        .filter((x): x is string => Boolean(x));
    };

    const suggestionsArray = Array.isArray(suggestionsRaw) ? suggestionsRaw : [];
    const dataTypeSuggestion = suggestionsArray.find(
      (s) => s?.field === "data_type" && s?.type === "buttons"
    );
    const dataTypeButtons = normalizeButtonOptions(dataTypeSuggestion?.options);

    const defaultDataTypeButtons: ButtonOption[] = [
      { label: "Detailed Imports", value: "detailed_imports" },
      { label: "Detailed Exports", value: "detailed_exports" },
      { label: "Mirror Imports", value: "mirror_imports" },
      { label: "Mirror Exports", value: "mirror_exports" },
    ];

    const resolvedDataTypeButtons =
      dataTypeButtons.length > 0
        ? dataTypeButtons
        : missing_fields.includes("data_type")
        ? defaultDataTypeButtons
        : [];

    const countrySuggestion = suggestionsArray.find(
      (s) => s?.field === "country" && (s?.type === "select" || s?.type === "dropdown")
    );
    const countriesFromSuggestions = normalizeStringOptions(countrySuggestion?.options);

    const collecting =
      suggestionsState?.status === "collecting" ||
      suggestionsArray.length > 0 ||
      missing_fields.length > 0;

    return {
      dataTypeButtonOptions: resolvedDataTypeButtons,
      countryOptions: countriesFromSuggestions,
      isCollecting: collecting,
      missingFields: missing_fields,
    };
  }, [suggestionsState]);

  const getApiBaseUrl = (): string => {
    if (typeof window !== "undefined" && (window as any).CHATBOT_CONFIG) {
      return (window as any).CHATBOT_CONFIG.apiUrl || "http://localhost:8003";
    }
    return "http://localhost:8003";
  };

  // Generic Q&A checker
  const checkGenericQA = async (userQuery: string): Promise<ChatMessage | null> => {
    const normalizedQuery = userQuery.trim();
    
    // Special case: "I want to learn about your data" should call init
    if (normalizedQuery === "I want to learn about your data") {
      await callInitAndShowQuestions();
      return null; // Will be handled by callInitAndShowQuestions
    }
    
    // Check if query matches any generic question
    const qaEntry = (genericQA as Record<string, any>)[normalizedQuery];
    
    if (!qaEntry) return null;

    const actions: ChatMessage["actions"] = [];

    // Build action buttons based on type
    if (qaEntry.type === "schedule_demo") {
      actions.push({
        type: "schedule_demo",
        label: "Schedule a Demo"
      });
    } else if (qaEntry.type === "whatsapp") {
      actions.push({
        type: "whatsapp",
        label: "Connect on WhatsApp"
      });
    } else if (qaEntry.type === "hybrid" && qaEntry.actions) {
      if (qaEntry.actions.includes("chat")) {
        actions.push({
          type: "chat",
          label: "Learn More"
        });
      }
      if (qaEntry.actions.includes("schedule_demo")) {
        actions.push({
          type: "schedule_demo",
          label: "Schedule a Demo"
        });
      }
    }

    return {
      id: `generic-${Date.now()}`,
      role: "assistant",
      text: qaEntry.message,
      actions: actions.length > 0 ? actions : undefined
    };
  };

  // Call init and show suggested questions as chat message
  const callInitAndShowQuestions = async () => {
    const sid = sessionIdRef.current || createSessionId();
    if (!sessionIdRef.current) {
      sessionIdRef.current = sid;
      setSessionId(sid);
      try {
        window.localStorage.setItem(SESSION_STORAGE_KEY, sid);
      } catch {}
    }

    setIsInitializing(true);

    try {
      const apiBaseUrl = getApiBaseUrl();
      const resp = await fetch(`${apiBaseUrl}/api/init`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sid,
          dynamic_url: currentUrl,
        }),
      });

      if (resp.ok) {
        const data = await resp.json();
        console.log("Init response:", data);

        if (data.suggested_questions && Array.isArray(data.suggested_questions)) {
          // Add assistant message with data info and pill buttons
          const assistantMsg: ChatMessage = {
            id: `init-${Date.now()}`,
            role: "assistant",
            text: "We provide comprehensive trade data covering 190+ countries with detailed import/export records, HS codes, company information, and real-time trade intelligence. Here are some questions you can ask:",
            suggestions: data.suggested_questions
          };
          setMessages((prev) => [...prev, assistantMsg]);
        }
      } else {
        // Fallback message
        setMessages((prev) => [
          ...prev,
          {
            id: `init-error-${Date.now()}`,
            role: "assistant",
            text: "I can help you with trade intelligence data. What would you like to know?"
          }
        ]);
      }
    } catch (error) {
      console.error("Init call failed:", error);
      setMessages((prev) => [
        ...prev,
        {
          id: `init-error-${Date.now()}`,
          role: "assistant",
          text: "I can help you with trade intelligence data. What would you like to know?"
        }
      ]);
    } finally {
      setIsInitializing(false);
    }
  };

  // Open schedule demo modal
  const openScheduleDemo = () => {
    if (typeof window !== "undefined" && typeof (window as any).openScheduleDemo === "function") {
      (window as any).openScheduleDemo();
    } else {
      console.error("Schedule demo function not available");
    }
  };

  // Open WhatsApp
  const openWhatsApp = () => {
    const whatsappUrl = "https://api.whatsapp.com/send/?phone=4407727449124&text&type=phone_number&app_absent=0";
    window.open(whatsappUrl, "_blank");
  };

  // Handle action button clicks
  const handleActionClick = (actionType: string, originalQuery?: string) => {
    if (actionType === "schedule_demo") {
      openScheduleDemo();
    } else if (actionType === "whatsapp") {
      openWhatsApp();
    } else if (actionType === "chat" && originalQuery) {
      // Call the chat/stream API with the original query
      void handleSend(originalQuery, undefined, true);
    } else if (actionType === "refresh") {
      // Re-initialize session to get fresh questions
      void initializeSessionProactive(currentUrl);
    }
  };

  // Lead capture functions (keeping logic for future use)
  const _handleLeadFormChange = (field: string, value: string) => {
    setLeadFormData((prev) => ({ ...prev, [field]: value }));
    setLeadFormError("");
  };

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const _submitLeadForm = async () => {
    if (!leadFormData.email.trim()) {
      setLeadFormError("Email is required");
      return;
    }
    if (!validateEmail(leadFormData.email)) {
      setLeadFormError("Please enter a valid email address");
      return;
    }

    setIsSubmittingLead(true);
    setLeadFormError("");

    try {
      const apiBaseUrl = getApiBaseUrl();
      const response = await fetch(`${apiBaseUrl}/api/lead/capture`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          email: leadFormData.email.trim(),
          phone: leadFormData.phone.trim() || null,
          company_name: leadFormData.company_name.trim() || null,
          source_url: currentUrl,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        console.log("Lead captured:", data);
        setLeadCaptured(true);
        setShowLeadForm(false);
        setLeadPrompt(null);

        setMessages((prev) => [
          ...prev,
          {
            id: `lead-thanks-${Date.now()}`,
            role: "assistant",
            text: data.message || "Thank you! I'll send you personalized insights.",
          },
        ]);
      } else {
        const error = await response.json();
        setLeadFormError(error.detail || "Failed to submit. Please try again.");
      }
    } catch (error) {
      console.error("Lead submission error:", error);
      setLeadFormError("Network error. Please try again.");
    } finally {
      setIsSubmittingLead(false);
    }
  };

  const _skipLeadForm = async () => {
    try {
      const apiBaseUrl = getApiBaseUrl();
      await fetch(`${apiBaseUrl}/api/lead/skip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch (error) {
      console.error("Error recording skip:", error);
    }

    setShowLeadForm(false);
    setLeadPrompt(null);
    setLeadFormError("");
  };

  async function _initializeSession() {
    const sid = sessionId || createSessionId();
    if (!sessionId) {
      setSessionId(sid);
      try {
        window.localStorage.setItem(SESSION_STORAGE_KEY, sid);
      } catch {}
    }

    try {
      const apiBaseUrl = getApiBaseUrl();
      const resp = await fetch(`${apiBaseUrl}/api/init`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sid,
          dynamic_url: currentUrl,
        }),
      });

      if (resp.ok) {
        const data = await resp.json();
        console.log("Session initialized:", data);

        if (data.suggested_questions && Array.isArray(data.suggested_questions)) {
          setSuggestedQuestions(data.suggested_questions);
        }
      }
    } catch (error) {
      console.error("Failed to initialize session:", error);
    }
  }

  async function initializeSessionProactive(url: string) {
    if (isInitializingRef.current) return;

    isInitializingRef.current = true;
    setIsInitializing(true);

    const sid = sessionIdRef.current || createSessionId();
    if (!sessionIdRef.current) {
      sessionIdRef.current = sid;
      setSessionId(sid);
      try {
        window.localStorage.setItem(SESSION_STORAGE_KEY, sid);
      } catch {}
    }

    try {
      const apiBaseUrl = getApiBaseUrl();
      const resp = await fetch(`${apiBaseUrl}/api/init`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sid,
          dynamic_url: url,
        }),
      });

      if (resp.ok) {
        const data = await resp.json();
        console.log("Proactive init for URL:", url);

        if (data.suggested_questions && Array.isArray(data.suggested_questions)) {
          setSuggestedQuestions(data.suggested_questions);
        } else {
          // Fallback to generic questions if no URL-specific questions
          const genericQuestions = Object.keys(genericQA).slice(0, 3);
          setSuggestedQuestions(genericQuestions);
        }
      } else {
        // If init fails, show generic questions
        const genericQuestions = Object.keys(genericQA).slice(0, 3);
        setSuggestedQuestions(genericQuestions);
      }
    } catch (error) {
      console.error("Failed to proactively initialize:", error);
      // On error, show generic questions
      const genericQuestions = Object.keys(genericQA).slice(0, 3);
      setSuggestedQuestions(genericQuestions);
    } finally {
      setIsInitializing(false);
      isInitializingRef.current = false;
    }
  }

  async function sendStreamingRequest(
    query: string,
    assistantMsgId: string,
    slotValues?: SlotValues
  ) {
    const sid = sessionIdRef.current || createSessionId();
    if (!sessionIdRef.current) {
      sessionIdRef.current = sid;
      setSessionId(sid);
      try {
        window.localStorage.setItem(SESSION_STORAGE_KEY, sid);
      } catch {}
    }

    const apiBaseUrl = getApiBaseUrl();
    const extraData: any = {};
    if (slotValues && Object.keys(slotValues).length > 0) {
      extraData.slot_values = slotValues;
    }

    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: query,
          session_id: sid,
          dynamic_url: currentUrl,
          ...extraData,
        }),
      });

      if (!response.ok) throw new Error("Stream request failed");
      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulatedText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));

              if (data.error) {
                throw new Error(data.error);
              }

              if (data.chunk) {
                accumulatedText += data.chunk;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId ? { ...m, text: accumulatedText } : m
                  )
                );
              }

              if (data.done) {
                console.log(`Streaming complete in ${data.processing_time?.toFixed(2)}s`);
              }
            } catch (parseError) {}
          }
        }
      }

      return accumulatedText;
    } catch (error) {
      console.error("Streaming error:", error);
      throw error;
    }
  }

  // Lead prompt check (keeping logic but not showing UI)
  const checkLeadPrompt = async (_message: string, _messageCount: number) => {
    if (leadCaptured) return;
    // Logic kept but UI disabled
  };
  // Suppress unused warnings for lead functions
  void _handleLeadFormChange; void _submitLeadForm; void _skipLeadForm; void _initializeSession;

  async function handleSend(text: string, slotValues?: SlotValues, skipGenericCheck = false) {
    if (isSending) return;

    const userId = `user-${Date.now()}`;
    const assistantId = `assistant-${Date.now() + 1}`;

    // Add user message first
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user" as const, text },
    ]);

    // Check if this is a generic question (only if not skipping)
    if (!skipGenericCheck) {
      const genericResponse = await checkGenericQA(text);
      if (genericResponse) {
        // Show generic response immediately
        setMessages((prev) => [...prev, genericResponse]);
        return;
      }
      // If checkGenericQA handled it (like init call), return early
      if (text.trim() === "I want to learn about your data") {
        return;
      }
    }

    // Not a generic question, proceed with streaming API
    setIsSending(true);

    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant" as const, text: "" },
    ]);

    try {
      await sendStreamingRequest(text, assistantId, slotValues);
      setSuggestionsState(null);
      const currentMessageCount = messages.length + 2;
      checkLeadPrompt(text, currentMessageCount);
    } catch (err) {
      console.error("Chat error:", err);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, text: "Something went wrong. Please try again." }
            : m
        )
      );
    } finally {
      setIsSending(false);
    }
  }

  const handleTooltipClick = () => {
    setShowTooltip(false);
    setOpen(true);
  };

  const dismissTooltip = () => {
    setShowTooltip(false);
    setTooltipDismissed(true);
  };

  return (
    <>
      {/* AWS-Style Tooltip Notifications */}
      {showTooltip && !open && (
        <div className="fixed bottom-24 right-5 z-2147483646 flex flex-col gap-2 max-w-sm">
          {/* Main tooltip */}
          <div
            className="tooltip-notification flex items-start gap-3 bg-slate-800 text-white rounded-xl p-4 cursor-pointer"
            onClick={handleTooltipClick}
          >
            <div className="flex-shrink-0 mt-0.5">
              <div className="h-8 w-8 rounded-lg bg-orange-500/20 flex items-center justify-center">
                <svg className="h-5 w-5 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">
                Hi, I can help you find trade data and answer questions.
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                dismissTooltip();
              }}
              className="flex-shrink-0 text-gray-400 hover:text-white transition-colors"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Secondary tooltip with hint */}
          <div
            className="tooltip-notification flex items-start gap-3 bg-slate-800 text-white rounded-xl p-4 cursor-pointer"
            style={{ animationDelay: '0.1s' }}
            onClick={handleTooltipClick}
          >
            <div className="flex-shrink-0 mt-0.5">
              <div className="h-8 w-8 rounded-lg bg-amber-500/20 flex items-center justify-center">
                <svg className="h-5 w-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">
                Ask about buyers, suppliers, or market trends!
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                dismissTooltip();
              }}
              className="flex-shrink-0 text-gray-400 hover:text-white transition-colors"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Floating Button */}
      <div className="fixed bottom-5 right-5 z-2147483647">
        <button
          onClick={() => {
            setOpen(true);
            setShowTooltip(false);
          }}
          className="relative flex items-center justify-center h-14 w-14 rounded-full
            bg-gradient-to-br from-orange-500 to-orange-600
            text-white shadow-lg
            hover:shadow-xl hover:scale-105 transition-all duration-200"
        >
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>

          {/* Notification badge */}
          {!open && suggestedQuestions.length > 0 && !showTooltip && (
            <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white animate-pulse">
              {Math.min(suggestedQuestions.length, 3)}
            </span>
          )}

          {/* Loading spinner */}
          {isInitializing && (
            <div className="absolute inset-0 flex items-center justify-center rounded-full bg-orange-600/90">
              <svg className="h-5 w-5 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            </div>
          )}
        </button>
      </div>

      {/* Chat Popup - AWS Style Layout */}
      {open && (
        <div
          className="fixed bottom-24 right-5 z-2147483647
            flex flex-col
            rounded-2xl bg-white shadow-2xl overflow-hidden
            border border-gray-200"
          style={{
            width: '380px',
            height: '580px',
            animation: 'scaleIn 0.3s ease-out forwards'
          }}
        >
          <ChatHeader onClose={() => setOpen(false)} />

          {/* Input Field - AWS Style (at top, below header) */}

          {/* Welcome Section with Suggested Questions - AWS Style */}
          {questionCards.length > 0 && messages.length <= 1 && (
            <div className="px-4 py-4 bg-white border-b border-gray-100">
              <p className="text-sm font-medium text-gray-700 mb-2">
                Want help getting started?
              </p>
              <p className="text-xs text-gray-500 mb-3">
                Tell us a little bit about what you're looking for.
              </p>

              {/* AWS-style Question Buttons */}
              <div className="space-y-2">
                {questionCards.map((card, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSend(card.title)}
                    disabled={isSending}
                    className="question-card w-full text-left px-4 py-3 rounded-lg bg-white border border-gray-200
                      hover:bg-orange-50 hover:border-orange-300 disabled:opacity-50 disabled:cursor-not-allowed
                      transition-all duration-200"
                  >
                    <p className="question-title text-sm text-gray-700">
                      {card.title}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Messages Area - Scrollable */}
          <ChatMessages 
            messages={messages} 
            isStreaming={isSending} 
            onActionClick={handleActionClick}
          />

          {/* Data Collection UI (if needed) */}
          {isCollecting && (
            <div className="border-t border-gray-200 px-4 py-3 bg-gray-50">
              {missingFields.length > 0 && (
                <div className="mb-2 text-xs text-gray-500">
                  Needed: {missingFields.join(", ")}
                </div>
              )}

              {dataTypeButtonOptions.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-2">
                  {dataTypeButtonOptions.map((opt) => (
                    <button
                      key={opt.value}
                      disabled={isSending}
                      onClick={() => handleSend(opt.label, { data_type: opt.value })}
                      className="rounded-full bg-orange-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-orange-600 disabled:opacity-50"
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              )}

              {(countryOptions.length > 0 || missingFields.includes("country")) && (
                <div className="mb-3 flex items-center gap-2">
                  <input
                    type="text"
                    value={countryInput}
                    onChange={(e) => setCountryInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        const v = countryInput.trim();
                        if (!v) return;
                        setCountryInput("");
                        handleSend(v, { country: v });
                      }
                    }}
                    placeholder="Select country..."
                    list="country-options"
                    disabled={isSending}
                    className="flex-1 rounded-full border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-orange-500 disabled:opacity-50"
                  />
                  <datalist id="country-options">
                    {countryOptions.map((c) => (
                      <option key={c} value={c} />
                    ))}
                  </datalist>
                  <button
                    disabled={isSending || !countryInput.trim()}
                    onClick={() => {
                      const v = countryInput.trim();
                      if (!v) return;
                      setCountryInput("");
                      handleSend(v, { country: v });
                    }}
                    className="rounded-full bg-orange-500 px-3 py-2 text-xs font-medium text-white hover:bg-orange-600 disabled:opacity-50"
                  >
                    Set
                  </button>
                </div>
              )}

              {missingFields.includes("product") && (
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={productInput}
                    onChange={(e) => setProductInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        const v = productInput.trim();
                        if (!v) return;
                        setProductInput("");
                        handleSend(v, { product: v });
                      }
                    }}
                    placeholder="Type product..."
                    disabled={isSending}
                    className="flex-1 rounded-full border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-orange-500 disabled:opacity-50"
                  />
                  <button
                    disabled={isSending || !productInput.trim()}
                    onClick={() => {
                      const v = productInput.trim();
                      if (!v) return;
                      setProductInput("");
                      handleSend(v, { product: v });
                    }}
                    className="rounded-full bg-orange-500 px-3 py-2 text-xs font-medium text-white hover:bg-orange-600 disabled:opacity-50"
                  >
                    Set
                  </button>
                </div>
              )}
            </div>
          )}
           <ChatFooter onSend={handleSend} isSending={isSending} position="bottom" />

          {/* Disclaimer at bottom - AWS Style */}
          <div className="px-4 py-2 bg-white border-t border-gray-100">
            <p className="text-[10px] text-gray-400 text-center">
              By chatting, you agree to this{" "}
              <a href="#" className="text-orange-600 hover:underline">disclaimer</a>.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
