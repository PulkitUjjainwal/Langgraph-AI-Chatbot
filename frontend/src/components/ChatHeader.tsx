type Props = {
  onClose: () => void;
};

export function ChatHeader({ onClose }: Props) {
  return (
    <div className="flex items-center justify-between border-b border-chat-border px-5 py-4 bg-white">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-chat-accent to-chat-primary text-white font-semibold shadow-md">
          MI
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-chat-text">
            Market Inside AI
          </span>
          <span className="text-xs text-chat-muted flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-green-500"></span>
            Online
          </span>
        </div>
      </div>

      <button
        onClick={onClose}
        className="flex h-8 w-8 items-center justify-center rounded-full text-xl leading-none text-chat-muted hover:bg-gray-100 hover:text-chat-text transition-colors"
        aria-label="Close chat"
      >
        ×
      </button>
    </div>
  );
}
