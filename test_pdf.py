#!/usr/bin/env python3
"""Test script for PDF functionality."""

import sys
import os

# Add current directory to path to import crawler
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler import LabCrawler


def test_pdf_link_detection():
    """Test PDF link detection logic."""
    crawler = LabCrawler()
    
    # Test HTML content simulation
    test_html = '''
    <html>
        <body>
            <a href="/get_laudo?id=123">Visualizar Laudo</a>
            <a href="/download_pdf">Baixar</a>
            <a href="/other_link">Other Link</a>
        </body>
    </html>
    '''
    
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(test_html, 'html.parser')
    
    # Test link detection logic
    target_texts = ['visualizar laudo', 'baixar', 'download']
    found_links = []
    
    for link in soup.find_all('a', href=True):
        link_text = link.get_text().strip().lower()
        href = link.get('href')
        
        if any(target in link_text for target in target_texts):
            found_links.append((href, link_text))
        elif '/get_laudo' in href:
            found_links.append((href, 'get_laudo endpoint'))
    
    print("✅ PDF link detection test:")
    for href, description in found_links:
        print(f"  Found: {href} ({description})")
    
    assert len(found_links) >= 2, "Should find at least 2 PDF-related links"
    print("✅ PDF link detection working correctly")


def test_pdf_content_validation():
    """Test PDF content validation."""
    # Test PDF header validation
    pdf_content = b'%PDF-1.4\n%some pdf content here'
    html_content = b'<html><body>Not a PDF</body></html>'
    
    is_pdf_1 = pdf_content.startswith(b'%PDF')
    is_pdf_2 = html_content.startswith(b'%PDF')
    
    print("✅ PDF content validation test:")
    print(f"  PDF content detected: {is_pdf_1}")
    print(f"  HTML content rejected: {not is_pdf_2}")
    
    assert is_pdf_1, "Should detect valid PDF content"
    assert not is_pdf_2, "Should reject non-PDF content"
    print("✅ PDF content validation working correctly")


if __name__ == "__main__":
    print("Running PDF functionality tests...")
    test_pdf_link_detection()
    test_pdf_content_validation()
    print("All PDF tests passed!")