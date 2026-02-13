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
        Transcribe audio using OpenAI Whisper

        Args:
            audio_data: Raw audio bytes
            audio_format: Audio format (webm, mp3, wav, etc.)

        Returns:
            Transcribed text or None if transcription fails
        """
        try:
            # Create a file-like object from audio bytes
            audio_file = io.BytesIO(audio_data)
            audio_file.name = f"audio.{audio_format}"

            # Call Whisper API
            start_time = time.time()
            transcript = await self.openai_client.audio.transcriptions.create(
                model=self.config.stt_model,
                file=audio_file,
                language=self.config.stt_language,
                response_format="text"
            )

            duration = time.time() - start_time
            logger.info(f"Transcription completed in {duration:.2f}s: {transcript[:100]}")

            return transcript

        except Exception as e:
            logger.error(f"Error transcribing audio: {str(e)}")
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

            # Generate speech
            response = await self.openai_client.audio.speech.create(
                model=self.config.tts_model,
                voice=voice or self.config.tts_voice,
                input=text[:4096],  # TTS has 4096 char limit
                speed=self.config.tts_speed
            )

            # Get audio bytes - response.content contains the full audio data
            audio_data = response.content

            duration = time.time() - start_time
            logger.info(f"TTS completed in {duration:.2f}s for {len(text)} chars")

            return audio_data

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
