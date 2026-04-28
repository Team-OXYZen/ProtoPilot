# ProtoPilot

**Turning Product Vision into Working Prototypes**

An intelligent prototyping platform that uses LLM agents to transform product requirements into fully functional Angular applications.

# Quick Start

### Prerequisites
- Node.js 18+ (for frontend)
- Python 3.8+ (for backend)
- npm or yarn (for frontend package management)

---

# Backend Setup

### Step 1: Navigate to Backend Directory
```bash
cd backend
```

### Step 2: Create Virtual Environment

**MacOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Create a `.env` file in the `backend` directory. A reference `.env` file with required authentication variables is available in the backend folder.

**Important:** ProtoPilot uses Cotality's private LLM service, which requires an additional layer of authentication including OAuth credentials (CLIENT_ID and CLIENT_SECRET) in addition to LiteLLM API configuration. These credentials must be added to your `.env` file for the backend to communicate with the LLM service.

Add the following environment variables to your `.env` file:

```bash
# OAuth Credentials (Cotality Authentication)
CLIENT_ID=your-client-id
CLIENT_SECRET=your-client-secret

# LiteLLM Configuration
LITELLM_MODEL=openai/gemini-2.5-pro-litellm-usc1
LITELLM_API_BASE=https://api-uat.cotality.com/llmservice
LITELLM_API_KEY=your-litellm-api-key

# Agent model overrides (optional, falls back to LITELLM_MODEL if not set)
# LITELLM_MODEL_REQUIREMENTS=openai/gemini-2.5-flash-litellm-usw1
# LITELLM_MODEL_ARTIFACTS=openai/gemini-2.5-flash-litellm-usw1
# LITELLM_MODEL_CODEGEN=openai/gemini-2.5-pro-litellm-usw1

# Session Configuration
USER_ID=your-user-id
APP_NAME=your-app-name
SESSION_ID=your-session-id

```

### Step 5: Run Backend Server
```bash
uvicorn api.server:app --reload --port 8000
```


---

# Frontend Setup

### Step 1: Open New Terminal and Navigate to Frontend
```bash
cd frontend
```

### Step 2: Install Dependencies
```bash
npm install
```

### Step 3: Run Frontend Development Server
```bash
npm start
```

### Step 4: Open in Browser
```
http://localhost:4200
```

---
# Available LLM Models

The following models are available for your ProtoPilot agents:

```
gemini-2.0-flash-001-litellm-usc1
gemini-2.0-flash-001-litellm-usw1
gemini-2.0-flash-lite-001-litellm-usc1
gemini-2.0-flash-lite-001-litellm-usw1
gemini-2.5-flash-litellm-usc1
gemini-2.5-flash-litellm-usw1
gemini-2.5-flash-lite-litellm-usc1
gemini-2.5-flash-lite-litellm-usw1
gemini-2.5-pro-litellm-usc1
gemini-2.5-pro-litellm-usw1
claude-sonnet-4@20250514-litellm-use5
claude-sonnet-4-6-litellm-use5
imagen-3.0-generate-002-litellm-usc1
text-embedding-005-litellm-usc1
text-embedding-005-litellm-usw1
llama-4-maverick-17b-128e-instruct-maas-litellm-use5
```

---
