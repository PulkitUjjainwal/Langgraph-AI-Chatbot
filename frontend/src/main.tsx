import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import "./index.css";
import App from './App.tsx'


function initWidget(){
  const container = document.createElement('div');
  document.body.appendChild(container);
  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

if(document.readyState === 'complete') {
  initWidget();
} else {
  window.addEventListener('load', initWidget);
}
