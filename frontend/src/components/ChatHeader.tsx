type Props = {
  onClose: () => void;
};

// MI Logo component - inline SVG for portability
function MiLogo({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="40" height="40" rx="8" fill="#1f2937"/>
      <text x="50%" y="55%" dominantBaseline="middle" textAnchor="middle" fill="white" fontSize="16" fontWeight="bold" fontFamily="Inter, sans-serif">MI</text>
    </svg>
  );
}

export function ChatHeader({ onClose }: Props) {
  return (
    <div
      className="px-5 py-4"
      style={{ background: 'linear-gradient(135deg, #374151 0%, #1f2937 100%)' }}
    >
      {/* Top row with logo, title and close button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* MI Logo */}
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white backdrop-blur-sm border border-white/20 overflow-hidden">
            <MiLogo className="h-8 w-8" />
          </div>

          {/* Title Section */}
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="text-lg font-semibold text-white tracking-wide">
                ASK MI
              </span>
              <span className="px-2 py-0.5 text-[10px] font-bold bg-orange-500 text-white rounded-full uppercase tracking-wider">
                AI
              </span>
            </div>
            <span className="text-[11px] text-gray-300">
              Market Inside Assistant
            </span>
          </div>
        </div>

        {/* Close Button */}
        <button
          onClick={onClose}
          className="flex h-9 w-9 items-center justify-center rounded-xl text-gray-300 hover:bg-white/10 hover:text-white transition-all duration-200"
          aria-label="Close chat"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18 12H6" />
          </svg>
        </button>
      </div>

      {/* Description */}
      <p className="text-xs text-gray-300 mt-3 leading-relaxed">
        Get instant answers about global trade data, buyers, suppliers, and market insights.
      </p>
    </div>
  );
}
