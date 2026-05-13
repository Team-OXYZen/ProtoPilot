# ProtoPilot Frontend

Angular 21 application for the ProtoPilot intelligent prototyping platform. Transforms product requirements into functional applications using LLM agents.

## Quick Start

### Install Dependencies

```bash
npm install
```

### Run Development Server

```bash
npm start
```

Navigate to `http://localhost:4200/`. The application automatically reloads when you modify source files.

---

## User Flow

1. **Welcome** → User lands on the welcome page
2. **Dashboard** → View and manage existing projects
3. **Requirements** → Create a new project through an interactive wizard to gather product requirements
4. **Spec Review** → Review the generated specification with an AI-powered chat interface
5. **Prototype Preview** → Live preview of the app + Project artifacts (design, code) ready for download

---

## Screens

### Welcome (`/welcome`)
Entry point for the application. Option to create a new project or navigate to the dashboard.

### Dashboard (`/dashboard`)
Display list of projects with status and recent activity. Users can:
- Create a new project
- View existing projects
- Access project details

### Requirements Wizard (`/requirements`)
Interactive multi-step wizard to gather product requirements:
- Project details (name, description)
- Feature requirements
- Design preferences
- Technical specifications

Collected data is sent to the backend for processing by the agents.

### Spec Review (`/spec-review`)
Multi-panel interface to review generated specifications:
- **Left Panel**: Specification preview with Markdown rendering
- **Chat Panel**: AI-powered chat to ask clarifying questions and refine specs
- **Right Panel**: Generated artifacts preview (if available)

Users can iterate and refine the specification before proceeding.

### Prototype Preview
Live interactive preview of the generated Angular application:
- **Live App Preview**: Run the generated prototype in an embedded iframe or side panel
- **Design Artifacts**: View generated design files (Figma, wireframes, etc.)
- **Code Artifacts**: Browse generated source code with syntax highlighting
- **Download**: Export artifacts (code, design files, documentation)

Users can test the prototype functionality and download all generated materials.

---

## Key Services

| Service | Location | Purpose |
|---------|----------|---------|
| `AuthService` | `core/auth.service.ts` | User authentication & token management |
| `ThemeService` | `core/theme.service.ts` | Dark/light theme management |
| `LoaderService` | `shared/services/loader.service.ts` | Global loading state |
| Requirements API | `features/requirements/services/` | Communicate with backend wizard API |
| Spec Review API | `features/spec-review/services/` | Chat and spec retrieval endpoints |

---

## Important Files

- [src/app/app.routes.ts](src/app/app.routes.ts) — Route definitions
- [src/app/app.config.ts](src/app/app.config.ts) — App initialization config
- [src/app/features/requirements/models/project.model.ts](src/app/features/requirements/models/project.model.ts) — Project data structure
- [src/app/shared/models/user.model.ts](src/app/shared/models/user.model.ts) — User data structure
- [src/styles/variables.scss](src/styles/variables.scss) — Design tokens and theme variables

---

