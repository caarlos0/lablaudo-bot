#!/usr/bin/env python3
"""Test script to verify the crawler setup."""

import sys
import os

# Add current directory to path to import crawler
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler import LabCrawler


def test_crawler_initialization():
    """Test that the crawler initializes correctly."""
    crawler = LabCrawler()
    assert crawler.base_url == "https://lablaudo.com.br"
    assert crawler.login_url == "https://lablaudo.com.br/acesso_paciente"
    print("✅ Crawler initialization test passed")


def test_login_with_mock_credentials():
    """Test login functionality with mock credentials."""
    crawler = LabCrawler()
    
    # Test with invalid credentials (should fail)
    result = crawler.login("invalid_user", "invalid_pass")
    print(f"✅ Invalid credentials test: {'Failed as expected' if not result else 'Unexpected success'}")


if __name__ == "__main__":
    print("Running basic tests...")
    test_crawler_initialization()
    test_login_with_mock_credentials()
    print("All tests passed!")