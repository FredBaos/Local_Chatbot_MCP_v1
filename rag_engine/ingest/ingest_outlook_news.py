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
import json
import getpass
from email.header import decode_header
from datetime import datetime
from pathlib import Path
from typing import Optional, Set
from bs4 import BeautifulSoup

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rag_engine.storage.chroma_knowledge import get_chroma_client


# File to track processed email IDs
PROCESSED_EMAILS_FILE = os.path.join(os.path.dirname(__file__), "..", "storage", "data", "processed_emails.json")


def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """
    Split text into overlapping chunks.
    
    Args:
        text: Text to chunk
        chunk_size: Size of each chunk in characters
        chunk_overlap: Overlap between chunks
    
    Returns:
        List of text chunks
    """
    if not text or chunk_size <= 0:
        return [text] if text else []
    
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunks.append(text[start:end])
        start = end - chunk_overlap if end < text_length else text_length
    
    return chunks


def load_processed_emails() -> Set[str]:
    """Load set of already-processed email IDs from tracking file."""
    if not os.path.exists(PROCESSED_EMAILS_FILE):
        return set()
    
    try:
        with open(PROCESSED_EMAILS_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("email_ids", []))
    except Exception as e:
        print(f"⚠ Could not load processed emails file: {e}")
        return set()


def save_processed_emails(email_ids: Set[str]) -> None:
    """Save processed email IDs to tracking file."""
    try:
        os.makedirs(os.path.dirname(PROCESSED_EMAILS_FILE), exist_ok=True)
        with open(PROCESSED_EMAILS_FILE, "w") as f:
            json.dump({"email_ids": list(email_ids)}, f, indent=2)
        print(f"✓ Saved {len(email_ids)} processed email IDs")
    except Exception as e:
        print(f"⚠ Could not save processed emails file: {e}")


def get_email_uid(email_message) -> Optional[str]:
    """Extract or generate a unique ID for an email."""
    message_id = email_message.get("Message-ID")
    if message_id:
        return message_id.strip("<>")
    
    # Fallback: create ID from subject + date
    subject = email_message.get("Subject", "")
    date = email_message.get("Date", "")
    if subject and date:
        return f"{subject}:{date}"
    
    return None


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
        print(f"🔗 Connecting to {server}:{port}...")
        mail = imaplib.IMAP4_SSL(server, port, timeout=15)
        print(f"✓ SSL connection established")
        
        print(f"🔑 Attempting login with {email_address}...")
        mail.login(email_address, password)
        print(f"✓ Authentication successful")
        return mail
    except imaplib.IMAP4.error as e:
        error_msg = str(e)
        print(f"✗ IMAP authentication failed: {error_msg}")
        
        # Provide diagnostics
        if "AUTHENTICATIONFAILED" in error_msg.upper():
            print("\n⚠ Authentication failed. Check:")
            print("  • Are you using an app-specific password (not your regular password)?")
            print("  • Is two-factor authentication (2FA) enabled on your Outlook account?")
            print("  • Is IMAP enabled in Outlook settings (Account > App passwords)?")
            print("  • For Office 365/Outlook.com, use an app-specific password")
        elif "NO" in error_msg:
            print("\n⚠ Login credentials rejected by server")
            print("  • Check that email and password are correct")
            print("  • Verify the account hasn't been temporarily locked")
        
        return None
    except TimeoutError:
        print(f"✗ Connection timeout to {server}:{port}")
        print("  • Check your internet connection")
        print("  • Verify the server is reachable")
        return None
    except Exception as e:
        print(f"✗ Connection error: {type(e).__name__}: {e}")
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
            available_folders = [b.decode() for b in mailbox_list]
            print(f"\n📁 Available folders:")
            for folder in available_folders[:10]:
                print(f"   • {folder}")
            if len(available_folders) > 10:
                print(f"   ... and {len(available_folders) - 10} more")
        
        # Try to select the specified folder
        status, _ = mail.select(f'"{folder_name}"')
        if status == "OK":
            print(f"✓ Selected '{folder_name}' folder")
            return True
        
        # If folder not found, try alternative names
        print(f"⚠ '{folder_name}' folder not found. Trying alternatives...")
        alternatives = ["[Gmail]/All Mail", "All Mail", "Inbox", "[Gmail]/Important"]
        for alt_folder in alternatives:
            status, _ = mail.select(f'"{alt_folder}"')
            if status == "OK":
                print(f"✓ Selected '{alt_folder}' folder instead")
                return True
        
        print(f"✗ Could not find or select any readable folder")
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
    sender_filter: str = "tldr",
    processed_ids: Optional[Set[str]] = None
) -> tuple[list[dict], Set[str]]:
    """
    Fetch TLDR newsletter emails from selected folder, skipping already-processed ones.
    
    Args:
        mail: Connected IMAP object
        limit: Maximum number of emails to fetch
        sender_filter: Filter emails by sender substring (default: 'tldr')
        processed_ids: Set of already-processed email IDs to skip
    
    Returns:
        Tuple of (list of new email dicts, set of all processed IDs including new ones)
    """
    if processed_ids is None:
        processed_ids = set()
    
    try:
        status, message_ids = mail.search(None, "ALL")
        if status != "OK":
            print("✗ No emails found")
            return [], processed_ids
        
        email_list = message_ids[0].split()
        email_list = email_list[-limit:]  # Get most recent N emails
        
        emails = []
        skipped = 0
        for email_id in email_list:
            status, email_data = mail.fetch(email_id, "(RFC822)")
            if status == "OK":
                email_body = email_data[0][1]
                email_message = email.message_from_bytes(email_body)
                
                # Get unique email ID
                uid = get_email_uid(email_message)
                
                # Skip if already processed
                if uid and uid in processed_ids:
                    skipped += 1
                    continue
                
                # Filter by sender if specified
                sender = email_message.get("From", "").lower()
                if sender_filter.lower() in sender or not sender_filter:
                    content = extract_email_content(email_message)
                    if content["body"].strip():  # Only add if body is not empty
                        emails.append(content)
                        if uid:
                            processed_ids.add(uid)
                        print(f"✓ Fetched: {content['subject'][:50]}...")
        
        if skipped > 0:
            print(f"⊘ Skipped {skipped} already-processed emails")
        print(f"✓ Successfully fetched {len(emails)} new emails")
        return emails, processed_ids
    except Exception as e:
        print(f"✗ Error fetching emails: {e}")
        return [], processed_ids


def _ingest_emails_to_chroma(
    emails: list[dict],
    collection_name: str,
    chunk_size: int,
    chunk_overlap: int,
    processed_ids: Set[str],
) -> int:
    """
    Helper function to ingest emails into ChromaDB.
    
    Args:
        emails: List of email dicts with subject, date, sender, body
        collection_name: ChromaDB collection name
        chunk_size: Characters per chunk
        chunk_overlap: Overlap between chunks
        processed_ids: Set of already-processed IDs
    
    Returns:
        Number of chunks ingested
    """
    if not emails:
        print("✗ No emails to process")
        return 0
    
    # Get ChromaDB client and collection
    client = get_chroma_client()
    try:
        collection = client.get_or_create_collection(name=collection_name)
    except Exception as e:
        print(f"✗ Error accessing collection '{collection_name}': {e}")
        return 0
    
    # Process and ingest emails
    total_ingested = 0
    all_documents = []
    all_metadatas = []
    all_ids = []
    email_counter = 0
    
    for email_data in emails:
        subject = email_data["subject"]
        date = email_data["date"]
        sender = email_data["sender"]
        body = email_data["body"]
        
        # Create document with metadata
        document = f"Subject: {subject}\nDate: {date}\nFrom: {sender}\n\n{body}"
        
        # Chunk the content
        chunks = chunk_text(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        
        # Add chunks to batch
        for i, chunk in enumerate(chunks):
            metadata = {
                "source": "outlook_email",
                "sender": sender,
                "subject": subject,
                "date": date,
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
            
            all_documents.append(chunk)
            all_metadatas.append(metadata)
            all_ids.append(f"outlook_email_{email_counter}_{i}")
        
        email_counter += 1
        total_ingested += len(chunks)
        print(f"✓ Prepared {len(chunks)} chunks from: {subject}")
    
    # Batch add all documents to ChromaDB
    if all_documents:
        try:
            collection.add(
                documents=all_documents,
                metadatas=all_metadatas,
                ids=all_ids
            )
            print(f"\n{'='*60}")
            print(f"✓ Successfully ingested {total_ingested} chunks")
            print(f"✓ Collection: '{collection_name}'")
            print(f"{'='*60}\n")
        except Exception as e:
            print(f"✗ Error adding documents to ChromaDB: {e}")
            total_ingested = 0
    
    # Save processed email IDs for next run (incremental ingestion)
    save_processed_emails(processed_ids)
    
    return total_ingested


def ingest_outlook_news(
    email_address: str,
    password: str,
    folder_name: str = "News",
    email_limit: int = 20,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    collection_name: str = "tech_news",
    dry_run: bool = False,
) -> int:
    """
    Main function to ingest TLDR/tech news from Outlook into ChromaDB.
    
    Args:
        email_address: Outlook email address
        password: Outlook password or app-specific password
        folder_name: Folder to fetch emails from (default: 'News')
        email_limit: Maximum emails to process (default: 20)
        chunk_size: Size of text chunks (default: 500 characters)
        chunk_overlap: Overlap between chunks (default: 50 characters)
        collection_name: ChromaDB collection name (default: 'tech_news')
        dry_run: Test mode - shows what would happen without real auth (default: False)
    
    Returns:
        Number of documents successfully ingested
    """
    print(f"\n{'='*60}")
    print("📰 TLDR News Outlook Scraper")
    print(f"{'='*60}\n")
    
    if dry_run:
        print("🧪 DRY-RUN MODE - Testing without authentication")
        print("   This demonstrates the pipeline without connecting to Outlook\n")
        
        # Demo: Create sample emails
        sample_emails = [
            {
                "subject": "[TLDR] Tech News #1: AI Breakthroughs",
                "date": "2026-08-14",
                "sender": "tldr@tldr.com",
                "body": "Today's top AI stories: New transformer architecture released...",
            },
            {
                "subject": "[TLDR] Tech News #2: Cloud Developments",
                "date": "2026-08-13",
                "sender": "tldr@tldr.com",
                "body": "Cloud infrastructure updates: Kubernetes 2.0 announced...",
            },
        ]
        
        return _ingest_emails_to_chroma(
            sample_emails,
            collection_name,
            chunk_size,
            chunk_overlap,
            load_processed_emails(),  # Still track processed emails
        )
    
    # Real authentication mode
    print(f"🔒 Securing connection to Outlook...")
    print("   (Password will be prompted securely)\n")
    
    # Load previously processed emails
    processed_ids = load_processed_emails()
    print(f"📋 Found {len(processed_ids)} previously processed emails\n")
    
    # Connect to Outlook
    mail = get_imap_connection(email_address, password)
    if not mail:
        return 0
    
    # Select News folder
    select_news_folder(mail, folder_name)
    
    # Fetch emails (excluding already-processed ones)
    emails, processed_ids = fetch_tldr_emails(
        mail, 
        limit=email_limit, 
        sender_filter="",
        processed_ids=processed_ids
    )
    mail.close()
    mail.logout()
    
    # Use helper function to ingest emails into ChromaDB
    return _ingest_emails_to_chroma(
        emails,
        collection_name,
        chunk_size,
        chunk_overlap,
        processed_ids,
    )


if __name__ == "__main__":
    import sys
    
    # Check for dry-run flag
    dry_run = "--dry-run" in sys.argv or "-d" in sys.argv
    
    # Prompt for email and password (secure input)
    email_address = os.getenv("OUTLOOK_EMAIL") if not dry_run else "demo@outlook.com"
    
    if not email_address and not dry_run:
        email_address = input("📧 Enter your Outlook email address: ").strip()
    
    if dry_run:
        print("\n🧪 DRY-RUN MODE activated")
        print("   This will test the ingestion pipeline with sample data\n")
        password = ""  # Not needed for dry-run
    else:
        password = getpass.getpass("🔑 Enter your Outlook password or app-specific password: ")
        
        if not email_address or not password:
            print("✗ Email and password are required")
            sys.exit(1)
    
    ingest_outlook_news(
        email_address=email_address,
        password=password,
        folder_name="News",
        email_limit=20,  # Fetch more emails to handle incremental updates
        chunk_size=500,
        chunk_overlap=50,
        dry_run=dry_run,
    )
