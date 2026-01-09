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

  // Get current page URL
  useEffect(() => {
    if (typeof window !== "undefined") {
      setCurrentUrl(window.location.href);
    }
  }, []);

  // Monitor URL changes
  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleUrlChange = () => {
      const newUrl = window.location.href;
      if (newUrl !== currentUrl) {
        setCurrentUrl(newUrl);
        console.log("URL changed to:", newUrl);
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

  // Initialize session with current URL
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
        console.log("Session initialized:", data);

        // Store suggested questions
        if (data.suggested_questions && Array.isArray(data.suggested_questions)) {
          setSuggestedQuestions(data.suggested_questions);
          console.log("Suggested questions:", data.suggested_questions);
        }
      }
    } catch (error) {
      console.error("Failed to initialize session:", error);
    }
  }

  // Initialize session when chat opens
  useEffect(() => {
    if (open && sessionId) {
      initializeSession();
    }
  }, [open, sessionId]);

  async function sendChatRequest(query: string, slotValues?: SlotValues) {
    const sid = sessionId || createSessionId();
    if (!sessionId) {
      setSessionId(sid);
      try {
        window.localStorage.setItem(SESSION_STORAGE_KEY, sid);
      } catch {
        // ignore
      }
    }

    const extraData: any = {};
    if (slotValues && Object.keys(slotValues).length > 0) {
      extraData.slot_values = slotValues;
    }

    const apiBaseUrl = getApiBaseUrl();
    
    // CRITICAL FIX: Always send dynamic_url in chat requests
    const resp = await fetch(`${apiBaseUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: query,
        session_id: sid,
        dynamic_url: currentUrl, // Always include current URL
        ...extraData,
      }),
    });

    return resp;
  }

  async function handleSend(text: string, slotValues?: SlotValues) {
    if (isSending) return;
    setIsSending(true);

    const userId = `user-${Date.now()}`;
    const typingId = `typing-${Date.now() + 1}`;

    setMessages((prev) => [
      ...prev,
      {
        id: userId,
        role: "user" as const,
        text,
      },
      {
        id: typingId,
        role: "assistant" as const,
        text: "thinking...",
      },
    ]);

    try {
      const resp = await sendChatRequest(text, slotValues);
      if (!resp.ok) throw new Error("bad_response");

      const data: any = await resp.json();
      console.log("API response data:", data);

      // CRITICAL FIX: Use 'response' field instead of 'message'
      // Backend sends ChatResponse with 'response' field
      const assistantText: string = data.response || data.message || "I couldn't process that request.";

      // Handle suggestions state if present
      const payload = data?.api_response ?? data;
      const collecting =
        payload?.status === "collecting" ||
        Boolean(payload?.suggestions) ||
        (Array.isArray(payload?.missing_fields) && payload.missing_fields.length > 0);

      setSuggestionsState(
        collecting
          ? {
              status: payload?.status,
              missing_fields: Array.isArray(payload?.missing_fields) ? payload.missing_fields : [],
              draft_payload: payload?.draft_payload,
              suggestions: payload?.suggestions,
            }
          : null
      );

      // Replace typing indicator with actual response
      setMessages((prev) =>
        prev.map((m) =>
          m.id === typingId
            ? {
                id: `api-${Date.now()}`,
                role: "assistant" as const,
                text: assistantText,
              }
            : m
        )
      );
    } catch (err) {
      console.error("Chat error:", err);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === typingId
            ? {
                id: `err-${Date.now()}`,
                role: "assistant",
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
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-[2147483647]
          flex items-center gap-2 rounded-full bg-gradient-to-r from-chat-accent to-chat-primary
          px-6 py-3.5 text-sm font-semibold text-white shadow-xl
          hover:shadow-2xl hover:scale-105 transition-all duration-200
          ring-2 ring-white ring-offset-2"
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
        Chat with AI
      </button>

      {/* Popup */}
      {open && (
        <div className="fixed bottom-24 right-5 z-[2147483647]
          flex h-[600px] w-[400px] flex-col
          rounded-2xl bg-white shadow-2xl border border-chat-border overflow-hidden"
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

          <ChatMessages messages={messages} />
          
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