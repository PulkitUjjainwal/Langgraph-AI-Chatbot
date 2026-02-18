import { useEffect, useState, useRef } from "react";
import { createRoot } from "react-dom/client";
import ChatWidget from "./components/ChatWidget";
import widgetCSS from "./index.css?inline";

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

    // Inject all styles into shadow DOM only — nothing touches document.head
    const styleElement = document.createElement("style");
    styleElement.textContent = widgetCSS;

    shadowRoot.insertBefore(styleElement, reactContainer);

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
