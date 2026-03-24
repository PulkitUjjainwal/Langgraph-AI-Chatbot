import { useState, forwardRef, useImperativeHandle, useRef } from "react";

type Props = {
  onSend: (text: string) => void;
  isSending?: boolean;
  position?: "top" | "bottom";
  onOpenOptionsMenu?: () => void;
  onCloseOptionsMenu?: () => void;
};

export type ChatFooterHandle = {
  setMessage: (text: string) => void;
  send: () => void;
  focus: () => void;
};

export const ChatFooter = forwardRef<ChatFooterHandle, Props>(function ChatFooter(
  { onSend, isSending = false, position = "bottom", onOpenOptionsMenu, onCloseOptionsMenu },
  ref
) {
  const [message, setMessage] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function handleSend() {
    if (isSending) return;
    if (!message.trim()) return;
    onSend(message);
    setMessage("");
  }

  // Expose imperative methods so host integration can programmatically set/send
  useImperativeHandle(ref, () => ({
    setMessage: (text: string) => setMessage(text),
    send: () => handleSend(),
    focus: () => inputRef.current?.focus(),
  }), [message, isSending]);

  const isTop = position === "bottom";

  return (
    <div className="px-4 py-3 bg-white">
      {/* Input Container - Complete black outlined box containing ALL elements */}
      <div
        className="flex items-center gap-0 rounded-full bg-white"
        style={{
          border: '2px solid #000000',
          padding: '4px'
        }}
      >
        {/* Three Dots Menu Button - Left side inside the black outline */}
        <button
          onClick={onOpenOptionsMenu}
          className="flex items-center justify-center h-10 w-10 rounded-full hover:bg-gray-100 transition-all duration-200 cursor-pointer flex-shrink-0"
          aria-label="More options"
        >
          <svg className="h-5 w-5 text-black" fill="currentColor" viewBox="0 0 24 24">
            <circle cx="12" cy="5" r="2"/>
            <circle cx="12" cy="12" r="2"/>
            <circle cx="12" cy="19" r="2"/>
          </svg>
        </button>

        {/* Input Field - Middle, taking up remaining space, no borders */}
        <input
          ref={inputRef}
          type="text"
          value={message}
          onChange={(e) => {
            setMessage(e.target.value);
            // Close options menu when user starts typing
            if (onCloseOptionsMenu) onCloseOptionsMenu();
          }}
          onFocus={() => {
            // Close options menu when user focuses on input
            if (onCloseOptionsMenu) onCloseOptionsMenu();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!isSending) handleSend();
            }
          }}
          placeholder="Ask me a question"
          disabled={isSending}
          className={`
            flex-1
            px-2 py-2 text-base
            text-black placeholder-gray-500
            focus:outline-none
            transition-all duration-200
            border-none bg-transparent
            ${isSending ? "opacity-60 cursor-not-allowed" : "cursor-text"}
          `}
        />

        {/* Send Button - Right side inside the black outline - Paper plane icon */}
        <button
          onClick={handleSend}
          disabled={isSending || !message.trim()}
          className={`
            flex items-center justify-center
            h-10 w-10 rounded-full
            bg-black text-white
            hover:bg-gray-800
            transition-all duration-200
            cursor-pointer
            flex-shrink-0
            disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-black
          `}
          aria-label="Send message"
        >
          {isSending ? (
            <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          ) : (
            <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24" style={{ transform: 'rotate(-45deg)' }}>
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
            </svg>
          )}
        </button>
      </div>

      {/* Disclaimer - matching the reference exactly */}
      {!isTop && (
        <p className="text-[11px] text-gray-600 text-center mt-2.5">
          By chatting, you are agreeing to our{" "}
          <a href="https://www.marketinside.io/terms" target="_blank" rel="noopener noreferrer" className="text-orange-500 hover:text-orange-600 hover:underline">
            terms & conditions
          </a>
        </p>
      )}
    </div>
  );
});
