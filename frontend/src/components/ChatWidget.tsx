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

  // Fallback: not a perfect UUID, but unique enough for per-tab chat sessions.
  return `sid-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function safeStringify(value: unknown): string {
  try {
    if (typeof value === "string") return value;
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [suggestionsState, setSuggestionsState] = useState<SuggestionsState | null>(null);

  const [sessionId, setSessionId] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(SESSION_STORAGE_KEY) ?? "";
  });

  const [countryInput, setCountryInput] = useState("");
  const [productInput, setProductInput] = useState("");

  // Show initial welcome message the first time the chat is opened
  useEffect(() => {
    if (open && messages.length === 0) {
      // Generate/persist a session_id at chat start
      if (!sessionId) {
        const newSessionId = createSessionId();
        setSessionId(newSessionId);
        try {
          window.localStorage.setItem(SESSION_STORAGE_KEY, newSessionId);
        } catch {
          // ignore storage failures
        }
      }

      setMessages([
        {
          id: "welcome-1",
          role: "assistant",
          text: "Hi! I’m your trade intelligence assistant. Ask me anything about markets, products or companies.",
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

    // Backend shape: suggestions: [{ field, type, options: [{label,value}...] }]
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

  // Get current page URL for dynamic content
  const getCurrentPageUrl = (): string => {
    try {
      return window.location.href;
    } catch {
      return "";
    }
  };

  const [currentUrl, setCurrentUrl] = useState(getCurrentPageUrl());

  // Monitor URL changes (for SPAs)
  useEffect(() => {
    const handleUrlChange = () => {
      const newUrl = getCurrentPageUrl();
      if (newUrl !== currentUrl) {
        setCurrentUrl(newUrl);
        console.log("URL changed to:", newUrl);
      }
    };

    // Listen for history changes (pushState, replaceState)
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

    // Listen for popstate (back/forward buttons)
    window.addEventListener('popstate', handleUrlChange);

    return () => {
      history.pushState = originalPushState;
      history.replaceState = originalReplaceState;
      window.removeEventListener('popstate', handleUrlChange);
    };
  }, [currentUrl]);

  // Get API base URL from config or default
  const getApiBaseUrl = (): string => {
    // Check for global config
    if (typeof window !== "undefined" && (window as any).CHATBOT_CONFIG) {
      return (window as any).CHATBOT_CONFIG.apiUrl || "http://localhost:8003";
    }
    return "http://localhost:8003";
  };

  async function sendChatRequest(query: string, slotValues?: SlotValues) {
    const sid = sessionId || createSessionId();
    if (!sessionId) {
      setSessionId(sid);
      try {
        window.localStorage.setItem(SESSION_STORAGE_KEY, sid);
      } catch {
        // ignore storage failures
      }
    }

    const extraData: any = {};
    if (slotValues && Object.keys(slotValues).length > 0) extraData.slot_values = slotValues;

    const apiBaseUrl = getApiBaseUrl();
    const resp = await fetch(`${apiBaseUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: query,
        session_id: sid,
        dynamic_url: currentUrl, // Pass current page URL
        ...extraData,
      }),
    });

    return resp;
  }

  // Initialize session with current URL
  async function initializeSession() {
    const sid = sessionId || createSessionId();
    if (!sessionId) {
      setSessionId(sid);
      try {
        window.localStorage.setItem(SESSION_STORAGE_KEY, sid);
      } catch {
        // ignore storage failures
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

        // Optionally show suggested questions
        if (data.suggested_questions && Array.isArray(data.suggested_questions)) {
          // Store suggested questions if needed
          console.log("Suggested questions:", data.suggested_questions);
        }
      }
    } catch (error) {
      console.error("Failed to initialize session:", error);
    }
  }

  // Initialize session when chat opens
  useEffect(() => {
    if (open && !sessionId) {
      initializeSession();
    }
  }, [open]);

  async function handleSend(text: string, slotValues?: SlotValues) {
    if (isSending) return; // prevent duplicate sends
    setIsSending(true);

    const userId = `user-${Date.now()}`;
    const typingId = `typing-${Date.now() + 1}`;

    // add user's message and a typing indicator
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

      // Your backend may wrap the payload under api_response
      const payload = data?.api_response ?? data;

      const assistantText: string =
        typeof payload?.message === "string"
          ? payload.message
          : typeof payload?.answer === "string"
          ? payload.answer
          : "";

      const collecting =
        payload?.status === "collecting" ||
        data?.state?.status === "collecting" ||
        Boolean(payload?.suggestions) ||
        Boolean(data?.suggestions) ||
        (Array.isArray(payload?.missing_fields) && payload.missing_fields.length > 0) ||
        (Array.isArray(data?.state?.missing_fields) && data.state.missing_fields.length > 0);

      setSuggestionsState(
        collecting
          ? {
              status: payload?.status ?? data?.state?.status,
              missing_fields: Array.isArray(payload?.missing_fields)
                ? payload.missing_fields
                : Array.isArray(data?.state?.missing_fields)
                ? data.state.missing_fields
                : [],
              draft_payload: payload?.draft_payload ?? data?.state?.draft_payload,
              suggestions: payload?.suggestions ?? data?.suggestions,
            }
          : null
      );

      // replace typing message with actual assistant response
      setMessages((prev) => {
        const replaced = prev.map((m) =>
          m.id === typingId
            ? {
                id: `api-${Date.now()}`,
                role: "assistant" as const,
                text: data.message,
              }
            : m
        );

        // If final response includes data, render it as an additional message.
        // const finalData = payload?.data ?? data?.data ?? payload?.api_response?.data;
        // if (!collecting && finalData != null) {
        //   const rendered = safeStringify(finalData);
        //   const trimmed = rendered.length > 4000 ? `${rendered.slice(0, 4000)}\n…` : rendered;
        //   return [
        //     ...replaced,
        //     {
        //       id: `data-${Date.now()}`,
        //       role: "assistant" as const,
        //       text: trimmed,
        //     },
        //   ];
        // }

        return replaced;
      });
    } catch (err) {
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
          rounded-full bg-chat-primary px-5 py-3
          text-sm font-medium text-white shadow-lg"
      >
        💬 Chat
      </button>

      {/* Popup */}
      {open && (
        <div className="fixed bottom-20 right-5 z-[2147483647]
          flex h-[480px] w-[340px] flex-col
          rounded-xl bg-chat-bg shadow-2xl"
        >
          <ChatHeader onClose={() => setOpen(false)} />
          <ChatMessages messages={messages} />
          {isCollecting && (
            <div className="border-t px-4 py-3">
              {missingFields.length > 0 && (
                <div className="mb-2 text-xs text-chat-text">
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
                      className={`rounded-lg bg-chat-accent px-3 py-2 text-xs font-medium text-white hover:opacity-90 ${
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
                    className={`flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm text-chat-text focus:outline-none focus:ring-1 focus:ring-chat-primary ${
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
                    className={`rounded-lg bg-chat-accent px-3 py-2 text-xs font-medium text-white hover:opacity-90 ${
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
                    className={`flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm text-chat-text focus:outline-none focus:ring-1 focus:ring-chat-primary ${
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
                    className={`rounded-lg bg-chat-accent px-3 py-2 text-xs font-medium text-white hover:opacity-90 ${
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
