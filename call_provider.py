"""
Call Provider interface for prank calls.
Designed for easy swap between Mock/Twilio/other providers.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CallResult:
    """Result of a completed call."""
    success: bool
    duration: int = 0  # seconds
    recording_url: Optional[str] = None
    error: Optional[str] = None
    provider_call_id: Optional[str] = None


class CallProvider(ABC):
    """Abstract base class for call providers."""

    @abstractmethod
    async def make_call(self, phone_number: str, audio_file_id: str) -> CallResult:
        """
        Initiate a prank call that plays the specified audio.

        Args:
            phone_number: Target phone number in +380XXXXXXXXX format
            audio_file_id: Telegram file_id of the audio to play

        Returns:
            CallResult with call outcome
        """
        pass

    @abstractmethod
    async def get_recording(self, provider_call_id: str) -> Optional[bytes]:
        """
        Get call recording as bytes (for sending to Telegram).

        Args:
            provider_call_id: Provider-specific call identifier

        Returns:
            Audio bytes or None if unavailable
        """
        pass


class MockCallProvider(CallProvider):
    """
    Mock provider for development/testing.
    Simulates a call with a delay and returns fake results.
    """

    async def make_call(self, phone_number: str, audio_file_id: str) -> CallResult:
        logger.info(f"[MOCK] Calling {phone_number} with audio {audio_file_id[:20]}...")
        # Simulate call duration
        await asyncio.sleep(3)
        logger.info(f"[MOCK] Call to {phone_number} completed")
        return CallResult(
            success=True,
            duration=45,  # fake 45 second call
            recording_url=None,
            provider_call_id=f"mock_{phone_number}",
        )

    async def get_recording(self, provider_call_id: str) -> Optional[bytes]:
        """Mock provider has no recordings."""
        return None


def get_call_provider() -> CallProvider:
    """
    Factory function to get the active call provider.
    Switch to TwilioCallProvider when ready.
    """
    return MockCallProvider()
