# 🎯 ProtoPilot

**Turning Product Vision into Working Prototypes**

An intelligent prototyping platform that uses LLM agents to transform product requirements into fully functional Angular applications. Simply describe your product idea, and ProtoPilot generates a complete specification, design artifacts, and working code—with an interactive chat interface for iterative refinement.

> **UCI MCS 2026 Capstone Project** | **Sponsored by [Cotality](https://cotality.com)**

---

## 📋 Project Overview

**ProtoPilot** bridges the gap between product vision and working prototypes. Instead of lengthy specification documents and manual development cycles, PMs and non-technical stakeholders can:

1. Answer guided questions about their product
2. Receive AI-generated specifications (PRD, user flows, design docs)
3. Refine specs through conversational chat
4. Preview a live, interactive prototype
5. Download all artifacts (code, designs, documentation)

**Target Users:**
- **Product Managers** — Define and iterate on product vision rapidly
- **Non-Technical Stakeholders** — Communicate requirements without technical jargon
- **Startup Founders** — Validate product concepts with working prototypes
- **Design Teams** — Generate initial design systems and documentation

---

## 👥 Team

| Name | LinkedIn |
|------|----------|
| Omkar Dabir | https://www.linkedin.com/in/rakmo33/ |
| Xin Jiang | https://www.linkedin.com/in/xin-jiang12/ |
| Yiniu Han | https://www.linkedin.com/in/yiniu-han-0a323638b/ |
| Zhihao Wang | https://www.linkedin.com/in/zhihao-wang-83a154378/ |

---

## ✨ Features

✅ **Guided Requirements Gathering** — Interactive Q&A wizard to collect product details, features, and design preferences

✅ **Smart Suggestions** — Choose from AI-generated suggestions or define custom requirements

✅ **User Dashboard** — Manage multiple projects, view project status, access previous work

✅ **Specification Documents** — Auto-generated PRD, user flow diagrams, design docs, technical specs rendered as Markdown

✅ **Iterative Chat Interface** — Refine specifications through natural conversation with AI

✅ **Live Prototype Preview** — View and interact with generated Angular application in real-time

✅ **Code Editor View** — Browse generated source code with syntax highlighting and make temporary modifications

✅ **Code Refinement Chat** — Use chat to request code changes and improvements

✅ **Export All Artifacts** — Download complete code files, design files, and documentation

---

## 🏗️ Architecture

ProtoPilot uses a multi-agent orchestration system to generate production-ready prototypes:

![Architecture Diagram](./frontend/src/assets/architecture-diagram.png)

**Key Components:**

- **Frontend (Angular 21)**: Handles user dashboard, requirements wizard, spec review with chat, live prototype preview, and code editor
- **FastAPI Backend**: REST API for project management, authentication, and agent orchestration
- **Orchestrator**: Coordinates multi-agent workflow, manages conversation state and project data
- **4 Specialized Agents**: 
  - **Requirements Agent** — Analyzes user input and generates detailed PRD
  - **Code Generation Agent** — Creates Angular components and services
  - **QA Agent** — Validates specifications and identifies gaps
  - **Artifacts Agent** — Generates design docs, user flows, and export packages
- **LLM Integration**: Google Gemini & Claude models via Cotality's private LLM service
- **SQLite Database**: Stores projects, sessions, and user data
- **Tools & Functions**: Markdown rendering, diagram generation, code export utilities

---

## ⚙️ Setup & Run Locally

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Node.js | 18+ | Frontend runtime |
| npm | 11.6.2+ | Frontend package manager |
| Python | 3.8+ | Backend runtime |
| pip | Latest | Python package manager |

### Installation & Running

**Backend Setup** (Terminal 1):

```bash
cd backend

python3 -m venv .venv # One-time creation of virtual environment

source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .example.env .env # Add your environment variables in '/backend/.env'

uvicorn api.server:app --reload --port 8000 # Start the FastAPI Server
```

**Important:** ProtoPilot uses Cotality's private LLM service, which requires credentials (CLIENT_ID and CLIENT_SECRET). Refer to the `.example.env` file and add your Cotality credentials to `.env`.

**Frontend Setup** (Terminal 2):

```bash
cd frontend
npm install
npm run start
```

Navigate to `http://localhost:4200/`. The application automatically reloads when you modify source files.

⚠️ **API Key Setup:** ProtoPilot currently does not support custom LLM API key configuration. So the platform might not work as expected without Cotality's private LiteLLM proxy credentials.

**Verify it's working:** Create a new project through the **Requirements Wizard**, answer the guided questions, and watch ProtoPilot generate your specification and prototype in real-time.

---

## Project Structure

```
ProtoPilot/
├── frontend/              # Angular 21 application
│   ├── src/
│   ├── package.json
│   └── README.md          # Frontend-specific documentation
│
├── backend/               # FastAPI Python application
│   ├── agents/            # 4 specialized AI agents
│   ├── api/               # REST API routes
│   ├── core/              # Core services (auth, LLM, sessions)
│   ├── orchestration/     # Agent orchestrator & workflow
│   ├── requirements.txt
│   ├── .example.env       # Environment variables template
│   └── README.md          # Backend-specific documentation
│
└── README.md              # This file (main project docs)
```

**Key Locations:**
- **Frontend**: `./frontend/` — Angular UI, user dashboard, requirements wizard, spec review chat
- **Backend**: `./backend/` — FastAPI server, LLM agent orchestration, session management
- **Documentation**: Each folder has its own `README.md` with detailed setup and architecture info

---

## 🚀 Running the Application

Once both backend and frontend are running:

1. Open `http://localhost:4200` in your browser
2. Create a new project through the **Requirements Wizard**
3. Answer the guided questions
4. Watch ProtoPilot generate your specification and interactive prototype in real-time

---

## ✅ Testing & Verification

TBD

---

## 🌐 Deployment & CI/CD

⚠️ **Important:** The deployed version currently does not function without API credentials. We have intentionally removed all LLM API keys from the deployment for security purposes. If you would like to test the deployed application, please reach out via LinkedIn and we will add the credentials temporarily for your testing session.

**Live URL:** https://protopilot.onrender.com/

**Current Status:** CI/CD is set up for this repo and gets triggered whenever new commits are pushed into the `chore/render_deployment` branch.

### Backend Deployment
- **Deployed on:** Google Cloud Run
- **Configuration:** Requires environment variables for LLM API credentials

### Frontend Deployment
- **Deployed on:** Render
- **Configuration:** Built with `npm run build` and served via Render's static hosting

---

## 🎬 Demo

Watch ProtoPilot transform a product idea into a working prototype:

📹 **Demo Video Link:** `[TBD]`

The demo shows the complete workflow: requirements gathering → specification preview → chat refinement → live prototype interaction → code download.

---

## 🔮 Known Issues & Future Work
Please refer our issues tracker here: \
https://github.com/orgs/Team-OXYZen/projects/1

### Known Issues / Improvements
- [ ] Add support for user authentication. We are using demo credentials for loggin in as of now
- [ ] Allow users to export the generated markdown files
- [ ] Allow users to configure env variables or API keys from UI 
- [ ] Generate a publically sharable URL for viewing the prototype

### Future Enhancements
- [ ] **GitHub Integration** — Auto-create repository and push generated code
- [ ] **JIRA Integration** — Sync requirements and track development tasks
- [ ] **User Authentication** — Implement OAuth2 with multiple identity providers
- [ ] **Java Backend Support** — Generate Java/Spring Boot backends in addition to frontend
- [ ] **Multi-framework Support** — Extend beyond Angular (React, Vue, Svelte)

---

## 🧠 Available LLM Models via Cotality LiteLLM Proxy

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
