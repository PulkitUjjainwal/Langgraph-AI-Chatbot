import { useState } from "react";

type Props = {
  onSend: (text: string) => void;
  isSending?: boolean;
  position?: "top" | "bottom";
};

export function ChatFooter({ onSend, isSending = false, position = "bottom" }: Props) {
  const [message, setMessage] = useState("");

  function handleSend() {
    if (isSending) return;
    if (!message.trim()) return;
    onSend(message);
    setMessage("");
  }

  const isTop = position === "top";

  return (
    <div className={`px-4 py-3 ${isTop ? "bg-gray-50 border-b border-gray-200" : "border-t border-gray-200 bg-white"}`}>
      {/* Input Container */}
      <div className="flex items-center gap-2">
        <div className="flex-1 relative">
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!isSending) handleSend();
              }
            }}
            placeholder="Ask a question"
            disabled={isSending}
            className={`
              w-full rounded-full border border-gray-300
              pl-4 pr-12 py-2.5 text-sm
              text-gray-900 placeholder-gray-500
              focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500
              transition-all duration-200
              ${isSending ? "opacity-60 cursor-not-allowed bg-gray-50" : "bg-white"}
            `}
          />

          {/* Send Button - Inside Input */}
          <button
            onClick={handleSend}
            disabled={isSending || !message.trim()}
            className={`
              absolute right-1.5 top-1/2 -translate-y-1/2
              flex items-center justify-center
              h-8 w-8 rounded-full
              bg-orange-500 text-white
              hover:bg-orange-600
              transition-all duration-200
              disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-orange-500
            `}
            aria-label="Send message"
          >
            {isSending ? (
              <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            ) : (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Disclaimer - only show at bottom */}
      {!isTop && (
        <p className="text-[10px] text-gray-400 text-center mt-2">
          By chatting, you agree to our{" "}
          <a href="#" className="text-orange-600 hover:underline">terms</a>
        </p>
      )}
    </div>
  );
}
