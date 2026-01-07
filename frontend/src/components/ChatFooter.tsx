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
    <div className="flex items-center gap-2 border-t px-4 py-3">
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
        placeholder="Type a message..."
        disabled={isSending}
        className={`
          flex-1 rounded-lg border border-gray-200
          px-3 py-2 text-sm
          text-chat-text
          focus:outline-none
          focus:ring-1 focus:ring-chat-primary
          ${isSending ? "opacity-60 cursor-not-allowed" : ""}
        `}
      />

      <button
        onClick={handleSend}
        disabled={isSending}
        className={`
          rounded-lg bg-chat-accent
          px-4 py-2 text-sm font-medium
          text-white
          hover:opacity-90
          ${isSending ? "opacity-70 cursor-not-allowed" : ""}
        `}
      >
        {isSending ? "Sending..." : "Send"}
      </button>
    </div>
  );
}
