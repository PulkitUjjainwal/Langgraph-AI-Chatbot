import React, { useState, useEffect, useRef } from 'react';

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

// ─── Frequency-domain VAD ────────────────────────────────────────────────────
// Computes the probability that the current frame contains speech by comparing
// energy in the human speech band (300–3400 Hz) vs broadband noise.
// Background noise (fans, AC, room) is wideband → low SNR → prob ≈ 0.
// Human voice concentrates energy in the speech band → high SNR → prob ≈ 1.
function computeSpeechProb(analyser: AnalyserNode, sampleRate: number): number {
  const freqBuf = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(freqBuf);

  const nyquist = sampleRate / 2;
  const freqPerBin = nyquist / freqBuf.length;

  // Speech band: 300–3400 Hz
  const speechLo = Math.max(1, Math.round(300 / freqPerBin));
  const speechHi = Math.min(freqBuf.length - 1, Math.round(3400 / freqPerBin));
  // Upper noise bound: 8000 Hz (above this is ultrasonic noise)
  const noiseHiIdx = Math.min(freqBuf.length - 1, Math.round(8000 / freqPerBin));

  let speechSum = 0, noiseSum = 0;
  let speechCount = 0, noiseCount = 0;

  for (let i = 1; i < noiseHiIdx; i++) {
    if (i >= speechLo && i <= speechHi) {
      speechSum += freqBuf[i];
      speechCount++;
    } else {
      noiseSum += freqBuf[i];
      noiseCount++;
    }
  }

  const speechMean = speechCount > 0 ? speechSum / speechCount : 0;
  const noiseMean  = noiseCount > 0  ? noiseSum  / noiseCount  : 0;

  // If overall energy is too low, it's silence
  if (speechMean < 8) return 0;

  // SNR: how much louder is the speech band vs the noise band?
  const snr = speechMean / (noiseMean + 0.5);
  // Map SNR [1.0, 3.5] → prob [0, 1]
  return Math.min(1, Math.max(0, (snr - 1.0) / 2.5));
}

// ─── VAD constants ───────────────────────────────────────────────────────────
const SPEECH_PROB_THRESHOLD  = 0.40;  // SNR-based probability to count as a speech frame
const SPEECH_ONSET_FRAMES    = 6;     // ~100 ms of sustained speech before we start recording
const SILENCE_FRAMES_END     = 55;    // ~900 ms of silence after speech before we send
const MIN_RECORD_MS          = 600;   // Ignore recordings shorter than this (noise bursts)
const POST_AI_COOLDOWN_MS    = 1400;  // Pause VAD after AI finishes speaking (prevent echo)

const VoiceChatComponent: React.FC<VoiceChatProps> = ({
  sessionId,
  apiUrl,
  onTranscript,
  onResponse,
  onError
}) => {
  const [isListening,   setIsListening]   = useState(false);
  const [isProcessing,  setIsProcessing]  = useState(false);
  const [isThinking,    setIsThinking]    = useState(false);
  const [isPlaying,     setIsPlaying]     = useState(false);
  const [messages,      setMessages]      = useState<VoiceMessage[]>([]);
  const [error,         setError]         = useState<string | null>(null);
  const [audioLevel,    setAudioLevel]    = useState(0);
  const [isSpeaking,    setIsSpeaking]    = useState(false); // visual: user is speaking
  const [waveformTime,  setWaveformTime]  = useState(0);

  // Core refs
  const mediaRecorderRef      = useRef<MediaRecorder | null>(null);
  const audioChunksRef        = useRef<Blob[]>([]);
  const audioContextRef       = useRef<AudioContext | null>(null);
  const analyserRef           = useRef<AnalyserNode | null>(null);
  const animationFrameRef     = useRef<number | null>(null);
  const streamRef             = useRef<MediaStream | null>(null);
  const currentAudioRef       = useRef<HTMLAudioElement | null>(null);
  const recordingStartTimeRef = useRef<number>(0);
  const isListeningRef        = useRef<boolean>(false);
  const isPlayingRef          = useRef<boolean>(false); // sync ref for animation frame
  const messagesEndRef        = useRef<HTMLDivElement | null>(null);
  const audioQueueRef         = useRef<string[]>([]);
  const isPlayingQueueRef     = useRef<boolean>(false);
  const thinkingTimeoutRef    = useRef<number | null>(null);

  // VAD frame counters
  const speechFrameCountRef   = useRef<number>(0); // consecutive speech frames (onset detection)
  const silenceFrameCountRef  = useRef<number>(0); // consecutive silence frames (end detection)
  const aiCooldownUntilRef    = useRef<number>(0); // timestamp: don't pick up audio until this

  // Keep isPlayingRef in sync with state (animation frame can't read stale state)
  useEffect(() => { isPlayingRef.current = isPlaying; }, [isPlaying]);

  // ── Waveform animation timer ────────────────────────────────────────────────
  useEffect(() => {
    let id: number | null = null;
    if (isListening || isPlaying) {
      id = window.setInterval(() => setWaveformTime(Date.now()), 50);
    }
    return () => { if (id !== null) clearInterval(id); };
  }, [isListening, isPlaying]);

  // ── AudioContext init ───────────────────────────────────────────────────────
  useEffect(() => {
    audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
    return () => {
      if (mediaRecorderRef.current?.state === 'recording') mediaRecorderRef.current.stop();
      audioContextRef.current?.close();
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
      streamRef.current?.getTracks().forEach(t => t.stop());
      if (thinkingTimeoutRef.current) clearTimeout(thinkingTimeoutRef.current);
      audioQueueRef.current = [];
      isPlayingQueueRef.current = false;
      if (currentAudioRef.current) { currentAudioRef.current.pause(); currentAudioRef.current = null; }
    };
  }, []);

  // ── VAD + waveform loop ─────────────────────────────────────────────────────
  // Called every animation frame (~16 ms / 60 fps).
  // Phase 1 (not recording): count consecutive speech frames → start recording when onset confirmed.
  // Phase 2 (recording):     count consecutive silence frames → send when silence confirmed.
  const updateWaveform = () => {
    if (!analyserRef.current || !audioContextRef.current) {
      animationFrameRef.current = requestAnimationFrame(updateWaveform);
      return;
    }

    // ── Waveform level (RMS on time-domain for visual only) ──────────────────
    const timeBuf = new Uint8Array(analyserRef.current.fftSize);
    analyserRef.current.getByteTimeDomainData(timeBuf);
    let sum = 0;
    for (let i = 0; i < timeBuf.length; i++) {
      const n = (timeBuf[i] - 128) / 128;
      sum += n * n;
    }
    setAudioLevel(Math.min(1, Math.sqrt(sum / timeBuf.length) * 3));

    // ── Skip VAD during AI cooldown or AI speech (echo prevention) ───────────
    const now = Date.now();
    if (isPlayingRef.current || now < aiCooldownUntilRef.current) {
      speechFrameCountRef.current  = 0;
      silenceFrameCountRef.current = 0;
      animationFrameRef.current = requestAnimationFrame(updateWaveform);
      return;
    }

    const prob              = computeSpeechProb(analyserRef.current, audioContextRef.current.sampleRate);
    const isSpeechFrame     = prob > SPEECH_PROB_THRESHOLD;
    const isCurrentRecording = mediaRecorderRef.current?.state === 'recording';

    if (!isCurrentRecording) {
      // ── Phase 1: waiting for speech onset ──────────────────────────────────
      if (isSpeechFrame) {
        speechFrameCountRef.current++;
        if (speechFrameCountRef.current >= SPEECH_ONSET_FRAMES) {
          // Speech confirmed — start capturing
          speechFrameCountRef.current  = 0;
          silenceFrameCountRef.current = 0;
          setIsSpeaking(true);
          startRecording();
        }
      } else {
        // Decay slowly so brief pauses between words don't reset the counter
        speechFrameCountRef.current = Math.max(0, speechFrameCountRef.current - 1);
      }
    } else {
      // ── Phase 2: recording — watch for end-of-utterance silence ────────────
      if (isSpeechFrame) {
        silenceFrameCountRef.current = 0;
        setIsSpeaking(true);
      } else {
        silenceFrameCountRef.current++;
        const recDuration = now - recordingStartTimeRef.current;
        if (
          silenceFrameCountRef.current >= SILENCE_FRAMES_END &&
          recDuration >= MIN_RECORD_MS
        ) {
          silenceFrameCountRef.current = 0;
          speechFrameCountRef.current  = 0;
          setIsSpeaking(false);
          stopRecordingAndSend();
        }
      }
    }

    animationFrameRef.current = requestAnimationFrame(updateWaveform);
  };

  // ── Start listening session ─────────────────────────────────────────────────
  const startListening = async () => {
    if (isListeningRef.current) return;

    try {
      isListeningRef.current = true;
      setError(null);

      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('Your browser does not support audio recording');
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: { ideal: 48000 },
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      });
      streamRef.current = stream;

      if (audioContextRef.current) {
        const source = audioContextRef.current.createMediaStreamSource(stream);
        analyserRef.current = audioContextRef.current.createAnalyser();
        analyserRef.current.fftSize = 4096;               // high freq resolution
        analyserRef.current.smoothingTimeConstant = 0.25; // fast response
        analyserRef.current.minDecibels = -90;
        analyserRef.current.maxDecibels = -10;
        source.connect(analyserRef.current);
        updateWaveform();
      }

      speechFrameCountRef.current  = 0;
      silenceFrameCountRef.current = 0;
      aiCooldownUntilRef.current   = 0;
      setIsListening(true);

    } catch (err: any) {
      const msg = err.name === 'NotAllowedError'
        ? 'Microphone access denied. Please allow microphone access and try again.'
        : `Failed to access microphone: ${err.message || 'Unknown error'}`;
      setError(msg);
      onError?.(msg);
      setIsListening(false);
      isListeningRef.current = false;
    }
  };

  // ── Stop listening session ──────────────────────────────────────────────────
  const stopListening = () => {
    isListeningRef.current = false;
    setIsListening(false);
    setIsSpeaking(false);
    setIsProcessing(false);
    setIsThinking(false);

    if (mediaRecorderRef.current?.state === 'recording') mediaRecorderRef.current.stop();
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;

    if (thinkingTimeoutRef.current) { clearTimeout(thinkingTimeoutRef.current); thinkingTimeoutRef.current = null; }
    if (animationFrameRef.current) { cancelAnimationFrame(animationFrameRef.current); animationFrameRef.current = null; }

    audioQueueRef.current = [];
    isPlayingQueueRef.current = false;
    if (currentAudioRef.current) { currentAudioRef.current.pause(); currentAudioRef.current = null; }
    setIsPlaying(false);
    isPlayingRef.current = false;
  };

  // ── Start a recording segment (called by VAD only) ──────────────────────────
  const startRecording = () => {
    if (!streamRef.current || !isListeningRef.current) return;
    if (mediaRecorderRef.current?.state === 'recording') return;

    try {
      let mimeType = 'audio/webm;codecs=opus';
      if (!MediaRecorder.isTypeSupported(mimeType)) mimeType = 'audio/webm';
      if (!MediaRecorder.isTypeSupported(mimeType)) mimeType = 'audio/ogg;codecs=opus';

      const mediaRecorder = new MediaRecorder(streamRef.current, { mimeType });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      recordingStartTimeRef.current = Date.now();

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        const totalSize = audioChunksRef.current.reduce((a, c) => a + c.size, 0);
        if (totalSize < 1000) {
          // Too small — discard (likely noise burst that got through)
          audioChunksRef.current = [];
          return;
        }
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        await processVoiceMessage(audioBlob);
        // VAD loop will automatically start the next recording when speech is detected again
      };

      mediaRecorder.start(100);

    } catch (err) {
      console.error('[VoiceChat] Error starting recording:', err);
    }
  };

  // ── Stop and send (called by VAD only) ──────────────────────────────────────
  const stopRecordingAndSend = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  };

  // ── Render message text with clickable URLs ──────────────────────────────────
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

  // ── Process voice message via SSE ────────────────────────────────────────────
  const processVoiceMessage = async (audioBlob: Blob) => {
    // Interrupt bot if speaking
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
      audioQueueRef.current = [];
      isPlayingQueueRef.current = false;
      setIsPlaying(false);
      isPlayingRef.current = false;
    }

    setIsSpeaking(false);
    setIsProcessing(true);
    setIsThinking(true);
    setError(null);

    // 150 s safety net — backend heartbeats keep the connection alive so this
    // should never fire under normal conditions.
    thinkingTimeoutRef.current = window.setTimeout(() => {
      setIsThinking(false);
      setIsProcessing(false);
      // Don't show an error — just silently resume listening so the user can try again
    }, 150000);

    try {
      const arrayBuffer = await audioBlob.arrayBuffer();
      const base64Audio = btoa(
        new Uint8Array(arrayBuffer).reduce((d, b) => d + String.fromCharCode(b), '')
      );

      let audioFormat = 'webm';
      if (audioBlob.type.includes('ogg')) audioFormat = 'ogg';
      else if (audioBlob.type.includes('wav')) audioFormat = 'wav';
      else if (audioBlob.type.includes('mp3')) audioFormat = 'mp3';

      let baseUrl = apiUrl;
      if (!baseUrl.endsWith('/api')) baseUrl = `${baseUrl}/api`;

      const controller = new AbortController();
      const timeoutId  = setTimeout(() => controller.abort(), 150000);

      const response = await fetch(`${baseUrl}/voice/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, audio_data: base64Audio, audio_format: audioFormat }),
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      if (!response.ok || !response.body) {
        const errData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errData.detail || `Server error (${response.status})`);
      }

      const reader  = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const streamingMsgId = `assistant-streaming-${Date.now()}`;
      let streamingText = '';
      let receivedFirstChunk = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          try {
            const event = JSON.parse(jsonStr);

            if (event.type === 'heartbeat') {
              // Backend keep-alive ping — silently ignore, connection stays open
              continue;

            } else if (event.type === 'transcript') {
              setMessages(prev => [...prev, {
                id: `user-${Date.now()}`,
                type: 'user',
                transcript: event.text,
                timestamp: new Date()
              }]);
              onTranscript?.(event.text);

            } else if (event.type === 'text_chunk') {
              if (!receivedFirstChunk) {
                setIsThinking(false);
                receivedFirstChunk = true;
                if (thinkingTimeoutRef.current) { clearTimeout(thinkingTimeoutRef.current); thinkingTimeoutRef.current = null; }
              }
              streamingText += event.text;
              const currentText = streamingText;
              setMessages(prev => {
                const exists = prev.some(m => m.id === streamingMsgId);
                if (exists) return prev.map(m => m.id === streamingMsgId ? { ...m, transcript: currentText } : m);
                return [...prev, { id: streamingMsgId, type: 'assistant', transcript: currentText, timestamp: new Date() }];
              });

            } else if (event.type === 'audio') {
              playAudioResponse(event.data).catch(console.error);

            } else if (event.type === 'done') {
              onResponse?.(streamingText);

            } else if (event.type === 'error') {
              // Only surface truly unexpected errors; routine issues (silence,
              // noise, echo) are already discarded server-side without an error event
              console.warn('[VoiceChat] Server error event:', event.message);
              setIsThinking(false);
            }
          } catch {
            // ignore malformed lines
          }
        }
      }

      // Stream ended with no text — silence/noise discarded server-side, resume quietly
      if (!receivedFirstChunk) setIsThinking(false);

    } catch (err: any) {
      // AbortController fired (request took >150s) or network dropped — silent recovery
      console.warn('[VoiceChat] Request error:', err.message);
      setIsThinking(false);
      // Don't call setError — just let the VAD resume and the user can speak again
    } finally {
      setIsProcessing(false);
      setIsThinking(false);
      if (thinkingTimeoutRef.current) { clearTimeout(thinkingTimeoutRef.current); thinkingTimeoutRef.current = null; }
    }
  };

  // ── Audio queue ──────────────────────────────────────────────────────────────
  const processAudioQueue = async () => {
    if (isPlayingQueueRef.current) return;
    isPlayingQueueRef.current = true;

    while (audioQueueRef.current.length > 0) {
      const b64 = audioQueueRef.current.shift();
      if (!b64) continue;
      try { await playAudioChunk(b64); } catch (err) { console.error('[VoiceChat] Audio chunk error:', err); }
    }

    isPlayingQueueRef.current = false;
    setIsPlaying(false);
    isPlayingRef.current = false;
    // Apply cooldown so VAD doesn't pick up the echo of the AI's voice
    aiCooldownUntilRef.current = Date.now() + POST_AI_COOLDOWN_MS;
  };

  const playAudioChunk = (base64Audio: string): Promise<void> =>
    new Promise((resolve, reject) => {
      try {
        setIsPlaying(true);
        isPlayingRef.current = true;

        const bytes = Uint8Array.from(atob(base64Audio), c => c.charCodeAt(0));
        const url   = URL.createObjectURL(new Blob([bytes], { type: 'audio/mpeg' }));
        const audio = new Audio(url);
        currentAudioRef.current = audio;

        audio.onended = () => { currentAudioRef.current = null; URL.revokeObjectURL(url); resolve(); };
        audio.onerror = (e)  => { currentAudioRef.current = null; URL.revokeObjectURL(url); reject(e); };
        audio.play();
      } catch (err) {
        currentAudioRef.current = null;
        reject(err);
      }
    });

  const playAudioResponse = async (base64Audio: string) => {
    audioQueueRef.current.push(base64Audio);
    processAudioQueue();
  };

  const cancelResponse = () => {
    if (currentAudioRef.current) { currentAudioRef.current.pause(); currentAudioRef.current = null; }
    audioQueueRef.current = [];
    isPlayingQueueRef.current = false;
    setIsPlaying(false);
    isPlayingRef.current = false;
    aiCooldownUntilRef.current = Date.now() + POST_AI_COOLDOWN_MS;
  };

  const toggleListening = () => { isListening ? stopListening() : startListening(); };

  useEffect(() => {
    if (messagesEndRef.current) messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isProcessing, isSpeaking]);

  useEffect(() => {
    if (error) {
      const t = setTimeout(() => setError(null), 5000);
      return () => clearTimeout(t);
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
                {isPlaying ? '🔊 Speaking...' : isThinking ? '💭 Thinking...' : isProcessing ? '⚙️ Processing...' : isSpeaking ? '🎤 Listening...' : isListening ? '✅ Ready — speak to start' : '💬 Start voice chat'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Messages */}
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
            {messages.map((message) => (
              <div key={message.id} className={`flex min-w-0 ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] rounded-2xl px-4 py-3 min-w-0 ${message.type === 'user' ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white' : 'bg-white/10 text-white backdrop-blur-sm'}`}>
                  <p className="text-sm whitespace-pre-wrap min-w-0">{renderMessageText(message.transcript)}</p>
                  <p className="text-xs mt-1 opacity-60">{message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
                </div>
              </div>
            ))}

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

            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="flex-shrink-0 mx-6 mb-4 px-4 py-3 bg-red-500/20 border border-red-500/50 rounded-lg">
          <p className="text-red-200 text-sm">{error}</p>
        </div>
      )}

      {/* Waveform */}
      <div className="waveform-container flex-shrink-0 px-6 py-4">
        <div className="h-20 flex items-center justify-center space-x-1">
          {Array.from({ length: 40 }).map((_, i) => {
            let baseHeight = 20, waveOffset = 0;
            if (isPlaying) {
              baseHeight  = 40;
              waveOffset  = Math.sin((i / 3) + (waveformTime / 150)) * 30;
            } else if (isListening) {
              baseHeight  = 20 + (audioLevel * 200);
              waveOffset  = Math.sin((i / 5) + (waveformTime / 200)) * 15;
            }
            const height = Math.max(15, Math.min(95, baseHeight + waveOffset));
            const gradientClass = isPlaying
              ? 'bg-gradient-to-t from-blue-500 to-cyan-400'
              : isSpeaking
              ? 'bg-gradient-to-t from-green-500 to-emerald-400'
              : 'bg-gradient-to-t from-purple-500 to-pink-500';
            return <div key={i} className={`w-1 ${gradientClass} rounded-full transition-all duration-75`} style={{ height: `${height}%` }} />;
          })}
        </div>
      </div>

      {/* Controls */}
      <div className="voice-controls flex-shrink-0 px-6 pb-6">
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
          {isPlaying
            ? 'AI is speaking — use cancel button to interrupt'
            : isThinking
            ? 'Processing your message...'
            : isProcessing
            ? 'Sending your message...'
            : isListening
            ? 'Speak naturally — I\'ll auto-send when you pause'
            : 'Click button to start voice conversation'}
        </p>
      </div>
    </div>
  );
};

export const VoiceChat = React.memo(VoiceChatComponent, (prev, next) =>
  prev.sessionId === next.sessionId && prev.apiUrl === next.apiUrl
);

export default VoiceChat;
