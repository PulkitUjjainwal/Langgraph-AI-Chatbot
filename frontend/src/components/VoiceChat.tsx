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
  exploreUrl?: string;
}

// ─── Frequency-domain VAD ────────────────────────────────────────────────────
function computeSpeechProb(analyser: AnalyserNode, sampleRate: number): number {
  const freqBuf = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(freqBuf);

  const nyquist     = sampleRate / 2;
  const freqPerBin  = nyquist / freqBuf.length;
  const speechLo    = Math.max(1, Math.round(300 / freqPerBin));
  const speechHi    = Math.min(freqBuf.length - 1, Math.round(3400 / freqPerBin));
  const noiseHiIdx  = Math.min(freqBuf.length - 1, Math.round(8000 / freqPerBin));

  let speechSum = 0, noiseSum = 0, speechCount = 0, noiseCount = 0;
  for (let i = 1; i < noiseHiIdx; i++) {
    if (i >= speechLo && i <= speechHi) { speechSum += freqBuf[i]; speechCount++; }
    else { noiseSum += freqBuf[i]; noiseCount++; }
  }
  const speechMean = speechCount > 0 ? speechSum / speechCount : 0;
  const noiseMean  = noiseCount  > 0 ? noiseSum  / noiseCount  : 0;
  if (speechMean < 8) return 0;
  return Math.min(1, Math.max(0, (speechMean / (noiseMean + 0.5) - 1.0) / 2.5));
}

// ─── VAD constants ────────────────────────────────────────────────────────────
const SPEECH_PROB_THRESHOLD = 0.40;
const SPEECH_ONSET_FRAMES   = 6;
const SILENCE_FRAMES_END    = 55;
const MIN_RECORD_MS         = 600;
const POST_AI_COOLDOWN_MS   = 1400;

// ─── Timer helper ─────────────────────────────────────────────────────────────
function fmtTime(s: number) {
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

const VoiceChatComponent: React.FC<VoiceChatProps> = ({
  sessionId,
  apiUrl,
  onTranscript,
  onResponse,
  onError
}) => {
  const [isListening,  setIsListening]  = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isThinking,   setIsThinking]   = useState(false);
  const [isPlaying,    setIsPlaying]    = useState(false);
  const [isSpeaking,   setIsSpeaking]   = useState(false);
  const [messages,     setMessages]     = useState<VoiceMessage[]>([]);
  const [error,        setError]        = useState<string | null>(null);
  const [audioLevel,   setAudioLevel]   = useState(0);
  const [waveformTime, setWaveformTime] = useState(0);
  const [elapsed,      setElapsed]      = useState(0); // session timer (seconds)

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
  const isPlayingRef          = useRef<boolean>(false);
  const messagesEndRef        = useRef<HTMLDivElement | null>(null);
  const audioQueueRef         = useRef<string[]>([]);
  const isPlayingQueueRef     = useRef<boolean>(false);
  const thinkingTimeoutRef    = useRef<number | null>(null);
  const elapsedTimerRef       = useRef<number | null>(null);
  const abortControllerRef    = useRef<AbortController | null>(null);

  // VAD frame counters
  const speechFrameCountRef  = useRef<number>(0);
  const silenceFrameCountRef = useRef<number>(0);
  const aiCooldownUntilRef   = useRef<number>(0);

  useEffect(() => { isPlayingRef.current = isPlaying; }, [isPlaying]);

  // ── Waveform animation timer ────────────────────────────────────────────────
  useEffect(() => {
    let id: number | null = null;
    if (isListening || isPlaying || isThinking || isProcessing) {
      id = window.setInterval(() => setWaveformTime(Date.now()), 50);
    }
    return () => { if (id !== null) clearInterval(id); };
  }, [isListening, isPlaying, isThinking, isProcessing]);

  // ── Session elapsed timer ────────────────────────────────────────────────────
  useEffect(() => {
    if (isListening) {
      elapsedTimerRef.current = window.setInterval(
        () => setElapsed(s => s + 1), 1000
      );
    } else {
      if (elapsedTimerRef.current) { clearInterval(elapsedTimerRef.current); elapsedTimerRef.current = null; }
      setElapsed(0);
    }
    return () => { if (elapsedTimerRef.current) { clearInterval(elapsedTimerRef.current); elapsedTimerRef.current = null; } };
  }, [isListening]);

  // ── AudioContext init ────────────────────────────────────────────────────────
  useEffect(() => {
    audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
    return () => {
      if (mediaRecorderRef.current?.state === 'recording') mediaRecorderRef.current.stop();
      audioContextRef.current?.close();
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
      streamRef.current?.getTracks().forEach(t => t.stop());
      if (thinkingTimeoutRef.current) clearTimeout(thinkingTimeoutRef.current);
      if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
      if (abortControllerRef.current) { abortControllerRef.current.abort(); abortControllerRef.current = null; }
      audioQueueRef.current = [];
      if (currentAudioRef.current) { currentAudioRef.current.pause(); currentAudioRef.current = null; }
    };
  }, []);

  // ── VAD + waveform loop ──────────────────────────────────────────────────────
  const updateWaveform = () => {
    if (!analyserRef.current || !audioContextRef.current) {
      animationFrameRef.current = requestAnimationFrame(updateWaveform);
      return;
    }
    const timeBuf = new Uint8Array(analyserRef.current.fftSize);
    analyserRef.current.getByteTimeDomainData(timeBuf);
    let sum = 0;
    for (let i = 0; i < timeBuf.length; i++) { const n = (timeBuf[i] - 128) / 128; sum += n * n; }
    setAudioLevel(Math.min(1, Math.sqrt(sum / timeBuf.length) * 3));

    const now = Date.now();
    if (isPlayingRef.current || now < aiCooldownUntilRef.current) {
      speechFrameCountRef.current  = 0;
      silenceFrameCountRef.current = 0;
      animationFrameRef.current = requestAnimationFrame(updateWaveform);
      return;
    }

    const prob = computeSpeechProb(analyserRef.current, audioContextRef.current.sampleRate);
    const isSpeechFrame = prob > SPEECH_PROB_THRESHOLD;
    const isCurrentRecording = mediaRecorderRef.current?.state === 'recording';

    if (!isCurrentRecording) {
      if (isSpeechFrame) {
        speechFrameCountRef.current++;
        if (speechFrameCountRef.current >= SPEECH_ONSET_FRAMES) {
          speechFrameCountRef.current  = 0;
          silenceFrameCountRef.current = 0;
          setIsSpeaking(true);
          startRecording();
        }
      } else {
        speechFrameCountRef.current = Math.max(0, speechFrameCountRef.current - 1);
      }
    } else {
      if (isSpeechFrame) {
        silenceFrameCountRef.current = 0;
        setIsSpeaking(true);
      } else {
        silenceFrameCountRef.current++;
        const recDuration = now - recordingStartTimeRef.current;
        if (silenceFrameCountRef.current >= SILENCE_FRAMES_END && recDuration >= MIN_RECORD_MS) {
          silenceFrameCountRef.current = 0;
          speechFrameCountRef.current  = 0;
          setIsSpeaking(false);
          stopRecordingAndSend();
        }
      }
    }
    animationFrameRef.current = requestAnimationFrame(updateWaveform);
  };

  // ── Start listening ──────────────────────────────────────────────────────────
  const startListening = async () => {
    if (isListeningRef.current) return;
    try {
      isListeningRef.current = true;
      setError(null);
      if (!navigator.mediaDevices?.getUserMedia)
        throw new Error('Your browser does not support audio recording');

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: { ideal: 48000 }, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });
      streamRef.current = stream;

      if (audioContextRef.current) {
        const source = audioContextRef.current.createMediaStreamSource(stream);
        analyserRef.current = audioContextRef.current.createAnalyser();
        analyserRef.current.fftSize               = 4096;
        analyserRef.current.smoothingTimeConstant = 0.25;
        analyserRef.current.minDecibels           = -90;
        analyserRef.current.maxDecibels           = -10;
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

  // ── Stop listening ───────────────────────────────────────────────────────────
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

  // ── Recording segment ────────────────────────────────────────────────────────
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

      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mediaRecorder.onstop = async () => {
        const totalSize = audioChunksRef.current.reduce((a, c) => a + c.size, 0);
        if (totalSize < 1000) { audioChunksRef.current = []; return; }
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        await processVoiceMessage(audioBlob);
      };
      mediaRecorder.start(100);
    } catch (err) { console.error('[VoiceChat] Error starting recording:', err); }
  };

  const stopRecordingAndSend = () => {
    if (mediaRecorderRef.current?.state === 'recording') mediaRecorderRef.current.stop();
  };

  // ── Send immediately (manual trigger) ───────────────────────────────────────
  const sendNow = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      setIsSpeaking(false);
      stopRecordingAndSend();
    } else {
      stopListening();
    }
  };

  // ── Render message text ───────────────────────────────────────────────────────
  const renderMessageText = (text: string) => {
    const clean = text
      .replace(/\[([^\]]+)\]\(https?:\/\/[^)]*\)/g, '')
      .replace(/https?:\/\/\S+/g, '')
      .replace(/\s{2,}/g, ' ')
      .trim();
    return <span style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>{clean}</span>;
  };

  // ── Process voice message via SSE ────────────────────────────────────────────
  const processVoiceMessage = async (audioBlob: Blob) => {
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

    thinkingTimeoutRef.current = window.setTimeout(() => {
      setIsThinking(false);
      setIsProcessing(false);
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
      abortControllerRef.current = controller;
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
      let extractedUrl = '';

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
              if (!extractedUrl) {
                const mdMatch   = event.text.match(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/);
                const bareMatch = event.text.match(/https?:\/\/\S+/);
                extractedUrl = (mdMatch?.[2] || bareMatch?.[0] || '').replace(/\)+$/, '');
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
              const finalUrl: string = event.explore_url || extractedUrl || '';
              if (finalUrl) {
                setMessages(prev =>
                  prev.map(m => m.id === streamingMsgId ? { ...m, exploreUrl: finalUrl } : m)
                );
              }
              onResponse?.(streamingText);
            } else if (event.type === 'error') {
              console.warn('[VoiceChat] Server error event:', event.message);
              setIsThinking(false);
            }
          } catch { /* ignore malformed lines */ }
        }
      }

      if (!receivedFirstChunk) setIsThinking(false);

    } catch (err: any) {
      console.warn('[VoiceChat] Request error:', err.message);
      setIsThinking(false);
    } finally {
      abortControllerRef.current = null;
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
      try { await playAudioChunk(b64); } catch (e) { console.error('[VoiceChat] Audio error:', e); }
    }
    isPlayingQueueRef.current = false;
    setIsPlaying(false);
    isPlayingRef.current = false;
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
      } catch (err) { currentAudioRef.current = null; reject(err); }
    });

  const playAudioResponse = async (base64Audio: string) => {
    audioQueueRef.current.push(base64Audio);
    processAudioQueue();
  };

  const cancelResponse = () => {
    // Abort in-flight SSE request (covers thinking + streaming states)
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    // Clear thinking timeout
    if (thinkingTimeoutRef.current) { clearTimeout(thinkingTimeoutRef.current); thinkingTimeoutRef.current = null; }
    // Stop audio playback and clear queue
    if (currentAudioRef.current) { currentAudioRef.current.pause(); currentAudioRef.current = null; }
    audioQueueRef.current = [];
    isPlayingQueueRef.current = false;
    setIsPlaying(false);
    isPlayingRef.current = false;
    // Reset processing states — returns UI to listening/ready
    setIsThinking(false);
    setIsProcessing(false);
    setIsSpeaking(false);
    aiCooldownUntilRef.current = Date.now() + POST_AI_COOLDOWN_MS;
  };

  useEffect(() => {
    if (messagesEndRef.current) messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSpeaking, isThinking]);

  useEffect(() => {
    if (error) { const t = setTimeout(() => setError(null), 5000); return () => clearTimeout(t); }
  }, [error]);

  // ─── Derived booleans ────────────────────────────────────────────────────────
  const isActive = isListening || isPlaying || isProcessing || isThinking;

  // ─── Waveform bars ───────────────────────────────────────────────────────────
  const WaveformBars = () => (
    <div className="flex items-center gap-[2px] flex-1 h-full overflow-hidden">
      {Array.from({ length: 26 }).map((_, i) => {
        let h = 18;
        if (isPlaying) {
          h = 22 + Math.sin((i / 1.8) + (waveformTime / 120)) * 58;
        } else if (isSpeaking) {
          h = 20 + audioLevel * 170 + Math.sin((i / 2.8) + (waveformTime / 150)) * 22;
        } else if (isProcessing || isListening) {
          h = 16 + Math.sin((i / 2.5) + (waveformTime / 220)) * 12;
        }
        const clampedH = Math.max(10, Math.min(100, h));
        return (
          <div
            key={i}
            className="w-[3px] rounded-full bg-orange-500 transition-all duration-75"
            style={{ height: `${clampedH}%`, opacity: isProcessing && !isSpeaking ? 0.35 : 1 }}
          />
        );
      })}
    </div>
  );

  return (
    <div
      className="voice-chat-container flex flex-col flex-1 overflow-hidden"
      style={{ background: 'linear-gradient(165deg, #fff9f6 0%, #ffffff 52%, #fff4ef 100%)' }}
    >

      {/* ── Section header ──────────────────────────────────────────────────── */}
      <div className="flex-shrink-0 flex items-center gap-3 px-4 py-3 border-b border-orange-100/50"
        style={{ background: 'rgba(255,255,255,0.7)', backdropFilter: 'blur(8px)' }}
      >
        <div className={`relative w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0
          bg-orange-500 shadow-sm shadow-orange-300`}>
          <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
          {isListening && (
            <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse ring-2 ring-white" />
          )}
        </div>
        <span className="font-bold text-gray-800 text-sm tracking-wide">Voice Chat</span>
      </div>

      {/* ── Messages ────────────────────────────────────────────────────────── */}
      <div
        className="voice-messages flex-1 overflow-y-auto overflow-x-hidden px-4 py-3 space-y-3"
        style={{ scrollBehavior: 'smooth', minHeight: 0 }}
      >
        {messages.length === 0 && !isSpeaking && !isThinking ? (

          /* Empty state */
          <div className="flex flex-col items-center justify-center h-full text-center select-none">
            <div className="w-14 h-14 rounded-full bg-orange-50 flex items-center justify-center mb-4">
              <svg className="w-7 h-7 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </div>
            <p className="text-sm font-medium text-gray-500">Press the button below to start talking</p>
            <p className="text-xs text-gray-400 mt-1">I'll respond automatically when you finish</p>
          </div>

        ) : (
          <>
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col min-w-0 ${msg.type === 'user' ? 'items-end' : 'items-start'}`}
              >
                {/* Bubble */}
                <div className={`max-w-[80%] rounded-2xl px-3.5 py-2.5 min-w-0 ${
                  msg.type === 'user'
                    ? 'bg-gray-800 text-white rounded-br-sm shadow-sm shadow-gray-800/20'
                    : 'bg-white text-gray-700 rounded-bl-sm border border-orange-100/70 shadow-sm shadow-orange-100/40'
                }`}>
                  <p className="text-xs leading-relaxed whitespace-pre-wrap">
                    {renderMessageText(msg.transcript)}
                  </p>
                  <p className={`text-[9px] mt-0.5 ${msg.type === 'user' ? 'text-white/40' : 'text-gray-400/80'}`}>
                    {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>

                {/* Explore button */}
                {msg.type === 'assistant' && msg.exploreUrl && (
                  <div className="mt-1.5 max-w-[80%]">
                    <p className="text-[9px] text-gray-400 mb-1 pl-0.5">
                      Click the button below for more information.
                    </p>
                    <a
                      href={msg.exploreUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={e => e.stopPropagation()}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold
                        bg-orange-50 hover:bg-orange-100 text-orange-600
                        border border-orange-200 hover:border-orange-400
                        transition-all duration-150 hover:scale-[1.02] active:scale-95 shadow-sm"
                    >
                      <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                      <span>Explore More Details</span>
                      <svg className="w-3 h-3 flex-shrink-0 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                      </svg>
                    </a>
                  </div>
                )}
              </div>
            ))}

            {/* Listening indicator pill */}
            {isSpeaking && !isProcessing && (
              <div className="flex justify-center py-1">
                <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-white border border-orange-100/70
                  rounded-full shadow-sm shadow-orange-100/40">
                  <span className="flex gap-[3px]">
                    {[0, 150, 300].map(d => (
                      <span key={d} className="w-1 h-1 rounded-full bg-orange-400 animate-bounce"
                        style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </span>
                  <span className="text-xs font-medium text-orange-500">listening...</span>
                </div>
              </div>
            )}

            {/* Thinking indicator pill */}
            {isThinking && (
              <div className="flex justify-center py-1">
                <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-orange-50 rounded-full shadow-sm border border-orange-100">
                  <span className="flex gap-[3px]">
                    {[0, 150, 300].map(d => (
                      <span key={d} className="w-1 h-1 rounded-full bg-orange-400 animate-bounce"
                        style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </span>
                  <span className="text-xs font-medium text-orange-500">Thinking...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* ── Error toast ──────────────────────────────────────────────────────── */}
      {error && (
        <div className="flex-shrink-0 mx-4 mb-1 px-3 py-2 bg-red-50/90 border border-red-200/70 rounded-xl shadow-sm">
          <p className="text-red-600 text-xs">{error}</p>
        </div>
      )}

      {/* ── Bottom control bar ───────────────────────────────────────────────── */}
      <div className="flex-shrink-0 px-4 pb-5 pt-3 border-t border-orange-100/40"
        style={{ background: 'rgba(255,255,255,0.75)', backdropFilter: 'blur(10px)' }}
      >

        {!isActive ? (

          /* ── IDLE ── */
          <button
            onClick={startListening}
            className="w-full py-3.5 rounded-2xl font-bold text-white text-sm tracking-wide
              bg-orange-500 hover:bg-orange-600 active:bg-orange-700
              shadow-md shadow-orange-400/30 hover:shadow-lg hover:shadow-orange-400/40
              active:scale-[0.98] transition-all duration-200"
          >
            Start Conversation
          </button>

        ) : isThinking ? (

          /* ── THINKING ── [✕] [  AI is thinking ...  ] */
          <div className="flex items-center gap-2.5">
            <button
              onClick={cancelResponse}
              className="flex-shrink-0 w-11 h-11 rounded-full bg-red-500 hover:bg-red-600
                flex items-center justify-center shadow-md shadow-red-400/30
                transition-all duration-150 active:scale-90"
            >
              <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            <div className="flex-1 h-11 rounded-2xl bg-orange-500 flex items-center justify-center gap-2 shadow-sm">
              <span className="flex gap-1">
                {[0, 160, 320].map(d => (
                  <span key={d} className="w-1.5 h-1.5 rounded-full bg-white animate-bounce"
                    style={{ animationDelay: `${d}ms` }} />
                ))}
              </span>
              <span className="text-white text-sm font-semibold">AI is thinking</span>
            </div>
          </div>

        ) : (

          /* ── ACTIVE: [✕] [〰 timer] [↑] ── */
          <div className="flex items-center gap-2.5">

            {/* Cancel / Stop */}
            <button
              onClick={isPlaying ? cancelResponse : stopListening}
              title={isPlaying ? 'Cancel response' : 'End conversation'}
              className="flex-shrink-0 w-11 h-11 rounded-full bg-red-500 hover:bg-red-600
                flex items-center justify-center shadow-md shadow-red-400/30
                transition-all duration-150 active:scale-90"
            >
              <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            {/* Waveform + timer pill */}
            <div className="flex-1 h-11 flex items-center gap-2 px-3 rounded-2xl
              bg-white/80 border border-orange-100/60 overflow-hidden shadow-sm shadow-orange-100/30">
              <WaveformBars />
              <span className="flex-shrink-0 text-[10px] font-mono font-bold text-orange-400
                bg-orange-50 border border-orange-100 px-1.5 py-0.5 rounded-md tabular-nums">
                {fmtTime(elapsed)}
              </span>
            </div>

            {/* Send now / confirm */}
            <button
              onClick={sendNow}
              title="Send now"
              className="flex-shrink-0 w-11 h-11 rounded-full bg-gray-800 hover:bg-gray-700
                flex items-center justify-center shadow-md shadow-gray-600/20
                transition-all duration-150 active:scale-90"
            >
              <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export const VoiceChat = React.memo(VoiceChatComponent, (prev, next) =>
  prev.sessionId === next.sessionId && prev.apiUrl === next.apiUrl
);

export default VoiceChat;
