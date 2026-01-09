import { useState } from "react";

type Props = {
  onSend: (text: string) => void;
  isSending?: boolean;
};

export function ChatFooter({ onSend, isSending = false }: Props) {
  const [message, setMessage] = useState("");

  function handleSend() {
    if (isSending) return;
    if (!message.trim()) return;
    onSend(message);
    setMessage("");
  }

  return (
    <div className="flex items-center gap-2 border-t border-chat-border px-4 py-4 bg-white">
      <input
        type="text"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={(e) => {
          // Enter sends (unless Shift+Enter is used to insert newline)
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!isSending) handleSend();
          }
        }}
        placeholder="Type your message..."
        disabled={isSending}
        className={`
          flex-1 rounded-xl border border-gray-200
          px-4 py-2.5 text-sm
          text-chat-text placeholder-gray-400
          focus:outline-none
          focus:ring-2 focus:ring-chat-accent focus:border-transparent
          transition-all duration-200
          ${isSending ? "opacity-60 cursor-not-allowed" : ""}
        `}
      />

      <button
        onClick={handleSend}
        disabled={isSending || !message.trim()}
        className={`
          flex items-center justify-center
          rounded-xl bg-gradient-to-r from-chat-accent to-chat-primary
          px-5 py-2.5 text-sm font-semibold
          text-white shadow-md
          hover:shadow-lg hover:scale-105
          transition-all duration-200
          disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100
        `}
      >
        {isSending ? (
          <>
            <svg className="animate-spin h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Sending
          </>
        ) : (
          <>
            Send
            <svg className="h-4 w-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </>
        )}
      </button>
    </div>
  );
}
