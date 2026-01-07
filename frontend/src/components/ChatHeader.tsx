type Props = {
  onClose: () => void;
};

export function ChatHeader({ onClose }: Props) {
  return (
    <div className="flex items-center justify-between border-b px-4 py-3">
      <div className="flex flex-col">
        <span className="text-sm font-semibold text-chat-text">
          Market Inside AI
        </span>
        <span className="text-xs text-chat-muted">
          Online
        </span>
      </div>

      <button
        onClick={onClose}
        className="text-lg leading-none text-chat-muted hover:text-chat-text"
        aria-label="Close chat"
      >
        ×
      </button>
    </div>
  );
}
