import React, { useState, useEffect, useRef } from 'react';

/**
 * VoiceChat Component - Real-time Conversation Mode
 *
 * Features:
 * - Continuous listening with Voice Activity Detection
 * - Auto-send when user stops speaking
 * - Animated waveform visualization
 * - OpenAI Whisper STT + TTS
 * - Interrupt handling (stop bot if user starts speaking)
 */

interface VoiceChatProps {
  sessionId: string;
  apiUrl: string;
  onTranscript?: (transcript: string) => void;
  onResponse?: (response: string) => void;
  onError?: (error: string) => void;
}

interface VoiceMessage {
  id: string;
  type: 'user' | 'assistant';
  transcript: string;
  timestamp: Date;
}

const VoiceChatComponent: React.FC<VoiceChatProps> = ({
  sessionId,
  apiUrl,
  onTranscript,
  onResponse,
  onError
}) => {
  // State
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isThinking, setIsThinking] = useState(false); // true from start until first text chunk
  const [isPlaying, setIsPlaying] = useState(false);
  const [messages, setMessages] = useState<VoiceMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [waveformTime, setWaveformTime] = useState(0);

  // Refs
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const silenceTimerRef = useRef<number | null>(null);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const recordingStartTimeRef = useRef<number>(0);
  const isListeningRef = useRef<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const audioQueueRef = useRef<string[]>([]);
  const isPlayingQueueRef = useRef<boolean>(false);
  const thinkingTimeoutRef = useRef<number | null>(null);

  // VAD Configuration
  const SILENCE_THRESHOLD = 0.05; // Audio level threshold for silence (increased for RMS calculation)
  const SILENCE_DURATION = 1500; // ms of silence before auto-send
  const MIN_RECORDING_DURATION = 500; // Minimum recording length in ms

  // Waveform animation timer - update every 50ms when listening or playing for smooth animation
  useEffect(() => {
    let intervalId: number | null = null;

    if (isListening || isPlaying) {
      intervalId = window.setInterval(() => {
        setWaveformTime(Date.now());
      }, 50); // Update 20 times per second for smooth animation
    }

    return () => {
      if (intervalId !== null) {
        clearInterval(intervalId);
      }
    };
  }, [isListening, isPlaying]);

  // Initialize audio context
  useEffect(() => {
    audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();

    // Cleanup on unmount only
    return () => {
      console.log('[VoiceChat] Component unmounting - cleaning up');

      // Stop recording
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.stop();
      }

      // Stop audio context
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }

      // Cancel animation
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }

      // Stop stream tracks
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }

      // Clear timers
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
      }
      if (thinkingTimeoutRef.current) {
        clearTimeout(thinkingTimeoutRef.current);
      }

      // Clear audio queue and stop playback
      audioQueueRef.current = [];
      isPlayingQueueRef.current = false;
      if (currentAudioRef.current) {
        currentAudioRef.current.pause();
        currentAudioRef.current = null;
      }
    };
  }, []);

  // Waveform visualization and VAD
  const updateWaveform = () => {
    if (!analyserRef.current) {
      setAudioLevel(0);
      animationFrameRef.current = requestAnimationFrame(updateWaveform);
      return;
    }

    // Use time domain data for better volume detection
    const bufferLength = analyserRef.current.fftSize;
    const dataArray = new Uint8Array(bufferLength);
    analyserRef.current.getByteTimeDomainData(dataArray);

    // Calculate RMS (Root Mean Square) for accurate volume level
    let sum = 0;
    for (let i = 0; i < bufferLength; i++) {
      const normalized = (dataArray[i] - 128) / 128; // Normalize to -1 to 1
      sum += normalized * normalized;
    }
    const rms = Math.sqrt(sum / bufferLength);
    const normalizedLevel = Math.min(1, rms * 3); // Amplify and cap at 1

    setAudioLevel(normalizedLevel);

    // Voice Activity Detection (using refs to avoid stale closures)
    const isCurrentlyRecording = mediaRecorderRef.current?.state === 'recording';

    if (isCurrentlyRecording && normalizedLevel > SILENCE_THRESHOLD) {
      // User is speaking
      setIsSpeaking(true);
      // Clear silence timer
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
    } else if (isCurrentlyRecording && normalizedLevel <= SILENCE_THRESHOLD) {
      // Potential silence detected
      // DON'T immediately hide "Listening..." - keep it visible until we actually send
      // This provides better UX - user sees "Listening..." throughout their speech

      // Start silence timer if not already started
      if (!silenceTimerRef.current) {
        silenceTimerRef.current = window.setTimeout(() => {
          const recordingDuration = Date.now() - recordingStartTimeRef.current;
          if (recordingDuration >= MIN_RECORDING_DURATION) {
            console.log('[VAD] Silence detected - auto-sending message');
            stopRecordingAndSend();
          }
          silenceTimerRef.current = null;
        }, SILENCE_DURATION);
      }
    }

    animationFrameRef.current = requestAnimationFrame(updateWaveform);
  };

  // Start continuous listening
  const startListening = async () => {
    // Prevent multiple simultaneous starts
    if (isListeningRef.current) {
      console.log('[VoiceChat] Already listening, ignoring start request');
      return;
    }

    try {
      console.log('[VoiceChat] startListening called');
      isListeningRef.current = true;
      setError(null);

      // Check if getUserMedia is supported
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Your browser does not support audio recording');
      }

      console.log('[VoiceChat] Requesting microphone access...');

      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      console.log('[VoiceChat] Microphone access granted');

      // Set up audio analysis for waveform and VAD
      if (audioContextRef.current) {
        const source = audioContextRef.current.createMediaStreamSource(stream);
        analyserRef.current = audioContextRef.current.createAnalyser();
        analyserRef.current.fftSize = 2048; // Larger FFT for better frequency resolution
        analyserRef.current.smoothingTimeConstant = 0.3; // Less smoothing for more responsive waveform
        analyserRef.current.minDecibels = -90;
        analyserRef.current.maxDecibels = -10;
        source.connect(analyserRef.current);
        console.log('[VoiceChat] Audio analyser connected');
        updateWaveform();
      }

      setIsListening(true);
      console.log('[VoiceChat] isListening set to true');

      // Automatically start recording
      console.log('[VoiceChat] Starting recording in 500ms...');
      setTimeout(() => {
        if (isListeningRef.current) {
          console.log('[VoiceChat] Calling startRecording()');
          startRecording();
        }
      }, 500);

      console.log('[VoiceChat] Continuous listening started successfully');
    } catch (err: any) {
      const errorMessage = err.name === 'NotAllowedError'
        ? 'Microphone access denied. Please allow microphone access and try again.'
        : `Failed to access microphone: ${err.message || 'Unknown error'}`;

      console.error('[VoiceChat] Error starting listening:', err);
      setError(errorMessage);
      onError?.(errorMessage);
      setIsListening(false);
      isListeningRef.current = false;
    }
  };

  // Stop continuous listening
  const stopListening = () => {
    console.log('[VoiceChat] stopListening called');
    isListeningRef.current = false;
    setIsListening(false);
    setIsSpeaking(false);
    setIsProcessing(false);
    setIsThinking(false);

    // Stop recording if active
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }

    // Stop all tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }

    // Clear all timers
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (thinkingTimeoutRef.current) {
      clearTimeout(thinkingTimeoutRef.current);
      thinkingTimeoutRef.current = null;
    }

    // Cancel animation frame
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    // Clear audio queue
    audioQueueRef.current = [];
    isPlayingQueueRef.current = false;
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    setIsPlaying(false);

    console.log('[VoiceChat] Listening stopped - all states cleared');
  };

  // Start recording segment
  const startRecording = () => {
    if (!streamRef.current || !isListeningRef.current) {
      console.log('[VoiceChat] Cannot start recording - no stream or not listening');
      return;
    }

    try {
      // Set up media recorder with better format support
      let mimeType = 'audio/webm;codecs=opus';
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = 'audio/webm';
        if (!MediaRecorder.isTypeSupported(mimeType)) {
          mimeType = 'audio/ogg;codecs=opus';
        }
      }

      console.log('[VoiceChat] Starting recording with MIME type:', mimeType);

      const mediaRecorder = new MediaRecorder(streamRef.current, { mimeType });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      recordingStartTimeRef.current = Date.now();

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const totalSize = audioChunksRef.current.reduce((acc, chunk) => acc + chunk.size, 0);
        console.log('[VoiceChat] Recording stopped. Total size:', totalSize, 'bytes');

        if (totalSize < 1000) {
          console.log('[VoiceChat] Recording too short, restarting...');
          audioChunksRef.current = [];
          if (isListeningRef.current) {
            setTimeout(() => startRecording(), 100);
          }
          return;
        }

        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        await processVoiceMessage(audioBlob);

        // Restart recording after processing (if still listening)
        if (isListeningRef.current) {
          setTimeout(() => startRecording(), 500);
        }
      };

      // Start recording - collect data every 100ms
      mediaRecorder.start(100);
      setIsSpeaking(false);

    } catch (err) {
      console.error('[VoiceChat] Error starting recording:', err);
    }
  };

  // Stop recording and send
  const stopRecordingAndSend = () => {
    console.log('[VoiceChat] Stopping recording and sending...');
    // Don't set isSpeaking=false here - let processVoiceMessage do it
    // This keeps the "Listening..." indicator visible until processing starts
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  };

  // Render message text with clickable URLs
  const renderMessageText = (text: string) => {
    const parts = text.split(/(https?:\/\/[^\s<>"]+)/g);
    return (
      <span style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>
        {parts.map((part, i) =>
          /^https?:\/\//.test(part) ? (
            <a
              key={i}
              href={part}
              target="_blank"
              rel="noopener noreferrer"
              className="text-purple-300 underline hover:text-purple-200 break-all"
              onClick={e => e.stopPropagation()}
            >
              {part}
            </a>
          ) : (
            <span key={i}>{part}</span>
          )
        )}
      </span>
    );
  };

  // Process voice message via SSE streaming endpoint
  const processVoiceMessage = async (audioBlob: Blob) => {
    console.log('[VoiceChat] processVoiceMessage called');

    // Interrupt bot if speaking
    if (currentAudioRef.current && isPlaying) {
      console.log('[VoiceChat] User interrupted - stopping playback');
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
      setIsPlaying(false);
      // Clear audio queue
      audioQueueRef.current = [];
      isPlayingQueueRef.current = false;
    }

    // Set processing states IMMEDIATELY and clear speaking state
    setIsSpeaking(false);  // User finished speaking, now processing
    setIsProcessing(true);
    setIsThinking(true);
    setError(null);
    console.log('[VoiceChat] Set isSpeaking=false, isProcessing=true, isThinking=true');

    // Safety timeout: if we're still "Thinking..." after 30 seconds, force exit
    thinkingTimeoutRef.current = window.setTimeout(() => {
      console.warn('[VoiceChat] Thinking timeout - forcing state reset');
      setIsThinking(false);
      setIsProcessing(false);
      setError('Response timed out. Please try again.');
    }, 30000);

    try {
      // Convert blob to base64
      const arrayBuffer = await audioBlob.arrayBuffer();
      const base64Audio = btoa(
        new Uint8Array(arrayBuffer).reduce((data, byte) => data + String.fromCharCode(byte), '')
      );

      // Detect audio format from MIME type
      let audioFormat = 'webm';
      if (audioBlob.type.includes('ogg')) {
        audioFormat = 'ogg';
      } else if (audioBlob.type.includes('wav')) {
        audioFormat = 'wav';
      } else if (audioBlob.type.includes('mp3')) {
        audioFormat = 'mp3';
      }

      // Ensure correct API URL
      let baseUrl = apiUrl;
      if (!baseUrl.endsWith('/api')) {
        baseUrl = `${baseUrl}/api`;
      }

      console.log('[VoiceChat] Sending to:', `${baseUrl}/voice/stream`);

      const response = await fetch(`${baseUrl}/voice/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          audio_data: base64Audio,
          audio_format: audioFormat
        })
      });

      if (!response.ok || !response.body) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      console.log('[VoiceChat] Starting to read SSE stream...');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const streamingMsgId = `assistant-streaming-${Date.now()}`;
      let streamingText = '';
      let receivedFirstChunk = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log('[VoiceChat] SSE stream ended');
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE lines
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          try {
            const event = JSON.parse(jsonStr);

            if (event.type === 'transcript') {
              // Show user's spoken text immediately; AI is still thinking
              console.log('[VoiceChat] Received transcript:', event.text);
              const userMsg: VoiceMessage = {
                id: `user-${Date.now()}`,
                type: 'user',
                transcript: event.text,
                timestamp: new Date()
              };
              setMessages(prev => [...prev, userMsg]);
              onTranscript?.(event.text);
              // keep isProcessing=true and isThinking=true — AI hasn't responded yet

            } else if (event.type === 'text_chunk') {
              // First chunk means AI started responding — hide "Thinking..." bubble
              if (!receivedFirstChunk) {
                console.log('[VoiceChat] First text chunk received - exiting thinking state');
                setIsThinking(false);
                receivedFirstChunk = true;

                // Clear thinking timeout
                if (thinkingTimeoutRef.current) {
                  clearTimeout(thinkingTimeoutRef.current);
                  thinkingTimeoutRef.current = null;
                }
              }

              streamingText += event.text;
              const currentText = streamingText;
              setMessages(prev => {
                const exists = prev.some(m => m.id === streamingMsgId);
                if (exists) {
                  return prev.map(m =>
                    m.id === streamingMsgId ? { ...m, transcript: currentText } : m
                  );
                }
                return [...prev, {
                  id: streamingMsgId,
                  type: 'assistant',
                  transcript: currentText,
                  timestamp: new Date()
                }];
              });

            } else if (event.type === 'audio') {
              // Play audio without blocking - let text and audio happen simultaneously
              console.log('[VoiceChat] Received audio chunk');
              playAudioResponse(event.data).catch(err => {
                console.error('[VoiceChat] Audio playback error:', err);
              });

            } else if (event.type === 'done') {
              console.log('[VoiceChat] Received done event');
              onResponse?.(streamingText);

            } else if (event.type === 'error') {
              console.error('[VoiceChat] Received error event:', event.message);
              setError(event.message || 'An error occurred');
              // Exit thinking state on error
              setIsThinking(false);
            }

          } catch (parseError) {
            // ignore malformed SSE lines
            console.warn('[VoiceChat] Failed to parse SSE line:', line);
          }
        }
      }

      // If we never got a text chunk, make sure thinking state is cleared
      if (!receivedFirstChunk) {
        console.log('[VoiceChat] WARNING: Stream ended without receiving text chunks');
        setIsThinking(false);
      }

    } catch (err: any) {
      const errorMessage = err.message || 'Failed to process voice message';
      console.error('[VoiceChat] Error processing message:', err);
      setError(errorMessage);
      onError?.(errorMessage);

      // Make sure to exit thinking state on error
      setIsThinking(false);
    } finally {
      console.log('[VoiceChat] Processing complete, clearing states');
      setIsProcessing(false);
      setIsThinking(false);

      // Clear thinking timeout
      if (thinkingTimeoutRef.current) {
        clearTimeout(thinkingTimeoutRef.current);
        thinkingTimeoutRef.current = null;
      }
    }
  };

  // Process audio queue - plays audio chunks in sequence
  const processAudioQueue = async () => {
    if (isPlayingQueueRef.current) return; // Already processing

    isPlayingQueueRef.current = true;

    while (audioQueueRef.current.length > 0) {
      const base64Audio = audioQueueRef.current.shift();
      if (!base64Audio) continue;

      try {
        await playAudioChunk(base64Audio);
      } catch (err) {
        console.error('[VoiceChat] Error playing audio chunk:', err);
      }
    }

    isPlayingQueueRef.current = false;
    setIsPlaying(false);
  };

  // Play a single audio chunk
  const playAudioChunk = async (base64Audio: string): Promise<void> => {
    return new Promise((resolve, reject) => {
      try {
        setIsPlaying(true);

        // Decode base64 to binary
        const binaryString = atob(base64Audio);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }

        // Create audio blob
        const audioBlob = new Blob([bytes], { type: 'audio/mpeg' });
        const audioUrl = URL.createObjectURL(audioBlob);

        // Play audio
        const audio = new Audio(audioUrl);
        currentAudioRef.current = audio;

        audio.onended = () => {
          currentAudioRef.current = null;
          URL.revokeObjectURL(audioUrl);
          resolve();
        };

        audio.onerror = (err) => {
          currentAudioRef.current = null;
          URL.revokeObjectURL(audioUrl);
          reject(err);
        };

        audio.play();

        console.log('[VoiceChat] Playing audio chunk');
      } catch (err) {
        currentAudioRef.current = null;
        reject(err);
      }
    });
  };

  // Add audio to queue and start processing
  const playAudioResponse = async (base64Audio: string): Promise<void> => {
    audioQueueRef.current.push(base64Audio);
    processAudioQueue();
  };

  // Cancel AI response (stop audio playback)
  const cancelResponse = () => {
    console.log('[VoiceChat] Canceling AI response');

    // Stop current audio
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }

    // Clear audio queue
    audioQueueRef.current = [];
    isPlayingQueueRef.current = false;
    setIsPlaying(false);

    console.log('[VoiceChat] AI response canceled');
  };

  // Toggle listening
  const toggleListening = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isProcessing, isSpeaking]);

  // Clear error after 5 seconds
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  return (
    <div className="voice-chat-container flex flex-col flex-1 overflow-hidden bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* Header */}
      <div className="voice-chat-header flex-shrink-0 px-4 py-3 border-b border-white/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="relative">
              <div className="w-10 h-10 rounded-full bg-gradient-to-r from-purple-500 to-pink-500 flex items-center justify-center">
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
              </div>
              {(isListening || isPlaying) && (
                <div className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full animate-pulse" />
              )}
            </div>
            <div>
              <h3 className="text-white font-semibold text-lg">Voice Chat</h3>
              <p className="text-white/60 text-xs">
                {isPlaying ? '🔊 Speaking...' : isThinking ? '💭 Thinking...' : isProcessing ? '⚙️ Processing...' : isSpeaking ? '🎤 Listening...' : isListening ? '✅ Ready' : '💬 Start'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Messages Container */}
      <div className="voice-messages flex-1 overflow-y-auto overflow-x-hidden px-6 py-4 space-y-4" style={{ scrollBehavior: 'smooth', minHeight: 0 }}>
        {messages.length === 0 && !isSpeaking && !isProcessing ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-white/40">
            <svg className="w-16 h-16 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
            <p className="text-sm">Press the button below to start talking</p>
            <p className="text-xs mt-2">I'll respond automatically when you finish speaking</p>
          </div>
        ) : (
          <>
            {/* Render all messages */}
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex min-w-0 ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 min-w-0 ${
                    message.type === 'user'
                      ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white'
                      : 'bg-white/10 text-white backdrop-blur-sm'
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap min-w-0">
                    {renderMessageText(message.transcript)}
                  </p>
                  <p className="text-xs mt-1 opacity-60">
                    {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>
            ))}

            {/* Show "Listening..." indicator when user is speaking */}
            {isSpeaking && !isProcessing && (
              <div className="flex justify-end">
                <div className="max-w-[80%] rounded-2xl px-4 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white">
                  <div className="flex items-center space-x-2">
                    <div className="flex space-x-1">
                      <div className="w-2 h-2 bg-white rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-2 h-2 bg-white rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-2 h-2 bg-white rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                    <p className="text-sm">Listening...</p>
                  </div>
                </div>
              </div>
            )}

            {/* Show "Thinking..." indicator while waiting for AI response */}
            {isThinking && (
              <div className="flex justify-start">
                <div className="max-w-[80%] rounded-2xl px-4 py-3 bg-white/10 text-white backdrop-blur-sm">
                  <div className="flex items-center space-x-2">
                    <div className="flex space-x-1">
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                    <p className="text-sm">Thinking...</p>
                  </div>
                </div>
              </div>
            )}

            {/* Auto-scroll anchor */}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Error Message */}
      {error && (
        <div className="flex-shrink-0 mx-6 mb-4 px-4 py-3 bg-red-500/20 border border-red-500/50 rounded-lg">
          <p className="text-red-200 text-sm">{error}</p>
        </div>
      )}

      {/* Waveform Visualization */}
      <div className="waveform-container flex-shrink-0 px-6 py-4">
        <div className="h-20 flex items-center justify-center space-x-1">
          {Array.from({ length: 40 }).map((_, i) => {
            // Calculate height based on audio level and animated sine wave
            let baseHeight = 20;
            let waveOffset = 0;

            if (isPlaying) {
              // AI speaking - smooth wave pattern
              baseHeight = 40;
              waveOffset = Math.sin((i / 3) + (waveformTime / 150)) * 30;
            } else if (isListening) {
              // User listening - responsive to microphone
              baseHeight = 20 + (audioLevel * 200);
              waveOffset = Math.sin((i / 5) + (waveformTime / 200)) * 15;
            }

            const height = Math.max(15, Math.min(95, baseHeight + waveOffset));

            // Different gradient for AI speaking vs user speaking
            const gradientClass = isPlaying
              ? 'bg-gradient-to-t from-blue-500 to-cyan-400'
              : 'bg-gradient-to-t from-purple-500 to-pink-500';

            return (
              <div
                key={i}
                className={`w-1 ${gradientClass} rounded-full transition-all duration-75`}
                style={{ height: `${height}%` }}
              />
            );
          })}
        </div>
      </div>

      {/* Toggle Button */}
      <div className="voice-controls flex-shrink-0 px-6 pb-6">
        {/* Cancel Button - Shows when AI is speaking */}
        {isPlaying && !isProcessing && !isThinking && (
          <button
            onClick={cancelResponse}
            className="w-full mb-3 py-3 rounded-2xl font-semibold text-white bg-gradient-to-r from-orange-500 to-red-500 hover:shadow-lg hover:shadow-orange-500/50 active:scale-95 transition-all duration-200"
          >
            <div className="flex items-center justify-center space-x-2">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              <span>Cancel Response</span>
            </div>
          </button>
        )}

        {/* Main Control Button */}
        <button
          onClick={toggleListening}
          disabled={isProcessing || isThinking || isPlaying}
          className={`w-full py-4 rounded-2xl font-semibold text-white transition-all duration-200 ${
            isListening && !isProcessing && !isThinking && !isPlaying
              ? 'bg-gradient-to-r from-red-500 to-pink-500 shadow-lg shadow-red-500/50'
              : (isProcessing || isThinking || isPlaying)
              ? 'bg-gray-600 cursor-not-allowed opacity-50'
              : 'bg-gradient-to-r from-purple-500 to-pink-500 hover:shadow-lg hover:shadow-purple-500/50 active:scale-95'
          }`}
        >
          {isProcessing && !isThinking ? (
            <div className="flex items-center justify-center space-x-2">
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              <span>Processing...</span>
            </div>
          ) : isThinking ? (
            <div className="flex items-center justify-center space-x-2">
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              <span>AI is thinking...</span>
            </div>
          ) : isPlaying ? (
            <div className="flex items-center justify-center space-x-2">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/>
              </svg>
              <span>AI is Speaking...</span>
            </div>
          ) : isListening ? (
            <div className="flex items-center justify-center space-x-2">
              <div className="w-3 h-3 bg-white rounded-full animate-pulse" />
              <span>Stop Conversation</span>
            </div>
          ) : (
            <span>Start Conversation</span>
          )}
        </button>
        <p className="text-center text-white/40 text-xs mt-3">
          {isPlaying ? 'AI is speaking - use cancel button to interrupt' : isThinking ? 'Processing your message...' : isProcessing ? 'Sending your message...' : isListening ? 'Speak naturally - I\'ll auto-send when you pause' : 'Click button to start voice conversation'}
        </p>
      </div>
    </div>
  );
};

// Memoize to prevent unnecessary re-renders
export const VoiceChat = React.memo(VoiceChatComponent, (prevProps, nextProps) => {
  // Only re-render if sessionId changes
  return prevProps.sessionId === nextProps.sessionId && prevProps.apiUrl === nextProps.apiUrl;
});

export default VoiceChat;
