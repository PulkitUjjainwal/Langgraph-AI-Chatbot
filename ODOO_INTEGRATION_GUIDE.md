# Odoo Live Chat Integration Guide

## Overview

This guide explains how to integrate the Chatbot AI with Odoo Live Chat on your website. When users click the "Chat with us" button in the chatbot, their conversation history will be automatically sent to Odoo and the Odoo live chat widget will open.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│         Chatbot AI Widget                   │
│    (Running on Your Website)                │
└──────────────┬──────────────────────────────┘
               │
               │ Click "Chat with us"
               ▼
┌─────────────────────────────────────────────┐
│    Send History to Backend API              │
│  POST /api/odoo/send-context                │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│         Backend (FastAPI)                   │
│ 1. Fetch history from Redis                 │
│ 2. Format nicely                            │
│ 3. Send to Odoo API                         │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│    Odoo Live Chat API                       │
│ POST /im_livechat/cors/message/post         │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│   Open Odoo Chat Widget via Event           │
│   (User sees conversation context + chat)   │
└─────────────────────────────────────────────┘
```

---

## Implementation Steps

### Step 1: Configure Environment Variables

Add the following to your `.env` file:

```dotenv
# Odoo Live Chat Integration
ODOO_BASE_URL=https://personal-company.odoo.com
ODOO_LIVECHAT_CHANNEL_ID=1
ODOO_LIVECHAT_OPERATOR_ID=3
ODOO_SESSION_COOKIE=session_id=your_session_id_here
```

**Where to find these values:**

#### ODOO_BASE_URL
- Your Odoo instance URL (e.g., `https://your-company.odoo.com`)

#### ODOO_LIVECHAT_CHANNEL_ID
- Get this from your first Odoo session request
- In the response JSON, look for: `result.channel_id`
- Example: `"channel_id": 17`

#### ODOO_LIVECHAT_OPERATOR_ID
- Get this from your first Odoo session request
- In the response JSON, look for: `result.store_data.discuss.channel[0].livechat_operator_id`
- Example: `"livechat_operator_id": 3`

#### ODOO_SESSION_COOKIE
- Get this from the Set-Cookie headers in your Odoo API responses
- Look for the `session_id` cookie
- Format: `session_id=YOUR_SESSION_ID_VALUE`

---

### Step 2: Get Initial Odoo Session (First Time Setup)

Run this curl command to get your initial Odoo session:

```bash
curl --location 'https://personal-company.odoo.com/im_livechat/cors/get_session' \
  --header 'Content-Type: application/json' \
  --data '{
    "id": 1,
    "jsonrpc": "2.0",
    "method": "call",
    "params": {
      "channel_id": 1,
      "previous_operator_id": null,
      "persisted": false
    }
  }'
```

**Response includes:**
```json
{
  "result": {
    "channel_id": -1,
    "store_data": {
      "Store": { /* ... */ },
      "discuss.channel": [{ "livechat_operator_id": 3, /* ... */ }]
    }
  }
}
```

**Copy these values to your `.env` file.**

---

### Step 3: Setup Odoo Script Tag on Website

Add the Odoo Live Chat script to your website's HTML (in the `<head>` or before closing `</body>`):

```html
<!-- Odoo Live Chat Integration -->
<script type="text/javascript">
  (function() {
    var odooUrl = 'https://personal-company.odoo.com';
    var websiteLiveChat = new XMLHttpRequest();
    websiteLiveChat.open("GET", `${odooUrl}/im_livechat_mail_bot/website/${parseInt(1)}/live_chat_script`, true);
    websiteLiveChat.onload = function() {
      var websiteLiveChatCode = document.createElement('script');
      websiteLiveChatCode.type = 'text/javascript';
      websiteLiveChatCode.innerHTML = websiteLiveChat.response;
      document.querySelector('head').appendChild(websiteLiveChatCode);
    };
    websiteLiveChat.send();
  })();
</script>

<!-- Listen for Chatbot's custom event to open Odoo chat -->
<script type="text/javascript">
  window.addEventListener('openOdooChat', function(e) {
    console.log('[WebsiteScript] Received openOdooChat event', e.detail);
    
    // Method 1: Try Odoo mail_bot API if available
    if (window.odoo && window.odoo.mail_bot) {
      window.odoo.mail_bot.open();
      return;
    }
    
    // Method 2: Look for Odoo chat button and click it
    setTimeout(function() {
      var odooButton = document.querySelector('[data-action="im_support"]');
      if (odooButton) {
        odooButton.click();
        console.log('[WebsiteScript] Clicked Odoo chat button');
      }
    }, 500);
  });
</script>
```

---

### Step 4: Backend Endpoint Usage

The chatbot widget automatically calls this endpoint when "Chat with us" is clicked:

**Endpoint:** `POST /api/odoo/send-context`

**Request Body:**
```json
{
  "session_id": "user123"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Context sent to Odoo successfully",
  "history_sent": true,
  "message_count": 5,
  "odoo_channel_id": 17,
  "error": null
}
```

**What happens:**
1. ✅ Fetches the last 50 messages from the chatbot session
2. ✅ Formats them nicely (User: ... → AI: ...)
3. ✅ Sends as a message to Odoo live chat
4. ✅ Opens the Odoo chat widget

---

## Conversation History Format

When sent to Odoo, the conversation is formatted like this:

```
=== Conversation History from Chatbot ===
User: What is Export Genius?
AI: Export Genius is a global trade intelligence platform...
User: Show me top buyers
AI: Here are the top buyers:...
=== End of History ===

I need to discuss this with an agent.
```

This gives the Odoo agent full context of what the user discussed with the chatbot.

---

## frontend Implementation (Already Done)

The frontend automatically:

1. **Calls the backend endpoint** when "Chat with us" is clicked:
   ```typescript
   POST /api/odoo/send-context with { session_id }
   ```

2. **Dispatches custom event** that your website script listens to:
   ```javascript
   window.dispatchEvent(new CustomEvent('openOdooChat', {
     detail: { session_id: sessionIdRef.current }
   }))
   ```

3. **Tries multiple methods to open Odoo chat:**
   - Custom event listener (if website script implements it)
   - Direct Odoo mail_bot API (if available)
   - Click Odoo chat button (fallback)

---

## Testing the Integration

### 1. Test Backend Endpoint Manually

```bash
curl -X POST http://localhost:8000/api/odoo/send-context \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-user-123"}'
```

Expected response:
```json
{
  "success": true,
  "message": "Context sent to Odoo successfully",
  "history_sent": true,
  "message_count": 3
}
```

### 2. Test in Browser Console

```javascript
// Send a message to chatbot first
fetch('http://localhost:8000/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    message: 'Hello',
    session_id: 'test-session-123'
  })
})
.then(r => r.json())
.then(d => console.log('Chat:', d));

// Then click "Chat with us" button in the chatbot widget
// Check browser console for [ODOO] logs
```

### 3. Verify History Appears in Odoo

1. Open your website
2. Chat with the AI chatbot a few times
3. Click "Chat with us"
4. Check Odoo Live Chat - you should see the conversation history as a message from the chatbot user

---

## Troubleshooting

### Issue: Context not appearing in Odoo

**Check 1: Verify .env variables**
```bash
# In your backend terminal:
echo $ODOO_BASE_URL
echo $ODOO_LIVECHAT_CHANNEL_ID
```

**Check 2: Enable debug logging**
- Look for `[ODOO]` logs in your FastAPI terminal
- They show each step of sending the context

**Check 3: Verify session cookie**
- The `ODOO_SESSION_COOKIE` might expire
- Run the curl command again to get a fresh session
- Update `.env` with the new session_id

### Issue: Odoo chat widget not opening

**Check 1: Website script is loaded**
```javascript
// In browser console:
console.log(window.odoo);
```

**Check 2: Listen for event**
```javascript
// In browser console:
window.addEventListener('openOdooChat', (e) => {
  console.log('Event fired!', e.detail);
});
```

### Issue: 401/403 errors from Odoo

**Cause:** Session expired
**Solution:** 
1. Get a fresh session using the curl command above
2. Update `ODOO_SESSION_COOKIE` in `.env`
3. Restart the backend server

---

## API Reference

### Odoo API Endpoint Used

**Endpoint:** `POST /im_livechat/cors/message/post`

**Full Request Example:**
```bash
curl -X POST https://personal-company.odoo.com/im_livechat/cors/message/post \
  -H "Content-Type: application/json" \
  -H "Cookie: session_id=HA-05cCXD7Sn8raoJAtFzCfXkCMV7XewmMwPrSyCfXcYLztyTI08UAGgGNzQ9JBeBhwLD-lajSwaA5vfkFjGWA" \
  -d '{
    "id": 1,
    "jsonrpc": "2.0",
    "method": "call",
    "params": {
      "post_data": {
        "body": "User conversation history here...",
        "email_add_signature": false,
        "message_type": "comment",
        "subtype_xmlid": "mail.mt_comment"
      },
      "thread_id": 17,
      "thread_model": "discuss.channel",
      "context": { "temporary_id": 0.5 },
      "guest_token": null
    }
  }'
```

---

## Security Notes

⚠️ **Important:**

1. **Session Cookie** - This is sensitive data:
   - Store in `.env` file (gitignore it)
   - Rotate regularly (monthly recommended)
   - Don't commit to version control

2. **Conversation History** - Only sent to Odoo:
   - Not stored permanently
   - Automatically formatted
   - Available only during active sessions

3. **CORS** - Odoo has CORS handling:
   - Backend (FastAPI) makes the request
   - Frontend never calls Odoo directly
   - Protects against token exposure

---

## Next Steps

1. ✅ Add `.env` variables
2. ✅ Add Odoo script to your website  
3. ✅ Test with sample conversation
4. ✅ Monitor `[ODOO]` logs for issues
5. ✅ Train support team on new workflow

---

## Support

For issues:
1. Check the `[ODOO]` logs in FastAPI terminal
2. Test the curl command manually
3. Verify all `.env` variables are set
4. Check browser console for JavaScript errors

