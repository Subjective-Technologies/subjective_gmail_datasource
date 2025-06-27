# Gmail DataSource for BrainBoost

A powerful Gmail integration that converts your email messages into BrainBoost context files for AI processing and analysis.

## 🚀 Features

### Email Processing
- **Multiple Filter Options**: Unread messages, all messages, specific folders, date ranges, or search queries
- **Context File Generation**: Converts emails to structured JSON format for BrainBoost
- **Smart Resume**: Automatically resumes interrupted processing sessions
- **Progress Tracking**: Visual progress bars for large email processing jobs

### Account Management
- **Multi-Account Support**: Each datasource instance manages one Gmail account
- **Embedded Authentication**: Secure OAuth credentials built-in (no external files needed)
- **Easy Setup**: Simple email address input with automated OAuth flow

### Advanced Options
- **Flexible Filtering**: 
  - Unread messages only
  - All messages with optional limits
  - Recent messages (last N days)
  - Specific Gmail folders/labels
  - Custom search queries
- **Batch Processing**: Handle thousands of emails efficiently
- **Duplicate Prevention**: Skips already processed messages
- **Error Recovery**: Continues processing even if individual emails fail

## 📋 Requirements

```bash
pip install -r requirements.txt
```

Key dependencies:
- Google API packages (gmail, auth, oauth)
- Cryptography for secure credential storage
- BrainBoost core packages
- Optional: alive-progress for visual progress bars

## 🛠️ Quick Start

### 1. Setup Virtual Environment
```bash
python3 -m venv myenv
source myenv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Account
```bash
# Interactive setup
python gmail_receive.py --add-more-accounts

# Or add account directly
python gmail_receive.py --add-account work user@gmail.com "Work email"
```

### 3. Process Emails
```bash
# Convert unread emails to context files
python gmail_receive.py --use-account work --unread --create-context

# Convert all emails (with progress bar)
python gmail_receive.py --use-account work --all --create-context --progress

# Convert recent emails (last 7 days)
python gmail_receive.py --use-account work --recent 7 --create-context
```

## 📊 Usage Examples

### Basic Operations
```bash
# List configured accounts
python gmail_receive.py --list-accounts

# Test account connection
python gmail_receive.py --test-account work

# View unread messages (no context files)
python gmail_receive.py --use-account work --unread
```

### Context File Generation
```bash
# Unread messages only
python gmail_receive.py --use-account work --unread --create-context

# All messages with limit
python gmail_receive.py --use-account work --all --count 100 --create-context

# Specific folder
python gmail_receive.py --use-account work --folder "Sent" --create-context

# Search query
python gmail_receive.py --use-account work --search "from:boss@company.com" --create-context
```

### Advanced Processing
```bash
# Resume interrupted processing
python gmail_receive.py --use-account work --all --create-context --resume

# Start fresh (ignore previous progress)
python gmail_receive.py --use-account work --all --create-context --fresh

# Start from specific message number
python gmail_receive.py --use-account work --all --create-context --start-from=500

# Show progress bar during processing
python gmail_receive.py --use-account work --all --create-context --progress
```

## 🔧 Configuration

### Connection Parameters

When integrating with external systems, the datasource supports these configuration fields:

- **Account Setup**: Gmail address, account name, description
- **Message Filtering**: Filter type (unread/all/recent/folder/search)
- **Processing Options**: Context file creation, progress display, resume behavior
- **Output Settings**: Context directory, message limits

### Security

- **Embedded Credentials**: OAuth client credentials are encrypted and embedded in the code
- **Token Storage**: User access tokens are securely stored per account
- **No External Dependencies**: No need for separate credential files

## 📁 Output Format

Generated context files follow BrainBoost standards:

```json
{
  "type": "gmail",
  "folder": "Inbox",
  "video_filename": "gmail_work_sender_subject",
  "video_recording_time": "2024-01-15T10:30:00",
  "transcription": "EMAIL METADATA:\nFrom: sender@example.com\n...",
  "gmail_metadata": {
    "account_name": "work",
    "message_id": "abc123",
    "from": "sender@example.com",
    "subject": "Important Meeting",
    "attachments": [...]
  }
}
```

## 🏗️ Architecture

- **Single Account Per Instance**: Each datasource manages one Gmail account
- **Multiple Instances**: External system creates separate instances for multiple accounts
- **Embedded Security**: No external credential files required
- **Resume Capability**: Handles large email processing jobs efficiently

## 🔍 Troubleshooting

### Import Errors
If you see "Import could not be resolved" errors:
1. Ensure virtual environment is activated
2. Set Python interpreter in your editor to `./myenv/bin/python`
3. Install all requirements: `pip install -r requirements.txt`

### Authentication Issues
- Use `--test-account accountname` to verify authentication
- Re-run account setup if OAuth tokens are expired
- Check that embedded credentials are not corrupted

### Processing Issues
- Use `--resume` to continue interrupted processing
- Use `--fresh` to start over and ignore previous state
- Check context directory permissions for file creation

## 📄 License

Part of the BrainBoost ecosystem. See main project for licensing details.
