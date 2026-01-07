# Chatbot Widget - Deployment & Integration Guide

## Overview

This guide explains how to deploy the Marketinside chatbot widget and integrate it into any website using a simple script tag.

## Features

✅ **URL Tracking**: Automatically detects and sends the current page URL to the backend
✅ **Session Persistence**: Maintains chat history across page navigations
✅ **SPA Support**: Monitors URL changes in Single Page Applications
✅ **Responsive Design**: Works on desktop, tablet, and mobile devices
✅ **Easy Integration**: Just add one script tag to your website
✅ **Configurable**: Customize API endpoint and other settings

---

## Quick Start

### 1. Development Mode

For local development and testing:

```bash
cd frontend
npm install
npm run dev
```

This will start the development server at `http://localhost:5173`

### 2. Build for Production

```bash
cd frontend
npm run build
```

This creates an optimized production build in `../backend/assets/` with:
- `chat-widget.js` - The widget script (all CSS inlined)

### 3. Deploy the Widget

Upload `chat-widget.js` to your CDN or static hosting service.

Example locations:
- `https://your-cdn.com/chat-widget.js`
- `https://your-domain.com/assets/chat-widget.js`
- AWS S3 / CloudFront
- Vercel / Netlify

---

## Integration Methods

### Method 1: Basic Integration (Recommended)

Add this to your website's HTML (before closing `</body>` tag):

```html
<!-- Configure chatbot (optional) -->
<script>
  window.CHATBOT_CONFIG = {
    apiUrl: 'https://your-api-domain.com'
  };
</script>

<!-- Load chatbot widget -->
<script type="module" src="https://your-cdn.com/chat-widget.js"></script>
```

### Method 2: Dynamic Loading

Load the widget conditionally or on-demand:

```html
<script>
  // Configure
  window.CHATBOT_CONFIG = {
    apiUrl: 'https://your-api-domain.com'
  };

  // Load widget when needed
  function loadChatbot() {
    const script = document.createElement('script');
    script.type = 'module';
    script.src = 'https://your-cdn.com/chat-widget.js';
    document.body.appendChild(script);
  }

  // Load on page load
  window.addEventListener('load', loadChatbot);

  // OR load after user interaction
  // document.getElementById('help-button').addEventListener('click', loadChatbot);
</script>
```

### Method 3: Google Tag Manager

1. Create a new **Custom HTML** tag
2. Add the script:

```html
<script>
  window.CHATBOT_CONFIG = { apiUrl: 'https://your-api-domain.com' };
</script>
<script type="module" src="https://your-cdn.com/chat-widget.js"></script>
```

3. Set trigger to **All Pages**
4. Publish

---

## Configuration Options

### Global Configuration Object

```javascript
window.CHATBOT_CONFIG = {
  // API endpoint (required)
  apiUrl: 'https://your-api-domain.com',

  // You can add more options here as needed
  // theme: 'light',
  // position: 'bottom-right',
  // etc.
};
```

---

## How It Works

### URL Tracking Flow

```
1. User visits: https://example.com/products
   └─> Widget sends URL to backend via /api/init

2. User navigates: https://example.com/about
   └─> Widget detects change and updates URL

3. User asks question: "Tell me about this page"
   └─> Widget sends URL + message to /api/chat
   └─> Backend fetches content from URL
   └─> Chatbot responds with context-aware answer
```

### Session Management

- **Session ID**: Unique per user, stored in localStorage
- **Persistence**: Chat history maintained across pages
- **Auto-cleanup**: Old sessions cleaned up server-side
- **Cross-tab**: Same session ID used across browser tabs

### URL Change Detection

The widget monitors URL changes using:

1. **History API**: Detects `pushState` and `replaceState`
2. **Popstate Event**: Detects back/forward navigation
3. **Polling**: Fallback for edge cases

This ensures the widget works with:
- Static websites (normal navigation)
- SPAs (React, Vue, Angular)
- Hybrid applications

---

## API Endpoints Used

### 1. `/api/init` (POST)

**Purpose**: Initialize session and fetch suggested questions

**Payload**:
```json
{
  "session_id": "user-1234567890",
  "dynamic_url": "https://example.com/products"
}
```

**Response**:
```json
{
  "session_id": "user-1234567890",
  "suggested_questions": ["Question 1", "Question 2", ...],
  "status": "initialized"
}
```

### 2. `/api/chat` (POST)

**Purpose**: Send user message and get response

**Payload**:
```json
{
  "message": "What products are available?",
  "session_id": "user-1234567890",
  "dynamic_url": "https://example.com/products"
}
```

**Response**:
```json
{
  "message": "Based on the current page, here are the available products...",
  "session_id": "user-1234567890",
  "status": "success"
}
```

---

## Testing

### Local Testing

1. **Start Backend**:
   ```bash
   cd "C:\MI Ticket\MI Chat Bot\Scrapper Function"
   ./venv/Scripts/python.exe -m uvicorn fastapi_chatbot:app --host 0.0.0.0 --port 8000 --reload
   ```

2. **Start Frontend Dev Server**:
   ```bash
   cd frontend
   npm run dev
   ```

3. **Open Test Page**:
   ```
   http://localhost:5173/embed-example.html
   ```

### Production Testing

1. Build the widget: `npm run build`
2. Deploy `chat-widget.js` to your hosting
3. Create a test HTML file:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Widget Test</title>
</head>
<body>
    <h1>Test Page</h1>
    <p>The chatbot should appear in the bottom-right corner.</p>

    <script>
        window.CHATBOT_CONFIG = {
            apiUrl: 'https://your-api-domain.com'
        };
    </script>
    <script type="module" src="https://your-cdn.com/chat-widget.js"></script>
</body>
</html>
```

---

## Deployment Checklist

- [ ] Backend API is running and accessible
- [ ] CORS is enabled on backend for your domain
- [ ] Widget is built: `npm run build`
- [ ] `chat-widget.js` is uploaded to CDN/hosting
- [ ] `CHATBOT_CONFIG.apiUrl` points to production API
- [ ] SSL/HTTPS is enabled (required for production)
- [ ] Test on multiple pages and devices
- [ ] Test URL navigation and back/forward buttons
- [ ] Verify session persistence works
- [ ] Check browser console for errors

---

## Troubleshooting

### Widget doesn't appear

1. Check browser console for errors
2. Verify script URL is correct and accessible
3. Ensure script type is `module`: `<script type="module">`
4. Check for CSP (Content Security Policy) blocking

### API requests fail

1. Verify `CHATBOT_CONFIG.apiUrl` is correct
2. Check CORS is enabled on backend
3. Ensure backend is running and accessible
4. Check network tab in browser DevTools

### Session not persisting

1. Verify localStorage is enabled in browser
2. Check session ID is being generated
3. Look for localStorage errors in console
4. Ensure domain cookies/storage aren't blocked

### URL not updating

1. Check console logs for "URL changed to: ..."
2. Verify history API is supported
3. Test with browser back/forward buttons
4. Check if SPA framework is interfering

---

## Browser Support

- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+
- ✅ Opera 76+

**Note**: The widget uses modern JavaScript (ES6+) and may not work in older browsers without polyfills.

---

## Performance Considerations

### Load Time
- Widget script: ~50-100KB (gzipped)
- CSS: Inlined, no separate request
- Initial load: <500ms on fast connections

### Optimization Tips
1. **Lazy Load**: Load widget on user interaction
2. **CDN**: Use CDN for faster global delivery
3. **Caching**: Set long cache headers (1 year)
4. **Compression**: Ensure gzip/brotli is enabled

---

## Security

### Best Practices

1. **HTTPS Only**: Always use HTTPS in production
2. **CORS**: Whitelist only trusted domains
3. **Rate Limiting**: Implement on backend
4. **Input Validation**: Sanitize user inputs
5. **CSP**: Configure Content Security Policy
6. **Session Expiry**: Implement server-side

### Example CSP Header

```
Content-Security-Policy:
  script-src 'self' https://your-cdn.com;
  connect-src https://your-api-domain.com;
```

---

## Advanced Integration

### Custom Styling

The widget uses Tailwind CSS classes. To customize, modify the source and rebuild:

```typescript
// In ChatWidget.tsx
className="fixed bottom-5 right-5 ... bg-blue-600"
//                                      ^^^^^^^^^^^^
//                                      Change colors here
```

### Event Listeners

Listen to widget events:

```javascript
window.addEventListener('chatbot:open', () => {
  console.log('Chatbot opened');
  // Track with analytics
});

window.addEventListener('chatbot:close', () => {
  console.log('Chatbot closed');
});
```

### Programmatic Control

```javascript
// Open chatbot programmatically
window.openChatbot?.();

// Close chatbot
window.closeChatbot?.();

// Send message programmatically
window.sendChatbotMessage?.('Hello');
```

---

## Support & Maintenance

### Updating the Widget

1. Make changes to source code
2. Rebuild: `npm run build`
3. Upload new `chat-widget.js` to CDN
4. Clear CDN cache if needed
5. Users get update on next page load

### Versioning

Consider versioning your widget URL:

```html
<script src="https://your-cdn.com/chat-widget.v1.2.3.js"></script>
```

This allows controlled rollouts and easy rollback.

---

## Example Websites

Check these examples for integration patterns:

1. **Static Site**: [embed-example.html](./public/embed-example.html)
2. **React App**: See documentation for React integration
3. **WordPress**: Use Custom HTML block or theme footer

---

## Contact & Support

For issues or questions:
- Check troubleshooting section above
- Review browser console for errors
- Contact: [Your Support Email/Link]

---

## License

[Your License Here]
