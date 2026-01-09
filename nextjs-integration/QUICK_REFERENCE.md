# 🚀 Quick Reference - Market Inside Chatbot Integration

## One-Minute Setup

### 1. Copy Component
```bash
cp nextjs-integration/ChatbotWidget.tsx your-nextjs-app/components/chatbot-widget/
```

### 2. Add to Layout
```tsx
// app/layout.tsx
import ChatbotWidget from "@/components/chatbot-widget/ChatbotWidget"

export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        {children}
        <ChatbotWidget /> {/* ← Add this */}
      </body>
    </html>
  )
}
```

### 3. Deploy Widget
```bash
# Build
cd frontend && npm run build

# Copy to Next.js
cp backend/assets/chat-widget.js your-nextjs-app/public/chatbot/
```

**Done! 🎉**

---

## Development vs Production

| Mode | Widget Source | API URL |
|------|--------------|---------|
| **Development** | `http://localhost:5173/src/main.tsx` | `http://localhost:8003` |
| **Production** | `/chatbot/chat-widget.js` | `https://chatbot.exportgenius.in` |

The component automatically detects the environment.

---

## Common Commands

```bash
# Start widget dev server
cd frontend && npm run dev

# Build widget for production
cd frontend && npm run build

# Test isolation (open in browser)
open nextjs-integration/test-isolation.html

# Check widget bundle size
ls -lh backend/assets/chat-widget.js
```

---

## Verify Integration

### ✅ Checklist

Open DevTools and check:

1. **Console**: Look for `✅ MI Chatbot initialized with Shadow DOM isolation`
2. **Elements**: Find `<div id="mi-chatbot-shadow-host">` with `#shadow-root`
3. **Network**: Verify `chat-widget.js` loaded (or `main.tsx` in dev)
4. **Styles**: Chatbot should have orange theme, Inter font
5. **Functionality**: Click button, send message, check response

### 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Chatbot doesn't appear | Check console for script load errors |
| Wrong styles | Clear cache (Ctrl+Shift+R), rebuild widget |
| API not responding | Verify API is running: `curl http://localhost:8003/api/health` |
| Dev server 404 | Run `cd frontend && npm run dev` |

---

## File Locations

```
chatbot-project/
├── frontend/src/           ← Edit styles/components here
├── backend/assets/         ← Production bundle here
└── nextjs-integration/     ← Integration files

your-nextjs-app/
├── components/chatbot-widget/ChatbotWidget.tsx  ← Integration component
└── public/chatbot/chat-widget.js                ← Production bundle
```

---

## Update Workflow

```
1. Edit frontend/src/...
2. npm run build
3. Copy chat-widget.js to Next.js public/
4. Deploy
```

---

## Key Features

✅ **Shadow DOM Isolation** - Zero CSS conflicts
✅ **Auto Environment Detection** - Dev/prod modes
✅ **URL Detection** - Tracks page navigation
✅ **Orange Theme** - Matches marketinsidedata.com
✅ **Inter Font** - Professional typography

---

## Support

- 📖 Full Guide: `INTEGRATION_GUIDE.md`
- 🧪 Test File: `test-isolation.html`
- 🔧 Widget Source: `frontend/src/`

---

**Happy Chatting! 💬**
