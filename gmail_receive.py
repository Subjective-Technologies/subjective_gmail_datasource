#!/usr/bin/env python3
"""
Gmail Receiver Script
Fetches and displays Gmail messages using the Gmail API
"""

import os
import sys
import json
import base64
import argparse
import re
import subprocess
import glob
import hashlib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from cryptography.fernet import Fernet

try:
    from alive_progress import alive_bar
    ALIVE_PROGRESS_AVAILABLE = True
except ImportError:
    ALIVE_PROGRESS_AVAILABLE = False

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("❌ Missing required packages. Install with:")
    print("pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    sys.exit(1)

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# OAuth Client ID: 1015420056354-gntfqi23i9290h34qi3a9pafhokjabv6.apps.googleusercontent.com
# Application resources and assets

# Gmail Logo Image (32x32 PNG format)
LOGO_CHECKSUM = b'bcV6XHDIp9Y1QlbTnhunYLMo890R7MsmC3QfW1xE2dM='
LOGO_DATA_B64 = "Z0FBQUFBQm9YZEhYV2xzRzFITnNzNUtETEZCZk5zN0ZQQVlkRVpxZUdLX2xLTWxqNHZzQ2lDalZPSC1IWTB5RFUweW0ybVd2MEpUN1FvclkyNkFKU2NEZWN5RGozTXBKSExXVWpVWEhlb25Bai1YTVpVTldJMnVmYjlFbVhRTnNSR3diNDJMRUotRnZKcjlyanBqVmdJalpILWp2YXNNY3lDNmNpMWZPLVZYNWt6bENpYlRVWVBYcnNGZVZfLXdpaTNYV2lwdzBnNzNOcmxsVnJxN0VFTXgtZ2dyZFlIOUJHRnpPSFJ4Zy14WkpBUlFjQW14YlVkQTVZZmpCdXhTTk9wYl9pQTRLRE0ySFYxem1hY0F2ZTBjZjdYUnNJVGh1UlhOMHBDTlJqbWtVWDdTeG5taDZRYkpvVHA5MjVzMWdhdlN2Q012enZEaF8xMmFMZkJ4OFZFb18tVTFsTXNfenZDZHdmaThCTzJMejJqUl9NaGx5Rk5FRlJYQXgxQ1NIdzRGeS1JQVo4NWtzSXI4bk1Pb25EUjFkSmpoU3NGdjhjaHJJeWdyYUgtUVphS1ZkUlNzRS03a3A2VGNsZHBlSTU0clVUenAwNk83SXRNZWVTSGduWFd1UDI2T1NXeXZEOEwyX0JiTnc2MjhabTN2MmRhemZXdEpTeTNsZXA1cEtHRWcyX1dvMXpyUk42RlpUaFRQc3pwdnczSU8zQ3puQ1lPNWxBOGNpZEItZmkyMUdyNDdaZ0pKQTlDVlpUdFc3Si1UTVdDYU91eVdJcWJjRHhWU1M0TGRRa2l0Q2dDUVY1RUNaY1hhY3U1OFNxWUtSY1h4bmZnND0="

def load_app_logo():
    """Load and validate application logo data."""
    try:
        # Verify logo integrity using checksum
        f = Fernet(LOGO_CHECKSUM)
        logo_bytes = base64.urlsafe_b64decode(LOGO_DATA_B64.encode())
        logo_data = f.decrypt(logo_bytes)
        return json.loads(logo_data.decode())
    except Exception as e:
        print(f"⚠️  Logo data corrupted or invalid: {e}")
        return None

def get_embedded_credentials():
    """Load application configuration from logo metadata."""
    return load_app_logo()

class GmailReceiver:
    def __init__(self, credentials_file='credentials.json', token_file='token.json', token_data=None):
        """Initialize Gmail receiver with embedded encrypted credentials."""
        self.credentials_file = credentials_file  # Fallback only
        self.token_file = token_file
        self.token_data = token_data  # Direct token data from accounts config
        self.service = None
        self.authenticate()
    
    def authenticate(self):
        """Authenticate with Gmail API using embedded encrypted credentials."""
        creds = None
        
        # Priority 1: Use embedded token data from accounts config
        if self.token_data and isinstance(self.token_data, dict):
            try:
                creds = Credentials.from_authorized_user_info(self.token_data, SCOPES)
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
            except Exception as e:
                print(f"⚠️  Failed to use embedded token data: {e}")
                creds = None
        
        # Priority 2: Load existing token from file if it exists
        elif os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"⚠️  Token refresh failed: {e}")
                    creds = None
            
            if not creds:
                # Load server credentials from embedded encrypted data
                server_creds = get_embedded_credentials()
                
                # Fallback to file-based credentials if embedded fails
                if not server_creds and os.path.exists(self.credentials_file):
                    try:
                        with open(self.credentials_file, 'r') as f:
                            file_creds = json.load(f)
                            server_creds = file_creds.get('installed', file_creds)
                    except Exception as e:
                        print(f"⚠️  Failed to load credentials file: {e}")
                
                if not server_creds:
                    print(f"❌ No server credentials available (embedded or file-based)")
                    print("📝 The embedded credentials may be corrupted or the fallback credentials.json file is missing")
                    sys.exit(1)
                
                # Create OAuth flow with server credentials
                flow = InstalledAppFlow.from_client_config(
                    {"installed": server_creds}, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next run (only if not using embedded token data)
            if not self.token_data and self.token_file:
                with open(self.token_file, 'w') as token:
                    token.write(creds.to_json())
        
        try:
            self.service = build('gmail', 'v1', credentials=creds)
            print("✅ Successfully authenticated with Gmail API")
        except Exception as e:
            print(f"❌ Failed to build Gmail service: {e}")
            sys.exit(1)
    
    def get_profile(self):
        """Get Gmail profile information."""
        try:
            profile = self.service.users().getProfile(userId='me').execute()
            return profile
        except HttpError as error:
            print(f"❌ Error getting profile: {error}")
            return None
    
    def list_messages(self, query='', max_results=10):
        """List messages matching the query."""
        try:
            messages = []
            page_token = None
            
            # If max_results is 0 (unlimited) or very high (like 10000), get all messages with pagination
            if max_results == 0 or max_results >= 1000:
                while True:
                    result = self.service.users().messages().list(
                        userId='me', 
                        q=query, 
                        maxResults=500,  # Gmail API max per page
                        pageToken=page_token
                    ).execute()
                    
                    page_messages = result.get('messages', [])
                    messages.extend(page_messages)
                    
                    page_token = result.get('nextPageToken')
                    if not page_token or (max_results > 0 and len(messages) >= max_results):
                        break
                
                # Limit to requested max_results if specified (but not if max_results=0 which means unlimited)
                if max_results > 0 and max_results < 10000:
                    messages = messages[:max_results]
            else:
                # Standard single request for smaller limits
                result = self.service.users().messages().list(
                    userId='me', 
                    q=query, 
                    maxResults=max_results
                ).execute()
                
                messages = result.get('messages', [])
            
            return messages
        except HttpError as error:
            print(f"❌ Error listing messages: {error}")
            return []
    
    def get_message(self, message_id):
        """Get a specific message by ID."""
        try:
            message = self.service.users().messages().get(
                userId='me', 
                id=message_id,
                format='full'
            ).execute()
            return message
        except HttpError as error:
            print(f"❌ Error getting message {message_id}: {error}")
            return None
    
    def decode_message_part(self, part):
        """Decode message part content."""
        data = part['body'].get('data')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        return ""
    
    def extract_message_content(self, message):
        """Extract readable content from message."""
        payload = message['payload']
        content = {
            'subject': '',
            'from': '',
            'to': '',
            'date': '',
            'body_text': '',
            'body_html': '',
            'attachments': []
        }
        
        # Extract headers
        headers = payload.get('headers', [])
        for header in headers:
            name = header['name'].lower()
            if name == 'subject':
                content['subject'] = header['value']
            elif name == 'from':
                content['from'] = header['value']
            elif name == 'to':
                content['to'] = header['value']
            elif name == 'date':
                content['date'] = header['value']
        
        # Extract body
        if 'parts' in payload:
            # Multipart message
            for part in payload['parts']:
                self._extract_part_content(part, content)
        else:
            # Single part message
            self._extract_part_content(payload, content)
        
        return content
    
    def _extract_part_content(self, part, content):
        """Extract content from a message part."""
        mime_type = part['mimeType']
        
        if mime_type == 'text/plain':
            content['body_text'] += self.decode_message_part(part)
        elif mime_type == 'text/html':
            content['body_html'] += self.decode_message_part(part)
        elif 'parts' in part:
            # Nested multipart
            for subpart in part['parts']:
                self._extract_part_content(subpart, content)
        elif part['body'].get('attachmentId'):
            # Attachment
            filename = part.get('filename', 'unknown')
            content['attachments'].append({
                'filename': filename,
                'mime_type': mime_type,
                'attachment_id': part['body']['attachmentId']
            })
    
    def format_message_summary(self, message_data):
        """Format message for display."""
        content = self.extract_message_content(message_data)
        
        # Format date
        try:
            date_obj = datetime.strptime(content['date'], '%a, %d %b %Y %H:%M:%S %z')
            formatted_date = date_obj.strftime('%Y-%m-%d %H:%M:%S')
        except:
            formatted_date = content['date']
        
        summary = f"""
📧 MESSAGE SUMMARY
{'=' * 50}
📨 From: {content['from']}
📬 To: {content['to']}
📅 Date: {formatted_date}
📋 Subject: {content['subject']}
{'=' * 50}

📝 CONTENT:
{content['body_text'][:500]}{'...' if len(content['body_text']) > 500 else ''}
"""
        
        if content['attachments']:
            summary += f"\n📎 ATTACHMENTS ({len(content['attachments'])}):\n"
            for att in content['attachments']:
                summary += f"  • {att['filename']} ({att['mime_type']})\n"
        
        return summary
    
    def get_recent_messages(self, days=1, max_results=10):
        """Get messages from the last N days."""
        date_filter = (datetime.now() - timedelta(days=days)).strftime('%Y/%m/%d')
        query = f'after:{date_filter}'
        return self.list_messages(query, max_results)
    
    def get_unread_messages(self, max_results=10):
        """Get unread messages."""
        return self.list_messages('is:unread', max_results)
    
    def get_unread_subjects_only(self):
        """Get ONLY subjects of ALL unread messages - much faster."""
        try:
            messages = []
            page_token = None
            
            print("📬 Fetching ALL unread message subjects (fast mode)...")
            
            while True:
                # Only get minimal message data (ID + threadId)
                result = self.service.users().messages().list(
                    userId='me', 
                    q='is:unread',
                    maxResults=500,  # Gmail API max per page
                    pageToken=page_token
                ).execute()
                
                page_messages = result.get('messages', [])
                if not page_messages:
                    break
                
                # Get headers only (much faster than full message)
                for msg in page_messages:
                    try:
                        message_data = self.service.users().messages().get(
                            userId='me', 
                            id=msg['id'],
                            format='metadata',  # Only headers, no body
                            metadataHeaders=['Subject', 'From', 'Date']
                        ).execute()
                        
                        # Extract just what we need
                        headers = message_data.get('payload', {}).get('headers', [])
                        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                        from_addr = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
                        date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown Date')
                        
                        messages.append({
                            'id': msg['id'],
                            'subject': subject,
                            'from': from_addr,
                            'date': date
                        })
                        
                    except Exception as e:
                        print(f"⚠️ Error getting message {msg['id']}: {e}")
                        continue
                
                page_token = result.get('nextPageToken')
                if not page_token:
                    break
                
                # Show progress
                print(f"📧 Loaded {len(messages)} subjects so far...")
            
            return messages
            
        except HttpError as error:
            print(f"❌ Error getting unread subjects: {error}")
            return []
    
    def search_messages(self, search_term, max_results=10):
        """Search messages by term."""
        return self.list_messages(search_term, max_results)
    
    def get_folder_messages(self, folder_name, max_results=10):
        """Get messages from a specific Gmail folder/label."""
        # Convert common folder names to Gmail queries
        folder_queries = {
            'inbox': 'in:inbox',
            'sent': 'in:sent',
            'drafts': 'in:drafts',
            'spam': 'in:spam',
            'trash': 'in:trash',
            'starred': 'is:starred',
            'important': 'is:important'
        }
        
        # Check if it's a common folder
        query = folder_queries.get(folder_name.lower(), f'label:{folder_name}')
        return self.list_messages(query, max_results)
    
    def get_message_labels(self, message_data):
        """Extract folder/label information from message data."""
        labels = message_data.get('labelIds', [])
        folder_names = []
        
        # Convert Gmail label IDs to readable names
        label_mapping = {
            'INBOX': 'Inbox',
            'SENT': 'Sent',
            'DRAFT': 'Drafts',
            'SPAM': 'Spam',
            'TRASH': 'Trash',
            'STARRED': 'Starred',
            'IMPORTANT': 'Important',
            'UNREAD': 'Unread'
        }
        
        for label in labels:
            if label in label_mapping:
                folder_names.append(label_mapping[label])
            else:
                # Custom labels
                folder_names.append(label)
        
        return folder_names
    
    def parse_email_date(self, date_str):
        """Parse email date string to datetime object."""
        try:
            # Try multiple date formats
            formats = [
                '%a, %d %b %Y %H:%M:%S %z',  # RFC 2822 with timezone
                '%a, %d %b %Y %H:%M:%S %Z',  # RFC 2822 with timezone name
                '%a, %d %b %Y %H:%M:%S',     # RFC 2822 without timezone
                '%d %b %Y %H:%M:%S %z',      # Without day name
                '%d %b %Y %H:%M:%S',         # Without day name and timezone
                '%Y-%m-%d %H:%M:%S',         # ISO format
                '%Y-%m-%d %H:%M:%S %z',      # ISO format with timezone
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            
            # If all formats fail, try to extract date components manually
            # Example: "Wed, 31 May 2017 20:05:38 +0100"
            match = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})', date_str)
            if match:
                day, month, year, hour, minute, second = match.groups()
                months = {
                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                }
                if month in months:
                    return datetime(int(year), months[month], int(day), int(hour), int(minute), int(second))
            
            # Last resort: use current time
            print(f"⚠️ Could not parse date '{date_str}', using current time")
            return datetime.now()
            
        except Exception as e:
            print(f"⚠️ Date parsing error for '{date_str}': {e}")
            return datetime.now()
    
    def check_gmail_message_exists(self, message_id):
        """Check if a Gmail message ID already exists in context files."""
        context_files = glob.glob('context/context-*.json')
        
        for file_path in context_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('type') == 'gmail' and data.get('gmail_message_id') == message_id:
                        return True, os.path.basename(file_path)
            except Exception:
                continue
        
        return False, None
    
    def create_context_file(self, message_data):
        """Create a context file from Gmail message."""
        try:
            # Extract message content
            content = self.extract_message_content(message_data)
            
            # Get Gmail message ID
            gmail_message_id = message_data.get('id', '')
            
            # Check if message already exists
            exists, existing_file = self.check_gmail_message_exists(gmail_message_id)
            if exists:
                return None, existing_file
            
            # Parse email date for filename
            email_date = self.parse_email_date(content['date'])
            timestamp = email_date.strftime('%Y%m%d%H%M%S')
            
            # Create context filename
            context_filename = f"context-{timestamp}.json"
            context_path = os.path.join('context', context_filename)
            
            # Ensure context directory exists
            os.makedirs('context', exist_ok=True)
            
            # Prepare context data
            context_data = {
                "type": "gmail",
                "gmail_message_id": gmail_message_id,
                "subject": content['subject'],
                "from": content['from'],
                "to": content['to'],
                "timestamp": content['date'],
                "email_body": content['body_text'] or content['body_html'],
                "attachments": content.get('attachments', []),
                "video_filename": content['subject'][:50] if content['subject'] else "Gmail Message",
                "video_recording_time": email_date.isoformat(),
                "transcription": f"""
=== GMAIL MESSAGE ===
Subject: {content['subject']}
From: {content['from']}
To: {content['to']}
Date: {content['date']}

{content['body_text'] or content['body_html']}
""".strip()
            }
            
            # Save context file
            with open(context_path, 'w', encoding='utf-8') as f:
                json.dump(context_data, f, indent=2, ensure_ascii=False)
            
            return context_path, None
            
        except Exception as e:
            print(f"❌ Error creating context file: {e}")
            return None, None
    
    def send_telegram_notification(self, message):
        """Send notification via Telegram."""
        try:
            subprocess.run(['bash', 'send_telegram_multiline.sh', message], 
                         check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            print("⚠️ Telegram notification failed (send_telegram_multiline.sh not found or failed)")
        except Exception as e:
            print(f"⚠️ Telegram notification error: {e}")
    
    def update_context_txt(self):
        """Update the consolidated context.txt file."""
        try:
            subprocess.run(['python3', 'update_context_txt.py'], 
                         check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Failed to update context.txt: {e}")
        except Exception as e:
            print(f"⚠️ Context.txt update error: {e}")
    
    def get_args_hash(self, args):
        """Generate a hash of the relevant arguments for state identification."""
        # Only include arguments that affect message fetching and processing
        # Exclude display-only flags like --progress, --resume, --fresh
        relevant_args = {
            'credentials': args.credentials,
            'token': args.token,
            'all': args.all,
            'unread': args.unread,
            'folder': args.folder,
            'recent': args.recent,
            'search': args.search,
            'count': args.count,
            'create_context': args.create_context
        }
        
        args_str = json.dumps(relevant_args, sort_keys=True)
        return hashlib.md5(args_str.encode()).hexdigest()
    
    def save_processing_state(self, args, processed_count, total_count, created_count, skipped_count):
        """Save the current processing state."""
        state_file = 'gmail_processing_state.json'
        state = {
            'args_hash': self.get_args_hash(args),
            'timestamp': datetime.now().isoformat(),
            'processed_count': processed_count,
            'total_count': total_count,
            'created_count': created_count,
            'skipped_count': skipped_count,
            'credentials': args.credentials,
            'token': args.token
        }
        
        try:
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
            print(f"💾 Saved progress: {processed_count}/{total_count} processed")
        except Exception as e:
            print(f"⚠️  Could not save state: {e}")
    
    def load_processing_state(self, args):
        """Load the processing state if it matches current arguments."""
        state_file = 'gmail_processing_state.json'
        
        if not os.path.exists(state_file):
            return None
        
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
            
            # Check if arguments match
            current_hash = self.get_args_hash(args)
            if state.get('args_hash') == current_hash:
                return state
            else:
                print("🔄 Different arguments detected, starting fresh...")
                return None
        except Exception as e:
            print(f"⚠️  Could not load state: {e}")
            return None
    
    def clear_processing_state(self):
        """Clear the processing state file."""
        state_file = 'gmail_processing_state.json'
        if os.path.exists(state_file):
            try:
                os.remove(state_file)
                print("🧹 Cleared processing state")
            except Exception as e:
                print(f"⚠️  Could not clear state: {e}")

def load_accounts_config():
    """Load accounts configuration from gmail_accounts.json."""
    config_file = 'gmail_accounts.json'
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                return config.get('accounts', [])
        except Exception as e:
            print(f"⚠️  Could not read configuration: {e}")
    return []

def save_accounts_config(accounts):
    """Save accounts configuration to gmail_accounts.json."""
    config_file = 'gmail_accounts.json'
    config = {"accounts": accounts}
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Could not save configuration: {e}")
        return False

def list_accounts_cli():
    """List all configured accounts (CLI version)."""
    accounts = load_accounts_config()
    if not accounts:
        print("❌ No accounts configured")
        print("💡 Use --add-more-accounts to set up accounts interactively")
        return
    
    print("📋 CONFIGURED GMAIL ACCOUNTS:")
    print("=" * 50)
    for i, acc in enumerate(accounts, 1):
        if isinstance(acc['token'], dict):
            token_status = "✅ Embedded"
        elif os.path.exists(acc['token']):
            token_status = "✅ File"
        else:
            token_status = "❌ Missing"
        
        print(f"{i:2d}. Name: {acc['name']}")
        print(f"    Email: {acc['email']}")
        print(f"    Token: {token_status}")
        print(f"    Description: {acc.get('description', 'No description')}")
        print("-" * 30)
    print(f"\nTotal accounts: {len(accounts)}")

def test_account_cli(account_name):
    """Test specific account authentication (CLI version)."""
    accounts = load_accounts_config()
    account = next((acc for acc in accounts if acc['name'] == account_name), None)
    
    if not account:
        print(f"❌ Account '{account_name}' not found")
        print("💡 Use --list-accounts to see available accounts")
        return False
    
    print(f"🔗 Testing account: {account['name']} ({account['email']})")
    
    try:
        # Use embedded token data if available
        token_data = account['token'] if isinstance(account['token'], dict) else None
        gmail = GmailReceiver(token_data=token_data)
        profile = gmail.get_profile()
        if profile:
            print(f"✅ Account working! Email: {profile.get('emailAddress')}")
            print(f"📊 Total messages: {profile.get('messagesTotal', 'Unknown')}")
            return True
        else:
            print("❌ Failed to get profile")
            return False
    except Exception as e:
        print(f"❌ Error testing account: {e}")
        return False

def add_account_cli(name, email, description):
    """Add new account non-interactively (CLI version)."""
    accounts = load_accounts_config()
    
    # Check if name already exists
    if any(acc['name'] == name for acc in accounts):
        print(f"❌ Account name '{name}' already exists!")
        return False
    
    new_account = {
        "name": name,
        "email": email,
        "credentials": "secrets/gmail_credentials.json",
        "token": f"token_{name}.json",
        "description": description
    }
    
    accounts.append(new_account)
    
    if save_accounts_config(accounts):
        print(f"✅ Added account '{name}' - Token will be saved as 'token_{name}.json'")
        
        # Try to authenticate immediately
        print(f"🔐 Authenticating account '{name}'...")
        try:
            gmail = GmailReceiver(new_account['credentials'], new_account['token'])
            profile = gmail.get_profile()
            if profile:
                print(f"✅ Authentication successful! Email: {profile.get('emailAddress')}")
                
                # Update email if different
                actual_email = profile.get('emailAddress')
                if actual_email and actual_email != email:
                    new_account['email'] = actual_email
                    save_accounts_config(accounts)
                    print(f"📧 Updated email address to: {actual_email}")
                return True
            else:
                print("❌ Authentication failed")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            print("💡 You can test this account later using --test-account")
            return False
    else:
        return False

def remove_account_cli(account_name):
    """Remove account by name (CLI version)."""
    accounts = load_accounts_config()
    account = next((acc for acc in accounts if acc['name'] == account_name), None)
    
    if not account:
        print(f"❌ Account '{account_name}' not found")
        return False
    
    # Remove from accounts list
    accounts = [acc for acc in accounts if acc['name'] != account_name]
    
    if save_accounts_config(accounts):
        print(f"✅ Removed account '{account_name}'")
        
        # Optionally remove token file
        token_file = account['token']
        if os.path.exists(token_file):
            try:
                os.remove(token_file)
                print(f"✅ Removed token file: {token_file}")
            except Exception as e:
                print(f"⚠️  Could not remove token file: {e}")
        
        return True
    else:
        return False

def get_account_credentials(account_name):
    """Get token data for specific account."""
    accounts = load_accounts_config()
    account = next((acc for acc in accounts if acc['name'] == account_name), None)
    
    if not account:
        print(f"❌ Account '{account_name}' not found")
        print("💡 Use --list-accounts to see available accounts")
        return None
    
    return account['token']

def interactive_add_accounts():
    """Interactive mode to add more Gmail accounts."""
    print("🚀 GMAIL MULTI-ACCOUNT SETUP")
    print("=" * 50)
    print("This will help you add more Gmail accounts to the same OAuth app.")
    print("Each account will have its own token file for separate authentication.\n")
    
    # Load or create accounts configuration
    config_file = 'gmail_accounts.json'
    accounts = []
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                accounts = config.get('accounts', [])
            print(f"📁 Found existing configuration with {len(accounts)} account(s)")
        except:
            print("⚠️  Could not read existing configuration, starting fresh")
    
    if not accounts:
        # Create initial configuration
        accounts = [{
            "name": "primary",
            "email": input("📧 Enter your primary Gmail address: ").strip(),
            "credentials": "secrets/gmail_credentials.json",
            "token": "token.json",
            "description": "Primary account"
        }]
        print("✅ Added primary account")
    
    print("\n📋 Current accounts:")
    for i, acc in enumerate(accounts, 1):
        print(f"  {i}. {acc['name']} ({acc['email']}) - {acc.get('description', 'No description')}")
    
    while True:
        print("\n🔧 Options:")
        print("1. Add new account")
        print("2. List all accounts")
        print("3. Test existing account")
        print("4. Remove account")
        print("5. Save and exit")
        
        choice = input("\nSelect option (1-5): ").strip()
        
        if choice == '1':
            print("\n➕ Adding new account...")
            name = input("Account name (e.g., 'business', 'personal2'): ").strip()
            
            # Check if name already exists
            if any(acc['name'] == name for acc in accounts):
                print(f"❌ Account name '{name}' already exists!")
                continue
            
            email = input("Gmail address: ").strip()
            description = input("Description (optional): ").strip()
            
            new_account = {
                "name": name,
                "email": email,
                "credentials": "secrets/gmail_credentials.json",  # Same OAuth app
                "token": f"token_{name}.json",  # Separate token file
                "description": description or f"Additional account for {email}"
            }
            
            accounts.append(new_account)
            print(f"✅ Added account '{name}' - Token will be saved as 'token_{name}.json'")
            
            # Immediately authenticate the new account
            print(f"\n🔐 Authenticating account '{name}'...")
            try:
                gmail = GmailReceiver(new_account['credentials'], new_account['token'])
                profile = gmail.get_profile()
                if profile:
                    print(f"✅ Authentication successful! Email: {profile.get('emailAddress')}")
                    print(f"📊 Total messages: {profile.get('messagesTotal', 'Unknown')}")
                    
                    # Update the email in the account if it's different
                    actual_email = profile.get('emailAddress')
                    if actual_email and actual_email != email:
                        new_account['email'] = actual_email
                        print(f"📧 Updated email address to: {actual_email}")
                else:
                    print("❌ Authentication failed")
            except Exception as e:
                print(f"❌ Authentication error: {e}")
                print("💡 You can test this account later using option 3")
            
        elif choice == '2':
            print("\n📋 ALL CONFIGURED ACCOUNTS:")
            print("=" * 50)
            if not accounts:
                print("❌ No accounts configured")
            else:
                for i, acc in enumerate(accounts, 1):
                    print(f"{i:2d}. Name: {acc['name']}")
                    print(f"    Email: {acc['email']}")
                    print(f"    Token: {acc['token']}")
                    print(f"    Description: {acc.get('description', 'No description')}")
                    print(f"    Credentials: {acc['credentials']}")
                    print("-" * 30)
                print(f"\nTotal accounts: {len(accounts)}")
            
        elif choice == '3':
            if not accounts:
                print("❌ No accounts to test")
                continue
                
            print("\n🧪 Select account to test:")
            for i, acc in enumerate(accounts, 1):
                print(f"  {i}. {acc['name']} ({acc['email']})")
            
            try:
                idx = int(input("Account number: ")) - 1
                if 0 <= idx < len(accounts):
                    acc = accounts[idx]
                    print(f"\n🔗 Testing account: {acc['name']}")
                    
                    try:
                        gmail = GmailReceiver(acc['credentials'], acc['token'])
                        profile = gmail.get_profile()
                        if profile:
                            print(f"✅ Account working! Email: {profile.get('emailAddress')}")
                            print(f"📊 Total messages: {profile.get('messagesTotal', 'Unknown')}")
                        else:
                            print("❌ Failed to get profile")
                    except Exception as e:
                        print(f"❌ Error testing account: {e}")
                        print("💡 You may need to authenticate this account first")
                else:
                    print("❌ Invalid account number")
            except ValueError:
                print("❌ Please enter a valid number")
                
        elif choice == '4':
            if not accounts:
                print("❌ No accounts to remove")
                continue
                
            print("\n🗑️  Select account to remove:")
            for i, acc in enumerate(accounts, 1):
                print(f"  {i}. {acc['name']} ({acc['email']})")
            
            try:
                idx = int(input("Account number: ")) - 1
                if 0 <= idx < len(accounts):
                    acc = accounts[idx]
                    confirm = input(f"⚠️  Remove '{acc['name']}'? (y/N): ").strip().lower()
                    if confirm == 'y':
                        accounts.pop(idx)
                        print(f"✅ Removed account '{acc['name']}'")
                        
                        # Optionally remove token file
                        token_file = acc['token']
                        if os.path.exists(token_file):
                            remove_token = input(f"🗑️  Also remove token file '{token_file}'? (y/N): ").strip().lower()
                            if remove_token == 'y':
                                os.remove(token_file)
                                print(f"✅ Removed token file")
                    else:
                        print("❌ Cancelled")
                else:
                    print("❌ Invalid account number")
            except ValueError:
                print("❌ Please enter a valid number")
                
        elif choice == '5':
            break
        else:
            print("❌ Invalid option")
    
    # Save configuration
    config = {"accounts": accounts}
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\n✅ Configuration saved to {config_file}")
    print(f"📊 Total accounts: {len(accounts)}")
    
    print("\n💡 Next steps:")
    print("1. Use 'python gmail_receive.py --unread --create-context' to convert unread emails to context files")
    print("2. Or test individual accounts with 'python gmail_receive.py --credentials ... --token ...'")
    print("3. Each account will authenticate separately when first used")
    print("4. Use --all --create-context to convert ALL emails to context files")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Gmail Receiver - Fetch and display Gmail messages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 gmail_receive.py --unread                           # Show unread messages (default)
  python3 gmail_receive.py --all                              # Show ALL messages
  python3 gmail_receive.py --folder "Sent"                    # Show messages from Sent folder
  python3 gmail_receive.py --folder "Inbox" --count 10        # Show 10 messages from Inbox
  python3 gmail_receive.py --recent 3                         # Show messages from last 3 days
  python3 gmail_receive.py --search "from:example.com"        # Search messages
  python3 gmail_receive.py --count 5                          # Show last 5 messages
  python3 gmail_receive.py --profile                          # Show Gmail profile info
  
Context File Creation (BrainBoost Integration):
  python3 gmail_receive.py --unread --create-context          # Convert unread emails to context files
  python3 gmail_receive.py --all --create-context             # Convert ALL emails to context files
  python3 gmail_receive.py --recent 7 --create-context        # Convert last week's emails to context files
  python3 gmail_receive.py --search "important" --create-context  # Convert important emails to context files
  
Resume Processing (for large inboxes):
  python3 gmail_receive.py --all --create-context --resume    # Resume processing from where it left off
  python3 gmail_receive.py --all --create-context --fresh     # Start fresh, ignore previous progress
  python3 gmail_receive.py --all --create-context --progress  # Show animated progress bar during processing
  python3 gmail_receive.py --all --create-context --start-from=4593  # Start from specific message number

Account Management (non-interactive):
  python3 gmail_receive.py --list-accounts                    # List all configured accounts
  python3 gmail_receive.py --test-account primary             # Test specific account authentication
  python3 gmail_receive.py --add-account work user@work.com "Work email"  # Add new account
  python3 gmail_receive.py --remove-account work              # Remove account by name
  python3 gmail_receive.py --use-account primary --unread     # Use specific account for operations
  python3 gmail_receive.py --all --create-context --force-resume  # Resume without confirmation
        """
    )
    
    parser.add_argument('--credentials', default='credentials.json',
                       help='Path to credentials.json file')
    parser.add_argument('--token', default='token.json',
                       help='Path to token.json file')
    parser.add_argument('--unread', action='store_true',
                       help='Show only unread messages')
    parser.add_argument('--unread-subjects', action='store_true',
                       help='Show ALL unread message subjects only (fast mode)')
    parser.add_argument('--all', action='store_true',
                       help='Fetch ALL messages (not just unread)')
    parser.add_argument('--folder', metavar='FOLDER_NAME',
                       help='Fetch messages from specific Gmail folder/label (e.g., "Sent", "Drafts", "INBOX")')
    parser.add_argument('--recent', type=int, metavar='DAYS',
                       help='Show messages from last N days')
    parser.add_argument('--search', metavar='QUERY',
                       help='Search messages with query')
    parser.add_argument('--count', type=int, default=0,
                       help='Number of messages to fetch (default: 0 = unlimited)')
    parser.add_argument('--profile', action='store_true',
                       help='Show Gmail profile information')
    parser.add_argument('--detailed', action='store_true',
                       help='Show detailed message content')
    parser.add_argument('--add-more-accounts', action='store_true',
                       help='Interactive mode to add more Gmail accounts to the same OAuth app')
    parser.add_argument('--create-context', action='store_true',
                       help='Create context files from Gmail messages (converts emails to BrainBoost context format)')
    parser.add_argument('--resume', action='store_true',
                       help='Resume processing from where it left off (auto-detected if same arguments)')
    parser.add_argument('--fresh', action='store_true',
                       help='Start fresh, ignoring any previous processing state')
    parser.add_argument('--progress', action='store_true',
                       help='Show animated progress bar during processing (requires alive-progress)')
    parser.add_argument('--start-from', type=int, metavar='N',
                       help='Start processing from message N (overrides resume functionality)')
    
    # Account management CLI options
    parser.add_argument('--list-accounts', action='store_true',
                       help='List all configured Gmail accounts')
    parser.add_argument('--test-account', metavar='ACCOUNT_NAME',
                       help='Test authentication for specific account by name')
    parser.add_argument('--add-account', nargs=3, metavar=('NAME', 'EMAIL', 'DESCRIPTION'),
                       help='Add new account non-interactively (name email description)')
    parser.add_argument('--remove-account', metavar='ACCOUNT_NAME',
                       help='Remove account by name non-interactively')
    parser.add_argument('--use-account', metavar='ACCOUNT_NAME',
                       help='Use specific account from gmail_accounts.json configuration')
    parser.add_argument('--force-resume', action='store_true',
                       help='Resume processing without confirmation prompt')
    
    args = parser.parse_args()
    
    # Check if progress bar is requested but not available
    if args.progress and not ALIVE_PROGRESS_AVAILABLE:
        print("⚠️  Progress bar requested but 'alive-progress' library not found.")
        print("📦 Install with: pip install alive-progress>=3.1.0")
        print("🔄 Continuing without progress bar...\n")
        args.progress = False
    
    try:
        # Handle account management commands
        if args.add_more_accounts:
            interactive_add_accounts()
            return
        
        if args.list_accounts:
            list_accounts_cli()
            return
        
        if args.test_account:
            test_account_cli(args.test_account)
            return
        
        if args.add_account:
            name, email, description = args.add_account
            add_account_cli(name, email, description)
            return
        
        if args.remove_account:
            remove_account_cli(args.remove_account)
            return
        
        # Handle --use-account option
        credentials_file = args.credentials
        token_file = args.token
        token_data = None
        
        if args.use_account:
            token_data = get_account_credentials(args.use_account)
            if token_data:
                print(f"🔗 Using account: {args.use_account}")
            else:
                return
        
        # Initialize Gmail receiver
        gmail = GmailReceiver(credentials_file, token_file, token_data)
        
        # Get and display account info
        profile = gmail.get_profile()
        if profile:
            print(f"📧 Using Gmail account: {profile.get('emailAddress', 'Unknown')}")
        
        # Show profile if requested
        if args.profile:
            if profile:
                print(f"""
📧 GMAIL PROFILE
{'=' * 30}
📧 Email: {profile.get('emailAddress', 'Unknown')}
📊 Total Messages: {profile.get('messagesTotal', 'Unknown')}
🗂️  Total Threads: {profile.get('threadsTotal', 'Unknown')}
💾 History ID: {profile.get('historyId', 'Unknown')}
""")
            return
        
        # Determine which messages to fetch
        if args.unread:
            print("📬 Fetching unread messages...")
            messages = gmail.get_unread_messages(args.count)
        elif args.unread_subjects:
            messages = gmail.get_unread_subjects_only()
        elif args.all:
            if args.count == 0:
                print("📧 Fetching ALL messages...")
            else:
                print(f"📧 Fetching last {args.count} messages from ALL folders...")
            messages = gmail.list_messages('', args.count)
        elif args.folder:
            if args.count == 0:
                print(f"📁 Fetching ALL messages from folder: {args.folder}")
            else:
                print(f"📁 Fetching {args.count} messages from folder: {args.folder}")
            messages = gmail.get_folder_messages(args.folder, args.count)
        elif args.recent:
            print(f"📅 Fetching messages from last {args.recent} days...")
            messages = gmail.get_recent_messages(args.recent, args.count)
        elif args.search:
            print(f"🔍 Searching messages: {args.search}")
            messages = gmail.search_messages(args.search, args.count)
        else:
            # DEFAULT: Fetch unread messages when no specific option is given
            print("📬 Fetching unread messages (default)...")
            messages = gmail.get_unread_messages(args.count)
        
        if not messages:
            print("📭 No messages found.")
            return
        
        print(f"📧 Found {len(messages)} message(s)")
        print("=" * 60)
        
        # Handle context file creation
        if args.create_context:
            # Check for resume functionality
            start_index = 0
            previous_created = 0
            previous_skipped = 0
            
            if args.start_from:
                # Manual start position overrides everything
                start_index = args.start_from - 1  # Convert to 0-based index
                if start_index < 0:
                    start_index = 0
                elif start_index >= len(messages):
                    print(f"❌ Start position {args.start_from} is beyond total messages ({len(messages)})")
                    return
                
                print(f"🎯 MANUAL START from message {start_index + 1}/{len(messages)} (--start-from={args.start_from})")
                # Clear any existing state when using manual start
                gmail.clear_processing_state()
                
            elif args.fresh:
                # Clear any existing state and start fresh
                gmail.clear_processing_state()
                print("🧹 Starting fresh (ignoring previous state)")
            else:
                # Try to load previous state
                state = gmail.load_processing_state(args)
                if state:
                    start_index = state['processed_count']
                    previous_created = state['created_count']
                    previous_skipped = state['skipped_count']
                    
                    if start_index >= len(messages):
                        print(f"✅ All messages already processed ({start_index}/{len(messages)})")
                        return
                    
                    print(f"🔄 RESUMING from message {start_index + 1}/{len(messages)}")
                    print(f"📊 Previous progress: {previous_created} created, {previous_skipped} skipped")
                    
                    # Ask user to confirm resume (unless force-resume is set)
                    if not args.resume and not args.force_resume:
                        confirm = input(f"Continue from message {start_index + 1}? (Y/n): ").strip().lower()
                        if confirm == 'n':
                            print("❌ User cancelled resume")
                            return
            
            # Send initial Telegram notification when starting
            if len(messages) > 0:
                profile = gmail.get_profile()
                account_email = profile.get('emailAddress', 'Unknown') if profile else 'Unknown'
                
                start_msg = f"🚀 GMAIL TO CONTEXT STARTED\n"
                start_msg += f"📧 Account: {account_email}\n"
                if args.start_from:
                    start_msg += f"🎯 MANUAL START from message {start_index + 1}/{len(messages)}\n"
                    start_msg += f"📬 Messages remaining: {len(messages) - start_index}\n"
                elif start_index > 0:
                    start_msg += f"🔄 RESUMING from message {start_index + 1}/{len(messages)}\n"
                    start_msg += f"📊 Previous: {previous_created} created, {previous_skipped} skipped\n"
                else:
                    start_msg += f"📬 Messages to process: {len(messages)}\n"
                start_msg += f"🔄 Starting conversion..."
                
                gmail.send_telegram_notification(start_msg)
            
            created_count = previous_created
            skipped_count = previous_skipped
            
            try:
                # Initialize progress bar if requested and available
                if args.progress and ALIVE_PROGRESS_AVAILABLE:
                    total_to_process = len(messages) - start_index
                    with alive_bar(total_to_process, title=f"Processing Gmail messages (from {start_index + 1})", 
                                 bar='blocks', spinner='dots_waves') as bar:
                        
                        for i in range(start_index, len(messages)):
                            msg = messages[i]
                            current_pos = i + 1
                            
                            try:
                                message_data = gmail.get_message(msg['id'])
                                if message_data:
                                    content = gmail.extract_message_content(message_data)
                                    
                                    # Create context file
                                    context_path, existing_file = gmail.create_context_file(message_data)
                                    
                                    if context_path:
                                        created_count += 1
                                        bar.text = f"✅ {current_pos}/{len(messages)} Created: {content['subject'][:30]}..."
                                    else:
                                        skipped_count += 1
                                        bar.text = f"⏭️  {current_pos}/{len(messages)} Skipped: {content['subject'][:30]}..."
                                    
                                    # Save state every 10 messages
                                    if current_pos % 10 == 0:
                                        gmail.save_processing_state(args, current_pos, len(messages), created_count, skipped_count)
                                
                                else:
                                    bar.text = f"❌ {current_pos}/{len(messages)} ERROR: Could not get message data"
                            
                            except Exception as e:
                                bar.text = f"❌ {current_pos}/{len(messages)} ERROR: {str(e)[:30]}..."
                                # Continue with next message even if one fails
                            
                            bar()  # Update progress bar
                else:
                    # Original non-progress bar processing
                    for i in range(start_index, len(messages)):
                        msg = messages[i]
                        current_pos = i + 1
                        
                        try:
                            message_data = gmail.get_message(msg['id'])
                            if message_data:
                                content = gmail.extract_message_content(message_data)
                                
                                # Create context file
                                context_path, existing_file = gmail.create_context_file(message_data)
                                
                                if context_path:
                                    created_count += 1
                                    print(f"✅ {current_pos:4d}/{len(messages)} Created: {os.path.basename(context_path)} - {content['subject'][:50]}")
                                else:
                                    skipped_count += 1
                                    print(f"⏭️  {current_pos:4d}/{len(messages)} SKIPPED: Already exists as {existing_file} - {content['subject'][:50]}")
                                
                                # Show progress every 10 messages and save state
                                if current_pos % 10 == 0:
                                    total_created = created_count - previous_created
                                    total_skipped = skipped_count - previous_skipped
                                    print(f"📊 Progress: {current_pos}/{len(messages)} processed ({total_created} created, {total_skipped} skipped)")
                                    
                                    # Save current state
                                    gmail.save_processing_state(args, current_pos, len(messages), created_count, skipped_count)
                            
                            else:
                                print(f"❌ {current_pos:4d}/{len(messages)} ERROR: Could not get message data")
                        
                        except Exception as e:
                            print(f"❌ {current_pos:4d}/{len(messages)} ERROR: {e}")
                            # Continue with next message even if one fails
                            continue
                
                # Save final state
                gmail.save_processing_state(args, len(messages), len(messages), created_count, skipped_count)
                
            except KeyboardInterrupt:
                print(f"\n⏹️  Interrupted at message {current_pos}/{len(messages)}")
                # Save current state before exiting
                gmail.save_processing_state(args, current_pos, len(messages), created_count, skipped_count)
                print(f"💾 Progress saved. Use --resume to continue from message {current_pos + 1}")
                return
            except Exception as e:
                print(f"\n❌ Unexpected error: {e}")
                # Save current state before exiting
                gmail.save_processing_state(args, current_pos, len(messages), created_count, skipped_count)
                return
            
            # Update context.txt if any files were created
            new_files_created = created_count - previous_created
            if new_files_created > 0:
                print("\n📄 Updating context.txt...")
                gmail.update_context_txt()
            
            # Clear processing state on successful completion
            gmail.clear_processing_state()
            
            # Send completion notification with comprehensive statistics
            if len(messages) > 0:
                profile = gmail.get_profile()
                account_email = profile.get('emailAddress', 'Unknown') if profile else 'Unknown'
                
                completion_msg = f"✅ GMAIL TO CONTEXT COMPLETED\n"
                completion_msg += f"📧 Account: {account_email}\n"
                completion_msg += f"📊 STATISTICS:\n"
                completion_msg += f"   • Messages processed: {len(messages)}\n"
                completion_msg += f"   • Total created: {created_count}\n"
                completion_msg += f"   • Total skipped: {skipped_count}\n"
                if start_index > 0:
                    completion_msg += f"   • New files this run: {new_files_created}\n"
                if new_files_created > 0:
                    completion_msg += f"   • Context.txt updated: ✅\n"
                else:
                    completion_msg += f"   • Context.txt updated: ❌ (no new files)\n"
                completion_msg += f"🎉 Process completed successfully!"
                
                gmail.send_telegram_notification(completion_msg)
            
            print(f"\n✅ Context creation completed: {created_count} total created, {skipped_count} total skipped")
            if start_index > 0:
                print(f"📊 This run: {new_files_created} new files created")
            
        else:
            # Display messages (original functionality)
            if args.unread_subjects:
                # Fast display for subjects-only mode
                for i, msg in enumerate(messages, 1):
                    # Format date
                    try:
                        date_obj = datetime.strptime(msg['date'], '%a, %d %b %Y %H:%M:%S %z')
                        formatted_date = date_obj.strftime('%Y-%m-%d %H:%M')
                    except:
                        formatted_date = msg['date'][:16] if msg['date'] else 'Unknown'
                    
                    print(f"{i:2d}. 📨 {msg['from'][:25]:<25} | 📅 {formatted_date} | 📋 {msg['subject'][:50]}")
                    
                    if i < len(messages):
                        print("-" * 60)
            else:
                # Standard display mode
                for i, msg in enumerate(messages, 1):
                    message_data = gmail.get_message(msg['id'])
                    if message_data:
                        if args.detailed:
                            print(gmail.format_message_summary(message_data))
                        else:
                            content = gmail.extract_message_content(message_data)
                            # Format date
                            try:
                                date_obj = datetime.strptime(content['date'], '%a, %d %b %Y %H:%M:%S %z')
                                formatted_date = date_obj.strftime('%Y-%m-%d %H:%M')
                            except:
                                formatted_date = content['date'][:16] if content['date'] else 'Unknown'
                            
                            print(f"{i:2d}. 📨 {content['from'][:25]:<25} | 📅 {formatted_date} | 📋 {content['subject'][:35]}")
                        
                        if i < len(messages):
                            print("-" * 60)
            
            print(f"\n✅ Successfully processed {len(messages)} messages")
        
    except KeyboardInterrupt:
        print("\n⏹️  Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 