// Comprehensive country phone data with validation rules

export interface CountryPhoneData {
  code: string;           // Country code (e.g., "US")
  name: string;           // Country name
  dialCode: string;       // Dial code (e.g., "+1")
  flag: string;           // Flag emoji
  format: string;         // Display format (e.g., "XXX-XXX-XXXX")
  minDigits: number;      // Minimum digits (excluding country code)
  maxDigits: number;      // Maximum digits (excluding country code)
  placeholder: string;    // Example number
}

// Popular countries (shown first in dropdown)
export const POPULAR_COUNTRIES: CountryPhoneData[] = [
  {
    code: 'US',
    name: 'United States',
    dialCode: '+1',
    flag: '🇺🇸',
    format: 'XXX-XXX-XXXX',
    minDigits: 10,
    maxDigits: 10,
    placeholder: '555-123-4567'
  },
  {
    code: 'IN',
    name: 'India',
    dialCode: '+91',
    flag: '🇮🇳',
    format: 'XXXXX XXXXX',
    minDigits: 10,
    maxDigits: 10,
    placeholder: '98765 43210'
  },
  {
    code: 'GB',
    name: 'United Kingdom',
    dialCode: '+44',
    flag: '🇬🇧',
    format: 'XX XXXX XXXX',
    minDigits: 10,
    maxDigits: 10,
    placeholder: '20 7123 4567'
  },
  {
    code: 'CA',
    name: 'Canada',
    dialCode: '+1',
    flag: '🇨🇦',
    format: 'XXX-XXX-XXXX',
    minDigits: 10,
    maxDigits: 10,
    placeholder: '416-555-1234'
  }
];

// All other countries (alphabetically)
export const ALL_COUNTRIES: CountryPhoneData[] = [
  {
    code: 'AF',
    name: 'Afghanistan',
    dialCode: '+93',
    flag: '🇦🇫',
    format: 'XXX XXX XXXX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '701 234 567'
  },
  {
    code: 'AU',
    name: 'Australia',
    dialCode: '+61',
    flag: '🇦🇺',
    format: 'XXX XXX XXX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '412 345 678'
  },
  {
    code: 'BR',
    name: 'Brazil',
    dialCode: '+55',
    flag: '🇧🇷',
    format: 'XX XXXXX-XXXX',
    minDigits: 10,
    maxDigits: 11,
    placeholder: '11 98765-4321'
  },
  {
    code: 'CN',
    name: 'China',
    dialCode: '+86',
    flag: '🇨🇳',
    format: 'XXX XXXX XXXX',
    minDigits: 11,
    maxDigits: 11,
    placeholder: '138 0013 8000'
  },
  {
    code: 'FR',
    name: 'France',
    dialCode: '+33',
    flag: '🇫🇷',
    format: 'X XX XX XX XX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '6 12 34 56 78'
  },
  {
    code: 'DE',
    name: 'Germany',
    dialCode: '+49',
    flag: '🇩🇪',
    format: 'XXX XXXXXXX',
    minDigits: 10,
    maxDigits: 11,
    placeholder: '151 23456789'
  },
  {
    code: 'HK',
    name: 'Hong Kong',
    dialCode: '+852',
    flag: '🇭🇰',
    format: 'XXXX XXXX',
    minDigits: 8,
    maxDigits: 8,
    placeholder: '5123 4567'
  },
  {
    code: 'ID',
    name: 'Indonesia',
    dialCode: '+62',
    flag: '🇮🇩',
    format: 'XXX-XXX-XXXX',
    minDigits: 9,
    maxDigits: 11,
    placeholder: '812-345-6789'
  },
  {
    code: 'IE',
    name: 'Ireland',
    dialCode: '+353',
    flag: '🇮🇪',
    format: 'XX XXX XXXX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '85 123 4567'
  },
  {
    code: 'IL',
    name: 'Israel',
    dialCode: '+972',
    flag: '🇮🇱',
    format: 'XX-XXX-XXXX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '50-123-4567'
  },
  {
    code: 'IT',
    name: 'Italy',
    dialCode: '+39',
    flag: '🇮🇹',
    format: 'XXX XXX XXXX',
    minDigits: 9,
    maxDigits: 10,
    placeholder: '312 345 6789'
  },
  {
    code: 'JP',
    name: 'Japan',
    dialCode: '+81',
    flag: '🇯🇵',
    format: 'XX-XXXX-XXXX',
    minDigits: 10,
    maxDigits: 10,
    placeholder: '90-1234-5678'
  },
  {
    code: 'MY',
    name: 'Malaysia',
    dialCode: '+60',
    flag: '🇲🇾',
    format: 'XX-XXXX XXXX',
    minDigits: 9,
    maxDigits: 10,
    placeholder: '12-3456 7890'
  },
  {
    code: 'MX',
    name: 'Mexico',
    dialCode: '+52',
    flag: '🇲🇽',
    format: 'XX XXXX XXXX',
    minDigits: 10,
    maxDigits: 10,
    placeholder: '55 1234 5678'
  },
  {
    code: 'NL',
    name: 'Netherlands',
    dialCode: '+31',
    flag: '🇳🇱',
    format: 'X XX XX XX XX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '6 12 34 56 78'
  },
  {
    code: 'NZ',
    name: 'New Zealand',
    dialCode: '+64',
    flag: '🇳🇿',
    format: 'XX XXX XXXX',
    minDigits: 9,
    maxDigits: 10,
    placeholder: '21 123 4567'
  },
  {
    code: 'PH',
    name: 'Philippines',
    dialCode: '+63',
    flag: '🇵🇭',
    format: 'XXX XXX XXXX',
    minDigits: 10,
    maxDigits: 10,
    placeholder: '905 123 4567'
  },
  {
    code: 'PL',
    name: 'Poland',
    dialCode: '+48',
    flag: '🇵🇱',
    format: 'XXX XXX XXX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '512 345 678'
  },
  {
    code: 'RU',
    name: 'Russia',
    dialCode: '+7',
    flag: '🇷🇺',
    format: 'XXX XXX-XX-XX',
    minDigits: 10,
    maxDigits: 10,
    placeholder: '912 345-67-89'
  },
  {
    code: 'SA',
    name: 'Saudi Arabia',
    dialCode: '+966',
    flag: '🇸🇦',
    format: 'XX XXX XXXX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '50 123 4567'
  },
  {
    code: 'SG',
    name: 'Singapore',
    dialCode: '+65',
    flag: '🇸🇬',
    format: 'XXXX XXXX',
    minDigits: 8,
    maxDigits: 8,
    placeholder: '8123 4567'
  },
  {
    code: 'ZA',
    name: 'South Africa',
    dialCode: '+27',
    flag: '🇿🇦',
    format: 'XX XXX XXXX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '82 123 4567'
  },
  {
    code: 'KR',
    name: 'South Korea',
    dialCode: '+82',
    flag: '🇰🇷',
    format: 'XX-XXXX-XXXX',
    minDigits: 9,
    maxDigits: 10,
    placeholder: '10-1234-5678'
  },
  {
    code: 'ES',
    name: 'Spain',
    dialCode: '+34',
    flag: '🇪🇸',
    format: 'XXX XX XX XX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '612 34 56 78'
  },
  {
    code: 'SE',
    name: 'Sweden',
    dialCode: '+46',
    flag: '🇸🇪',
    format: 'XX-XXX XX XX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '70-123 45 67'
  },
  {
    code: 'CH',
    name: 'Switzerland',
    dialCode: '+41',
    flag: '🇨🇭',
    format: 'XX XXX XX XX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '78 123 45 67'
  },
  {
    code: 'TH',
    name: 'Thailand',
    dialCode: '+66',
    flag: '🇹🇭',
    format: 'XX XXX XXXX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '81 234 5678'
  },
  {
    code: 'TR',
    name: 'Turkey',
    dialCode: '+90',
    flag: '🇹🇷',
    format: 'XXX XXX XX XX',
    minDigits: 10,
    maxDigits: 10,
    placeholder: '532 123 45 67'
  },
  {
    code: 'AE',
    name: 'United Arab Emirates',
    dialCode: '+971',
    flag: '🇦🇪',
    format: 'XX XXX XXXX',
    minDigits: 9,
    maxDigits: 9,
    placeholder: '50 123 4567'
  },
  {
    code: 'VN',
    name: 'Vietnam',
    dialCode: '+84',
    flag: '🇻🇳',
    format: 'XX XXXX XXXX',
    minDigits: 9,
    maxDigits: 10,
    placeholder: '91 234 5678'
  }
];

// Combined list with popular countries first
export const COUNTRIES_LIST: CountryPhoneData[] = [
  ...POPULAR_COUNTRIES,
  ...ALL_COUNTRIES.filter(
    country => !POPULAR_COUNTRIES.find(p => p.code === country.code)
  )
];

// Helper function to find country by dial code
export function findCountryByDialCode(dialCode: string): CountryPhoneData | undefined {
  return COUNTRIES_LIST.find(c => c.dialCode === dialCode);
}

// Helper function to find country by code
export function findCountryByCode(code: string): CountryPhoneData | undefined {
  return COUNTRIES_LIST.find(c => c.code === code);
}

// Helper function to validate phone number for a country
export function validatePhoneNumber(
  phoneNumber: string,
  country: CountryPhoneData
): { valid: boolean; error?: string } {
  // Remove all non-digits
  const digitsOnly = phoneNumber.replace(/\D/g, '');

  // Check minimum length
  if (digitsOnly.length < country.minDigits) {
    return {
      valid: false,
      error: `Phone number too short. ${country.name} requires ${country.minDigits} digits.`
    };
  }

  // Check maximum length
  if (digitsOnly.length > country.maxDigits) {
    return {
      valid: false,
      error: `Phone number too long. ${country.name} allows maximum ${country.maxDigits} digits.`
    };
  }

  return { valid: true };
}

// Helper function to format phone number as E.164
export function formatAsE164(phoneNumber: string, country: CountryPhoneData): string {
  const digitsOnly = phoneNumber.replace(/\D/g, '');
  return `${country.dialCode}${digitsOnly}`;
}
