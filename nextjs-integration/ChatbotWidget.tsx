"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

interface ChatbotConfig {
  apiUrl: string;
  environment?: "development" | "production";
}

/**
 * Market Inside Chatbot Widget for Next.js
 *
 * This component integrates the MI chatbot with complete CSS isolation
 * Works in both development and production environments
 *
 * Usage in layout.tsx:
 * ```tsx
 * import ChatbotWidget from "@/components/chatbot-widget/ChatbotWidget"
 *
 * export default function RootLayout({ children }) {
 *   return (
 *     <html>
 *       <body>
 *         {children}
 *         <ChatbotWidget />
 *       </body>
 *     </html>
 *   )
 * }
 * ```
 */
export default function ChatbotWidget() {
  const pathname = usePathname();
  const [scriptLoaded, setScriptLoaded] = useState(false);

  useEffect(() => {
    // Determine environment
    const isDevelopment = process.env.NODE_ENV === "development";

    // Configure chatbot API
    if (typeof window !== "undefined") {
      (window as any).CHATBOT_CONFIG = {
        apiUrl: isDevelopment
          ? "http://localhost:8003"  // Development API
          : "https://chatbot.exportgenius.in", // Production API
        environment: isDevelopment ? "development" : "production"
      } as ChatbotConfig;

      console.log("🤖 Chatbot config:", (window as any).CHATBOT_CONFIG);
    }

    // Prevent duplicate loading
    if (scriptLoaded || typeof window === "undefined") return;

    // Check if already loaded
    if (document.getElementById("mi-chatbot-shadow-host")) {
      console.log("Chatbot already loaded");
      setScriptLoaded(true);
      return;
    }

    const loadScript = () => {
      const script = document.createElement("script");
      script.type = "module";
      script.id = "mi-chatbot-script";

      // Use development server in dev mode, production bundle in prod
      if (isDevelopment) {
        // Development: Load from Vite dev server
        script.src = "http://localhost:5173/src/main.tsx";
        script.onerror = () => {
          console.error(
            "❌ Failed to load chatbot from dev server. Make sure Vite is running on port 5173"
          );
        };
      } else {
        // Production: Load from your CDN or static assets
        // Option 1: From your domain
        script.src = "/chatbot/chat-widget.js";

        // Option 2: From CDN (if you host it separately)
        // script.src = "https://cdn.marketinsidedata.com/chatbot/chat-widget.js";

        script.onerror = () => {
          console.error("❌ Failed to load chatbot widget");
        };
      }

      script.onload = () => {
        console.log("✅ Chatbot script loaded successfully");
        setScriptLoaded(true);
      };

      document.body.appendChild(script);
    };

    // Load script when DOM is ready
    if (document.readyState === "complete") {
      loadScript();
    } else {
      window.addEventListener("load", loadScript);
    }

    return () => {
      // Cleanup: Remove script on unmount (optional)
      const script = document.getElementById("mi-chatbot-script");
      if (script) {
        // Don't remove in production to keep chatbot persistent across navigation
        if (isDevelopment) {
          script.remove();
        }
      }
    };
  }, [scriptLoaded]);

  // Log pathname changes (widget auto-detects via history API)
  useEffect(() => {
    if (scriptLoaded && typeof window !== "undefined") {
      console.log("📍 Next.js route changed:", pathname);
      // Widget automatically detects URL changes via history.pushState monitoring

      // Manually trigger re-initialization if needed
      if ((window as any).initMIChatbot) {
        // Optional: Re-init chatbot on route change
        // (window as any).initMIChatbot();
      }
    }
  }, [pathname, scriptLoaded]);

  // This component doesn't render anything visible
  // The chatbot renders itself via the loaded script
  return null;
}
