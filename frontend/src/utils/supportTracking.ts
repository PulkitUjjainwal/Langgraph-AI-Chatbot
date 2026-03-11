/**
 * Support Interaction Tracking Utility
 *
 * Tracks all support option clicks for analytics
 * Non-blocking, fire-and-forget implementation
 */

export type SupportInteractionType =
  | 'mode_switch'
  | 'suggested_question'
  | 'url_input'
  | 'lead_capture'
  | 'odoo_escalation'
  | 'twilio_callback'
  | 'voice_chat_start'
  | 'voice_chat_end'
  | 'file_upload'
  | 'export_data'
  | 'share_conversation'
  | 'clear_conversation'
  | 'feedback_given'
  | 'copy_message'
  | 'regenerate_response'
  | 'whatsapp_request'
  | 'schedule_demo'
  | 'chat_with_us'
  | 'call_request'
  | 'question_card_click'
  | 'data_type_selection'
  | 'country_input'
  | 'product_input'
  | 'other';

export type ConversionType = 'lead' | 'callback' | 'escalation' | 'none';

export interface SupportInteractionData {
  sessionId: string;
  interactionType: SupportInteractionType;
  interactionData?: Record<string, any>;
  pageUrl?: string;
  messageContext?: string;
  interactionOrder?: number;
  ledToConversion?: boolean;
  conversionType?: ConversionType;
}

// Track interaction order per session
let interactionOrder = 0;

export function getNextInteractionOrder(): number {
  return ++interactionOrder;
}

export function resetInteractionOrder(): void {
  interactionOrder = 0;
}

/**
 * Detect device type from user agent
 */
function getDeviceType(): string {
  const ua = navigator.userAgent;
  if (/Mobile|Android|iPhone|iPad/i.test(ua)) return 'mobile';
  if (/Tablet|iPad/i.test(ua)) return 'tablet';
  return 'desktop';
}

/**
 * Detect browser name
 */
function getBrowserName(): string {
  const ua = navigator.userAgent;
  if (ua.includes('Chrome')) return 'Chrome';
  if (ua.includes('Firefox')) return 'Firefox';
  if (ua.includes('Safari')) return 'Safari';
  if (ua.includes('Edge')) return 'Edge';
  return 'Other';
}

/**
 * Detect OS name
 */
function getOSName(): string {
  const ua = navigator.userAgent;
  if (ua.includes('Win')) return 'Windows';
  if (ua.includes('Mac')) return 'macOS';
  if (ua.includes('Linux')) return 'Linux';
  if (ua.includes('Android')) return 'Android';
  if (ua.includes('iOS')) return 'iOS';
  return 'Other';
}

/**
 * Get API base URL from environment or default
 */
function getApiBaseUrl(): string {
  // Try to get from window config first
  if (typeof window !== 'undefined' && (window as any).CHATBOT_API_URL) {
    return (window as any).CHATBOT_API_URL;
  }

  // Fallback to environment variable or default
  return import.meta.env.VITE_API_BASE_URL || 'http://localhost:8003/api';
}

/**
 * Track a support interaction
 * Non-blocking, fire-and-forget
 */
export async function trackSupportInteraction(
  sessionId: string,
  interactionType: SupportInteractionType,
  interactionData: Record<string, any> = {},
  options: {
    ledToConversion?: boolean;
    conversionType?: ConversionType;
    messageContext?: string;
  } = {}
): Promise<void> {
  try {
    const payload = {
      session_id: sessionId,
      interaction_type: interactionType,
      interaction_data: {
        ...interactionData,
        timestamp: new Date().toISOString(),
      },
      page_url: window.location.href,
      message_context: options.messageContext,
      interaction_order: getNextInteractionOrder(),
      led_to_conversion: options.ledToConversion || false,
      conversion_type: options.conversionType || 'none',
      device_type: getDeviceType(),
      browser_name: getBrowserName(),
      os_name: getOSName(),
    };

    const apiUrl = getApiBaseUrl();

    // Fire-and-forget - don't await or block
    fetch(`${apiUrl}/support/track`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })
      .then((response) => {
        if (response.ok) {
          console.debug(`✓ Tracked: ${interactionType}`, interactionData);
        } else {
          console.debug(`⚠ Tracking failed: ${response.status}`);
        }
      })
      .catch((error) => {
        // Silent fail - tracking should never break functionality
        console.debug('Tracking error:', error);
      });
  } catch (error) {
    // Silent fail - tracking errors should never affect user experience
    console.debug('Tracking setup error:', error);
  }
}

/**
 * Track suggested question click
 */
export function trackSuggestedQuestionClick(
  sessionId: string,
  question: string,
  index: number
): void {
  trackSupportInteraction(sessionId, 'suggested_question', {
    question,
    index,
    source: 'suggestion_pill',
  });
}

/**
 * Track question card click
 */
export function trackQuestionCardClick(
  sessionId: string,
  cardTitle: string,
  index: number
): void {
  trackSupportInteraction(sessionId, 'question_card_click', {
    card_title: cardTitle,
    index,
    source: 'question_card',
  });
}

/**
 * Track action button click
 */
export function trackActionClick(
  sessionId: string,
  actionType: string,
  metadata: Record<string, any> = {}
): void {
  // Map action types to interaction types
  const interactionTypeMap: Record<string, SupportInteractionType> = {
    schedule_demo: 'schedule_demo',
    whatsapp: 'whatsapp_request',
    call: 'call_request',
    chat_with_us: 'chat_with_us',
    hubspot_chat: 'chat_with_us',
    refresh: 'regenerate_response',
    continue_chat: 'other',
    chat: 'suggested_question', // Suggestion pills
  };

  const interactionType = interactionTypeMap[actionType] || 'other';

  trackSupportInteraction(sessionId, interactionType, {
    action_type: actionType,
    ...metadata,
  });
}

/**
 * Track reset conversation
 */
export function trackResetConversation(sessionId: string): void {
  trackSupportInteraction(sessionId, 'clear_conversation', {
    action: 'reset_conversation',
  });
}

/**
 * Track WhatsApp interaction
 */
export function trackWhatsAppClick(
  sessionId: string,
  method: 'qr_code' | 'direct_link'
): void {
  trackSupportInteraction(sessionId, 'whatsapp_request', {
    method,
  });
}

/**
 * Track voice chat
 */
export function trackVoiceChat(
  sessionId: string,
  action: 'start' | 'end',
  duration?: number
): void {
  const interactionType = action === 'start' ? 'voice_chat_start' : 'voice_chat_end';
  trackSupportInteraction(sessionId, interactionType, {
    action,
    ...(duration && { duration_seconds: duration }),
  });
}

/**
 * Track data type selection
 */
export function trackDataTypeSelection(
  sessionId: string,
  dataType: string
): void {
  trackSupportInteraction(sessionId, 'data_type_selection', {
    data_type: dataType,
  });
}

/**
 * Track country input
 */
export function trackCountryInput(sessionId: string, country: string): void {
  trackSupportInteraction(sessionId, 'country_input', {
    country,
  });
}

/**
 * Track product input
 */
export function trackProductInput(sessionId: string, product: string): void {
  trackSupportInteraction(sessionId, 'product_input', {
    product,
  });
}

/**
 * Track lead capture (conversion)
 */
export function trackLeadCapture(
  sessionId: string,
  leadData: { email?: string; phone?: string; company_name?: string }
): void {
  trackSupportInteraction(
    sessionId,
    'lead_capture',
    {
      has_email: !!leadData.email,
      has_phone: !!leadData.phone,
      has_company: !!leadData.company_name,
    },
    {
      ledToConversion: true,
      conversionType: 'lead',
    }
  );
}

/**
 * Track Odoo escalation (conversion)
 */
export function trackOdooEscalation(sessionId: string): void {
  trackSupportInteraction(
    sessionId,
    'odoo_escalation',
    {
      platform: 'odoo',
    },
    {
      ledToConversion: true,
      conversionType: 'escalation',
    }
  );
}

/**
 * Track callback request (conversion)
 */
export function trackCallbackRequest(sessionId: string, phone?: string): void {
  trackSupportInteraction(
    sessionId,
    'twilio_callback',
    {
      has_phone: !!phone,
    },
    {
      ledToConversion: true,
      conversionType: 'callback',
    }
  );
}
