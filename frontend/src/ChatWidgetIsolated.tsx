import { useEffect, useState, useRef } from "react";
import { createRoot } from "react-dom/client";
import ChatWidget from "./components/ChatWidget";
import "./index.css";

/**
 * Shadow DOM Isolated Chat Widget
 * This component renders the chat widget in a Shadow DOM to prevent CSS conflicts
 */
export default function ChatWidgetIsolated() {
  const shadowHostRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    if (!shadowHostRef.current || mounted) return;

    // Create shadow root for complete CSS isolation
    const shadowRoot = shadowHostRef.current.attachShadow({ mode: "open" });

    // Create container for React app
    const reactContainer = document.createElement("div");
    reactContainer.id = "chatbot-root";
    shadowRoot.appendChild(reactContainer);

    // Inject styles into shadow DOM
    const styleElement = document.createElement("style");

    // Import all necessary styles inline
    styleElement.textContent = `
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

      /* Tailwind-like reset for shadow DOM */
      *, *::before, *::after {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }

      /* Root styles */
      #chatbot-root {
        --chat-primary: #ea580c;
        --chat-primary-hover: #c2410c;
        --chat-accent: #f97316;
        --chat-accent-light: #fed7aa;
        --chat-text: #111827;
        --chat-bg: #ffffff;
        --chat-muted: #6b7280;
        --chat-border: #e5e7eb;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 16px;
        line-height: 1.5;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
      }

      /* Ensure widget is always on top */
      #chatbot-root > * {
        position: relative;
        z-index: 2147483647;
      }
    `;

    shadowRoot.insertBefore(styleElement, reactContainer);

    // Create a link element for Tailwind (if using CDN)
    // Note: Vite build will inject styles automatically

    // Render React component in shadow DOM
    const root = createRoot(reactContainer);
    root.render(<ChatWidget />);

    setMounted(true);

    return () => {
      root.unmount();
    };
  }, [mounted]);

  return <div ref={shadowHostRef} id="chatbot-shadow-host" />;
}
