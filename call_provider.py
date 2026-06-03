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
    async def make_call(self, phone_number: str, scenario: str) -> CallResult:
        """
        Initiate a prank call.
        
        Args:
            phone_number: Target phone number in +380XXXXXXXXX format
            scenario: Scenario key (e.g. 'police', 'debt', etc.)
        
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

    async def make_call(self, phone_number: str, scenario: str) -> CallResult:
        logger.info(f"[MOCK] Calling {phone_number} with scenario '{scenario}'")
        # Simulate call duration (3-5 seconds in mock)
        await asyncio.sleep(3)
        logger.info(f"[MOCK] Call to {phone_number} completed")
        return CallResult(
            success=True,
            duration=45,  # fake 45 second call
            recording_url=None,  # mock has no real recording
            provider_call_id=f"mock_{phone_number}_{scenario}",
        )

    async def get_recording(self, provider_call_id: str) -> Optional[bytes]:
        """Mock provider has no recordings."""
        return None


# ─── SCENARIOS ─────────────────────────────────────────────────────

CALL_SCENARIOS = {
    "police": {
        "emoji": "🚔",
        "name": "Поліція",
        "description": "Дзвінок нібито з поліції",
    },
    "debt": {
        "emoji": "💰",
        "name": "Борг",
        "description": "Дзвінок про борг",
    },
    "secret_admirer": {
        "emoji": "❤️",
        "name": "Таємний прихильник",
        "description": "Таємний прихильник зізнається",
    },
    "prize": {
        "emoji": "🎁",
        "name": "Ви виграли приз",
        "description": "Повідомлення про виграш",
    },
    "school": {
        "emoji": "🏫",
        "name": "Дзвінок зі школи",
        "description": "Дзвінок від класного керівника",
    },
    "ai_prank": {
        "emoji": "🤖",
        "name": "AI-пранк",
        "description": "AI розмовляє з жертвою",
    },
}


def get_call_provider() -> CallProvider:
    """
    Factory function to get the active call provider.
    Switch to TwilioCallProvider when ready.
    """
    return MockCallProvider()
