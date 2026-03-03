import { useEffect, useMemo, useRef, useState } from "react";
import { ChatHeader } from "./ChatHeader";
import { ChatMessages } from "./ChatMessages";
import { ChatFooter, type ChatFooterHandle } from "./ChatFooter";
import genericQA from "../data/genericQA.json";
import WhatsAppDropdown from "./WhatsAppDropdown";
// import VoiceChat from "./VoiceChat"; // Commented out - will add back later
import whatsappQr from  "../../public/whatsapp-qr.avif"

export type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
  actions?: {
    type: "schedule_demo" | "whatsapp" | "call" | "hubspot_chat" | "chat_with_us" | "chat" | "refresh" | "continue_chat";
    label: string;
  }[];
  suggestions?: string[]; // For pill buttons from init
  exploreUrl?: string; // Dynamic explore URL for data queries
  isCreditExhausted?: boolean; // Marks credit exhaustion messages
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

// CTA questions to randomize for the 2nd slot
const CTA_QUESTIONS = [
  "I want to schedule a product demo",
  "I want to find new customers",
  "I need to consult with an expert"
];

// Get a random CTA question
function getRandomCTAQuestion(): string {
  const randomIndex = Math.floor(Math.random() * CTA_QUESTIONS.length);
  return CTA_QUESTIONS[randomIndex];
}

// Generate initial questions with randomized CTA
function getInitialQuestions(): string[] {
  return [
    "I want to know about your products and services",
    getRandomCTAQuestion(),
    "I want to learn about your data"
  ];
}

const INITIAL_QUESTIONS = getInitialQuestions();

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
  // const [voiceMode, setVoiceMode] = useState(false); // Commented out - will add back later

  const [sessionId, setSessionId] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(SESSION_STORAGE_KEY) ?? "";
  });

  const [countryInput, setCountryInput] = useState("");
  const [productInput, setProductInput] = useState("");
  const [currentUrl, setCurrentUrl] = useState("");
  const [isInitializing, setIsInitializing] = useState(false);

  // Initialize with generic questions from JSON
 const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>(INITIAL_QUESTIONS);

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

  // Credit exhaustion state
  const [_creditExhausted, setCreditExhausted] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  // Refs
  const currentUrlRef = useRef<string>("");
  const sessionIdRef = useRef<string>(sessionId);
  const footerRef = useRef<ChatFooterHandle | null>(null);
  const isSendingRef = useRef<boolean>(false);

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
    return suggestedQuestions.slice(0, 3).map(q => ({
      title: q,
      description: generateQuestionDescription(q)
    }));
  }, [suggestedQuestions]);

  // Track current URL for init calls
  useEffect(() => {
  if (typeof window === "undefined") return;

  const updateUrl = () => {
    const url = window.location.href;
    currentUrlRef.current = url;
    setCurrentUrl(url);
  };

  // Run once
  updateUrl();

  // Listen to navigation
  window.addEventListener("popstate", updateUrl);

  // Patch pushState / replaceState (important for SPAs)
  const pushState = history.pushState;
  const replaceState = history.replaceState;

  history.pushState = function (...args) {
    pushState.apply(this, args as any);
    updateUrl();
  };

  history.replaceState = function (...args) {
    replaceState.apply(this, args as any);
    updateUrl();
  };

  return () => {
    window.removeEventListener("popstate", updateUrl);
    history.pushState = pushState;
    history.replaceState = replaceState;
  };
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

  // Load chat history on mount (for page refresh recovery)
  useEffect(() => {
    if (!sessionId || historyLoaded) return;

    const loadHistory = async () => {
      try {
        const apiBaseUrl = getApiBaseUrl();
        const resp = await fetch(`${apiBaseUrl}/api/history/${sessionId}`);

        if (resp.ok) {
          const data = await resp.json();

          if (data.messages && data.messages.length > 0) {
            console.log('[History] Loaded', data.messages.length, 'messages');

            const loadedMessages: ChatMessage[] = data.messages.map((m: any, idx: number) => ({
              id: m.message_id || `history-${idx}`,
              role: m.role as "user" | "assistant",
              text: m.content,
              exploreUrl: m.explore_url || undefined
            }));

            setMessages(loadedMessages);

            // Also restore suggested questions if available
            if (data.suggested_questions && data.suggested_questions.length > 0) {
              setSuggestedQuestions(data.suggested_questions);
            }
          }

          setHistoryLoaded(true);
        }
      } catch (error) {
        console.error('[History] Failed to load:', error);
        setHistoryLoaded(true);
      }
    };

    loadHistory();
  }, [sessionId, historyLoaded]);


// const lastInitUrlRef = useRef<string>("");

// useEffect(() => {
//   if (!currentUrl) return;
//   if (lastInitUrlRef.current === currentUrl) return;

//   lastInitUrlRef.current = currentUrl;
//   _initializeSession();
// }, [currentUrl]);

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

  // Get API base URL - memoized to avoid re-renders
  const apiBaseUrl = useMemo(() => {
    let url = "http://localhost:8000";
    if (typeof window !== "undefined" && (window as any).CHATBOT_CONFIG) {
      url = (window as any).CHATBOT_CONFIG.apiUrl || url;
    }
    // Remove trailing slash to prevent double slashes in API calls
    return url.replace(/\/$/, '');
  }, []);

  // Helper function for backward compatibility
  const getApiBaseUrl = (): string => apiBaseUrl;

  // Memoize VoiceChat component to prevent unmounting on parent re-renders
  // Commented out - will add back later
  // const voiceChatComponent = useMemo(() => {
  //   console.log('[ChatWidget] Creating VoiceChat with apiUrl:', apiBaseUrl);
  //   return (
  //     <VoiceChat
  //       key="voice-chat-stable"
  //       sessionId={sessionId}
  //       apiUrl={apiBaseUrl}
  //     />
  //   );
  // }, [sessionId, apiBaseUrl]); // Re-create if sessionId OR apiUrl changes

  // Check if query matches connect/help intent
  const isConnectHelpIntent = (query: string): boolean => {
    const normalizedQuery = query.toLowerCase().trim();

    // Direct keyword checks for better reliability
    const connectKeywords = [
      'connect me',
      'connect with',
      'connect to',
      'talk to someone',
      'talk to a person',
      'talk to support',
      'talk to agent',
      'talk to an agent',
      'talk to a agent',
      'talk to human',
      'speak to someone',
      'speak to a person',
      'speak to support',
      'speak to agent',
      'speak with someone',
      'speak with support',
      'human agent',
      'real person',
      'customer support',
      'customer service',
      'contact support',
      'contact team',
      'contact someone',
      'get help',
      'need help',
      'need assistance',
      'need support',
      'i need assistance',
      'i need support',
      'help me connect',
      'can you help',
      'could you help',
      'can you connect',
      'could you connect',
      'can i talk',
      'can i speak',
      'can i connect',
      'get in touch',
      'reach out',
      'want to connect',
      'looking to connect',
    ];

    // Check if any keyword is present in the query
    const hasConnectKeyword = connectKeywords.some(keyword =>
      normalizedQuery.includes(keyword)
    );

    if (hasConnectKeyword) {
      console.log('[ChatWidget] Connect/help intent detected:', normalizedQuery);
      return true;
    }

    return false;
  };

  // Generic Q&A checker
  const checkGenericQA = async (userQuery: string): Promise<ChatMessage | null | 'INIT_CALL'> => {
    const normalizedQuery = userQuery.trim();

    // Special case: "I want to learn about your data" should call init
    if (normalizedQuery === "I want to learn about your data") {
      // Return special marker to indicate init call is needed
      return 'INIT_CALL';
    }

    // Check for connect/help intent - show support options card
    if (isConnectHelpIntent(normalizedQuery)) {
      return {
        id: `connect-support-${Date.now()}`,
        role: "assistant",
        text: "I'd be happy to connect you with our team! Choose the option that works best for you:",
        actions: [
          { type: "schedule_demo", label: "Schedule a Demo" },
          { type: "chat_with_us", label: "Chat" },
          { type: "whatsapp", label: "WhatsApp" },
          { type: "continue_chat", label: "Continue Chat" }
        ],
        isCreditExhausted: true // Reuse the credit exhaustion card UI
      };
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
      actions.push(
        {
          type: "whatsapp",
          label: "WhatsApp"
        },
        {
          type: "call",
          label: "Call"
        },
        {
          type: "hubspot_chat",
          label: "Chat"
        }
      );
    } else if (qaEntry.type === "hybrid" && qaEntry.actions) {
      if (qaEntry.actions.includes("chat")) {
        actions.push({
          type: "refresh",
          label: "Show Suggested Questions"
        });
      }
      if (qaEntry.actions.includes("schedule_demo")) {
        actions.push({
          type: "schedule_demo",
          label: "Schedule a Demo"
        });
      }
    } else if (qaEntry.type === "precached") {
      // Precached static KB response - add schedule demo option
      actions.push({
        type: "schedule_demo",
        label: "Schedule a Demo"
      });
    }

    return {
      id: `generic-${Date.now()}`,
      role: "assistant",
      text: qaEntry.message,
      actions: actions.length > 0 ? actions : undefined
    };
  };

  // Call init and show suggested questions as chat message
  const callInitAndShowQuestions = async (assistantMsgId?: string) => {
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

        setSuggestedQuestions(data.suggested_questions);

        if (data.suggested_questions && Array.isArray(data.suggested_questions)) {
          // Add assistant message with data info and pill buttons
          const assistantMsg: ChatMessage = {
            id: assistantMsgId || `init-${Date.now()}`,
            role: "assistant",
            text: "We provide comprehensive trade data covering 190+ countries with detailed import/export records, HS codes, company information, and real-time trade intelligence. Here are some questions you can ask:",
            suggestions: data.suggested_questions
          };
          
          // If we have an assistantMsgId, update existing message; otherwise add new one
          if (assistantMsgId) {
            console.log('[callInitAndShowQuestions] Updating existing message with id:', assistantMsgId);
            setMessages((prev) => prev.map(m => m.id === assistantMsgId ? assistantMsg : m));
          } else {
            console.log('[callInitAndShowQuestions] Adding new message');
            setMessages((prev) => [...prev, assistantMsg]);
          }
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
  // const openWhatsApp = (option?: 'qr' | 'link') => {
  //   const waLink = "https://wa.me/447727449124";
  //   const qrPath = "/assets/whatsapp-qr.png";

  //   // If no option provided, ask the user (replace this prompt with a dropdown UI if you want)
  //   if (typeof window !== "undefined" && !option) {
  //     const choice = window
  //       .prompt('Enter "qr" to view the QR code or "link" to open WhatsApp', 'link')
  //       ?.toLowerCase();
  //     option = choice === "qr" ? "qr" : "link";
  //   }

  //   if (option === "qr") {
  //     // Open QR image in a new tab (or implement an in-widget modal instead)
  //     if (typeof window !== "undefined") {
  //       const qrUrl = `${window.location.origin}${qrPath}`;
  //       window.open(qrUrl, "_blank");
  //     }
  //   } else {
  //     // Open wa.me link
  //     window.open(waLink, "_blank");
  //   }
  // };

  

  // Handle continue chat after credit exhaustion
  const handleContinueChat = async () => {
    try {
      const apiBaseUrl = getApiBaseUrl();
      const resp = await fetch(`${apiBaseUrl}/api/continue-chat?session_id=${sessionId}`, {
        method: 'POST'
      });

      if (resp.ok) {
        const data = await resp.json();
        setCreditExhausted(false);

        // Add confirmation message
        setMessages(prev => [...prev, {
          id: `continue-${Date.now()}`,
          role: 'assistant',
          text: data.message || "I'm happy to continue helping you explore our trade data. What would you like to know?"
        }]);
      }
    } catch (error) {
      console.error('[ContinueChat] Error:', error);
    }
  };
  // Handle action button clicks
  const handleActionClick = (actionType: string, originalQuery?: string) => {
    if (actionType === "schedule_demo") {
      openScheduleDemo();
    } else if (actionType === "whatsapp") {
      // Open the options menu and show the WhatsApp submenu so users can choose QR or link
      setShowOptionsMenu(true);
      // small timeout to ensure menu container is visible before showing submenu
      setTimeout(() => setShowWhatsAppSubmenu(true), 80);
    } else if (actionType === "call") {
      window.location.href = "tel:+4407727449124";
    } else if (actionType === "hubspot_chat" || actionType === "chat_with_us") {
      // Hide AI chatbot and switch to Odoo livechat
      setOpen(false);
      setIsHiddenForOdoo(true);
      void sendContextToOdooAndOpenChat();
    } else if (actionType === "refresh") {
      // Call init API to show suggested questions
      void callInitAndShowQuestions();
    } else if (actionType === "chat" && originalQuery) {
      // Handle suggestion pill clicks - send the suggestion as a message
      void handleSend(originalQuery);
    } else if (actionType === "continue_chat") {
      // Handle continue chat after credit exhaustion
      void handleContinueChat();
    }
  };

  // Send conversation context to Odoo and open Odoo chat
  const sendContextToOdooAndOpenChat = async () => {
    console.log("[ODOO] Chat with us clicked — session_id:", sessionIdRef.current);

    const apiOrigin = new URL(import.meta.env.VITE_API_URL || "https://chatbot.exportgenius.in").origin;

    // ── Step 1: Click the Odoo chatbox button ────────────────────────────────
    // The button lives inside the shadow DOM of <o-livechat-root>.
    // We MUST open it this way so Odoo calls get_session for THIS channel —
    // if we call get_session ourselves we'd get a different channel/agent.
    const openOdoo = (): boolean => {
      // Remove the initial CSS hide so Odoo is visible before we click its button
      const _hideEl = document.getElementById('odoo-init-hide');
      if (_hideEl) { _hideEl.remove(); console.log('[ODOO] initial hide style removed'); }

      // Odoo 17 renders a <div class="o-livechat-root"> with a shadow root.
      // NOTE: selector must use "." prefix (class), NOT a bare tag name.
      const host = document.querySelector(".o-livechat-root") as (HTMLElement & { shadowRoot?: ShadowRoot }) | null;
      if (host?.shadowRoot) {
        // Priority order: bubble button (avatar) → openChatButton part → LivechatButton class → any non-utility button
        const btn = host.shadowRoot.querySelector(
          ".o-mail-ChatHub-bubbleBtn.btn.shadow, " +
          ".o-mail-ChatHub-bubbleBtn:not(.o-mail-ChatHub-optionsBtn), " +
          "button[part='openChatButton'], " +
          ".o-livechat-LivechatButton, " +
          "button:not(.o-mail-ChatHub-optionsBtn):not(.o-mail-ChatBubble-close)"
        ) as HTMLElement | null;
        if (btn) {
          console.log("[ODOO] Shadow button found, clicking:", btn.getAttribute("part") || btn.className);
          btn.click();
          return true;
        }
        // Shadow root exists but no usable button found — click host as fallback
        host.click();
        console.log("[ODOO] Clicked .o-livechat-root host (no inner button matched)");
        return true;
      }

      // Fallback: regular DOM (older Odoo versions or non-shadow rendering)
      for (const sel of [
        ".o-livechat-LivechatButton",
        "button[part='openChatButton']",
        ".o_livechat_button",
        ".o_im_livechat_button",
        "#o_livechat_button"
      ]) {
        const btn = document.querySelector(sel) as HTMLElement | null;
        if (btn) { console.log("[ODOO] Clicked DOM button:", sel); btn.click(); return true; }
      }

      // Last resort: scan all shadow roots
      const all = document.querySelectorAll("*");
      for (let j = 0; j < all.length; j++) {
        const root = (all[j] as HTMLElement & { shadowRoot?: ShadowRoot }).shadowRoot;
        if (!root) continue;
        const anyBtn = root.querySelector(
          ".o-mail-ChatHub-bubbleBtn:not(.o-mail-ChatHub-optionsBtn), button[part='openChatButton'], .o-livechat-LivechatButton"
        ) as HTMLElement | null;
        if (anyBtn) {
          console.log("[ODOO] Clicked shadow button in:", all[j].tagName, anyBtn.className);
          anyBtn.click();
          return true;
        }
      }

      console.warn("[ODOO] Odoo livechat button not found in DOM or shadowDOM");
      return false;
    };

    const clicked = openOdoo();
    if (!clicked) {
      // Nothing to do — Odoo widget not on this page
      return;
    }

    // ── Step 2: Start listening for session BEFORE sending message ───────────
    // We set up the promise NOW so we don't miss the event that fires when
    // Odoo calls get_session in response to the first message send.
    const waitForOdooSession = (): Promise<{ guest_token: string; channel_id: number }> => {
      return new Promise((resolve, reject) => {
        // Already captured from a previous open? Reuse it.
        const cached = (window as any).__odoo_session__ as { guest_token?: string; channel_id?: number } | undefined;
        if (cached?.guest_token && cached?.channel_id && cached.channel_id > 0) {
          console.log("[ODOO] Reusing cached session — channel_id:", cached.channel_id);
          resolve(cached as { guest_token: string; channel_id: number });
          return;
        }

        let resolved = false;
        const doResolve = (d: { guest_token: string; channel_id: number }) => {
          if (resolved) return;
          resolved = true;
          clearInterval(pollTimer);
          clearTimeout(timer);
          window.removeEventListener("odoo:session-ready", onReady);
          resolve(d);
        };

        // Listen for the interceptor event (fired by layout.tsx after get_session response)
        const onReady = (e: Event) => {
          const d = (e as CustomEvent<{ guest_token: string; channel_id: number }>).detail;
          if (d?.guest_token && d?.channel_id > 0) {
            console.log("[ODOO] odoo:session-ready event received — channel_id:", d.channel_id);
            doResolve(d);
          }
        };
        window.addEventListener("odoo:session-ready", onReady);

        // Polling fallback: check window.__odoo_session__ every 300 ms
        // Catches cases where get_session fired BEFORE this listener was set up,
        // or where the event was dispatched but missed.
        const pollTimer = setInterval(() => {
          const s = (window as any).__odoo_session__ as { guest_token?: string; channel_id?: number } | undefined;
          if (s?.guest_token && s?.channel_id && s.channel_id > 0) {
            console.log("[ODOO] Polled session — channel_id:", s.channel_id);
            doResolve(s as { guest_token: string; channel_id: number });
          }
        }, 300);

        // Allow up to 20 s — covers: chat window render + message send + get_session round-trip
        const timer = setTimeout(() => {
          if (!resolved) {
            resolved = true;
            clearInterval(pollTimer);
            window.removeEventListener("odoo:session-ready", onReady);
            reject(new Error("Odoo did not return a session within 20 s"));
          }
        }, 20_000);
      });
    };

    // Register the listener immediately (before the message send that triggers get_session)
    const sessionPromise = waitForOdooSession();

    // ── Backup interceptor: wrap fetch ourselves for 30 s ─────────────────────
    // This catches get_session even if the layout.tsx interceptor failed to
    // extract the guest_token (e.g. wrong response path, installed too late).
    const _origFetch = (window as any).__odoo_backup_orig_fetch__ || window.fetch;
    (window as any).__odoo_backup_orig_fetch__ = _origFetch;
    let _backupRestored = false;
    const _restoreBackup = () => {
      if (!_backupRestored) { _backupRestored = true; window.fetch = _origFetch; }
    };
    const _backupTimer = setTimeout(_restoreBackup, 30_000);

    // Helper: fire session-ready from a known guest_token + channel_id pair
    const _emitSession = (gt: string, cid: number, source: string) => {
      if (!(window as any).__odoo_session__?.guest_token) {
        console.log(`[ODOO-backup] session captured via ${source} — channel_id:`, cid, 'guest_token: ***set***');
        (window as any).__odoo_session__ = { guest_token: gt, channel_id: cid };
        window.dispatchEvent(new CustomEvent('odoo:session-ready', { detail: { guest_token: gt, channel_id: cid } }));
        clearTimeout(_backupTimer);
        _restoreBackup();
      }
    };

    if (!(window as any).__odoo_session__?.guest_token) {
      window.fetch = function(input: RequestInfo | URL, init?: RequestInit) {
        let reqUrl = '';
        try { reqUrl = typeof input === 'string' ? input : (input as Request).url ?? String(input); } catch(e) { /**/ }

        // ── Extract from message/post REQUEST body (most reliable path) ──────
        // The guest_token and thread_id are sent plainly in the outgoing payload.
        if (reqUrl.indexOf('/im_livechat/cors/message/post') !== -1 ||
            reqUrl.indexOf('/mail/message/post') !== -1) {
          try {
            const bodyStr = typeof init?.body === 'string' ? init.body : '';
            if (bodyStr) {
              const bodyJson = JSON.parse(bodyStr);
              const params = bodyJson?.params ?? {};
              const gt: string | undefined = params.guest_token;
              // thread_id is the channel id
              const cid: number | undefined = typeof params.thread_id === 'number' ? params.thread_id : undefined;
              if (gt && cid && cid > 0) {
                _emitSession(gt, cid, 'message/post request body');
              }
            }
          } catch(e) { /**/ }
        }

        const promise = _origFetch(input, init);

        // ── Also keep get_session RESPONSE extraction as secondary fallback ──
        if (reqUrl.indexOf('/im_livechat/cors/get_session') !== -1) {
          promise.then((resp: Response) => {
            resp.clone().json().then((json: any) => {
              try {
                const result = json?.result;
                if (!result) return;
                console.log('[ODOO-backup] get_session raw (first 800 chars):', JSON.stringify(result).substring(0, 800));

                // Try every known guest_token location
                let gt: string | null = null;
                const sd: any = result.store_data || {};
                if (sd?.Store?.guest_token)   gt = sd.Store.guest_token;
                if (!gt && sd['res.guest']) {
                  const recs: any[] = Array.isArray(sd['res.guest']) ? sd['res.guest'] : Object.values(sd['res.guest']);
                  for (const rec of recs) { if (rec?.access_token || rec?.guest_token) { gt = rec.access_token || rec.guest_token; break; } }
                }
                if (!gt) gt = result.guest_token ?? null;
                if (!gt) {
                  for (const key of Object.keys(sd)) {
                    const blk: any = sd[key];
                    const items: any[] = Array.isArray(blk) ? blk : Object.values(blk ?? {});
                    for (const item of items) {
                      if (item && (item.guest_token || item.access_token)) {
                        gt = item.guest_token || item.access_token;
                        console.log('[ODOO-backup] guest_token found in store_data.' + key);
                        break;
                      }
                    }
                    if (gt) break;
                  }
                }

                const cid: number = result.channel_id;
                console.log('[ODOO-backup] channelId:', cid, 'guestToken found:', !!gt);

                if (gt && typeof cid === 'number' && cid > 0) {
                  _emitSession(gt, cid, 'get_session response');
                }
              } catch(e) { /**/ }
            }).catch(() => { /**/ });
          }).catch(() => { /**/ });
        }

        return promise;
      } as typeof fetch;
    }

    // ── Step 3: Type and send a message via the Odoo chat input ──────────────
    // Odoo calls get_session only when the FIRST message is sent — so we must
    // send a message ourselves to trigger that call and capture the guest_token.
    const   sendMessageViaOdooInput = async (text: string): Promise<boolean> => {
      // Find the shadow root that contains Odoo's chat window
      const getShadowRoot = (): ShadowRoot | null => {
        const host = document.querySelector(".o-livechat-root") as (HTMLElement & { shadowRoot?: ShadowRoot }) | null;
        if (host?.shadowRoot) return host.shadowRoot;
        // Fallback: scan every element's shadow root
        const all = document.querySelectorAll("*");
        for (let i = 0; i < all.length; i++) {
          const r = (all[i] as HTMLElement & { shadowRoot?: ShadowRoot }).shadowRoot;
          if (r) return r;
        }
        return null;
      };

      // Poll for the composer input — Odoo needs ~1-3 s to render the chat window
      let input: HTMLElement | null = null;
      let shadowRoot: ShadowRoot | null = null;

      for (let i = 0; i < 80; i++) {  // up to 8 s
        shadowRoot = getShadowRoot();
        if (shadowRoot) {
          input = shadowRoot.querySelector(
            "textarea.o-mail-Composer-input, " +
            ".o-mail-Composer-input, " +
            "textarea[placeholder], " +
            "div[contenteditable='true']"
          ) as HTMLElement | null;
          if (input) break;
        }
        await new Promise(r => setTimeout(r, 100));
      }

      if (!input) {
        console.warn("[ODOO] Composer input not found after 8 s");
        return false;
      }

      console.log("[ODOO] Composer input found:", input.tagName, input.className);
      input.focus();
      await new Promise(r => setTimeout(r, 80));

      // Set value — handles both <textarea> and contenteditable <div>
      if (input.tagName === "TEXTAREA" || input.tagName === "INPUT") {
        const textarea = input as HTMLTextAreaElement;
        // Use native value setter so Owl/React change detection fires
        const nativeSetter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
        if (nativeSetter) {
          nativeSetter.call(textarea, text);
        } else {
          textarea.value = text;
        }
        textarea.dispatchEvent(new Event("input",  { bubbles: true, composed: true }));
        textarea.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
      } else {
        // contenteditable div
        input.textContent = text;
        input.dispatchEvent(new Event("input",  { bubbles: true, composed: true }));
        input.dispatchEvent(new InputEvent("input", { bubbles: true, composed: true, data: text }));
      }

      await new Promise(r => setTimeout(r, 200));

      // Submit via Enter key (what Odoo listens to)
      input.dispatchEvent(new KeyboardEvent("keydown",  { key: "Enter", code: "Enter", keyCode: 13, bubbles: true, composed: true }));
      input.dispatchEvent(new KeyboardEvent("keypress", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true, composed: true }));
      input.dispatchEvent(new KeyboardEvent("keyup",    { key: "Enter", code: "Enter", keyCode: 13, bubbles: true, composed: true }));

      await new Promise(r => setTimeout(r, 100));

      // Also click the send button if present
      if (shadowRoot) {
        const sendBtn = shadowRoot.querySelector(
          ".o-mail-Composer-send, button[aria-label='Send'], .o-mail-Composer button[type='submit'], button.o-mail-Composer-send"
        ) as HTMLElement | null;
        if (sendBtn) {
          console.log("[ODOO] Also clicking send button:", sendBtn.className);
          sendBtn.click();
        }
      }

      console.log("[ODOO] Transfer message sent via input");
      return true;
    };

    // Send the transfer message — this is what triggers Odoo's get_session call
    await sendMessageViaOdooInput("🤖 Transferring to a live agent — AI chat context has been shared.");


    // ── Step 4: Wait for session (get_session fires right after message send) ─
    try {
      const { guest_token, channel_id } = await sessionPromise;
      clearTimeout(_backupTimer);
      _restoreBackup();   // restore original fetch
      console.log("[ODOO] Session ready — channel_id:", channel_id, "| guest_token: ***set***");

      // ── Step 5: Send AI conversation history via backend ─────────────────
      // Always use the original (unpatched) fetch so we never intercept ourselves
      try {
        const histRes = await _origFetch(`${apiOrigin}/api/odoo/send-context`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionIdRef.current, guest_token, channel_id })
        });
        const histData = await histRes.json();
        console.log("[ODOO] /odoo/send-context response:", histData);
        if (histData.history_sent) {
          console.log(`[ODOO] History sent — ${histData.message_count} msgs to channel ${histData.odoo_channel_id}`);
        }
      } catch (histErr) {
        console.warn("[ODOO] /odoo/send-context error:", histErr);
      }

    } catch (err) {
      clearTimeout(_backupTimer);
      _restoreBackup();   // always restore fetch
      console.warn("[ODOO] Session wait failed:", (err as Error).message);
      // Chatbox is still open — user can chat with the agent manually
    }
  };

  // Handle feedback submission
  const handleFeedbackSubmit = async (feedbackData: {
    sessionId: string;
    feedbackType: 'thumbs_up' | 'thumbs_down';
    messageId: string;
    assistantMessage: string;
    userQuery?: string;
    reason?: string;
    pageUrl?: string;
    conversation: { role: string; content: string; message_id?: string }[];
  }) => {
    try {
      const apiBaseUrl = getApiBaseUrl();
      const response = await fetch(`${apiBaseUrl}/api/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: feedbackData.sessionId,
          feedback_type: feedbackData.feedbackType,
          message_id: feedbackData.messageId,
          assistant_message: feedbackData.assistantMessage,
          user_query: feedbackData.userQuery,
          comment: feedbackData.reason,
          page_url: feedbackData.pageUrl || currentUrl,
          conversation: feedbackData.conversation.map(msg => ({
            role: msg.role,
            content: msg.content,
            message_id: msg.message_id
          }))
        }),
      });

      if (!response.ok) {
        console.error('[Feedback] API error:', response.status);
      } else {
        const result = await response.json();
        console.log('[Feedback] Submitted successfully:', result);
      }
    } catch (error) {
      console.error('[Feedback] Submit error:', error);
      // Don't throw - feedback failure shouldn't break user experience
    }
  };

  // Handle delayed (idle) feedback submission - AWS style
  const handleDelayedFeedbackSubmit = async (feedbackData: {
    sessionId: string;
    feedbackType: 'rating';
    rating: number;
    workedWell: string[];
    comment?: string;
    pageUrl?: string;
    conversation: { role: string; content: string; message_id?: string }[];
  }) => {
    try {
      const apiBaseUrl = getApiBaseUrl();
      const response = await fetch(`${apiBaseUrl}/api/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: feedbackData.sessionId,
          feedback_type: feedbackData.feedbackType,
          rating: feedbackData.rating,
          comment: feedbackData.workedWell.length > 0
            ? `Worked well: ${feedbackData.workedWell.join(', ')}${feedbackData.comment ? `. Additional: ${feedbackData.comment}` : ''}`
            : feedbackData.comment,
          page_url: feedbackData.pageUrl || currentUrl,
          conversation: feedbackData.conversation.map(msg => ({
            role: msg.role,
            content: msg.content,
            message_id: msg.message_id
          }))
        }),
      });

      if (!response.ok) {
        console.error('[DelayedFeedback] API error:', response.status);
      } else {
        const result = await response.json();
        console.log('[DelayedFeedback] Submitted successfully:', result);
      }
    } catch (error) {
      console.error('[DelayedFeedback] Submit error:', error);
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
      // Create abort controller for timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000); // 120 second timeout

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
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok) throw new Error("Stream request failed");
        if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulatedText = "";
      let lineBuffer = "";   // buffer incomplete SSE lines across reads

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log('[SSE] Stream done, breaking');
          break;
        }

        lineBuffer += decoder.decode(value, { stream: true });

        // Split on newlines but keep the incomplete last piece in the buffer
        const lines = lineBuffer.split("\n");
        lineBuffer = lines.pop() ?? "";   // last element may be incomplete

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;

          try {
              const jsonStr = line.slice(6).trim();
              if (!jsonStr) continue;
              const data = JSON.parse(jsonStr);

              if (data.heartbeat) continue; // keepalive — backend is still processing

              if (data.error) {
                throw new Error(data.error);
              }

              // Handle credit exhaustion
              if (data.credit_exhausted) {
                console.log('[Stream] Credit exhausted - data:', data);
                setCreditExhausted(true);

                // Build actions for credit exhaustion
                const actions: ChatMessage["actions"] = (data.actions || []).map((a: any) => ({
                  type: a.type as any,
                  label: a.label
                }));

                console.log('[Stream] Built actions:', actions);
                console.log('[Stream] Message text:', data.message);

                setMessages((prev) => {
                  const updated = prev.map((m) =>
                    m.id === assistantMsgId ? {
                      ...m,
                      text: data.message || "Ready to unlock more insights?",
                      actions,
                      isCreditExhausted: true
                    } : m
                  );
                  console.log('[Stream] Updated messages:', updated.filter(m => m.id === assistantMsgId));
                  return updated;
                });
                return data.message;
              }

              // Handle clarifying question
              if (data.clarifying_question) {
                console.log('[Stream] Clarifying question:', data.question);

                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId ? {
                      ...m,
                      text: data.question,
                      suggestions: data.suggestions || []
                    } : m
                  )
                );
                return data.question;
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

                // Handle explore URL if present
                if (data.explore_url) {
                  console.log('[Stream] Explore URL:', data.explore_url);
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId ? { ...m, exploreUrl: data.explore_url } : m
                    )
                  );
                }
              }
            } catch (parseError) {}
          }
        }

      return accumulatedText;
      } catch (fetchError: any) {
        clearTimeout(timeoutId);

        // Handle timeout specifically
        if (fetchError.name === 'AbortError') {
          throw new Error("Request timed out. The server is taking too long to respond. Please try again.");
        }

        throw fetchError;
      }
    } catch (error: any) {
      console.error("Streaming error:", error);

      // Show user-friendly error message
      if (error.message && error.message.includes('timed out')) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, text: "⏱️ The request timed out. Please try again or rephrase your question." }
              : m
          )
        );
      }

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
    // Use ref for synchronous guard — React state update is async and too slow
    if (isSendingRef.current) return;
    isSendingRef.current = true;
    setIsSending(true);

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

      // Handle special init call case
      if (genericResponse === 'INIT_CALL') {
        console.log('[handleSend] INIT_CALL case - showing loader and closing suggestions');
        setSuggestedQuestions([]);
        setMessages((prev) => [
          ...prev,
          { id: assistantId, role: "assistant" as const, text: "" },
        ]);
        await callInitAndShowQuestions(assistantId);
        isSendingRef.current = false;
        setIsSending(false);
        return;
      }

      if (genericResponse) {
        setSuggestedQuestions([]);
        setMessages((prev) => [...prev, genericResponse]);
        isSendingRef.current = false;
        setIsSending(false);
        return;
      }
    }

    // Not a generic question, proceed with streaming API
    console.log('[ChatWidget] Starting to show loader and close suggestions');
    setMessages((prev) => {
      const newMessages = [
        ...prev,
        { id: assistantId, role: "assistant" as const, text: "" },
      ];
      console.log('[ChatWidget] Added empty assistant message for loader', { assistantId, messageCount: newMessages.length });
      return newMessages;
    });
    
    // Close suggested questions after adding the loader message
    setSuggestedQuestions([]);
    console.log('[ChatWidget] Closed suggested questions, isSending=true');

    try {
      await sendStreamingRequest(text, assistantId, slotValues);
      setSuggestionsState(null);
      const currentMessageCount = messages.length + 2;
      checkLeadPrompt(text, currentMessageCount);
      
      // After API response, restore suggested questions
      // const genericQuestions = Object.keys(genericQA).slice(0, 3);
      // setSuggestedQuestions(genericQuestions);
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
      isSendingRef.current = false;
      setIsSending(false);
    }
  }

  // Host integration: expose global API and listen for host events/postMessage
  useEffect(() => {
    let sendTimer: any = null;

    function openChatFromHost() {
      setShowTooltip(false);
      setOpen(true);
    }

    function setChatInputTextFromHost(text: string) {
      if (footerRef.current && typeof footerRef.current.setMessage === 'function') {
        footerRef.current.setMessage(text);
        return;
      }
      // If footer not mounted yet, open and retry
      openChatFromHost();
      setTimeout(() => footerRef.current?.setMessage(text), 120);
    }

    function triggerSendFromHost() {
      if (footerRef.current && typeof footerRef.current.send === 'function') {
        footerRef.current.send();
        return;
      }
      setTimeout(() => footerRef.current?.send(), 150);
    }

    // Attach stable API
    (window as any).chatWidget = (window as any).chatWidget || {};
    (window as any).chatWidget.sendMessage = (text: string, opts?: { autoSend?: boolean; debounceMs?: number }) => {
      openChatFromHost();
      setChatInputTextFromHost(text);
      if (opts?.autoSend === false) return;
      const ms = typeof opts?.debounceMs === 'number' ? opts!.debounceMs : 350;
      if (sendTimer) clearTimeout(sendTimer);
      sendTimer = setTimeout(() => triggerSendFromHost(), ms);
    };
    (window as any).chatWidget.setMessage = (text: string) => {
      openChatFromHost();
      setChatInputTextFromHost(text);
    };

    // Backwards-compatible globals
    (window as any).openChatWithMessage = (window as any).openChatWithMessage || function (text?: string) {
      openChatFromHost();
      if (typeof text === 'string') setChatInputTextFromHost(text);
    };
    (window as any).openLiveChat = (window as any).openLiveChat || function () { openChatFromHost(); };

    const onAction = (e: any) => {
      try {
        const detail = e?.detail || {};
        const action = detail.action;
        const message = detail.message;

        // Open the chat UI
        if (action === 'open') {
          openChatFromHost();
          return;
        }

        // Prefill input only
        if (action === 'prefill' && typeof message === 'string') {
          openChatFromHost();
          setChatInputTextFromHost(message);
          return;
        }

        // Prefill and auto-send
        if (action === 'sendMessage' && typeof message === 'string') {
          openChatFromHost();
          setChatInputTextFromHost(message);
          triggerSendFromHost();
          return;
        }

        // Host asked widget to open Schedule Demo on the main site
        if (action === 'openScheduleDemo') {
          try {
            if (typeof (window as any).openScheduleDemo === 'function') {
              (window as any).openScheduleDemo();
            } else {
              window.dispatchEvent(new CustomEvent('chatWidget:request', { detail: { action: 'openScheduleDemo' } }));
            }
          } catch (err) {
            console.warn('[chatWidget] openScheduleDemo failed', err);
          }
          return;
        }

        // Open Tawk.to / live chat on host
        if (action === 'openLiveChat' || action === 'openTawk' || action === 'openTawkTo') {
          try {
            if ((window as any).Tawk_API && typeof (window as any).Tawk_API.maximize === 'function') {
              (window as any).Tawk_API.maximize();
            } else if (typeof (window as any).openLiveChat === 'function') {
              (window as any).openLiveChat();
            } else {
              console.warn('[chatWidget] Tawk API not available to open live chat');
            }
          } catch (err) {
            console.warn('[chatWidget] openLiveChat handler error', err);
          }
          return;
        }
      } catch (err) {
        console.warn('chatWidget:action handler error', err);
      }
    };

    const onMessage = (ev: MessageEvent) => {
      try {
        const data = ev.data;

        // Legacy: simple chat message payload
        if (data && data.type === 'chat_message' && typeof data.text === 'string') {
          openChatFromHost();
          setChatInputTextFromHost(data.text);
          triggerSendFromHost();
          return;
        }

        // Support action-style postMessage payloads as fallback
        if (data && (data.type === 'chat_action' || data.action) ) {
          const action = data.action || data.type;
          const message = data.message || data.text;
          // Build a small event-like object and delegate to onAction logic
          try {
            const fakeEvent = { detail: { action, message } };
            onAction(fakeEvent);
          } catch (err) { /* ignore */ }
        }
      } catch (err) { /* ignore */ }
    };

    window.addEventListener('chatWidget:action', onAction);
    window.addEventListener('message', onMessage);

    console.log('chatWidget host API installed (frontend)');

    return () => {
      window.removeEventListener('chatWidget:action', onAction);
      window.removeEventListener('message', onMessage);
      if ((window as any).chatWidget) {
        try { delete (window as any).chatWidget.sendMessage; delete (window as any).chatWidget.setMessage; } catch {}
      }
    };
    // run once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleTooltipClick = () => {
    setShowTooltip(false);
    setOpen(true);
  };

  const dismissTooltip = () => {
    setShowTooltip(false);
    setTooltipDismissed(true);
  };

  // Controls visibility toggle between AI chatbot and Odoo livechat
  const [isHiddenForOdoo, setIsHiddenForOdoo] = useState(false);

  // Options menu state
  const [showOptionsMenu, setShowOptionsMenu] = useState(false);
  const [showWhatsAppSubmenu, setShowWhatsAppSubmenu] = useState(false);
  const [showWhatsAppQR, setShowWhatsAppQR] = useState(false);
  const [showWhatsAppDropdown, setShowWhatsAppDropdown] = useState(false);
  const [waDropdownRect, setWaDropdownRect] = useState<DOMRect | null>(null);

  const handleOpenOptionsMenu = () => {
    console.log('[ChatWidget] Opening options menu');
    setShowOptionsMenu(true);
  };

  const handleCloseOptionsMenu = () => {
    setShowOptionsMenu(false);
    setShowWhatsAppSubmenu(false);
  };

  const handleChatWithUs = () => {
    console.log('[ChatWidget] Chat with us clicked — switching to Odoo livechat');
    // Close AI chatbot panel and hide the entire widget
    setOpen(false);
    setShowOptionsMenu(false);
    setIsHiddenForOdoo(true);
    // Send conversation context to Odoo and open the Odoo chat
    void sendContextToOdooAndOpenChat();
  };

  const handleCallUs = () => {
    console.log('[ChatWidget] Call us clicked');
    window.location.href = "tel:+4407727449124";
    setShowOptionsMenu(false);
  };

  const handleWhatsAppUs = () => {
    console.log('[ChatWidget] WhatsApp clicked');
    // Toggle a small submenu with QR / Link options
    setShowWhatsAppSubmenu((s) => !s);
  };

  const openWhatsAppLink = () => {
    const wa = "https://wa.me/447727449124";
    try {
      window.open(wa, "_blank");
    } catch (err) {
      window.location.href = wa;
    }
    setShowOptionsMenu(false);
    setShowWhatsAppSubmenu(false);
    setShowWhatsAppDropdown(false);
  };

  const openWhatsAppQRInChat = () => {
    // Close menus and show QR overlay inside chat
    setShowWhatsAppQR(true);
    setShowWhatsAppSubmenu(false);
    setShowOptionsMenu(false);
    setShowWhatsAppDropdown(false);
  };

  const openWhatsAppDropdown = (anchorEl: HTMLElement) => {
    try {
      const rect = anchorEl.getBoundingClientRect();
      console.log('[ChatWidget] openWhatsAppDropdown rect:', rect);
      setWaDropdownRect(rect);
      setShowWhatsAppDropdown(true);
    } catch (err) {
      console.error('[WhatsAppDropdown] failed to open anchored dropdown', err);
    }
  };

  const closeWhatsAppDropdown = () => {
    setShowWhatsAppDropdown(false);
    setWaDropdownRect(null);
  };

  // Reset conversation - clear messages and create new session
  const handleResetConversation = async () => {
    console.log('[ChatWidget] Reset conversation clicked');

    // Call backend to reset session
    const oldSessionId = sessionIdRef.current;
    if (oldSessionId) {
      try {
        const apiBaseUrl = getApiBaseUrl();
        await fetch(`${apiBaseUrl}/api/reset`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: oldSessionId }),
        });
        console.log('[ChatWidget] Backend session reset successful');
      } catch (error) {
        console.error('[ChatWidget] Failed to reset backend session:', error);
        // Continue with frontend reset even if backend fails
      }
    }

    // Clear messages
    setMessages([]);
    // Create new session
    const newSessionId = createSessionId();
    sessionIdRef.current = newSessionId;
    setSessionId(newSessionId);
    try {
      window.localStorage.setItem(SESSION_STORAGE_KEY, newSessionId);
    } catch {}
    // Reset suggested questions to initial
    setSuggestedQuestions(INITIAL_QUESTIONS);
    // Clear any collecting state
    setSuggestionsState(null);
    // Reset lead capture state
    setLeadCaptured(false);
    setLeadFormData({ email: "", phone: "", company_name: "" });
    // Close options menu
    setShowOptionsMenu(false);
  };

  // When user has switched to Odoo livechat, hide the AI chatbot entirely
  if (isHiddenForOdoo) return null;

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

          {/* Voice/Text Mode Toggle - Commented out - will add back later */}
          {/* <div className="px-4 py-2 bg-white border-b border-gray-100 flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600">Chat Mode:</span>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setVoiceMode(false)}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all duration-200 ${
                  !voiceMode
                    ? 'bg-orange-500 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                <span className="flex items-center space-x-1">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                  <span>Text</span>
                </span>
              </button>
              <button
                onClick={() => setVoiceMode(true)}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all duration-200 ${
                  voiceMode
                    ? 'bg-orange-500 text-white shadow-sm shadow-orange-400/40'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                <span className="flex items-center space-x-1">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                  </svg>
                  <span>Voice</span>
                </span>
              </button>
            </div>
          </div> */}

          {/* Voice Chat - always mounted so messages survive mode switches - Commented out - will add back later */}
          {/* <div style={{ display: voiceMode ? 'flex' : 'none', flex: 1, flexDirection: 'column', overflow: 'hidden' }}>
            {voiceChatComponent}
          </div> */}

          {/* Text Chat - always mounted; display:contents is invisible to layout */}
          {/* Conditional Rendering: Text Chat */}
          <div style={{ display: 'contents' }}>
            <>
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
            onOpenWhatsAppDropdown={openWhatsAppDropdown}
            onFeedbackSubmit={handleFeedbackSubmit}
            onDelayedFeedbackSubmit={handleDelayedFeedbackSubmit}
            sessionId={sessionId}
            pageUrl={currentUrl}
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
           <ChatFooter ref={footerRef} onSend={handleSend} isSending={isSending} position="bottom" onOpenOptionsMenu={handleOpenOptionsMenu} />

          {/* Disclaimer at bottom - AWS Style */}
          <div className="px-4 py-2 bg-white border-t border-gray-100">
            <p className="text-[10px] text-gray-400 text-center">
              By chatting, you agree to this{" "}
              <a href="#" className="text-orange-600 hover:underline">disclaimer</a>.
            </p>
          </div>

          {/* Options Menu Overlay */}
          {showOptionsMenu && (
            <div
              className="fixed bottom-24 right-5 z-[2147483648] flex items-end justify-center rounded-2xl overflow-hidden"
              style={{
                width: '380px',
                height: '580px',
              }}
            >
              {/* Backdrop */}
              <div
                className="absolute inset-0 bg-black/30 rounded-2xl"
                onClick={handleCloseOptionsMenu}
              />
              {/* Menu Panel */}
              <div
                className="relative w-full bg-white rounded-t-2xl shadow-xl"
                style={{
                  animation: 'slideUp 0.3s ease-out forwards'
                }}
              >
                <div className="p-4">
                  {/* Handle bar */}
                  <div className="w-10 h-1 bg-gray-300 rounded-full mx-auto mb-4" />

                  {/* Menu Title */}
                  <h3 className="text-sm font-semibold text-gray-700 mb-3 px-2">Support Options</h3>

                  {/* Menu Items */}
                  <div className="space-y-1">
                    <button
                      onClick={handleChatWithUs}
                      className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 hover:bg-gray-50 rounded-xl transition-colors"
                    >
                      <div className="flex items-center justify-center w-10 h-10 rounded-full bg-orange-100">
                        <svg className="h-5 w-5 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                      </div>
                      <div className="text-left">
                        <p className="font-medium">Chat with us</p>
                        <p className="text-xs text-gray-500">Talk to our support team</p>
                      </div>
                    </button>

                    <button
                      onClick={handleCallUs}
                      className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 hover:bg-gray-50 rounded-xl transition-colors"
                    >
                      <div className="flex items-center justify-center w-10 h-10 rounded-full bg-green-100">
                        <svg className="h-5 w-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                        </svg>
                      </div>
                      <div className="text-left">
                        <p className="font-medium">Call Us</p>
                        <p className="text-xs text-gray-500">+44 07727 449124</p>
                      </div>
                    </button>

                    <div className="relative">
                      <button
                        onClick={handleWhatsAppUs}
                        className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 hover:bg-gray-50 rounded-xl transition-colors"
                      >
                        <div className="flex items-center justify-center w-10 h-10 rounded-full bg-green-100">
                          <svg className="h-5 w-5 text-green-600" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                          </svg>
                        </div>
                        <div className="text-left">
                          <p className="font-medium">WhatsApp Us</p>
                          <p className="text-xs text-gray-500">Message us on WhatsApp</p>
                        </div>
                      </button>

                      {showWhatsAppSubmenu && (
                        <div className="absolute right-3 top-full mt-2 w-56 bg-white rounded-lg shadow-lg border p-2 z-50">
                          <button
                            onClick={openWhatsAppQRInChat}
                            className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-50 text-sm text-gray-700 flex items-center gap-2"
                          >
                            <svg className="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h2M4 8h12m4 0h2M4 16h4m12 0h2M4 20h4" />
                            </svg>
                            Show QR
                          </button>
                          <button
                            onClick={openWhatsAppLink}
                            className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-50 text-sm text-gray-700 flex items-center gap-2 mt-1"
                          >
                            <svg className="w-4 h-4 text-[#25D366]" fill="currentColor" viewBox="0 0 24 24">
                              <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                            </svg>
                            Open WhatsApp
                          </button>
                        </div>
                      )}
                    </div>

                    <div className="border-t border-gray-100 my-2" />

                    <button
                      onClick={handleResetConversation}
                      className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 hover:bg-red-50 rounded-xl transition-colors"
                    >
                      <div className="flex items-center justify-center w-10 h-10 rounded-full bg-red-100">
                        <svg className="h-5 w-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                      </div>
                      <div className="text-left">
                        <p className="font-medium">Reset Conversation</p>
                        <p className="text-xs text-gray-500">Start a new chat session</p>
                      </div>
                    </button>
                  </div>

                  {/* Cancel Button */}
                  <button
                    onClick={handleCloseOptionsMenu}
                    className="w-full mt-3 py-3 text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
          </>
          </div>
          {/* End Conditional Rendering */}

          {showWhatsAppDropdown && waDropdownRect && (
            <WhatsAppDropdown
              rect={waDropdownRect}
              onClose={closeWhatsAppDropdown}
              onShowQR={() => { openWhatsAppQRInChat(); closeWhatsAppDropdown(); }}
              onOpenLink={() => { openWhatsAppLink(); closeWhatsAppDropdown(); }}
            />
          )}
          {/* WhatsApp QR Overlay (in-chat) */}
          {showWhatsAppQR && (
            <div className="fixed inset-0 z-[2147483649] flex items-center justify-center">
              <div className="absolute inset-0 bg-black/40" onClick={() => setShowWhatsAppQR(false)} />
              <div className="relative bg-white rounded-3xl p-6 w-[90vw] max-w-md shadow-2xl z-50">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-semibold text-slate-900">Scan to WhatsApp</h3>
                  <button onClick={() => setShowWhatsAppQR(false)} className="p-2 hover:bg-slate-100 rounded-full">
                    <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                <div className="bg-slate-50 p-4 rounded-2xl border-2 border-slate-100">
                  <div className="w-64 h-64 bg-white rounded-xl shadow-sm flex items-center justify-center border border-slate-200 overflow-hidden mx-auto">
                    <img src={whatsappQr} alt="WhatsApp QR Code" className="w-full h-full p-4 object-contain" />
                  </div>

                  <p className="mt-4 text-center text-sm text-slate-600">Open WhatsApp on your phone and scan this code to start chatting with us.</p>
                </div>

                <div className="mt-6">
                  <button onClick={openWhatsAppLink} className="w-full bg-[#25D366] text-white py-3 rounded-xl font-semibold hover:bg-[#20bd5c] transition-colors">Open WhatsApp Directly</button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
