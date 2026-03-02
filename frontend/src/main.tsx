import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import widgetCSS from "./index.css?inline";
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

  // Inject all styles into shadow DOM only — nothing touches document.head
  const styleElement = document.createElement('style');
  styleElement.textContent = widgetCSS;
  shadowRoot.insertBefore(styleElement, reactContainer);

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
