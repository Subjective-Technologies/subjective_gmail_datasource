#!/usr/bin/env python3
"""
Subjective Gmail Data Source
A BrainBoost data source plugin for processing Gmail messages
"""

import os
import sys
import json
from datetime import datetime
from gmail_receive import GmailReceiver

try:
    from subjective_abstract_data_source_package import SubjectiveDataSource
except ImportError as e:
    print(f"❌ Missing subjective_abstract_data_source_package: {e}")
    sys.exit(1)

# Fallback logger implementation
try:
    from brainboost_data_source_logger_package.BBLogger import BBLogger
except ImportError:
    class BBLogger:
        @staticmethod
        def log(message, level='info'):
            print(f"[{level.upper()}] {message}")

# Optional config (not used in current implementation)
try:
    from brainboost_configuration_package.BBConfig import BBConfig
except ImportError:
    BBConfig = None


class SubjectiveGmailDataSource(SubjectiveDataSource):
    def __init__(self, name=None, session=None, dependency_data_sources=[], subscribers=None, params=None):
        # Passing parameters to the base class
        super().__init__(name=name, session=session, dependency_data_sources=dependency_data_sources, subscribers=subscribers, params=params)
        self.params = params or {}
        self.gmail_receiver = None
        
        # Initialize Gmail receiver if credentials are provided
        self._initialize_gmail_receiver()
    
    def _initialize_gmail_receiver(self):
        """Initialize the Gmail receiver with provided credentials."""
        try:
            credentials_file = self.params.get('credentials_file', 'secrets/gmail_credentials.json')
            token_file = self.params.get('token_file', 'token.json')
            
            BBLogger.log(f"Initializing Gmail receiver with credentials: {credentials_file}, token: {token_file}")
            self.gmail_receiver = GmailReceiver(credentials_file, token_file)
            BBLogger.log("Gmail receiver initialized successfully")
            
        except Exception as e:
            BBLogger.log(f"Failed to initialize Gmail receiver: {e}")
            self.gmail_receiver = None
    
    def fetch(self):
        """Fetch Gmail messages and convert them to context files."""
        if not self.gmail_receiver:
            BBLogger.log("Gmail receiver not initialized. Cannot fetch messages.")
            return
        
        BBLogger.log(f"Starting Gmail fetch process for account.")
        
        try:
            # Get parameters
            max_messages = self.params.get('max_messages', 10)
            unread_only = self.params.get('unread_only', True)
            context_dir = self.params.get('context_dir', 'context')
            account_name = self.params.get('account_name', 'primary')
            force_process = self.params.get('force_process', False)
            
            # Ensure context directory exists
            os.makedirs(context_dir, exist_ok=True)
            
            # Fetch messages
            if unread_only:
                BBLogger.log(f"Fetching up to {max_messages} unread messages...")
                messages = self.gmail_receiver.get_unread_messages(max_messages)
            else:
                BBLogger.log(f"Fetching up to {max_messages} recent messages...")
                messages = self.gmail_receiver.get_recent_messages(days=7, max_results=max_messages)
            
            if not messages:
                BBLogger.log("No messages found to process.")
                self.set_total_items(0)
                self.set_processed_items(0)
                return
            
            BBLogger.log(f"Found {len(messages)} message(s) to process")
            
            # Set progress tracking
            self.set_total_items(len(messages))
            self.set_processed_items(0)
            
            processed_count = 0
            skipped_count = 0
            
            for i, msg in enumerate(messages, 1):
                try:
                    # Update progress callback if set
                    if self.progress_callback:
                        estimated_time = self.estimated_remaining_time()
                        self.progress_callback(
                            self.get_name(),
                            self.get_total_to_process(),
                            self.get_total_processed(),
                            estimated_time
                        )
                    
                    # Update status callback if set
                    if self.status_callback:
                        self.status_callback(self.get_name(), f"Processing message {i}/{len(messages)}")
                    
                    # Get full message data
                    message_data = self.gmail_receiver.get_message(msg['id'])
                    if not message_data:
                        BBLogger.log(f"Failed to get message data for message {i}")
                        continue
                    
                    # Check if message already exists (unless force processing)
                    if not force_process and self._check_message_exists(message_data['id'], context_dir):
                        BBLogger.log(f"Message {i} already exists in context, skipping...")
                        skipped_count += 1
                        self.increment_processed_items()
                        continue
                    
                    # Create context file
                    filepath, context_data = self._create_context_file(
                        message_data, account_name, context_dir
                    )
                    
                    if filepath:
                        processed_count += 1
                        BBLogger.log(f"Created context file: {filepath}")
                        
                        # Notify subscribers with the new data
                        self.update(context_data)
                    
                    self.increment_processed_items()
                    
                    # Log progress every 10 messages
                    if i % 10 == 0 or i == len(messages):
                        BBLogger.log(f"Progress: {i}/{len(messages)} messages processed")
                
                except Exception as e:
                    BBLogger.log(f"Error processing message {i}: {e}")
                    self.increment_processed_items()
                    continue
            
            # Final status update
            if self.status_callback:
                self.status_callback(
                    self.get_name(), 
                    f"Completed: {processed_count} processed, {skipped_count} skipped"
                )
            
            BBLogger.log(f"Gmail fetch completed. Processed: {processed_count}, Skipped: {skipped_count}")
            self.set_fetch_completed(True)
            
        except Exception as e:
            BBLogger.log(f"Error during Gmail fetch: {e}")
            if self.status_callback:
                self.status_callback(self.get_name(), f"Error: {str(e)}")
    
    def _check_message_exists(self, message_id, context_dir):
        """Check if a Gmail message ID already exists in context files."""
        if not os.path.exists(context_dir):
            return False
        
        for filename in os.listdir(context_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(context_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                    
                    # Check if this is a Gmail message with the same ID
                    if (existing_data.get('type') == 'gmail' and 
                        existing_data.get('gmail_metadata', {}).get('message_id') == message_id):
                        return True
                except (json.JSONDecodeError, IOError):
                    continue
        
        return False
    
    def _create_context_file(self, message_data, account_name, context_dir):
        """Create a context file from Gmail message data."""
        
        # Extract message content
        content = self.gmail_receiver.extract_message_content(message_data)
        
        # Extract folder/label information
        folders = self.gmail_receiver.get_message_labels(message_data)
        primary_folder = folders[0] if folders else "Unknown"
        
        # Parse timestamp - try multiple Gmail date formats
        date_formats = [
            '%a, %d %b %Y %H:%M:%S %z',           # Sun, 22 Jun 2025 22:47:06 +0000
            '%a, %d %b %Y %H:%M:%S %z (%Z)',      # Sun, 22 Jun 2025 22:47:06 +0000 (UTC)
            '%d %b %Y %H:%M:%S %z',               # 22 Jun 2025 22:47:06 +0000
            '%Y-%m-%d %H:%M:%S %z',               # 2025-06-22 22:47:06 +0000
            '%Y-%m-%d %H:%M:%S',                  # 2025-06-22 22:47:06 (no timezone)
            '%a, %d %b %Y %H:%M:%S',              # Sun, 22 Jun 2025 22:47:06 (no timezone)
        ]
        
        date_obj = None
        original_date = content['date']
        
        # Clean up the date string (remove timezone names in parentheses)
        clean_date = original_date
        if '(' in clean_date and ')' in clean_date:
            clean_date = clean_date.split('(')[0].strip()
        
        for date_format in date_formats:
            try:
                date_obj = datetime.strptime(clean_date, date_format)
                break
            except ValueError:
                continue
        
        if date_obj:
            timestamp = date_obj.strftime('%Y%m%d%H%M%S')
            iso_timestamp = date_obj.isoformat()
            BBLogger.log(f"Parsed email date: {original_date} -> {timestamp}")
        else:
            # Fallback to current time if all parsing fails
            BBLogger.log(f"Could not parse email date: {original_date}, using current time")
            now = datetime.now()
            timestamp = now.strftime('%Y%m%d%H%M%S')
            iso_timestamp = now.isoformat()
        
        # Generate filename following convention: context-YYYYMMDDHHMMSS.json
        filename = f"context-{timestamp}.json"
        filepath = os.path.join(context_dir, filename)
        
        # Check if file with this timestamp already exists
        if os.path.exists(filepath):
            BBLogger.log(f"File already exists: {filename}, skipping...")
            return None, None
        
        # Extract sender name (remove email part)
        sender = content['from']
        if '<' in sender:
            sender_name = sender.split('<')[0].strip().strip('"')
        else:
            sender_name = sender.split('@')[0] if '@' in sender else sender
        
        # Clean sender name for video_filename
        clean_sender = "".join(c for c in sender_name if c.isalnum() or c in (' ', '_', '-')).strip()
        clean_sender = clean_sender.replace(' ', '_').lower()
        
        # Handle attachments
        attachments = []
        for att in content['attachments']:
            attachment_info = {
                "filename": att['filename'],
                "mime_type": att['mime_type'],
                "attachment_id": att['attachment_id'],
                "download_url": f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_data['id']}/attachments/{att['attachment_id']}"
            }
            attachments.append(attachment_info)
        
        # Create context data structure
        context_data = {
            "type": "gmail",
            "folder": primary_folder,
            "video_filename": f"gmail_{account_name}_{clean_sender}_{content['subject'][:30].replace(' ', '_').lower()}",
            "video_recording_time": iso_timestamp,
            "video_file_path": None,  # Gmail messages don't have video files
            "video_link": None,
            "transcription": f"""EMAIL METADATA:
Account: {account_name}
From: {content['from']}
To: {content['to']}
Subject: {content['subject']}
Date: {content['date']}
Folder: {primary_folder}
Labels: {', '.join(folders)}

EMAIL CONTENT:
{content['body_text']}

{f"ATTACHMENTS ({len(attachments)}):" if attachments else ""}
{chr(10).join([f"- {att['filename']} ({att['mime_type']})" for att in attachments]) if attachments else ""}""",
            "gmail_metadata": {
                "account_name": account_name,
                "message_id": message_data['id'],
                "thread_id": message_data.get('threadId'),
                "from": content['from'],
                "to": content['to'],
                "subject": content['subject'],
                "date": content['date'],
                "folder": primary_folder,
                "all_folders": folders,
                "has_attachments": len(attachments) > 0,
                "attachments": attachments
            }
        }
        
        # Write context file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(context_data, f, indent=2, ensure_ascii=False)
        
        BBLogger.log(f"Created context file: {filepath}")
        return filepath, context_data
    
    def get_icon(self):
        """Return SVG icon content, preferring a local icon.svg in the plugin folder."""
        import os
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.svg')
        try:
            if os.path.exists(icon_path):
                with open(icon_path, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception:
            pass
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" rx="4" fill="#EA4335"/><path fill="#fff" d="M6 8l6 4 6-4v8H6z"/></svg>'
    
    def get_connection_data(self):
        """
        Return the connection type and required fields for a single Gmail account.
        Each datasource instance manages exactly one Gmail account.
        """
        return {
            "connection_type": "Gmail",
            "fields": [
                # Account Setup Section
                {
                    "name": "gmail_address",
                    "type": "email",
                    "label": "Gmail Address",
                    "description": "Your Gmail email address for this datasource",
                    "required": True,
                    "placeholder": "user@gmail.com",
                    "validation": "email",
                    "section": "account_setup"
                },
                {
                    "name": "account_name",
                    "type": "text",
                    "label": "Account Name",
                    "description": "Friendly name for this account (e.g., 'work', 'personal')",
                    "required": True,
                    "placeholder": "e.g., work, personal, main",
                    "section": "account_setup"
                },
                {
                    "name": "description",
                    "type": "text",
                    "label": "Description",
                    "description": "Optional description for this account",
                    "required": False,
                    "placeholder": "e.g., Work email account",
                    "section": "account_setup"
                },
                
                # Message Processing Section
                {
                    "name": "filter_type",
                    "type": "radio",
                    "label": "Message Filter",
                    "description": "Which messages to process",
                    "required": True,
                    "default": "unread",
                    "section": "processing",
                    "options": [
                        {"value": "unread", "label": "Unread messages only"},
                        {"value": "all", "label": "All messages"},
                        {"value": "recent", "label": "Recent messages (specify days)"},
                        {"value": "folder", "label": "Specific folder/label"},
                        {"value": "search", "label": "Search query"}
                    ]
                },
                {
                    "name": "recent_days",
                    "type": "spinner",
                    "label": "Days",
                    "description": "Number of recent days",
                    "required": False,
                    "default": 7,
                    "min": 1,
                    "max": 365,
                    "section": "processing",
                    "enabled_when": "filter_type == 'recent'"
                },
                {
                    "name": "folder_name",
                    "type": "dropdown",
                    "label": "Folder/Label",
                    "description": "Gmail folder or label name",
                    "required": False,
                    "default": "INBOX",
                    "section": "processing",
                    "options": ["INBOX", "Sent", "Drafts", "Spam", "Trash", "Important"],
                    "enabled_when": "filter_type == 'folder'"
                },
                {
                    "name": "search_query",
                    "type": "text",
                    "label": "Search Query",
                    "description": "Gmail search query (e.g., 'from:someone@example.com')",
                    "required": False,
                    "default": "",
                    "section": "processing",
                    "enabled_when": "filter_type == 'search'"
                },
                {
                    "name": "max_messages",
                    "type": "spinner",
                    "label": "Message Limit",
                    "description": "Maximum messages to process (0 = unlimited)",
                    "required": True,
                    "default": 100,
                    "min": 0,
                    "max": 10000,
                    "section": "processing"
                },
                {
                    "name": "create_context",
                    "type": "checkbox",
                    "label": "Create Context Files",
                    "description": "Convert emails to BrainBoost context format",
                    "required": False,
                    "default": True,
                    "section": "processing"
                },
                {
                    "name": "context_dir",
                    "type": "folder_picker",
                    "label": "Context Directory",
                    "description": "Directory to save context files",
                    "required": True,
                    "default": "./context",
                    "section": "processing"
                },
                {
                    "name": "show_progress",
                    "type": "checkbox",
                    "label": "Show Progress Bar",
                    "description": "Display animated progress during processing",
                    "required": False,
                    "default": True,
                    "section": "processing"
                },
                {
                    "name": "fresh_start",
                    "type": "checkbox",
                    "label": "Fresh Start",
                    "description": "Ignore previous processing state and start fresh",
                    "required": False,
                    "default": False,
                    "section": "processing"
                },
                {
                    "name": "resume_enabled",
                    "type": "checkbox",
                    "label": "Enable Resume",
                    "description": "Resume processing if interrupted",
                    "required": False,
                    "default": True,
                    "section": "processing"
                }
            ],
            "actions": [
                {
                    "name": "setup_account",
                    "label": "Setup Account",
                    "description": "Configure Gmail OAuth authentication",
                    "command": "setup_gmail_account"
                },
                {
                    "name": "test_connection",
                    "label": "Test Connection",
                    "description": "Test Gmail API connection",
                    "command": "test_gmail_connection"
                }
            ]
        }


# Example usage
if __name__ == "__main__":
    # Example parameters
    params = {
        'credentials_file': 'secrets/gmail_credentials.json',
        'token_file': 'token.json',
        'account_name': 'primary',
        'max_messages': 10,
        'unread_only': True,
        'context_dir': 'context',
        'force_process': False
    }
    
    # Create and test the data source
    gmail_source = SubjectiveGmailDataSource(
        name="test_gmail",
        params=params
    )
    
    # Set up progress callback
    def progress_callback(data_source_name, total_items, processed_items, estimated_time):
        print(f"Progress: {data_source_name} - {processed_items}/{total_items} - ETA: {estimated_time:.2f}s")
    
    def status_callback(data_source_name, status):
        print(f"Status: {data_source_name} - {status}")
    
    gmail_source.set_progress_callback(progress_callback)
    gmail_source.set_status_callback(status_callback)
    
    # Test the data source
    print("🚀 Testing SubjectiveGmailDataSource...")
    print(f"📋 Data source type: {gmail_source.get_data_source_type_name()}")
    print(f"🔗 Connection data: {gmail_source.get_connection_data()}")
    
    # Fetch messages
    gmail_source.fetch()
    
    print("✅ Test completed!") 