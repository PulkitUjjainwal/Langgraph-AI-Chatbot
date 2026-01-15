import { useEffect, useMemo, useState } from "react";
import { ChatHeader } from "./ChatHeader";
import { ChatMessages } from "./ChatMessages";
import { ChatFooter } from "./ChatFooter";

export type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
};

type SlotValues = Record<string, string>;

type SuggestionsState = {
  status?: string;
  missing_fields?: string[];
  draft_payload?: unknown;
  suggestions?: any;
};

// Lead capture types
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

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [suggestionsState, setSuggestionsState] = useState<SuggestionsState | null>(null);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);

  const [sessionId, setSessionId] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(SESSION_STORAGE_KEY) ?? "";
  });

  const [countryInput, setCountryInput] = useState("");
  const [productInput, setProductInput] = useState("");
  const [currentUrl, setCurrentUrl] = useState("");
  const [isInitializing, setIsInitializing] = useState(false);

  // Lead capture state
  const [showLeadForm, setShowLeadForm] = useState(false);
  const [leadPrompt, setLeadPrompt] = useState<LeadPrompt | null>(null);
  const [leadFormData, setLeadFormData] = useState<LeadFormData>({
    email: "",
    phone: "",
    company_name: "",
  });
  const [leadFormError, setLeadFormError] = useState("");
  const [isSubmittingLead, setIsSubmittingLead] = useState(false);
  const [leadCaptured, setLeadCaptured] = useState(false);

  // Get current page URL
  useEffect(() => {
    if (typeof window !== "undefined") {
      setCurrentUrl(window.location.href);
    }
  }, []);

  // Monitor URL changes and call /init immediately
  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleUrlChange = async () => {
      const newUrl = window.location.href;
      if (newUrl !== currentUrl) {
        setCurrentUrl(newUrl);
        console.log("🌐 URL changed to:", newUrl);

        // Proactively call /init when URL changes (even if chatbot is closed)
        await initializeSessionProactive(newUrl);
      }
    };

    const originalPushState = history.pushState;
    const originalReplaceState = history.replaceState;

    history.pushState = function(...args) {
      originalPushState.apply(history, args);
      handleUrlChange();
    };

    history.replaceState = function(...args) {
      originalReplaceState.apply(history, args);
      handleUrlChange();
    };

    window.addEventListener('popstate', handleUrlChange);

    return () => {
      history.pushState = originalPushState;
      history.replaceState = originalReplaceState;
      window.removeEventListener('popstate', handleUrlChange);
    };
  }, [currentUrl]);

  // Show initial welcome message on first open
  useEffect(() => {
    if (open && messages.length === 0) {
      if (!sessionId) {
        const newSessionId = createSessionId();
        setSessionId(newSessionId);
        try {
          window.localStorage.setItem(SESSION_STORAGE_KEY, newSessionId);
        } catch {
          // ignore
        }
      }

      setMessages([
        {
          id: "welcome-1",
          role: "assistant",
          text: "Hi! I'm your trade intelligence assistant. Ask me anything about markets, products or companies.",
        },
      ]);
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
              return {
                label: typeof label === "string" ? label : value,
                value,
              };
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

  // Lead capture functions
  const handleLeadFormChange = (field: string, value: string) => {
    setLeadFormData((prev) => ({ ...prev, [field]: value }));
    setLeadFormError("");
  };

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const submitLeadForm = async () => {
    // Validate email
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
        console.log("✅ Lead captured:", data);
        setLeadCaptured(true);
        setShowLeadForm(false);
        setLeadPrompt(null);

        // Add thank you message from bot
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
      console.error("❌ Lead submission error:", error);
      setLeadFormError("Network error. Please try again.");
    } finally {
      setIsSubmittingLead(false);
    }
  };

  const skipLeadForm = async () => {
    try {
      const apiBaseUrl = getApiBaseUrl();
      await fetch(`${apiBaseUrl}/api/lead/skip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      console.log("Lead form skipped");
    } catch (error) {
      console.error("Error recording skip:", error);
    }

    setShowLeadForm(false);
    setLeadPrompt(null);
    setLeadFormError("");
  };

  // Initialize session with current URL (when chatbot opens)
  async function initializeSession() {
    const sid = sessionId || createSessionId();
    if (!sessionId) {
      setSessionId(sid);
      try {
        window.localStorage.setItem(SESSION_STORAGE_KEY, sid);
      } catch {
        // ignore
      }
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
        console.log("✅ Session initialized:", data);

        // Store suggested questions
        if (data.suggested_questions && Array.isArray(data.suggested_questions)) {
          setSuggestedQuestions(data.suggested_questions);
          console.log("💡 Suggested questions:", data.suggested_questions);
        }
      }
    } catch (error) {
      console.error("❌ Failed to initialize session:", error);
    }
  }

  // Proactive initialization when URL changes (even if chatbot is closed)
  async function initializeSessionProactive(url: string) {
    if (isInitializing) return; // Prevent duplicate calls

    setIsInitializing(true);

    const sid = sessionId || createSessionId();
    if (!sessionId) {
      setSessionId(sid);
      try {
        window.localStorage.setItem(SESSION_STORAGE_KEY, sid);
      } catch {
        // ignore
      }
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
        console.log("🔄 Proactive init for URL:", url);
        console.log("✅ Context loaded:", data);

        // Update suggested questions for new page
        if (data.suggested_questions && Array.isArray(data.suggested_questions)) {
          setSuggestedQuestions(data.suggested_questions);
          console.log("💡 Updated suggested questions for new page:", data.suggested_questions);
        }
      }
    } catch (error) {
      console.error("❌ Failed to proactively initialize:", error);
    } finally {
      setIsInitializing(false);
    }
  }

  // Initialize session when chat opens
  useEffect(() => {
    if (open && sessionId) {
      initializeSession();
    }
  }, [open, sessionId]);

  // Streaming chat request using Server-Sent Events
  async function sendStreamingRequest(
    query: string,
    assistantMsgId: string,
    slotValues?: SlotValues
  ) {
    const sid = sessionId || createSessionId();
    if (!sessionId) {
      setSessionId(sid);
      try {
        window.localStorage.setItem(SESSION_STORAGE_KEY, sid);
      } catch {
        // ignore
      }
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
                // Update message with streamed content
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? { ...m, text: accumulatedText }
                      : m
                  )
                );
              }

              if (data.done) {
                console.log(`Streaming complete in ${data.processing_time?.toFixed(2)}s`);
              }
            } catch (parseError) {
              // Skip invalid JSON lines
            }
          }
        }
      }

      return accumulatedText;
    } catch (error) {
      console.error("Streaming error:", error);
      throw error;
    }
  }

  // Check if lead prompt should be shown (lightweight check)
  const checkLeadPrompt = async (message: string, messageCount: number) => {
    if (leadCaptured) return;

    // High-intent keywords that trigger lead prompt
    const highIntentKeywords = [
      'buyers', 'buyer', 'suppliers', 'supplier',
      'contact', 'contacts', 'email', 'phone',
      'download', 'export', 'send me', 'send it',
      'api', 'pricing', 'price', 'cost', 'quote',
      'list of', 'names of', 'complete list'
    ];

    const messageLower = message.toLowerCase();
    const hasHighIntent = highIntentKeywords.some(kw => messageLower.includes(kw));

    // Trigger on high intent OR after 3+ messages
    if (hasHighIntent || messageCount >= 3) {
      // Use a simple prompt without full chat request
      const promptMessages = {
        high_intent: "I can send you this detailed information directly. What's your email?",
        engagement: "I'm happy to help! To send you a summary, could you share your email?",
      };

      const promptType = hasHighIntent ? "high_intent" : "engagement";

      setLeadPrompt({
        show_form: true,
        prompt_type: promptType,
        message: promptMessages[promptType],
        fields: [
          { name: "email", type: "email", label: "Email", placeholder: "your@email.com", required: true },
          { name: "phone", type: "tel", label: "Phone", placeholder: "+1 234 567 8900", required: false },
          { name: "company_name", type: "text", label: "Company", placeholder: "Your Company", required: false },
        ],
        buttons: { submit: "Send to my email", skip: "Maybe later" },
      });
      setShowLeadForm(true);
      console.log("💡 Lead prompt triggered:", promptType);
    }
  };

  async function handleSend(text: string, slotValues?: SlotValues) {
    if (isSending) return;
    setIsSending(true);

    const userId = `user-${Date.now()}`;
    const assistantId = `assistant-${Date.now() + 1}`;

    // Add user message and empty assistant message for streaming
    setMessages((prev) => [
      ...prev,
      {
        id: userId,
        role: "user" as const,
        text,
      },
      {
        id: assistantId,
        role: "assistant" as const,
        text: "", // Start empty, will be filled by streaming
      },
    ]);

    try {
      // Use streaming for real-time response
      await sendStreamingRequest(text, assistantId, slotValues);

      // Clear suggestions state after successful response
      setSuggestionsState(null);

      // Check for lead prompt after response (lightweight client-side check)
      const currentMessageCount = messages.length + 2; // +2 for user msg and assistant msg
      checkLeadPrompt(text, currentMessageCount);

    } catch (err) {
      console.error("Chat error:", err);
      // Update the assistant message with error
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                text: "Something went wrong. Please try again.",
              }
            : m
        )
      );
    } finally {
      setIsSending(false);
    }
  }

  return (
    <>
      {/* Floating Button */}
      <div className="fixed bottom-5 right-5 z-[2147483647]">
        <button
          onClick={() => setOpen(true)}
          className="relative flex items-center gap-2 rounded-full bg-gradient-to-r from-chat-accent to-chat-primary
            px-6 py-3.5 text-sm font-semibold text-white shadow-xl
            hover:shadow-2xl hover:scale-105 transition-all duration-200
            ring-2 ring-white ring-offset-2"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          <span>Chat with AI</span>

          {/* Badge for new suggestions */}
          {!open && suggestedQuestions.length > 0 && (
            <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-green-500 text-xs font-bold text-white shadow-lg animate-pulse">
              {suggestedQuestions.length}
            </span>
          )}

          {/* Loading indicator */}
          {isInitializing && (
            <div className="absolute inset-0 flex items-center justify-center rounded-full bg-chat-primary bg-opacity-90">
              <svg className="h-5 w-5 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            </div>
          )}
        </button>
      </div>

      {/* Popup */}
      {open && (
        <div className="fixed bottom-24 right-5 z-[2147483647]
          flex h-[600px] w-[400px] flex-col
          rounded-2xl bg-white shadow-2xl border border-chat-border overflow-hidden
          animate-in slide-in-from-bottom-4 duration-300"
          style={{ animation: "scaleIn 0.3s ease-out forwards" }}
        >
          <ChatHeader onClose={() => setOpen(false)} />
          
          {/* Suggested Questions */}
          {suggestedQuestions.length > 0 && messages.length <= 1 && (
            <div className="border-b border-chat-border px-4 py-3 bg-gradient-to-b from-orange-50 to-white">
              <div className="flex items-center gap-2 mb-2">
                <svg className="h-4 w-4 text-chat-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                <p className="text-xs text-chat-primary font-semibold">Suggested questions:</p>
              </div>
              <div className="space-y-2">
                {suggestedQuestions.slice(0, 3).map((question, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSend(question)}
                    disabled={isSending}
                    className="w-full text-left text-xs px-3 py-2.5 rounded-lg
                      bg-white border border-gray-200 text-gray-700
                      hover:bg-chat-accent-light hover:border-chat-accent hover:text-chat-primary
                      transition-all duration-200 shadow-sm hover:shadow
                      disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          )}

          <ChatMessages messages={messages} isStreaming={isSending} />

          {/* Lead Capture Form */}
          {showLeadForm && leadPrompt && (
            <div className="border-t border-chat-border px-4 py-4 bg-gradient-to-b from-blue-50 to-white">
              <div className="flex items-start gap-2 mb-3">
                <svg className="h-5 w-5 text-blue-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                <p className="text-sm text-gray-700 font-medium">{leadPrompt.message}</p>
              </div>

              <div className="space-y-3">
                {/* Email Input */}
                <div>
                  <input
                    type="email"
                    value={leadFormData.email}
                    onChange={(e) => handleLeadFormChange("email", e.target.value)}
                    placeholder="your@email.com *"
                    disabled={isSubmittingLead}
                    className={`w-full rounded-lg border px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 ${
                      leadFormError && !leadFormData.email ? "border-red-400" : "border-gray-300"
                    } ${isSubmittingLead ? "opacity-60 cursor-not-allowed" : ""}`}
                  />
                </div>

                {/* Phone Input */}
                <div>
                  <input
                    type="tel"
                    value={leadFormData.phone}
                    onChange={(e) => handleLeadFormChange("phone", e.target.value)}
                    placeholder="Phone (optional)"
                    disabled={isSubmittingLead}
                    className={`w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 ${
                      isSubmittingLead ? "opacity-60 cursor-not-allowed" : ""
                    }`}
                  />
                </div>

                {/* Company Input */}
                <div>
                  <input
                    type="text"
                    value={leadFormData.company_name}
                    onChange={(e) => handleLeadFormChange("company_name", e.target.value)}
                    placeholder="Company (optional)"
                    disabled={isSubmittingLead}
                    className={`w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 ${
                      isSubmittingLead ? "opacity-60 cursor-not-allowed" : ""
                    }`}
                  />
                </div>

                {/* Error Message */}
                {leadFormError && (
                  <p className="text-xs text-red-500">{leadFormError}</p>
                )}

                {/* Buttons */}
                <div className="flex gap-2 pt-1">
                  <button
                    onClick={submitLeadForm}
                    disabled={isSubmittingLead}
                    className={`flex-1 rounded-lg bg-blue-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-600 transition-colors ${
                      isSubmittingLead ? "opacity-70 cursor-not-allowed" : ""
                    }`}
                  >
                    {isSubmittingLead ? (
                      <span className="flex items-center justify-center gap-2">
                        <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Sending...
                      </span>
                    ) : (
                      leadPrompt.buttons?.submit || "Send to my email"
                    )}
                  </button>
                  <button
                    onClick={skipLeadForm}
                    disabled={isSubmittingLead}
                    className={`rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors ${
                      isSubmittingLead ? "opacity-70 cursor-not-allowed" : ""
                    }`}
                  >
                    {leadPrompt.buttons?.skip || "Maybe later"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {isCollecting && (
            <div className="border-t px-4 py-3 bg-gray-50">
              {missingFields.length > 0 && (
                <div className="mb-2 text-xs text-gray-600">
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
                      className={`rounded-lg bg-chat-primary px-3 py-2 text-xs font-medium text-white hover:bg-chat-primary-hover ${
                        isSending ? "opacity-70 cursor-not-allowed" : ""
                      }`}
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
                    className={`flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-chat-accent ${
                      isSending ? "opacity-60 cursor-not-allowed" : ""
                    }`}
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
                    className={`rounded-lg bg-chat-primary px-3 py-2 text-xs font-medium text-white hover:bg-chat-primary-hover ${
                      isSending || !countryInput.trim() ? "opacity-70 cursor-not-allowed" : ""
                    }`}
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
                    className={`flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-chat-accent ${
                      isSending ? "opacity-60 cursor-not-allowed" : ""
                    }`}
                  />
                  <button
                    disabled={isSending || !productInput.trim()}
                    onClick={() => {
                      const v = productInput.trim();
                      if (!v) return;
                      setProductInput("");
                      handleSend(v, { product: v });
                    }}
                    className={`rounded-lg bg-chat-primary px-3 py-2 text-xs font-medium text-white hover:bg-chat-primary-hover ${
                      isSending || !productInput.trim() ? "opacity-70 cursor-not-allowed" : ""
                    }`}
                  >
                    Set
                  </button>
                </div>
              )}
            </div>
          )}
          
          <ChatFooter onSend={handleSend} isSending={isSending} />
        </div>
      )}
    </>
  );
}