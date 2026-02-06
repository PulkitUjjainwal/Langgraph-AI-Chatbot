import { useEffect } from 'react';
import { createPortal } from 'react-dom';

type Props = {
  rect: DOMRect;
  onClose: () => void;
  onShowQR: () => void;
  onOpenLink: () => void;
};

export default function WhatsAppDropdown({ rect, onClose, onShowQR, onOpenLink }: Props) {
  // Position the dropdown just below the anchor rect, aligned to right edge
  const dropdownWidth = 220;
  const margin = 8;
  let left = rect.right - dropdownWidth;
  if (left < 8) left = 8;
  const top = rect.bottom + margin;

  useEffect(() => {
    console.log('[WhatsAppDropdown] mounted at', { top, left, width: dropdownWidth });
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target) return;
      const el = document.getElementById('wa-dropdown-root');
      if (!el) return;
      if (!el.contains(target)) onClose();
    };
    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  }, [onClose]);

  const node = (
    <div
      id="wa-dropdown-root"
      style={{ position: 'fixed', top: `${top}px`, left: `${left}px`, width: `${dropdownWidth}px`, zIndex: 2147483655, pointerEvents: 'auto' }}
      className="bg-white rounded-lg shadow-lg border p-2"
      aria-hidden={false}
    >
      {/* debug-outline */}
      <div style={{ position: 'absolute', inset: 0, border: '2px solid rgba(220,38,38,0.12)', borderRadius: 8, pointerEvents: 'none' }} />
      <button
        onClick={() => { onShowQR(); }}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-lg transition-colors font-medium text-left"
      >
        <svg className="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h2M4 8h12m4 0h2M4 16h4m12 0h2M4 20h4" />
        </svg>
        Show QR
      </button>

      <button
        onClick={() => { onOpenLink(); }}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-lg transition-colors font-medium text-left mt-1"
      >
        <svg className="w-4 h-4 text-[#25D366]" fill="currentColor" viewBox="0 0 24 24">
          <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
        </svg>
        Open WhatsApp
      </button>
    </div>
  );

  return createPortal(node, document.body);
}
