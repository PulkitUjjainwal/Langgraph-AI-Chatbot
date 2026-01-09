# Market Inside Chatbot - Next.js Integration Guide

Complete guide to integrate the MI Chatbot into your Next.js website with **zero CSS conflicts** using Shadow DOM isolation.

---

## 🎯 Features

✅ **Complete CSS Isolation** - Shadow DOM prevents style conflicts
✅ **Orange Theme** - Matches marketinsidedata.com branding
✅ **Inter Font** - Professional B2B SaaS typography
✅ **Auto URL Detection** - Automatically detects page changes
✅ **Dev & Production Modes** - Seamless development experience
✅ **Zero Dependencies** - Single script bundle

---

## 📦 Quick Start

### Step 1: Copy the ChatbotWidget Component

Copy `ChatbotWidget.tsx` from this folder to your Next.js project:

```bash
cp ChatbotWidget.tsx <your-nextjs-project>/components/chatbot-widget/ChatbotWidget.tsx
```

### Step 2: Add to Your Layout

In your `app/layout.tsx` (App Router) or `pages/_app.tsx` (Pages Router):

```tsx
"use client"

import ChatbotWidget from "@/components/chatbot-widget/ChatbotWidget"

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* Your existing content */}
        {children}

        {/* Add chatbot at the end of body */}
        <ChatbotWidget />
      </body>
    </html>
  )
}
```

### Step 3: Deploy the Widget Script

#### Option A: Development Mode

1. Start the widget dev server:
```bash
cd frontend
npm run dev
```

This runs on `http://localhost:5173` and the component will automatically load from there.

#### Option B: Production Mode

1. Build the widget:
```bash
cd frontend
npm run build
```

2. Copy the built widget to your Next.js public folder:
```bash
# From the chatbot project root
cp backend/assets/chat-widget.js <your-nextjs-project>/public/chatbot/chat-widget.js
```

3. The component will automatically load `/chatbot/chat-widget.js` in production.

---

## 🔧 Configuration

### API URL Configuration

The component automatically configures the API URL based on environment:

- **Development**: `http://localhost:8003`
- **Production**: `https://chatbot.exportgenius.in`

To customize, edit `ChatbotWidget.tsx`:

```tsx
(window as any).CHATBOT_CONFIG = {
  apiUrl: isDevelopment
    ? "http://localhost:8003"
    : "https://your-production-api.com",
  environment: isDevelopment ? "development" : "production"
};
```

### CDN Hosting (Optional)

If you want to host the widget on a CDN:

1. Upload `chat-widget.js` to your CDN
2. Update the production script source in `ChatbotWidget.tsx`:

```tsx
if (!isDevelopment) {
  script.src = "https://cdn.marketinsidedata.com/chatbot/chat-widget.js";
}
```

---

## 🎨 How Shadow DOM Isolation Works

The widget uses **Shadow DOM** to completely isolate its styles from your website:

```
Your Website
└── <body>
    ├── Your existing content (your styles apply here)
    └── <div id="mi-chatbot-shadow-host">
        └── #shadow-root (isolated boundary)
            ├── <style> (chatbot styles - isolated)
            └── <div> (chatbot UI - no conflicts)
```

### Benefits:

1. **No CSS Conflicts** - Your website styles don't affect the chatbot
2. **No Leaking** - Chatbot styles don't affect your website
3. **Consistent Design** - Chatbot looks identical everywhere
4. **Easy Updates** - Update chatbot without touching your site

---

## 🚀 Advanced Usage

### Manual Initialization

If you need to manually control when the chatbot loads:

```tsx
// In your component
useEffect(() => {
  if (typeof window !== 'undefined' && (window as any).initMIChatbot) {
    (window as any).initMIChatbot();
  }
}, []);
```

### Checking if Loaded

```tsx
const isChatbotLoaded = typeof window !== 'undefined' &&
  document.getElementById('mi-chatbot-shadow-host') !== null;
```

### Remove Chatbot

```tsx
const removeChatbot = () => {
  const host = document.getElementById('mi-chatbot-shadow-host');
  const script = document.getElementById('mi-chatbot-script');

  host?.remove();
  script?.remove();
};
```

---

## 🐛 Troubleshooting

### Chatbot doesn't appear

1. Check console for errors
2. Verify the script is loading:
   ```bash
   # Development
   curl http://localhost:5173/src/main.tsx

   # Production
   curl http://localhost:3000/chatbot/chat-widget.js
   ```

3. Make sure API is running:
   ```bash
   curl http://localhost:8003/api/health
   ```

### Styling looks different

If you still see styling differences:

1. **Clear browser cache** - Hard refresh (Ctrl+Shift+R)
2. **Check Shadow DOM** - Open DevTools → Elements → Look for `#shadow-root`
3. **Rebuild widget** - Run `npm run build` in frontend folder
4. **Verify isolation** - Chatbot should be inside `#mi-chatbot-shadow-host`

### Dev server not running

```bash
cd frontend
npm install
npm run dev
```

Should start on `http://localhost:5173`

---

## 📊 URL Detection

The chatbot automatically detects URL changes in your Next.js app by monitoring:

1. `history.pushState()` - Next.js navigation
2. `history.replaceState()` - URL updates
3. `popstate` events - Browser back/forward

This is configured in `ChatWidget.tsx`:

```tsx
useEffect(() => {
  const handleUrlChange = () => {
    const newUrl = window.location.href;
    // Widget automatically sends this to backend
  };

  // Override history methods to detect Next.js navigation
  const originalPushState = history.pushState;
  history.pushState = function(...args) {
    originalPushState.apply(history, args);
    handleUrlChange();
  };

  window.addEventListener('popstate', handleUrlChange);
}, [currentUrl]);
```

---

## 🎨 Customization

### Change Colors

Edit `frontend/src/index.css`:

```css
:root {
  --chat-primary: #ea580c;        /* Orange-600 */
  --chat-primary-hover: #c2410c;  /* Orange-700 */
  --chat-accent: #f97316;         /* Orange-500 */
  --chat-accent-light: #fed7aa;   /* Orange-200 */
}
```

Then rebuild:
```bash
cd frontend && npm run build
```

### Change Font

Edit `frontend/src/index.css`:

```css
@import url('https://fonts.googleapis.com/css2?family=Your+Font&display=swap');

:root {
  font-family: 'Your Font', sans-serif;
}
```

---

## 📁 File Structure

```
your-nextjs-project/
├── components/
│   └── chatbot-widget/
│       └── ChatbotWidget.tsx       ← Integration component
├── public/
│   └── chatbot/
│       └── chat-widget.js          ← Production bundle
└── app/
    └── layout.tsx                   ← Import ChatbotWidget here
```

---

## 🔄 Update Workflow

When updating the chatbot:

1. **Make changes** in `frontend/src/` files
2. **Test locally** with `npm run dev`
3. **Build** with `npm run build`
4. **Copy** `backend/assets/chat-widget.js` to your Next.js `public/chatbot/`
5. **Deploy** your Next.js site

---

## 🎬 Production Deployment

### Vercel / Netlify

1. Build widget:
   ```bash
   cd frontend && npm run build
   ```

2. Copy to Next.js public:
   ```bash
   cp backend/assets/chat-widget.js ../your-nextjs/public/chatbot/
   ```

3. Deploy normally:
   ```bash
   cd your-nextjs
   git add .
   git commit -m "Update chatbot widget"
   git push
   ```

### Docker

Include in your Dockerfile:

```dockerfile
# Copy chatbot widget
COPY public/chatbot/chat-widget.js /app/public/chatbot/
```

---

## 💡 Best Practices

1. **Always use production build** in production (not dev server)
2. **Version your widget** - `chat-widget.v1.2.3.js` for cache busting
3. **Monitor console** - Check for initialization messages
4. **Test isolation** - Verify no CSS leaks using DevTools
5. **Use CDN** - For better performance and caching

---

## 📞 Support

- **Issues**: Report at GitHub repository
- **API Docs**: Check `DEPLOYMENT.md` in backend
- **Styling**: See `frontend/src/` for customization

---

## ✅ Checklist

Before going live:

- [ ] Widget builds without errors
- [ ] Shadow DOM is active (check DevTools)
- [ ] Styling matches design (orange theme, Inter font)
- [ ] API connection works (test chat)
- [ ] URL detection works (navigate pages, check console)
- [ ] No console errors
- [ ] Mobile responsive
- [ ] Performance is good (< 1s load time)

---

**You're all set! The chatbot will now work seamlessly with zero CSS conflicts.** 🎉
