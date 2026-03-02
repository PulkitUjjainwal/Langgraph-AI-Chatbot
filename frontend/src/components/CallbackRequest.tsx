import React, { useState, useRef
  // , useEffect
 } from 'react';
import type { CountryPhoneData } from '../utils/countryPhoneData';
import {
  COUNTRIES_LIST,
  validatePhoneNumber,
  formatAsE164
} from '../utils/countryPhoneData';

interface CallbackRequestProps {
  sessionId: string;
  apiUrl: string;
  onClose: () => void;
}

type CallStatus = 'idle' | 'calling' | 'connected' | 'failed';

const CallbackRequest: React.FC<CallbackRequestProps> = ({ sessionId, apiUrl, onClose }) => {
  // Default to US
  const [selectedCountry, setSelectedCountry] = useState<CountryPhoneData>(COUNTRIES_LIST[0]);
  const [phone, setPhone] = useState('');
  const [status, setStatus] = useState<CallStatus>('idle');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [showCountryDropdown, setShowCountryDropdown] = useState(false);
  const [countrySearch, setCountrySearch] = useState('');
  const [forceUpdate, setForceUpdate] = useState(0); // Force re-render
  const dropdownRef = useRef<HTMLDivElement>(null);

  // NO AUTOMATIC OUTSIDE CLICK HANDLER - Dropdown closes manually on selection or close button

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    let value = e.target.value;

    // Allow only digits, spaces, and common phone separators
    value = value.replace(/[^\d\s\-()]/g, '');

    setPhone(value);
    setError('');
  };

  const handleCountrySelect = (country: CountryPhoneData) => {
    // Update state IMMEDIATELY
    setSelectedCountry(country);
    setForceUpdate(prev => prev + 1);
    setPhone(''); // Clear phone when country changes
    setError('');

    // Close dropdown immediately
    setShowCountryDropdown(false);
    setCountrySearch('');
  };

  const filteredCountries = COUNTRIES_LIST.filter(country =>
    country.name.toLowerCase().includes(countrySearch.toLowerCase()) ||
    country.dialCode.includes(countrySearch) ||
    country.code.toLowerCase().includes(countrySearch.toLowerCase())
  );

  const requestCallback = async () => {
    // Validate phone number for selected country
    const validation = validatePhoneNumber(phone, selectedCountry);

    if (!validation.valid) {
      setError(validation.error || 'Invalid phone number');
      return;
    }

    // Format to E.164
    const e164Phone = formatAsE164(phone, selectedCountry);

    setStatus('calling');
    setError('');

    try {
      let baseUrl = apiUrl;
      if (!baseUrl.endsWith('/api')) baseUrl = `${baseUrl}/api`;

      const response = await fetch(`${baseUrl}/callback/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          phone_number: e164Phone
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to initiate callback');
      }

      setStatus('connected');
      setMessage(data.message || 'Call initiated successfully');
    } catch (err: any) {
      setStatus('failed');
      setError(err.message || 'Failed to request callback. Please try again.');
      console.error('Callback request error:', err);

      // Reset to idle after 3 seconds on error
      setTimeout(() => {
        setStatus('idle');
        setError('');
      }, 3000);
    }
  };

  if (status === 'calling') {
    return (
      <div className="p-5 bg-orange-50 border border-orange-200 rounded-2xl">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex gap-1">
            {[0, 150, 300].map(delay => (
              <span
                key={delay}
                className="w-2 h-2 rounded-full bg-orange-500 animate-bounce"
                style={{ animationDelay: `${delay}ms` }}
              />
            ))}
          </div>
          <span className="text-sm font-semibold text-orange-700">Initiating call...</span>
        </div>
        <p className="text-xs text-gray-600">
          Connecting to <span className="font-medium">{phone}</span>
        </p>
      </div>
    );
  }

  if (status === 'connected') {
    return (
      <div className="p-5 bg-green-50 border border-green-200 rounded-2xl">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse ring-4 ring-green-200" />
          <span className="text-sm font-semibold text-green-700">Call Initiated</span>
        </div>
        <p className="text-xs text-gray-700 mb-3">{message}</p>
        <p className="text-xs text-gray-600 mb-4">
          You'll receive a call at <span className="font-medium">{phone}</span> shortly.
          Please answer your phone, and our team will join you.
        </p>
        <button
          onClick={onClose}
          className="w-full py-2 rounded-xl bg-green-600 hover:bg-green-700 text-white text-sm font-semibold
            transition-all duration-150 active:scale-95"
        >
          Got It
        </button>
      </div>
    );
  }

  if (status === 'failed') {
    return (
      <div className="p-5 bg-red-50 border border-red-200 rounded-2xl">
        <div className="flex items-center gap-3 mb-3">
          <svg className="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="text-sm font-semibold text-red-700">Call Failed</span>
        </div>
        <p className="text-xs text-red-600 mb-4">{error}</p>
        <button
          onClick={onClose}
          className="w-full py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-sm font-semibold
            transition-all duration-150 active:scale-95"
        >
          Close
        </button>
      </div>
    );
  }

  // Idle state - show phone input form
  return (
    <div className="p-5 bg-white border border-orange-200 rounded-2xl shadow-lg">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-orange-100 flex items-center justify-center">
            <svg className="w-5 h-5 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-bold text-gray-800">Talk to Our Team</h3>
            <p className="text-xs text-gray-500">We'll call you right away</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="mb-4">
        <label className="block text-xs font-medium text-gray-700 mb-2">
          Your Phone Number
        </label>

        {/* Country selector and phone input */}
        <div className="flex gap-2">
          {/* Country dropdown */}
          <div className="relative" ref={dropdownRef} key={`country-selector-${forceUpdate}`}>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setShowCountryDropdown(!showCountryDropdown);
              }}
              className="flex items-center gap-2 px-3 py-2.5 border border-gray-300 rounded-xl
                hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-orange-500
                transition-all duration-150 bg-white min-w-[140px] cursor-pointer"
            >
              <span className="text-xl" key={`flag-${selectedCountry.code}`}>{selectedCountry.flag}</span>
              <span className="text-sm font-medium text-gray-700" key={`code-${selectedCountry.code}`}>{selectedCountry.dialCode}</span>
              <svg className={`w-4 h-4 text-gray-500 transition-transform ${showCountryDropdown ? 'rotate-180' : ''}`}
                fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {/* Dropdown menu */}
            {showCountryDropdown && (
              <div className="absolute z-50 mt-2 w-80 bg-white border border-gray-200 rounded-xl shadow-xl max-h-96 overflow-hidden">
                {/* Header with close button */}
                <div className="p-3 border-b border-gray-200 sticky top-0 bg-white flex items-center justify-between">
                  <span className="text-sm font-semibold text-gray-700">Select Country</span>
                  <button
                    type="button"
                    onClick={() => {
                      console.log('[Close Button] Closing dropdown');
                      setShowCountryDropdown(false);
                      setCountrySearch('');
                    }}
                    className="text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                {/* Search input */}
                <div className="p-3 border-b border-gray-200 bg-white">
                  <input
                    type="text"
                    value={countrySearch}
                    onChange={(e) => setCountrySearch(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    placeholder="Search country..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                      focus:outline-none focus:ring-2 focus:ring-orange-500"
                    autoFocus
                  />
                </div>

                {/* Country list */}
                <div className="overflow-y-auto max-h-80">
                  {filteredCountries.length > 0 ? (
                    filteredCountries.map((country) => (
                      <div
                        key={country.code}
                        onClick={() => {
                          console.log('[Country DIV] *** CLICKED ***:', country.name);
                          handleCountrySelect(country);
                        }}
                        className={`w-full flex items-center gap-3 px-4 py-3 hover:bg-orange-50 cursor-pointer
                          transition-colors ${
                            selectedCountry.code === country.code ? 'bg-orange-100' : ''
                          }`}
                      >
                        <span className="text-2xl">{country.flag}</span>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-gray-900 truncate">
                            {country.name}
                          </div>
                          <div className="text-xs text-gray-500">
                            {country.dialCode} • {country.format}
                          </div>
                        </div>
                        {selectedCountry.code === country.code && (
                          <svg className="w-5 h-5 text-orange-600" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="px-4 py-8 text-center text-sm text-gray-500">
                      No countries found
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Phone number input */}
          <input
            type="tel"
            value={phone}
            onChange={handlePhoneChange}
            placeholder={selectedCountry.placeholder}
            className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl text-sm
              focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent
              transition-all duration-150"
          />
        </div>

        {error && (
          <p className="mt-2 text-xs text-red-600 flex items-center gap-1">
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            {error}
          </p>
        )}
      </div>

      <p className="text-xs text-gray-500 mb-3 px-1">
        📞 Select your country and enter your phone number. We'll call you and connect you with our sales team within 30 seconds.
      </p>

      <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 mb-4" key={`example-${selectedCountry.code}-${forceUpdate}`}>
        <p className="text-xs text-blue-800 font-medium mb-1">Example for {selectedCountry.name}:</p>
        <div className="text-xs text-blue-700">
          <div>{selectedCountry.flag} {selectedCountry.name}: <code className="bg-blue-100 px-1 rounded">{selectedCountry.dialCode} {selectedCountry.placeholder}</code></div>
        </div>
        <div className="text-[10px] text-gray-400 mt-1 font-mono">
          Debug: {selectedCountry.code} | Update: {forceUpdate} | Dropdown: {showCountryDropdown ? 'OPEN' : 'CLOSED'}
        </div>
      </div>

      {/* Real-time debug panel */}
      <div className="bg-gray-100 border border-gray-300 rounded-lg px-3 py-2 mb-4">
        <p className="text-[10px] font-bold text-gray-700 mb-1">🔍 Live Debug Info:</p>
        <div className="text-[10px] text-gray-600 font-mono space-y-0.5">
          <div>Country: <strong className="text-orange-600">{selectedCountry.name}</strong></div>
          <div>Dial Code: <strong className="text-orange-600">{selectedCountry.dialCode}</strong></div>
          <div>Force Updates: <strong className="text-orange-600">{forceUpdate}</strong></div>
          <div>Dropdown State: <strong className="text-orange-600">{showCountryDropdown ? '✅ OPEN' : '❌ CLOSED'}</strong></div>
        </div>
      </div>

      <button
        onClick={requestCallback}
        disabled={!phone || phone.replace(/\D/g, '').length < 7}
        className="w-full py-3 rounded-xl bg-orange-500 hover:bg-orange-600
          text-white font-semibold text-sm shadow-md shadow-orange-400/30
          hover:shadow-lg hover:shadow-orange-400/40
          disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none
          transition-all duration-200 active:scale-95"
      >
        Call Me Now
      </button>
    </div>
  );
};

export default CallbackRequest;
