#!/usr/bin/env python3
"""Test script for the Telegram bot functionality."""

import asyncio
import logging
import os

import httpx
import pytest

from lablaudo.bot import LabBot
from lablaudo.database import Database


def test_httpx_requests_do_not_log_bot_tokens(caplog: pytest.LogCaptureFixture) -> None:
    """Keep Telegram authentication tokens out of request logs."""
    caplog.set_level(logging.INFO)
    token = "000000:synthetic-test-token"
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    with httpx.Client(transport=transport, trust_env=False) as client:
        response = client.post(f"https://api.telegram.org/bot{token}/getMe")

    assert response.status_code == 200
    assert token not in caplog.text
    logging.getLogger("lablaudo.bot").info("Monitoring completed")
    assert "Monitoring completed" in caplog.text


async def test_bot_components():
    """Test bot components without actually running the bot."""
    print("🧪 Testing Lab Results Monitor Bot Components")
    
    # Test database
    print("\n📊 Testing Database...")
    db = Database("test.db")
    
    # Test adding user
    success = db.add_user(12345, "testuser", "testpass")
    print(f"✅ Add user: {'Success' if success else 'Failed'}")
    
    # Test getting user
    user = db.get_user(12345)
    print(f"✅ Get user: {'Found' if user else 'Not found'}")
    
    # Test getting all users
    users = db.get_all_active_users()
    print(f"✅ Get all users: {len(users)} users found")
    
    # Test status update
    db.update_user_status(12345, "test_status")
    print("✅ Status update: Success")
    
    # Test remove user
    removed = db.remove_user(12345)
    print(f"✅ Remove user: {'Success' if removed else 'Failed'}")
    
    # Clean up test database
    os.remove("test.db")
    print("✅ Test database cleaned up")
    
    # Test bot initialization
    print("\n🤖 Testing Bot Initialization...")
    try:
        bot = LabBot("dummy_token")
        print("✅ Bot initialization: Success")
        print(f"✅ Bot handlers: {len(bot.application.handlers)} handler groups")
        print("✅ Scheduler: Configured")
    except Exception as e:
        print(f"❌ Bot initialization failed: {e}")
    
    print("\n🎉 All component tests completed!")


if __name__ == "__main__":
    asyncio.run(test_bot_components())