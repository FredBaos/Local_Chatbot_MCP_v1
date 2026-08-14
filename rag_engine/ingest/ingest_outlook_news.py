"""
TLDR News Outlook Scraper

Automatically extracts TLDR newsletters and other tech news from Outlook's 'News' folder
and converts them into searchable vector embeddings in ChromaDB.

Features:
- Connects to Outlook via IMAP (outlook.office365.com)
- Fetches emails from dedicated 'News' folder
- HTML parsing & cleaning (removes ads, unsubscribe links, etc.)
- Chunks content into overlapping segments
- Stores vectors in ChromaDB's 'tech_news' collection
"""

import os
import sys
import re
import imaplib
import email
from email.header import decode_header
from datetime import datetime
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rag_engine.storage.chroma_knowledge import add_to_chroma
from rag_engine.utils.rag_support import chunk_text


def get_imap_connection(email_address: str, password: str, server: str = "outlook.office365.com", port: int = 993):
    """
    Establish IMAP connection to Outlook.
    
    Args:
        email_address: Outlook email address
        password: Outlook password or app-specific password
        server: IMAP server (default: Outlook)
        port: IMAP port (default: 993 for SSL)
    
    Returns:
        Connected IMAP4_SSL object or None if connection fails
    """
    try:
        mail = imaplib.IMAP4_SSL(server, port)
        mail.login(email_address, password)
        print(f"✓ Connected to {server}")
        return mail
    except imaplib.IMAP4.error as e:
        print(f"✗ Failed to connect to {server}: {e}")
        return None


def select_news_folder(mail: imaplib.IMAP4_SSL, folder_name: str = "News") -> bool:
    """
    Select the specified folder in Outlook.
    
    Args:
        mail: Connected IMAP object
        folder_name: Name of folder to select (default: 'News')
    
    Returns:
        True if folder selected, False otherwise
    """
    try:
        status, mailbox_list = mail.list()
        if status == "OK":
            print(f"Available folders: {[b.decode() for b in mailbox_list[:5]]}...")
        
        status, _ = mail.select(f'"{folder_name}"')
        if status == "OK":
            print(f"✓ Selected '{folder_name}' folder")
            return True
        else:
            print(f"✗ Could not select '{folder_name}' folder. Trying 'INBOX' instead.")
            mail.select("INBOX")
            return False
    except Exception as e:
        print(f"✗ Error selecting folder: {e}")
        return False


def decode_email_header(header_value: str) -> str:
    """Safely decode email header values (handles MIME encoding)."""
    if not header_value:
        return ""
    
    if isinstance(header_value, str):
        return header_value
    
    decoded_parts = []
    for part, encoding in decode_header(header_value):
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(encoding or "utf-8"))
            except (UnicodeDecodeError, TypeError):
                decoded_parts.append(part.decode("utf-8", errors="ignore"))
        else:
            decoded_parts.append(str(part))
    
    return "".join(decoded_parts)


def clean_html_content(html_content: str) -> str:
    """
    Parse HTML email and extract clean text content.
    Removes: sponsor ads, unsubscribe links, HTML tags, extra whitespace.
    
    Args:
        html_content: Raw HTML email body
    
    Returns:
        Cleaned text content
    """
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove common noise elements
    for element in soup.find_all(["script", "style", "meta", "link"]):
        element.decompose()
    
    # Remove unsubscribe sections (commonly at the end)
    for element in soup.find_all(text=re.compile(r"unsubscribe|Unsubscribe|UNSUBSCRIBE", re.IGNORECASE)):
        parent = element.parent
        if parent:
            # Remove the parent container (usually a paragraph or div)
            if parent.parent:
                parent.parent.decompose()
            else:
                parent.decompose()
    
    # Remove sponsor/ad related sections
    for element in soup.find_all(text=re.compile(r"sponsor|Sponsor|SPONSOR|advertisement|Advertisement", re.IGNORECASE)):
        parent = element.parent
        if parent and parent.parent:
            parent.parent.decompose()
    
    # Extract text and clean whitespace
    text = soup.get_text(separator="\n", strip=True)
    
    # Remove multiple consecutive newlines
    text = re.sub(r"\n\n+", "\n", text)
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    return text


def extract_email_content(email_message) -> dict:
    """
    Extract subject, date, and body from email message.
    
    Args:
        email_message: Email message object from imaplib
    
    Returns:
        Dictionary with 'subject', 'date', 'body', and 'sender' keys
    """
    subject = decode_email_header(email_message.get("Subject", "No Subject"))
    date_str = decode_email_header(email_message.get("Date", ""))
    sender = decode_email_header(email_message.get("From", "Unknown"))
    
    # Extract body (prefer plain text, fallback to HTML)
    body = ""
    if email_message.is_multipart():
        for part in email_message.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                break
            elif part.get_content_type() == "text/html":
                html_content = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                body = clean_html_content(html_content)
    else:
        content_type = email_message.get_content_type()
        if content_type == "text/html":
            html_content = email_message.get_payload(decode=True).decode("utf-8", errors="ignore")
            body = clean_html_content(html_content)
        else:
            body = email_message.get_payload(decode=True).decode("utf-8", errors="ignore")
    
    return {
        "subject": subject,
        "date": date_str,
        "sender": sender,
        "body": body,
    }


def fetch_tldr_emails(
    mail: imaplib.IMAP4_SSL,
    limit: int = 10,
    sender_filter: str = "tldr"
) -> list[dict]:
    """
    Fetch TLDR newsletter emails from selected folder.
    
    Args:
        mail: Connected IMAP object
        limit: Maximum number of emails to fetch
        sender_filter: Filter emails by sender substring (default: 'tldr')
    
    Returns:
        List of email dictionaries with subject, date, body, sender
    """
    try:
        status, message_ids = mail.search(None, "ALL")
        if status != "OK":
            print("✗ No emails found")
            return []
        
        email_list = message_ids[0].split()
        email_list = email_list[-limit:]  # Get most recent N emails
        
        emails = []
        for email_id in email_list:
            status, email_data = mail.fetch(email_id, "(RFC822)")
            if status == "OK":
                email_body = email_data[0][1]
                email_message = email.message_from_bytes(email_body)
                
                # Filter by sender if specified
                sender = email_message.get("From", "").lower()
                if sender_filter.lower() in sender or not sender_filter:
                    content = extract_email_content(email_message)
                    if content["body"].strip():  # Only add if body is not empty
                        emails.append(content)
                        print(f"✓ Fetched: {content['subject'][:50]}...")
        
        print(f"✓ Successfully fetched {len(emails)} emails")
        return emails
    except Exception as e:
        print(f"✗ Error fetching emails: {e}")
        return []


def ingest_outlook_news(
    email_address: str,
    password: str,
    folder_name: str = "News",
    email_limit: int = 10,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    collection_name: str = "tech_news",
) -> int:
    """
    Main function to ingest TLDR/tech news from Outlook into ChromaDB.
    
    Args:
        email_address: Outlook email address
        password: Outlook password or app-specific password
        folder_name: Folder to fetch emails from (default: 'News')
        email_limit: Maximum emails to process (default: 10)
        chunk_size: Size of text chunks (default: 500 characters)
        chunk_overlap: Overlap between chunks (default: 50 characters)
        collection_name: ChromaDB collection name (default: 'tech_news')
    
    Returns:
        Number of documents successfully ingested
    """
    print(f"\n{'='*60}")
    print("TLDR News Outlook Scraper")
    print(f"{'='*60}\n")
    
    # Connect to Outlook
    mail = get_imap_connection(email_address, password)
    if not mail:
        return 0
    
    # Select News folder
    select_news_folder(mail, folder_name)
    
    # Fetch emails
    emails = fetch_tldr_emails(mail, limit=email_limit, sender_filter="")
    mail.close()
    mail.logout()
    
    if not emails:
        print("✗ No emails to process")
        return 0
    
    # Process and ingest emails
    total_ingested = 0
    for email_data in emails:
        subject = email_data["subject"]
        date = email_data["date"]
        sender = email_data["sender"]
        body = email_data["body"]
        
        # Create document with metadata
        document = f"Subject: {subject}\nDate: {date}\nFrom: {sender}\n\n{body}"
        
        # Chunk the content
        chunks = chunk_text(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        
        # Add to ChromaDB
        try:
            for i, chunk in enumerate(chunks):
                metadata = {
                    "source": "outlook_email",
                    "sender": sender,
                    "subject": subject,
                    "date": date,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                }
                
                add_to_chroma(
                    documents=[chunk],
                    metadatas=[metadata],
                    collection_name=collection_name,
                )
            
            total_ingested += len(chunks)
            print(f"✓ Ingested {len(chunks)} chunks from: {subject}")
        except Exception as e:
            print(f"✗ Error ingesting {subject}: {e}")
    
    print(f"\n{'='*60}")
    print(f"✓ Successfully ingested {total_ingested} chunks")
    print(f"✓ Collection: '{collection_name}'")
    print(f"{'='*60}\n")
    
    return total_ingested


if __name__ == "__main__":
    # Example usage
    # Note: Set environment variables for security
    email_address = os.getenv("OUTLOOK_EMAIL", "your_email@outlook.com")
    password = os.getenv("OUTLOOK_PASSWORD", "your_app_specific_password")
    
    if email_address == "your_email@outlook.com":
        print("⚠ Please set OUTLOOK_EMAIL and OUTLOOK_PASSWORD environment variables")
        print("Example: export OUTLOOK_EMAIL='your_email@outlook.com'")
        print("         export OUTLOOK_PASSWORD='your_app_specific_password'")
    else:
        ingest_outlook_news(
            email_address=email_address,
            password=password,
            folder_name="News",
            email_limit=10,
            chunk_size=500,
            chunk_overlap=50,
        )
