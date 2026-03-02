"""
Voice Chat Service - Real-time voice conversation with LiveKit + OpenAI

This service handles:
- LiveKit room management and token generation
- Real-time audio streaming
- Speech-to-Text using OpenAI Whisper
- Text-to-Speech using OpenAI TTS
- Integration with existing chatbot logic
"""

import asyncio
import base64
import io
import json
import os
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from livekit import api, rtc
from openai import AsyncOpenAI
import logging

# Configure logging
logger = logging.getLogger(__name__)


class VoiceChatConfig:
    """Configuration for voice chat service"""

    def __init__(self):
        self.livekit_api_key = os.getenv("LIVEKIT_API_KEY")
        self.livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
        self.livekit_url = os.getenv("LIVEKIT_URL")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

        # Validate configuration
        if not all([self.livekit_api_key, self.livekit_api_secret, self.livekit_url]):
            raise ValueError("LiveKit credentials not configured. Check .env file.")

        if not self.openai_api_key:
            raise ValueError("OpenAI API key not configured. Check .env file.")

        # TTS Configuration
        self.tts_model = "tts-1"  # or "tts-1-hd" for higher quality
        self.tts_voice = "alloy"  # alloy, echo, fable, nova, shimmer
        self.tts_speed = 1.0  # 0.25 to 4.0

        # STT Configuration
        self.stt_model = "whisper-1"
        self.stt_language = "en"  # Auto-detect if None

        # Audio Settings
        self.sample_rate = 16000  # 16kHz for speech
        self.channels = 1  # Mono
        self.chunk_duration = 0.5  # seconds


class VoiceChatService:
    """
    Real-time voice chat service using LiveKit for streaming and OpenAI for STT/TTS
    """

    def __init__(self):
        self.config = VoiceChatConfig()
        self.openai_client = AsyncOpenAI(api_key=self.config.openai_api_key)
        self.active_sessions: Dict[str, Any] = {}
        logger.info("VoiceChatService initialized")

    async def generate_access_token(
        self,
        room_name: str,
        participant_identity: str,
        participant_name: Optional[str] = None
    ) -> str:
        """
        Generate LiveKit access token for a participant to join a room

        Args:
            room_name: Name of the LiveKit room
            participant_identity: Unique identifier for the participant (e.g., session_id)
            participant_name: Display name for the participant

        Returns:
            JWT access token string
        """
        try:
            # Create access token
            token = api.AccessToken(
                self.config.livekit_api_key,
                self.config.livekit_api_secret
            )

            # Set token grants
            token.with_identity(participant_identity)
            token.with_name(participant_name or participant_identity)
            token.with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True
                )
            )

            # Set token expiration (1 hour)
            token.with_ttl(timedelta(hours=1))

            jwt_token = token.to_jwt()
            logger.info(f"Generated access token for {participant_identity} in room {room_name}")

            return jwt_token

        except Exception as e:
            logger.error(f"Error generating access token: {str(e)}")
            raise

    async def transcribe_audio(
        self,
        audio_data: bytes,
        audio_format: str = "webm"
    ) -> Optional[str]:
        """
        Transcribe audio using OpenAI Whisper.

        Attempts verbose_json first to get per-segment no_speech_prob scores,
        which lets us discard silence/noise before Whisper hallucinations
        ("Thanks for watching!", "you", etc.) reach the LLM.
        Falls back to plain text format if verbose_json is unsupported.

        Returns:
            Transcribed text, or None if the audio is silence/noise/failed.
        """
        start_time = time.time()

        # ── Attempt 1: verbose_json (gives no_speech_prob for hallucination filter) ──
        try:
            audio_file = io.BytesIO(audio_data)
            audio_file.name = f"audio.{audio_format}"

            result = await asyncio.wait_for(
                self.openai_client.audio.transcriptions.create(
                    model=self.config.stt_model,
                    file=audio_file,
                    language=self.config.stt_language,
                    response_format="verbose_json"
                ),
                timeout=30.0
            )

            # Filter by no_speech_prob — Whisper's own measure of whether the
            # audio contains actual speech. High value = likely silence/noise.
            try:
                segments = getattr(result, 'segments', None) or []
                if segments:
                    max_no_speech = max(
                        float(getattr(seg, 'no_speech_prob', 0)) for seg in segments
                    )
                    if max_no_speech > 0.6:
                        logger.info(
                            f"Discarding silence (no_speech_prob={max_no_speech:.2f}, "
                            f"text='{getattr(result, 'text', '')[:50]}')"
                        )
                        return None
            except Exception as filter_err:
                logger.warning(f"no_speech_prob filter skipped: {filter_err}")

            transcript = getattr(result, 'text', None)
            duration = time.time() - start_time
            # Empty text means no speech detected — return None, never stringify the object
            if not transcript or not transcript.strip():
                logger.info("Transcription returned empty text (silence/noise)")
                return None
            logger.info(f"Transcription (verbose) in {duration:.2f}s: {transcript[:100]}")
            return transcript.strip()

        except asyncio.TimeoutError:
            logger.error("Transcription timed out")
            return None
        except Exception as e:
            logger.warning(f"verbose_json failed ({e}), falling back to text format")

        # ── Attempt 2: plain text fallback ───────────────────────────────────
        try:
            audio_file2 = io.BytesIO(audio_data)
            audio_file2.name = f"audio.{audio_format}"

            transcript = await asyncio.wait_for(
                self.openai_client.audio.transcriptions.create(
                    model=self.config.stt_model,
                    file=audio_file2,
                    language=self.config.stt_language,
                    response_format="text"
                ),
                timeout=30.0
            )
            duration = time.time() - start_time
            logger.info(f"Transcription (text) in {duration:.2f}s: {transcript[:100]}")
            return transcript.strip() or None

        except asyncio.TimeoutError:
            logger.error("Transcription fallback timed out")
            return None
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return None

    async def generate_speech(
        self,
        text: str,
        voice: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Generate speech from text using OpenAI TTS

        Args:
            text: Text to convert to speech
            voice: Voice to use (alloy, echo, fable, nova, shimmer)

        Returns:
            Audio bytes in MP3 format or None if generation fails
        """
        try:
            if not text or not text.strip():
                logger.warning("Empty text provided for TTS")
                return None

            start_time = time.time()

            # Generate speech with timeout
            response = await asyncio.wait_for(
                self.openai_client.audio.speech.create(
                    model=self.config.tts_model,
                    voice=voice or self.config.tts_voice,
                    input=text[:4096],  # TTS has 4096 char limit
                    speed=self.config.tts_speed
                ),
                timeout=30.0
            )

            # Get audio bytes - response.content contains the full audio data
            audio_data = response.content

            duration = time.time() - start_time
            logger.info(f"TTS completed in {duration:.2f}s for {len(text)} chars")

            return audio_data

        except asyncio.TimeoutError:
            logger.error(f"TTS timed out after 30s for {len(text)} chars")
            return None
        except Exception as e:
            logger.error(f"Error generating speech: {str(e)}")
            return None

    async def stream_tts_response(
        self,
        text: str,
        voice: Optional[str] = None
    ):
        """
        Stream TTS response in chunks for lower latency

        Args:
            text: Text to convert to speech
            voice: Voice to use

        Yields:
            Audio chunks as they are generated
        """
        try:
            if not text or not text.strip():
                return

            logger.info(f"Streaming TTS for {len(text)} chars")

            # Generate speech with streaming
            response = await self.openai_client.audio.speech.create(
                model=self.config.tts_model,
                voice=voice or self.config.tts_voice,
                input=text[:4096],
                speed=self.config.tts_speed
            )

            # Stream chunks
            async for chunk in response.iter_bytes(chunk_size=4096):
                yield chunk

            logger.info("TTS streaming completed")

        except Exception as e:
            logger.error(f"Error streaming TTS: {str(e)}")

    def register_session(self, session_id: str, room_name: str):
        """Register an active voice chat session"""
        self.active_sessions[session_id] = {
            "room_name": room_name,
            "started_at": datetime.now(),
            "message_count": 0
        }
        logger.info(f"Registered voice session: {session_id}")

    def unregister_session(self, session_id: str):
        """Unregister a voice chat session"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            logger.info(f"Unregistered voice session: {session_id}")

    def get_active_sessions(self) -> Dict[str, Any]:
        """Get all active voice chat sessions"""
        return self.active_sessions

    async def handle_voice_message(
        self,
        session_id: str,
        audio_data: bytes,
        chatbot_handler: Any,
        audio_format: str = "webm"
    ) -> Optional[Dict[str, Any]]:
        """
        Complete voice message handling pipeline:
        1. Transcribe audio (STT)
        2. Process with chatbot
        3. Generate speech response (TTS)

        Args:
            session_id: Unique session identifier
            audio_data: Raw audio bytes from user
            chatbot_handler: Callable that processes text and returns response
            audio_format: Audio format

        Returns:
            Dict with transcript, response text, and audio data
        """
        try:
            # Step 1: Transcribe audio
            logger.info(f"Processing voice message for session {session_id}")
            transcript = await self.transcribe_audio(audio_data, audio_format)

            if not transcript:
                logger.error("Transcription failed")
                return None

            # Step 2: Process with chatbot
            logger.info(f"Chatbot processing: {transcript[:100]}")
            chatbot_response = await chatbot_handler(session_id, transcript)

            if not chatbot_response:
                logger.error("Chatbot processing failed")
                return None

            response_text = chatbot_response.get("response", "")

            # Step 3: Generate speech
            logger.info(f"Generating speech for response: {response_text[:100]}")
            audio_response = await self.generate_speech(response_text)

            if not audio_response:
                logger.error("TTS generation failed")
                return None

            # Update session stats
            if session_id in self.active_sessions:
                self.active_sessions[session_id]["message_count"] += 1

            return {
                "transcript": transcript,
                "response_text": response_text,
                "audio_data": audio_response,
                "audio_format": "mp3",
                "metadata": chatbot_response.get("metadata", {})
            }

        except Exception as e:
            logger.error(f"Error handling voice message: {str(e)}")
            return None


# Global voice chat service instance
_voice_chat_service: Optional[VoiceChatService] = None


def get_voice_chat_service() -> VoiceChatService:
    """Get or create the global voice chat service instance"""
    global _voice_chat_service

    if _voice_chat_service is None:
        _voice_chat_service = VoiceChatService()

    return _voice_chat_service
