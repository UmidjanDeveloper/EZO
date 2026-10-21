# EZO OS — Agent Ecosystem & Integration Contract

**Document Version:** 1.0.0  
**Status:** Approved Integration Contract  
**Target Integration Branch:** `claude/gifted-goodall-bpf01s`  
**Base Commit:** `16a4ae96dd4a436a5170c357e3de6222f8ef8136`  
**Feature Branch:** `feat/personal-intelligence-agent-ecosystem`  

---

## 1. Architectural Boundaries & Parallel Development Rules

To ensure clean isolation and zero merge collisions between parallel development streams:

1. **Codex Ownership (Student V1):**
   - Owns `apps/api/src/ezo_api/api/routes/student.py`
   - Owns durable jobs: `apps/api/src/ezo_api/knowledge/jobs/`
   - Owns document ingestion / parsers / knowledge indexing internals
   - Owns Student-specific frontend ingestion screens
   - **Rule:** This agent ecosystem package must not modify or import private internals of Student V1 modules. Integration with Student is done strictly via the documented public adapter contract in Section 2.

2. **Agent Ecosystem Ownership (This Package):**
   - **Personal Intelligence K9:** Privacy-first memory, user goals, preferences, learning progress, explicit consent, view/edit/delete/export, tenant isolation.
   - **Smart Agent Router:** Uzbek-first intent classification, multilingual routing (uz, en, ru), deterministic fallback, permission-aware orchestration.
   - **IELTS Examiner 2.0:** Full speaking session workflow (Parts 1–3), cue cards, rubric feedback, progress tracking, voice adapter interface with text fallback.
   - **Presentation Maker 2.0:** Brief intake, slide outline, structured slide deck generation, professional design themes, PPTX export via native builder, slide regeneration.
   - **Documents & Office Workspace:** Safe DOCX creation, XLSX/CSV export, PPTX export, templates, error handling, artifact delivery without untrusted macros.
   - **Premium Global UI/UX:** Unified Uzbek-first responsive interface across desktop and mobile, central chat with agent routing, dedicated workspaces for IELTS, Presentations, Office, and Personal Intelligence / Memory.
   - **Super Admin & Governance:** Strict role segregation (`user` vs `super_admin`), immutable system boundaries, no unauthorized code mutation or escalation.

---

## 2. Student Public Adapter Contract

Student capabilities are exposed through its published HTTP surface. The agent ecosystem integrates via `StudentClientAdapter`:

### 2.1 Public HTTP Endpoints
- `GET /api/student/status`
  - Response:
    ```json
    {
      "supported_submission": "authorized_utf8_text",
      "max_input_bytes": 2000000,
      "worker": "stored-normalized-text/v1",
      "native_execution": "disabled",
      "blocked_formats": ["pdf", "docx", "epub", "xlsx", "image", "html"],
      "reason": "..."
    }
    ```
- `POST /api/student/readings`
  - Request: `{"text": string, "title": string, "project_id": UUID | null}`
  - Response: `JobOut` (201 Created)
- `GET /api/student/readings/{job_id}?offset=0&limit=4000`
  - Response: `PublicationOut`

### 2.2 Python Client Adapter Interface
```python
class StudentClientAdapter:
    async def get_status(self) -> dict[str, Any]:
        """Fetch status and supported formats without importing Student internal services."""
        ...

    async def submit_reading(
        self, text: str, title: str = "Reading", project_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        """Submit text material to the Student durable queue."""
        ...

    async def get_reading(
        self, job_id: uuid.UUID, project_id: uuid.UUID | None = None, offset: int = 0, limit: int = 4000
    ) -> dict[str, Any]:
        """Retrieve paginated reading publication results."""
        ...
```

---

## 3. Personal Intelligence K9 Contract

Privacy-first personal intelligence is strictly tenant-isolated and opt-in.

### 3.1 Principles
- **Explicit Memory Consent:** Chat messages are never captured into long-term memory without explicit user consent (`memory_enabled: true` in user preferences or direct user-authored memory).
- **Zero Cross-User Leakage:** All queries, mutations, exports, and retrievals require `user_id == authenticated_user.id`.
- **User Agency:** Users can view, edit, delete individually, clear all, and export all stored memory and goals in JSON/Markdown.
- **Boundaries:** Sensitive personal identifiers, credentials, and payment data are filtered by `sensitive.py` and rejected even if memory is enabled.

### 3.2 Data Models & Endpoints
- `GET /api/personal/profile`: Returns user profile, preferences, consent flags, and intelligence summary.
- `PUT /api/personal/preferences`: Update preferences including `memory_consent: bool`, `preferred_language: str`, `learning_style: str`.
- `GET /api/personal/memories`: List memories with category, importance, confidence, source.
- `POST /api/personal/memories`: Manually add or confirm a memory fact.
- `PUT /api/personal/memories/{memory_id}`: Edit memory content or category.
- `DELETE /api/personal/memories/{memory_id}`: Delete an individual memory item.
- `DELETE /api/personal/memories`: Purge all memories for the user.
- `GET /api/personal/memories/export`: Export all memories in JSON format.
- `GET /api/personal/goals`: List active and completed learning/personal goals.
- `POST /api/personal/goals`: Create a new personal goal with milestone targets.
- `PUT /api/personal/goals/{goal_id}`: Update progress, status, or title.
- `DELETE /api/personal/goals/{goal_id}`: Delete a goal.

---

## 4. Smart Agent Router Contract

### 4.1 Routing Intent Matrix
| Input Trigger Example (Uzbek / English / Russian) | Intent | Target Agent | Primary Output Format |
|---|---|---|---|
| *"Python kitobini o'rgan"*, *"darslikni o'qib chiq"* | `student` | Student Adapter | Reading publication & chapter study |
| *"IELTS speaking qilaylik"*, *"mock interview"* | `language_coach` | IELTS Examiner 2.0 | Interactive speaking session / rubric feedback |
| *"Prezentatsiya tayyorla"*, *"10 slaydli taqdimot"* | `presentation` | Presentation Maker 2.0 | Slide outline + PPTX artifact |
| *"Word hujjat tayyorla"*, *"ariza yozish"* | `document` | Documents & Office Agent | Formatted DOCX / PDF artifact |
| *"Manbalar bilan tadqiqot qil"*, *"fact check"* | `research` | Research Agent | Cited web/source research report |
| *"Rasm chizib ber"*, *"diagramma yarat"* | `visual` | Visual Agent | Image / diagram artifact |
| *"Salom, qandaysan?"*, general inquiries | `general` | General Companion | Conversational response |

### 4.2 Deterministic Fallback & Safety
- If intent classification score is below threshold (`< 2.0`) or requested agent is not available, router deterministically falls back to `Intent.GENERAL` with clear transparency note.
- Irreversible operations (memory purge, file overwrites) require explicit confirmation.

---

## 5. IELTS Examiner 2.0 Contract

### 5.1 Speaking Workflow
- **Part 1 — Introduction & Familiar Topics:** 4–5 questions on hometown, work/study, daily habits.
- **Part 2 — Cue Card (Long Turn):** Prompt with 4 guiding points, 1-minute prep timer, 2-minute response window.
- **Part 3 — Two-way Discussion:** In-depth abstract questions connected to the Part 2 theme.
- **Evaluation & Feedback:** Scores across 4 criteria (Fluency & Coherence, Lexical Resource, Grammatical Range & Accuracy, Pronunciation notes).
- **Disclaimer:** Explicitly displays: *"Ushbu baho norasmiy baholash hisoblanadi (Estimated Band Score) va rasmiy IELTS sertifikati o'rnini bosmaydi."*

### 5.2 Voice / Audio Provider Interface
```python
class VoiceAdapterInterface(ABC):
    @abstractmethod
    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str) -> str:
        """Transcribe learner speech to text."""
        ...

    @abstractmethod
    async def synthesize_speech(self, text: str, voice_id: str) -> bytes:
        """Generate audio stream for examiner prompts."""
        ...

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Indicates if voice service is configured and ready."""
        ...
```
*Fallback:* If voice service is unavailable, the UI seamlessly operates in text-based interactive mode without error.

---

## 6. Presentation Maker 2.0 Contract

### 6.1 Workflow
1. **Intake & Brief:** Accepts topic, audience, slide count (3–20), language, style theme.
2. **Slide Outline Generation:** Generates title, structure, bullet points, key takeaways, and source attribution.
3. **Deck Compilation:** Builds professional `.pptx` presentations using native Python slide layout builders (no external paid design APIs required).
4. **Slide Regeneration:** Supports modifying individual slides or the entire deck based on user revisions.

---

## 7. Documents & Office Contract

### 7.1 Supported Document Workflows
- **DOCX Generation:** Clean styling, standard Uzbek business letterheads, official templates (ariza, xizmat xati, hisobot, CV).
- **Spreadsheet Creation (XLSX / CSV):** Safe numeric formulas, UTF-8 BOM encoding for Excel compatibility, structured headers.
- **PPTX Generation:** Full deck export matching presentation templates.
- **Security:** Macro execution is strictly blocked; XML sanitization is enforced; file size and memory limits apply.

---

## 8. Super Admin & Platform Governance Contract

- **Role Definitions:**
  - `user`: Controls only their personal workspace, memories, goals, documents, and chat history.
  - `super_admin`: Manages platform-level configuration, monitors system health, and inspects global logs.
- **Inviolable Rules:**
  - Subscription status or plan tier NEVER elevates a user to `super_admin`.
  - No user agent may autonomously alter application code or initiate deployments.
  - All admin endpoints require `role == "super_admin"` verification server-side.
