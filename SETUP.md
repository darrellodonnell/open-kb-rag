# Setup Guide

Step-by-step instructions for setting up the open-kb-rag knowledge base. Covers both macOS (development) and Ubuntu (deployment).

## Prerequisites

You need the following before starting:

- **Python 3.11+** — check with `python3 --version`
- **Git** — check with `git --version`
- **Ollama** — running on this machine or accessible via Tailscale
- **A Slack workspace** where you have admin permissions
- **A Supabase account** (free tier is fine)
- **Tailscale** — installed and connected to your tailnet

### Install Python (if needed)

**macOS:**

```bash
# Using Homebrew
brew install python@3.12
```

**Ubuntu:**

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip
```

### Install uv (recommended Python package manager)

```bash
# Option 1: Official installer
curl -LsSf https://astral.sh/uv/install.sh | sh

# Option 2: If the above 404s, install via Homebrew (macOS)
brew install uv

# Option 3: Install via pip (any platform)
pip install uv

# Option 4: Install via pipx (isolated, any platform)
pipx install uv
```

Restart your shell after installing. Verify with `uv --version`.

---

## 1. Supabase Setup

### 1.1 Create an Account

1. Go to [supabase.com](https://supabase.com)
2. Click **Start your project** (top right)
3. Sign up with GitHub or email

### 1.2 Create a New Project

1. From the Supabase dashboard, click **New project**
2. Choose your organization (or create one)
3. Fill in:
   - **Name**: `open-kb-rag` (or whatever you prefer)
   - **Database Password**: generate a strong password and **save it** — you'll need it later
   - **Region**: choose the closest to you (or your Ubuntu VM)
4. Click **Create new project**
5. Wait for the project to finish provisioning (takes ~2 minutes)

### 1.3 Enable pgvector Extension

1. In the left sidebar, click **Database**
2. Click **Extensions** in the submenu
3. Search for `vector` in the search box
4. Find **vector** (pgvector) in the list
5. Toggle it **ON**
6. Click **Enable extension** in the confirmation dialog
7. Leave the schema as `extensions` (default)

### 1.4 Get Your Project URL and API Key

1. In the left sidebar, click **Project Settings** (gear icon at the bottom)
2. Click **API** in the submenu
3. Copy these two values and save them:
   - **Project URL** — looks like `https://abcdefghij.supabase.co`
   - **Publishable Key** (`sb_publishable_...`) — under **API Keys → Publishable**

These go into your `.env` file as `SUPABASE_URL` and `SUPABASE_KEY`.

### 1.5 Run the Database Schema

> **Note:** Come back to this step after Phase 1 is built — `sql/init.sql` doesn't exist yet. The steps below are here for reference when you're ready.
>
> <!-- TODO: Remove this warning once sql/init.sql exists in the codebase -->

1. In the left sidebar, click **SQL Editor**
2. Click **New query**
3. Paste the contents of `sql/init.sql`
4. Click **Run** (or Cmd+Enter / Ctrl+Enter)
5. Verify: you should see "Success. No rows returned" for each statement
6. Check the tables exist: go to **Table Editor** in the left sidebar — you should see `sources`, `chunks`, `tags`, and `source_tags`

---

## 2. Ollama Setup

### 2.1 Install Ollama

**macOS:**

```bash
brew install ollama
```

**Ubuntu:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2.2 Start Ollama

**macOS:**

```bash
# Ollama runs as a background service after install
# Verify it's running:
ollama list
```

**Ubuntu:**

```bash
# Start the service
sudo systemctl enable ollama
sudo systemctl start ollama

# Verify it's running:
ollama list
```

### 2.3 Pull Required Models

```bash
# Embedding model (required)
ollama pull nomic-embed-text

# LLM for tagging and summarization (pick one, or pull several and configure later)
ollama pull llama3.2        # 3B params, fast, good for tagging
ollama pull mistral          # 7B params, strong structured output
```

### 2.4 Verify Models Work

```bash
# Test embedding
curl http://localhost:11434/api/embed -d '{
  "model": "nomic-embed-text",
  "input": "test embedding"
}'
# Should return a JSON object with an "embeddings" array

# Test generation (replace YOUR_MODEL with whatever you pulled, e.g., llama3.2, mistral, etc.)
curl http://localhost:11434/api/generate -d '{
  "model": "YOUR_MODEL",
  "prompt": "List 3 tags for: machine learning article",
  "stream": false
}'

# Should return a JSON object with a "response" field
```

### 2.5 Tailscale Access (if Ollama is on a different machine)

If Ollama runs on a separate machine on your tailnet:

1. Find the Tailscale IP of the Ollama machine:

   ```bash
   # On the Ollama machine:
   tailscale ip -4
   # Example output: 100.64.0.5
   ```

2. Configure Ollama to listen on all interfaces (not just localhost):

   **Ubuntu (systemd override):**

   ```bash
   sudo systemctl edit ollama
   ```

   Add these lines:

   ```ini
   [Service]
   Environment="OLLAMA_HOST=0.0.0.0"
   ```

   Then restart:

   ```bash
   sudo systemctl restart ollama
   ```

   **macOS:**

   ```bash
   launchctl setenv OLLAMA_HOST "0.0.0.0"
   # Restart Ollama app
   ```

3. Test from your other machine:

   ```bash
   curl http://100.64.0.5:11434/api/tags
   # Should list your pulled models
   ```

4. Use the Tailscale IP in your `.env`:

   ```ini
   OLLAMA_HOST=http://100.64.0.5:11434
   ```

---

## 3. OpenRouter Setup (for generation LLM)

OpenRouter provides access to 400+ models through a single API. We recommend **DeepSeek V3.2** for tagging and summarization — it matches frontier model quality at ~$0.26/$0.38 per million tokens.

### 3.1 Create an Account

1. Go to [openrouter.ai](https://openrouter.ai)
2. Click **Sign In** (top right)
3. Sign in with Google, GitHub, or email

### 3.2 Get Your API Key

1. Go to [openrouter.ai/keys](https://openrouter.ai/keys)
2. Click **Create Key**
3. Give it a name (e.g., `kb-rag`)
4. Copy the key — it starts with `sk-or-`. This is your `OPENROUTER_API_KEY`

### 3.3 Add Credits

1. Go to [openrouter.ai/credits](https://openrouter.ai/credits)
2. Add a small amount ($5 is plenty for months of personal KB use)

### 3.4 Verify

```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek/deepseek-v3.2",
    "messages": [{"role": "user", "content": "List 3 tags for: machine learning article. Return JSON array only."}]
  }'
# Should return a JSON response with tag suggestions
```

### 3.5 Model Options

| Model | Input / 1M tokens | Output / 1M tokens | Notes |
|-------|-------------------|--------------------|----|
| `deepseek/deepseek-v3.2` | $0.26 | $0.38 | **Recommended** — best value, strong structured output |
| `deepseek/deepseek-chat-v3.1` | $0.15 | $0.75 | Cheapest input cost |
| `anthropic/claude-sonnet-4-6` | $3.00 | $15.00 | Highest quality, ~40x more expensive |

Set your chosen model in `.env` as `OPENROUTER_MODEL`.

---

## 4. Slack App Setup

### 4.1 Create a New Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App**
3. Choose **From scratch**
4. Fill in:
   - **App Name**: `KB Bot` (or whatever you prefer)
   - **Workspace**: select your workspace
5. Click **Create App**

### 4.2 Enable Socket Mode

1. In the left sidebar, click **Socket Mode**
2. Toggle **Enable Socket Mode** to ON
3. You'll be prompted to create an app-level token:
   - **Token Name**: `kb-socket-token`
   - **Scope**: `connections:write` (should be pre-selected)
4. Click **Generate**
5. **Copy the token** — it starts with `xapp-`. This is your `SLACK_APP_TOKEN`
6. Click **Done**

### 4.3 Set Up Event Subscriptions

1. In the left sidebar, click **Event Subscriptions**
2. Toggle **Enable Events** to ON
3. Expand **Subscribe to bot events**
4. Click **Add Bot User Event** and add:
   - `message.channels` — listens for messages in public channels
   - `message.groups` — listens for messages in private channels (add this if your ingestion channel is private)
5. Click **Save Changes** at the bottom

### 4.4 Set Bot Token Scopes

1. In the left sidebar, click **OAuth & Permissions**
2. Scroll down to **Scopes → Bot Token Scopes**
3. Click **Add an OAuth Scope** and add each of these:
   - `chat:write` — post messages
   - `channels:history` — read messages in public channels
   - `channels:read` — list channels and get channel info
   - `groups:history` — read messages in private channels (add if using private channels)
   - `files:read` — access uploaded files (for PDF ingestion)
   - `files:write` — upload files (for cross-post if needed)
4. Scroll up and verify all 5 scopes are listed

### 4.5 Install the App to Your Workspace

1. Scroll to the top of the **OAuth & Permissions** page
2. Click **Install to Workspace**
3. Review the permissions and click **Allow**
4. **Copy the Bot User OAuth Token** — it starts with `xoxb-`. This is your `SLACK_BOT_TOKEN`

### 4.6 Create or Choose an Ingestion Channel

1. In Slack, create a new channel (e.g., `#kb-ingest`) or choose an existing one
2. Get the channel ID:
   - Right-click the channel name → **View channel details**
   - At the bottom of the details panel, you'll see the Channel ID (e.g., `C0123456789`)
   - Copy it — this is your `SLACK_CHANNEL_ID`
3. Optionally create a second channel for cross-post summaries (e.g., `#kb-feed`)
   - Get its channel ID too — this is your `SLACK_CROSSPOST_CHANNEL_ID`

### 4.7 Invite the Bot to the Channel(s)

In Slack, in each channel the bot needs access to:

```text
/invite @KB Bot
```

Or type a message mentioning the bot — Slack will prompt you to invite it.

---

## 5. Project Setup

### 5.1 Clone the Repository

```bash
git clone <your-repo-url> open-kb-rag
cd open-kb-rag
```

### 5.2 Create a Virtual Environment

**Using uv (recommended):**

```bash
uv venv
source .venv/bin/activate
```

**Using standard venv:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 5.3 Install Dependencies

**Using uv:**

```bash
uv pip install -e ".[dev]"
```

**Using pip:**

```bash
pip install -e ".[dev]"
```

### 5.4 Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your values:

```ini
# Supabase (from Section 1.4)
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Ollama (from Section 2)
OLLAMA_HOST=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_LLM_MODEL=llama3.2

# Storage — where markdown files are saved on disk
KB_STORAGE_PATH=~/kb-store

# Slack (from Section 4)
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-level-token
SLACK_CHANNEL_ID=C0123456789
SLACK_CROSSPOST_CHANNEL_ID=C9876543210

# Sanitization — set to true to enable LLM-based prompt injection scanning
SANITIZE_LLM_SCAN=false
```

### 5.5 Create the Storage Directory

```bash
mkdir -p ~/kb-store
```

---

## 6. Verification

Run these checks to confirm everything is connected:

### 6.1 Supabase Connection

```bash
python3 -c "
from kb.config import settings
from kb.db import get_client
client = get_client()
print('Supabase: connected')
"
```

### 6.2 Ollama Connection

```bash
curl -s ${OLLAMA_HOST:-http://localhost:11434}/api/tags | python3 -m json.tool
# Should list your models
```

### 6.3 Storage Path

```bash
ls -la ~/kb-store
# Should exist and be writable
```

### 6.4 Run Preflight (once code is built)

```bash
python3 -m kb.preflight
# Should report all checks passing
```

---

## 7. Ubuntu Deployment

For running on an Ubuntu VM on your Tailnet.

### 7.1 System Dependencies

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip git
```

### 7.2 Clone and Set Up

Follow Sections 5.1 through 5.5 above.

### 7.3 Systemd Service for Slack Bot

Create `/etc/systemd/system/kb-slack.service`:

```ini
[Unit]
Description=KB Slack Bot
After=network.target ollama.service

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/open-kb-rag
EnvironmentFile=/home/your-username/open-kb-rag/.env
ExecStart=/home/your-username/open-kb-rag/.venv/bin/python -m kb.slack.bot
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable kb-slack
sudo systemctl start kb-slack

# Check status
sudo systemctl status kb-slack

# View logs
journalctl -u kb-slack -f
```

### 7.4 Systemd Service for MCP Server (if running as SSE)

If you run the MCP server as an SSE HTTP endpoint (rather than stdio):

Create `/etc/systemd/system/kb-mcp.service`:

```ini
[Unit]
Description=KB MCP Server
After=network.target ollama.service

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/open-kb-rag
EnvironmentFile=/home/your-username/open-kb-rag/.env
ExecStart=/home/your-username/open-kb-rag/.venv/bin/python -m kb.mcp.server
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Note:** If using MCP over stdio (the default for Claude Code), you don't need a systemd service — Claude Code launches the MCP server as a subprocess. Add it to your Claude Code MCP config instead:

```json
{
  "mcpServers": {
    "kb": {
      "command": "/home/your-username/open-kb-rag/.venv/bin/python",
      "args": ["-m", "kb.mcp.server"],
      "cwd": "/home/your-username/open-kb-rag"
    }
  }
}
```

### 7.5 Updating

To update the deployment after code changes:

```bash
cd /home/your-username/open-kb-rag
git pull
source .venv/bin/activate
uv pip install -e ".[dev]"
sudo systemctl restart kb-slack
# Restart kb-mcp too if running as a service
```
