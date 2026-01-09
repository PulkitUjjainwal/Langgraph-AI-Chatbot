import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import "./index.css";
import App from './App.tsx'

/**
 * Initialize chatbot widget with Shadow DOM isolation
 * This prevents CSS conflicts with the host page
 */
function initWidget() {
  // Prevent multiple instances
  if (document.getElementById('mi-chatbot-shadow-host')) {
    console.warn('MI Chatbot already initialized');
    return;
  }

  // Create shadow host container
  const shadowHost = document.createElement('div');
  shadowHost.id = 'mi-chatbot-shadow-host';
  shadowHost.style.cssText = 'all: initial; position: fixed; z-index: 2147483647;';
  document.body.appendChild(shadowHost);

  // Create shadow root for complete CSS isolation
  const shadowRoot = shadowHost.attachShadow({ mode: 'open' });

  // Create React container inside shadow DOM
  const reactContainer = document.createElement('div');
  reactContainer.id = 'chatbot-react-root';
  shadowRoot.appendChild(reactContainer);

  // Inject Tailwind and custom styles into shadow DOM
  const styleContainer = document.createElement('div');
  styleContainer.innerHTML = `
    <style id="chatbot-styles">
      /* Import all necessary styles inline to avoid external CSS conflicts */
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    </style>
  `;
  shadowRoot.insertBefore(styleContainer.firstElementChild!, reactContainer);

  // Copy all stylesheets from document head (for Vite injected styles)
  const styles = document.querySelectorAll('style');
  styles.forEach((style) => {
    if (style.textContent && style.textContent.includes('chat-')) {
      const clonedStyle = style.cloneNode(true) as HTMLStyleElement;
      shadowRoot.insertBefore(clonedStyle, reactContainer);
    }
  });

  // Render React app in shadow DOM
  const root = createRoot(reactContainer);
  root.render(
    <StrictMode>
      <App />
    </StrictMode>
  );

  console.log('✅ MI Chatbot initialized with Shadow DOM isolation');
}

// Initialize when DOM is ready
if (document.readyState === 'complete') {
  initWidget();
} else {
  window.addEventListener('load', initWidget);
}

// Expose global init function for manual initialization
(window as any).initMIChatbot = initWidget;
