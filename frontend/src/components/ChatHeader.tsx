type Props = {
  onClose: () => void;
};

export function ChatHeader({ onClose }: Props) {
  return (
    <div
      className="flex items-center justify-between px-5 py-4"
      style={{ background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)' }}
    >
      <div className="flex items-center gap-3">
        {/* Logo/Avatar */}
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 backdrop-blur-sm">
          <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </div>

        {/* Title Section - AWS Style */}
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white">
              Ask MI
            </span>
            <span className="px-1.5 py-0.5 text-[10px] font-medium bg-orange-500/20 text-orange-300 rounded">
              AI
            </span>
          </div>
          <span className="text-xs text-gray-400">
            Trade intelligence assistant
          </span>
        </div>
      </div>

      {/* Close Button */}
      <button
        onClick={onClose}
        className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 hover:bg-white/10 hover:text-white transition-all duration-200"
        aria-label="Close chat"
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18 12H6" />
        </svg>
      </button>
    </div>
  );
}
