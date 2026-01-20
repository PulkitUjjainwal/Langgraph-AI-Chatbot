/**
 * ChatbotWidget - Production Component for Next.js
 *
 * USAGE:
 * 1. Copy this file to: components/chatbot-widget/chatbot-widget.tsx
 * 2. Add to your .env.local:
 *    NEXT_PUBLIC_CHATBOT_API_URL=https://chatbot.exportgenius.in
 *    NEXT_PUBLIC_CHATBOT_WIDGET_URL=https://chatbot.exportgenius.in/chat-widget.js
 * 3. Import in your layout.tsx:
 *    import ChatbotWidget from "@/components/chatbot-widget/chatbot-widget"
 * 4. Add <ChatbotWidget /> in your layout body
 */

'use client';

import { useEffect, useCallback, useRef } from 'react';
import { usePathname } from 'next/navigation';

// ============================================================
// CONFIGURATION
// ============================================================

const getConfig = () => {
  // Production URLs - UPDATE THESE FOR YOUR DEPLOYMENT
  const config = {
    // Your deployed API URL (Nginx proxies to FastAPI on port 8000)
    apiUrl: process.env.NEXT_PUBLIC_CHATBOT_API_URL || 'https://chatbot.exportgenius.in',

    // Your widget JS URL (served by Nginx from /chat-widget.js)
    widgetUrl: process.env.NEXT_PUBLIC_CHATBOT_WIDGET_URL || 'https://chatbot.exportgenius.in/chat-widget.js',
  };

  // Development fallbacks
  if (process.env.NODE_ENV === 'development') {
    return {
      apiUrl: config.apiUrl || 'http://localhost:8000',
      widgetUrl: config.widgetUrl || 'http://localhost:5173/src/main.tsx',
    };
  }

  return config;
};

// ============================================================
// COMPONENT
// ============================================================

export default function ChatbotWidget() {
  const pathname = usePathname();
  const config = getConfig();
  const isInitialized = useRef(false);

  // Setup global functions for widget communication
  const setupGlobalFunctions = useCallback(() => {
    if (typeof window === 'undefined') return;

    // Configure chatbot API URL (read by widget)
    (window as any).CHATBOT_CONFIG = {
      apiUrl: config.apiUrl,
    };

    // Function to open schedule demo modal
    (window as any).openScheduleDemo = () => {
      const event = new CustomEvent('chatWidget:action', {
        detail: { action: 'openScheduleDemo' },
      });
      window.dispatchEvent(event);
    };

    // Function to open WhatsApp
    (window as any).openWhatsApp = () => {
      const whatsappUrl = 'https://api.whatsapp.com/send/?phone=4407727449124&text&type=phone_number&app_absent=0';
      window.open(whatsappUrl, '_blank');
    };
  }, [config.apiUrl]);

  // Cleanup global functions
  const cleanupGlobalFunctions = useCallback(() => {
    if (typeof window === 'undefined') return;

    delete (window as any).CHATBOT_CONFIG;
    delete (window as any).openScheduleDemo;
    delete (window as any).openWhatsApp;
  }, []);

  // Load widget script
  useEffect(() => {
    // Check if already initialized
    if (isInitialized.current) return;
    if (document.getElementById('mi-chatbot-shadow-host')) return;

    // Validate config
    if (!config.apiUrl || !config.widgetUrl) {
      console.error('[Chatbot] Missing configuration. Check environment variables.');
      return;
    }

    isInitialized.current = true;

    // Setup global config
    setupGlobalFunctions();

    // Create script element
    const script = document.createElement('script');
    script.type = 'module';
    script.src = config.widgetUrl;
    script.id = 'mi-chatbot-script';
    script.async = true;

    script.onload = () => {
      console.log('[Chatbot] Widget loaded from:', config.widgetUrl);
    };

    script.onerror = () => {
      console.error('[Chatbot] Failed to load widget from:', config.widgetUrl);
      isInitialized.current = false;
    };

    document.body.appendChild(script);

    // Cleanup
    return () => {
      const existingScript = document.getElementById('mi-chatbot-script');
      if (existingScript?.parentNode) {
        existingScript.parentNode.removeChild(existingScript);
      }

      const shadowHost = document.getElementById('mi-chatbot-shadow-host');
      if (shadowHost?.parentNode) {
        shadowHost.parentNode.removeChild(shadowHost);
      }

      cleanupGlobalFunctions();
      isInitialized.current = false;
    };
  }, [config.apiUrl, config.widgetUrl, setupGlobalFunctions, cleanupGlobalFunctions]);

  // Debug: Log page changes
  useEffect(() => {
    if (process.env.NODE_ENV === 'development') {
      console.log('[Chatbot] Page changed:', pathname);
    }
  }, [pathname]);

  return null;
}

// ============================================================
// TypeScript Declarations
// ============================================================

declare global {
  interface Window {
    CHATBOT_CONFIG?: { apiUrl: string };
    openScheduleDemo?: () => void;
    openWhatsApp?: () => void;
    initMIChatbot?: () => void;
  }
}
