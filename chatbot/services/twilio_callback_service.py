"""
Twilio Callback Service - Phone call callback feature

This service handles:
- Phone callback requests from users
- Initiating calls to both user and sales team
- Conference call management
- Call status tracking and webhooks
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# Configure logging
logger = logging.getLogger(__name__)


class TwilioCallbackConfig:
    """Configuration for Twilio callback service"""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.phone_number = os.getenv("TWILIO_PHONE_NUMBER")
        self.sales_team_number = os.getenv("SALES_TEAM_PHONE_NUMBER")

        # Validate configuration
        if not all([self.account_sid, self.auth_token, self.phone_number, self.sales_team_number]):
            logger.warning(
                "Twilio callback feature is not fully configured. "
                "Check .env for: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
                "TWILIO_PHONE_NUMBER, SALES_TEAM_PHONE_NUMBER"
            )
            self.is_configured = False
        else:
            self.is_configured = True
            logger.info("Twilio callback service configured successfully")


class TwilioCallbackService:
    """
    Service for handling phone callback requests via Twilio
    """

    def __init__(self):
        self.config = TwilioCallbackConfig()

        if self.config.is_configured:
            try:
                self.client = Client(self.config.account_sid, self.config.auth_token)
                logger.info("Twilio client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")
                self.client = None
        else:
            self.client = None

        # Track active calls
        self.active_calls: Dict[str, Dict[str, Any]] = {}

    def is_available(self) -> bool:
        """Check if Twilio callback service is available"""
        return self.config.is_configured and self.client is not None

    async def request_callback(
        self,
        session_id: str,
        user_phone: str,
        base_url: str
    ) -> Dict[str, Any]:
        """
        Initiate a callback by calling both the user and sales team,
        connecting them via a conference call.

        Args:
            session_id: Unique session identifier
            user_phone: User's phone number (E.164 format)
            base_url: Base URL for webhooks (e.g., https://yourdomain.com)

        Returns:
            Dict with call details and status
        """
        if not self.is_available():
            raise Exception(
                "Twilio callback service not configured. "
                "Please set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
                "TWILIO_PHONE_NUMBER, and SALES_TEAM_PHONE_NUMBER in .env"
            )

        try:
            conference_name = f"support-{session_id}"
            status_callback_url = f"{base_url}/api/callback/status"

            logger.info(f"Initiating callback for session {session_id}")
            logger.info(f"User: {user_phone}, Team: {self.config.sales_team_number}")

            # Step 1: Call the user first
            user_call = self.client.calls.create(
                to=user_phone,
                from_=self.config.phone_number,
                twiml=f'''
                <Response>
                    <Say voice="alice">
                        Hello! Thank you for requesting a callback.
                        Connecting you to our sales team now. Please hold.
                    </Say>
                    <Dial>
                        <Conference
                            beep="false"
                            startConferenceOnEnter="true"
                            endConferenceOnExit="false"
                            statusCallback="{status_callback_url}"
                            statusCallbackEvent="start,end,join,leave">
                            {conference_name}
                        </Conference>
                    </Dial>
                </Response>
                ''',
                status_callback=status_callback_url,
                status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
                status_callback_method='POST'
            )

            logger.info(f"User call initiated: {user_call.sid}")

            # Step 2: Call the sales team (1 second delay to ensure user joins first)
            team_call = self.client.calls.create(
                to=self.config.sales_team_number,
                from_=self.config.phone_number,
                twiml=f'''
                <Response>
                    <Say voice="alice">
                        You have a support call from a customer via the chatbot.
                        Connecting you now.
                    </Say>
                    <Dial>
                        <Conference
                            beep="false"
                            startConferenceOnEnter="true"
                            endConferenceOnExit="true"
                            statusCallback="{status_callback_url}"
                            statusCallbackEvent="start,end,join,leave">
                            {conference_name}
                        </Conference>
                    </Dial>
                </Response>
                ''',
                status_callback=status_callback_url,
                status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
                status_callback_method='POST'
            )

            logger.info(f"Team call initiated: {team_call.sid}")

            # Track the call
            self.active_calls[session_id] = {
                "conference_name": conference_name,
                "user_call_sid": user_call.sid,
                "team_call_sid": team_call.sid,
                "user_phone": user_phone,
                "started_at": datetime.now().isoformat(),
                "status": "connecting"
            }

            return {
                "status": "connecting",
                "message": "You'll receive a call shortly. Please answer your phone.",
                "conference_name": conference_name,
                "user_call_sid": user_call.sid,
                "team_call_sid": team_call.sid
            }

        except TwilioRestException as e:
            logger.error(f"Twilio error initiating callback: {e}")
            error_msg = self._format_twilio_error(e)
            raise Exception(error_msg)
        except Exception as e:
            logger.error(f"Error initiating callback: {e}")
            raise Exception(f"Failed to initiate callback: {str(e)}")

    def handle_call_status(self, call_sid: str, status_data: Dict[str, Any]) -> None:
        """
        Handle call status webhook from Twilio

        Args:
            call_sid: Twilio call SID
            status_data: Status update data from Twilio webhook
        """
        try:
            call_status = status_data.get("CallStatus", "unknown")
            logger.info(f"Call status update - SID: {call_sid}, Status: {call_status}")

            # Find the session for this call
            session_id = None
            for sid, call_data in self.active_calls.items():
                if call_data.get("user_call_sid") == call_sid or call_data.get("team_call_sid") == call_sid:
                    session_id = sid
                    break

            if session_id:
                self.active_calls[session_id]["last_status"] = call_status
                self.active_calls[session_id]["last_updated"] = datetime.now().isoformat()

                # If call completed, we can clean up after some time
                if call_status == "completed":
                    logger.info(f"Call {call_sid} completed for session {session_id}")

        except Exception as e:
            logger.error(f"Error handling call status: {e}")

    def get_call_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get call information for a session"""
        return self.active_calls.get(session_id)

    def _format_twilio_error(self, error: TwilioRestException) -> str:
        """Format Twilio error into user-friendly message"""
        error_code = error.code

        common_errors = {
            21211: "Invalid phone number. Please check the number and try again.",
            21214: "The phone number is not verified. For trial accounts, verify the number first.",
            21217: "The phone number is not reachable. Please check the number.",
            21608: "This number is not allowed for your account type. Upgrade your Twilio account.",
            21610: "This number is blocked for your account.",
        }

        return common_errors.get(error_code, f"Call failed: {error.msg}")


# Global service instance
_twilio_callback_service: Optional[TwilioCallbackService] = None


def get_twilio_callback_service() -> TwilioCallbackService:
    """Get or create the global Twilio callback service instance"""
    global _twilio_callback_service

    if _twilio_callback_service is None:
        _twilio_callback_service = TwilioCallbackService()

    return _twilio_callback_service
