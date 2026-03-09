/**
 * Device and Browser Detection Utility
 *
 * Captures comprehensive device, browser, OS, and location information
 * for conversation history and feedback tracking.
 */

export interface DeviceInfo {
  // Device
  device_type: 'mobile' | 'tablet' | 'desktop' | 'unknown';

  // Browser
  browser_name: string;
  browser_version: string;
  user_agent: string;

  // Operating System
  os_name: string;
  os_version: string;

  // Location & Language
  timezone: string;
  language: string;

  // Screen
  screen_width: number;
  screen_height: number;
  viewport_width: number;
  viewport_height: number;
}

/**
 * Detect device type based on screen size and user agent
 */
function detectDeviceType(): 'mobile' | 'tablet' | 'desktop' | 'unknown' {
  const ua = navigator.userAgent.toLowerCase();
  const width = window.innerWidth;

  // Check user agent first
  if (/(tablet|ipad|playbook|silk)|(android(?!.*mobi))/i.test(ua)) {
    return 'tablet';
  }

  if (/Mobile|Android|iP(hone|od)|IEMobile|BlackBerry|Kindle|Silk-Accelerated|(hpw|web)OS|Opera M(obi|ini)/.test(ua)) {
    return 'mobile';
  }

  // Check screen width as fallback
  if (width < 768) {
    return 'mobile';
  } else if (width >= 768 && width < 1024) {
    return 'tablet';
  } else if (width >= 1024) {
    return 'desktop';
  }

  return 'unknown';
}

/**
 * Detect browser name and version
 */
function detectBrowser(): { name: string; version: string } {
  const ua = navigator.userAgent;
  let name = 'Unknown';
  let version = 'Unknown';

  // Edge (Chromium-based)
  if (ua.indexOf('Edg/') > -1) {
    name = 'Edge';
    const match = ua.match(/Edg\/([0-9.]+)/);
    if (match) version = match[1];
  }
  // Chrome
  else if (ua.indexOf('Chrome') > -1 && ua.indexOf('Edg') === -1) {
    name = 'Chrome';
    const match = ua.match(/Chrome\/([0-9.]+)/);
    if (match) version = match[1];
  }
  // Safari
  else if (ua.indexOf('Safari') > -1 && ua.indexOf('Chrome') === -1) {
    name = 'Safari';
    const match = ua.match(/Version\/([0-9.]+)/);
    if (match) version = match[1];
  }
  // Firefox
  else if (ua.indexOf('Firefox') > -1) {
    name = 'Firefox';
    const match = ua.match(/Firefox\/([0-9.]+)/);
    if (match) version = match[1];
  }
  // Opera
  else if (ua.indexOf('Opera') > -1 || ua.indexOf('OPR') > -1) {
    name = 'Opera';
    const match = ua.match(/(?:Opera|OPR)\/([0-9.]+)/);
    if (match) version = match[1];
  }
  // Internet Explorer
  else if (ua.indexOf('Trident') > -1) {
    name = 'Internet Explorer';
    const match = ua.match(/rv:([0-9.]+)/);
    if (match) version = match[1];
  }
  // Samsung Internet
  else if (ua.indexOf('SamsungBrowser') > -1) {
    name = 'Samsung Internet';
    const match = ua.match(/SamsungBrowser\/([0-9.]+)/);
    if (match) version = match[1];
  }

  return { name, version };
}

/**
 * Detect operating system name and version
 */
function detectOS(): { name: string; version: string } {
  const ua = navigator.userAgent;
  let name = 'Unknown';
  let version = 'Unknown';

  // Windows
  if (ua.indexOf('Win') > -1) {
    name = 'Windows';
    if (ua.indexOf('Windows NT 10.0') > -1) version = '10';
    else if (ua.indexOf('Windows NT 6.3') > -1) version = '8.1';
    else if (ua.indexOf('Windows NT 6.2') > -1) version = '8';
    else if (ua.indexOf('Windows NT 6.1') > -1) version = '7';
    else if (ua.indexOf('Windows NT 6.0') > -1) version = 'Vista';
    else if (ua.indexOf('Windows NT 5.1') > -1) version = 'XP';
  }
  // macOS
  else if (ua.indexOf('Mac') > -1) {
    name = 'macOS';
    const match = ua.match(/Mac OS X ([0-9_]+)/);
    if (match) version = match[1].replace(/_/g, '.');
  }
  // iOS
  else if (ua.indexOf('iPhone') > -1 || ua.indexOf('iPad') > -1) {
    name = 'iOS';
    const match = ua.match(/OS ([0-9_]+)/);
    if (match) version = match[1].replace(/_/g, '.');
  }
  // Android
  else if (ua.indexOf('Android') > -1) {
    name = 'Android';
    const match = ua.match(/Android ([0-9.]+)/);
    if (match) version = match[1];
  }
  // Linux
  else if (ua.indexOf('Linux') > -1) {
    name = 'Linux';
  }
  // Chrome OS
  else if (ua.indexOf('CrOS') > -1) {
    name = 'Chrome OS';
  }

  return { name, version };
}

/**
 * Get user's timezone
 */
function getTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return 'Unknown';
  }
}

/**
 * Get user's preferred language
 */
function getLanguage(): string {
  return navigator.language || 'Unknown';
}

/**
 * Get complete device information
 */
export function getDeviceInfo(): DeviceInfo {
  const browser = detectBrowser();
  const os = detectOS();

  return {
    // Device
    device_type: detectDeviceType(),

    // Browser
    browser_name: browser.name,
    browser_version: browser.version,
    user_agent: navigator.userAgent,

    // Operating System
    os_name: os.name,
    os_version: os.version,

    // Location & Language
    timezone: getTimezone(),
    language: getLanguage(),

    // Screen
    screen_width: window.screen.width,
    screen_height: window.screen.height,
    viewport_width: window.innerWidth,
    viewport_height: window.innerHeight,
  };
}

/**
 * Get a formatted device info string for display
 */
export function getDeviceInfoString(): string {
  const info = getDeviceInfo();
  return `${info.browser_name} ${info.browser_version} on ${info.os_name} ${info.os_version} (${info.device_type})`;
}

/**
 * Get device info for API requests
 */
export function getDeviceInfoForAPI() {
  const info = getDeviceInfo();
  return {
    device_type: info.device_type,
    browser_name: info.browser_name,
    browser_version: info.browser_version,
    os_name: info.os_name,
    os_version: info.os_version,
    timezone: info.timezone,
    language: info.language,
    user_agent: info.user_agent,
  };
}
