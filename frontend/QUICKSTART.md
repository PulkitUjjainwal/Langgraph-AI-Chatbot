# Quick Start Guide - Chatbot Widget

## 🚀 Deploy in 5 Minutes

### Step 1: Build the Widget

```bash
cd frontend
npm install
npm run build
```

This creates `chat-widget.js` in `../backend/assets/`

### Step 2: Upload to Your Server

Upload `chat-widget.js` to your web hosting:
- FTP/SFTP to your server
- AWS S3 bucket
- Vercel/Netlify
- Any CDN

### Step 3: Add to Your Website

Add this code before the closing `</body>` tag of your website:

```html
<!-- Configure -->
<script>
  window.CHATBOT_CONFIG = {
    apiUrl: 'http://your-api-domain.com:8000'  // Your API URL
  };
</script>

<!-- Load widget -->
<script type="module" src="http://your-cdn.com/chat-widget.js"></script>
```

### Step 4: Test

1. Open your website
2. Look for the chat button in bottom-right corner
3. Click and start chatting!

---

## 🧪 Test Locally First

### Terminal 1: Start Backend

```bash
cd "C:\MI Ticket\MI Chat Bot\Scrapper Function"
./venv/Scripts/python.exe -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2: Start Frontend Dev Server

```bash
cd frontend
npm run dev
```

### Open Test Page

Navigate to: `http://localhost:5173/embed-example.html`

---

## 🔧 Configuration

### Change API URL

Edit before loading widget:

```javascript
window.CHATBOT_CONFIG = {
  apiUrl: 'https://your-production-api.com'
};
```

### URL Tracking

The widget automatically:
- ✅ Detects current page URL
- ✅ Sends URL to backend with each request
- ✅ Monitors URL changes (SPAs)
- ✅ Maintains session across navigation

### Session Management

- **Automatic**: Session ID generated on first use
- **Persistent**: Stored in localStorage
- **Shared**: Same session across tabs
- **Lifetime**: Server-configured expiry

---

## 📱 What You Get

✅ Floating chat button (bottom-right)
✅ Clean chat interface
✅ URL-aware responses
✅ Session history
✅ Mobile responsive
✅ Easy to integrate

---

## 🐛 Troubleshooting

**Widget doesn't show?**
- Check browser console for errors
- Verify script URL is accessible
- Ensure `type="module"` is set

**API errors?**
- Check `CHATBOT_CONFIG.apiUrl` is correct
- Verify backend is running
- Enable CORS on backend

**URL not tracking?**
- Check console logs
- Verify browser supports History API
- Test navigation with back/forward buttons

---

## 📚 Full Documentation

See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) for complete documentation.

---

## 🎯 Example Integration

```html
<!DOCTYPE html>
<html>
<head>
    <title>My Website</title>
</head>
<body>
    <h1>Welcome</h1>
    <p>Your content here...</p>

    <!-- Chatbot Integration -->
    <script>
        window.CHATBOT_CONFIG = { apiUrl: 'http://localhost:8000' };
    </script>
    <script type="module" src="http://localhost:5173/src/main.tsx"></script>
</body>
</html>
```

---

## ✅ Deployment Checklist

- [ ] Built widget: `npm run build`
- [ ] Uploaded `chat-widget.js` to hosting
- [ ] Updated `apiUrl` in config
- [ ] Added script tags to website
- [ ] Tested on multiple pages
- [ ] Verified URL tracking works
- [ ] Checked mobile responsiveness
- [ ] Enabled CORS on backend

---

## 🎉 Done!

Your chatbot is now live on your website! Users can click the chat button and start asking questions.

The chatbot will automatically:
- Detect which page they're on
- Provide relevant, context-aware answers
- Remember their conversation history
- Work across all pages on your site
