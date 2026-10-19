"""Knowledge OS K3 — Capability Analyzer.

Inspects previously learned knowledge sources (websites, GitHub repositories,
Python/npm packages) in a knowledge library to analyze:
1. What the source provides.
2. What capabilities are described.
3. Which of those capabilities EZO already has (tool and agent registry comparison).
4. Which capabilities EZO does not yet have (missing functionality).
5. Relevance to EZO's assistant and productivity mission.
6. Required dependencies and execution permissions.
7. Security and licensing risks.
8. How it could be implemented in future phases.
9. Supporting source-backed evidence (directly_supported vs inferred vs unverified).
10. Incomplete, conflicting, or outdated evidence.

STRICT SECURITY GUARANTEE:
K3 is strictly READ-ONLY analysis and proposal generation.
EZO does not execute code, install packages, create executable tools, or alter runtime.
All proposed capabilities are marked with status="proposal".
All documentation is treated as untrusted data strings; prompt injections are flagged,
never executed.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.base import utcnow
from ezo_api.db.models import DocumentRevision, KnowledgeDocument, KnowledgeLibrary, LearnedSource
from ezo_api.learning.safety import assess_license, scan_text

EvidenceLevel = Literal["directly_supported", "inferred", "unverified"]
RelevanceLevel = Literal["high", "medium", "low", "irrelevant"]
CoverageLevel = Literal["full", "partial", "none"]
LicenseRisk = Literal["safe", "review_needed", "copyleft", "unknown"]

READING = ("queued", "inspecting", "reading", "indexing")
ANALYZER_VERSION = 2
"""Bumped when the analysis logic changes, so cached analyses are recomputed."""
MAX_DOCUMENTS = 50
MAX_CHARS_PER_DOCUMENT = 20_000
# Keyword hits suggest a capability; they never prove it.
INFERRED_CONFIDENCE = 0.55
WEAK_COPYLEFT_PREFIXES = ("lgpl", "mpl", "epl", "cddl")


# -----------------------------------------------------------------------------
# Domain Models
# -----------------------------------------------------------------------------


class SourceEvidence(BaseModel):
    """Direct or inferred evidence from indexed source documentation."""

    document_id: str | None = None
    title: str
    url: str | None = None
    chunk_id: str | None = None
    excerpt: str = Field(
        default="",
        description="Factual snippet from learned documentation (passive untrusted data).",
    )
    evidence_level: EvidenceLevel = "directly_supported"
    outdated_warning: str | None = None


class ExistingEquivalent(BaseModel):
    """Comparison against an existing EZO tool or agent."""

    kind: Literal["tool", "agent"]
    name: str
    coverage: CoverageLevel
    notes: str


class ProposedCapability(BaseModel):
    """A structured capability proposal derived from learned knowledge.

    Always has status='proposal'. Never installed or executed in K3.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(
        description="Standardized capability identifier, e.g. 'pdf_table_export' or 'ast_analysis'."
    )
    title: str = Field(description="Human-readable title in title case.")
    description: str = Field(description="Detailed explanation of what this capability does.")
    category: str = Field(
        default="general",
        description=(
            "Domain category: document, data_processing, networking, "
            "media, security, developer, official."
        ),
    )
    relevance: RelevanceLevel = "medium"
    relevance_reason: str = Field(description="Why this is or is not relevant to EZO's mission.")
    is_already_supported: bool = False
    existing_equivalents: list[ExistingEquivalent] = Field(default_factory=list)
    missing_functionality: str = Field(
        description="Specific features EZO currently lacks that this capability would provide."
    )
    required_dependencies: list[str] = Field(
        default_factory=list, description="Third-party packages, libraries, or external binaries."
    )
    required_permissions: list[str] = Field(
        default_factory=list,
        description=(
            "Required security boundaries: file_read, file_write, "
            "network_outbound, isolated_sandbox."
        ),
    )
    compatibility_notes: str = ""
    security_notes: str = ""
    licensing_notes: str = ""
    evidence: list[SourceEvidence] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    evidence_gaps: list[str] = Field(default_factory=list)
    recommended_next_step: str = ""
    status: Literal["proposal"] = "proposal"


class SourceCapabilityAnalysis(BaseModel):
    """Capability analysis report for an individual learned source."""

    source_id: str
    source_title: str
    source_target: str
    source_kind: str
    source_version: str | None = None
    license: str | None = None
    license_risk: LicenseRisk = "unknown"
    main_purpose: str = ""
    security_flags_count: int = 0
    capabilities: list[ProposedCapability] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    is_incomplete: bool = False
    analyzed_at: datetime = Field(default_factory=utcnow)
    status: Literal["proposal"] = "proposal"


class LibraryCapabilityReport(BaseModel):
    """Aggregate capability analysis report across all sources in a knowledge library."""

    library_id: str
    library_name: str
    sources_count: int = 0
    analyzed_sources_count: int = 0
    capabilities_count: int = 0
    proposals: list[ProposedCapability] = Field(default_factory=list)
    existing_capabilities_overlap: list[str] = Field(default_factory=list)
    missing_capabilities_highlight: list[str] = Field(default_factory=list)
    security_warnings: list[str] = Field(default_factory=list)
    evidence_limitations: list[str] = Field(default_factory=list)
    status: Literal["proposal"] = "proposal"
    generated_at: datetime = Field(default_factory=utcnow)


# -----------------------------------------------------------------------------
# Active EZO Capabilities Registry Knowledge
# -----------------------------------------------------------------------------

# Ground truth of existing tools in EZO's ToolRegistry
EZO_TOOL_PROFILES: dict[str, dict[str, Any]] = {
    "knowledge_search": {
        "title": "Knowledge Search",
        "category": "knowledge",
        "description": (
            "Semantic and keyword retrieval across user and learned knowledge documents."
        ),
        "keywords": ["search", "knowledge", "retrieval", "vector", "embedding", "rag", "index"],
    },
    "web_search": {
        "title": "Web Search",
        "category": "networking",
        "description": (
            "Live search engine queries (Tavily/Anthropic) to discover web pages and citations."
        ),
        "keywords": ["web search", "google", "bing", "search engine", "queries"],
    },
    "web_fetch": {
        "title": "Safe Web Fetcher",
        "category": "networking",
        "description": (
            "Fetches and parses public web pages with SSRF prevention and robots.txt compliance."
        ),
        "keywords": ["http", "crawl", "fetch", "html", "scrape", "request", "download", "url"],
    },
    "read_document": {
        "title": "Document Reader",
        "category": "document",
        "description": "Extracts text and metadata from uploaded DOCX, PDF, XLSX, and TXT files.",
        "keywords": [
            "read document",
            "parse document",
            "extract text",
            "docx",
            "pdf",
            "xlsx",
            "file reader",
        ],
    },
    "create_document": {
        "title": "Word Document Creator",
        "category": "document",
        "description": "Generates professional Microsoft Word (.docx) documents with styling.",
        "keywords": ["word", "docx", "write document", "create document", "report generation"],
    },
    "create_spreadsheet": {
        "title": "Spreadsheet Creator",
        "category": "document",
        "description": (
            "Creates Microsoft Excel (.xlsx) and CSV spreadsheets with formulas and headers."
        ),
        "keywords": ["excel", "xlsx", "csv", "spreadsheet", "workbook", "table", "data sheet"],
    },
    "sheet_ops": {
        "title": "Spreadsheet Operations",
        "category": "document",
        "description": (
            "Applies transformations, row filtering, sorting, and recalculations to spreadsheets."
        ),
        "keywords": ["sheet ops", "filter rows", "sort columns", "spreadsheet math"],
    },
    "create_presentation": {
        "title": "Presentation Creator",
        "category": "presentation",
        "description": "Generates multi-slide Microsoft PowerPoint (.pptx) decks.",
        "keywords": ["powerpoint", "pptx", "slides", "deck", "presentation"],
    },
    "generate_image": {
        "title": "Image Generator",
        "category": "media",
        "description": "Generates images via AI visual models.",
        "keywords": ["generate image", "text to image", "illustration", "art", "picture"],
    },
    "edit_image": {
        "title": "Image Editor",
        "category": "media",
        "description": "Modifies or transforms existing images.",
        "keywords": ["edit image", "image modification", "image filter", "crop", "resize"],
    },
    "create_graphic": {
        "title": "Graphic & Diagram Creator",
        "category": "media",
        "description": "Renders vector graphics, diagrams, flowcharts, and SVG charts.",
        "keywords": ["diagram", "svg", "chart", "graph", "flowchart", "infographic"],
    },
    "pdf_tool": {
        "title": "PDF Processor",
        "category": "document",
        "description": "Extracts page ranges, text, and renders page previews from PDF files.",
        "keywords": ["pdf", "pdf extract", "pdf pages", "split pdf", "merge pdf"],
    },
    "office_pdf": {
        "title": "Office to PDF Converter",
        "category": "document",
        "description": "Converts DOCX, PPTX, and XLSX files to PDF format via LibreOffice.",
        "keywords": ["convert to pdf", "office pdf", "libreoffice", "export pdf"],
    },
    "ocr_tool": {
        "title": "Optical Character Recognition",
        "category": "document",
        "description": "Extracts text from images and scanned documents using Tesseract OCR.",
        "keywords": [
            "ocr",
            "tesseract",
            "scanned document",
            "image to text",
            "optical recognition",
        ],
    },
    "ocr_export": {
        "title": "OCR Exporter",
        "category": "document",
        "description": "Exports OCR results to structured formats.",
        "keywords": ["ocr export", "hocr", "searchable pdf"],
    },
    "extract_tables": {
        "title": "Table Extractor",
        "category": "document",
        "description": "Detects and extracts structured tabular data from PDF files and images.",
        "keywords": ["extract table", "table detection", "tabular data", "pdf table", "camelot"],
    },
    "official_search": {
        "title": "Official Legislation Search",
        "category": "official",
        "description": "Searches synchronized Uzbekistan official legislation from LEX.UZ.",
        "keywords": ["lex.uz", "legislation", "law", "qonun", "qaror", "official act"],
    },
    "verify_official_document": {
        "title": "Official Document Verifier",
        "category": "official",
        "description": (
            "Verifies current legal validity and dates of official government documents."
        ),
        "keywords": ["verify law", "currentness", "amendment", "lexuz verification"],
    },
}

# Domains of EZO's agents; availability is read from the live agent catalog (AGENTS), so
# a planned agent is never reported as existing.
EZO_AGENT_PROFILES: dict[str, dict[str, Any]] = {
    "general": {"title": "General Companion", "domain": "conversation"},
    "language_coach": {"title": "Language Coach", "domain": "education"},
    "presentation": {"title": "Presentation Agent", "domain": "presentation"},
    "developer": {
        "title": "Developer Agent",
        "domain": "coding",
        "note": "Planned: repository access, running tests, git operations.",
    },
    "legal_research": {"title": "Legal Research Agent", "domain": "legal"},
    "research": {"title": "Research Agent", "domain": "research"},
    "document": {"title": "Document Agent", "domain": "document"},
    "business": {"title": "Business Agent", "domain": "business"},
    "visual": {"title": "Visual Agent", "domain": "media"},
    "knowledge_os": {"title": "Knowledge OS", "domain": "learning"},
}


# -----------------------------------------------------------------------------
# Comparison and Matching Engine
# -----------------------------------------------------------------------------


def _agent_available(key: str) -> bool:
    from ezo_api.agents.catalog import AGENTS

    return any(spec.key == key and spec.available for spec in AGENTS.values())


def _match_ezo_equivalents(
    name: str,
    description: str,
    keywords: list[str],
    registered_tools: list[str] | None = None,
) -> list[ExistingEquivalent]:
    """Compare a proposed capability against the tools registered in this EZO instance and
    its agents (whole-word matches only). A domain match with an agent is "partial": the
    agent works in that area, which does not mean it has this capability."""
    search_text = f"{name} {description} {' '.join(keywords)}".lower().replace("_", " ")
    matches: list[ExistingEquivalent] = []
    available_tools = set(registered_tools) if registered_tools is not None else None

    # Check tools
    for tool_name, profile in EZO_TOOL_PROFILES.items():
        if available_tools is not None and tool_name not in available_tools:
            continue
        hits = 0
        for kw in profile["keywords"]:
            if re.search(r"\b" + re.escape(kw) + r"\b", search_text):
                hits += 1
        if hits > 0:
            coverage: CoverageLevel = "full" if hits >= 3 else "partial"
            matches.append(
                ExistingEquivalent(
                    kind="tool",
                    name=tool_name,
                    coverage=coverage,
                    notes=f"EZO already includes `{tool_name}`: {profile['description']}",
                )
            )

    # Check agents
    for agent_key, agent_profile in EZO_AGENT_PROFILES.items():
        domain = agent_profile["domain"]
        if re.search(rf"\b{re.escape(domain)}\b", search_text):
            available = _agent_available(agent_key)
            agent_coverage: CoverageLevel = "partial" if available else "none"
            note_str = (
                f"The `{agent_key}` agent works in this area ({domain})."
                if available
                else (
                    f"Part of `{agent_key}` agent "
                    "(status: planned, not currently active in runtime)."
                )
            )
            matches.append(
                ExistingEquivalent(
                    kind="agent",
                    name=agent_key,
                    coverage=agent_coverage,
                    notes=note_str,
                )
            )

    return matches


def _assess_license_risk(
    license_name: str | None, profile_review: dict[str, Any] | None
) -> tuple[LicenseRisk, str]:
    """Determine license compatibility and risk for EZO proposals."""
    if not license_name and not profile_review:
        return (
            "unknown",
            "No license detected in source. Code or design patterns must be reviewed before reuse.",
        )

    review = profile_review or {}
    category = review.get("category")
    if not category and license_name:
        assessment = assess_license(license_name)
        category = assessment.get("category")
    if category == "copyleft_or_restricted":
        # safety.assess_license's category for GPL, AGPL, LGPL, MPL, SSPL, BUSL…
        name = str(license_name or review.get("license") or "").lower()
        category = "weak_copyleft" if name.startswith(WEAK_COPYLEFT_PREFIXES) else "copyleft"

    if category == "permissive":
        return (
            "safe",
            f"Permissive license ({license_name or 'standard'}). Compatible with EZO integration.",
        )
    if category == "copyleft":
        return (
            "copyleft",
            (
                f"Copyleft license ({license_name or 'GPL-like'}). Requires license isolation "
                "or cleanroom reimplementation to avoid license contamination."
            ),
        )
    if category == "weak_copyleft":
        return (
            "review_needed",
            (
                f"Weak copyleft ({license_name or 'LGPL/MPL'}). "
                "Dynamic linking or service isolation required."
            ),
        )
    if category == "other":
        return (
            "review_needed",
            f"Unrecognised licence ({license_name}). Legal review needed before reusing code.",
        )
    return "unknown", f"License '{license_name or 'unknown'}' needs legal and architecture review."


def _sanitize_untrusted_text(text: str, max_chars: int = 400) -> str:
    """Normalize and truncate documentation text for passive storage. It stays untrusted:
    callers show it only as quoted data, never as instructions."""
    clean = re.sub(r"\s+", " ", text).strip()
    return clean[:max_chars]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:80] or "source"


def _unique_flags(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for flag in flags:
        key = (str(flag.get("kind")), str(flag.get("location")), str(flag.get("excerpt")))
        if key not in seen:
            seen.add(key)
            unique.append(dict(flag))
    return unique


# -----------------------------------------------------------------------------
# Capability Analyzer Service
# -----------------------------------------------------------------------------


class CapabilityAnalyzer:
    """Read-only service that analyzes learned knowledge sources and formulates

    structured capability proposals.
    """

    def __init__(self, registered_tools: list[str] | None = None) -> None:
        self.registered_tools = registered_tools or list(EZO_TOOL_PROFILES.keys())

    async def analyze_source(
        self,
        session: AsyncSession,
        source: LearnedSource,
    ) -> SourceCapabilityAnalysis:
        """Inspect one LearnedSource and its documents to formulate capability proposals."""
        # 1. Gather documents and revisions
        stmt = (
            select(
                KnowledgeDocument,
                func.substr(DocumentRevision.raw_text, 1, MAX_CHARS_PER_DOCUMENT),
            )
            .outerjoin(
                DocumentRevision,
                DocumentRevision.id == KnowledgeDocument.current_revision_id,
            )
            .where(KnowledgeDocument.source_id == source.knowledge_source_id)
            .order_by(KnowledgeDocument.created_at)
            .limit(MAX_DOCUMENTS)
        )
        results = (await session.execute(stmt)).all()

        profile = source.profile or {}
        license_name = source.license or profile.get("license")
        license_review = profile.get("license_review")
        lic_risk, lic_notes = _assess_license_risk(license_name, license_review)

        # 2. Check for security flags and prompt injection (a copy: the stored K1 list is
        # never changed here, and a passage K1 already flagged is not counted twice).
        sec_flags = [dict(flag) for flag in source.security_flags or []]
        doc_texts: list[tuple[str, str, str | None, str]] = []  # (doc_id, title, url, text)

        for doc, raw_text in results:
            text = raw_text or ""
            doc_texts.append((str(doc.id), doc.title, doc.source_url, text))
            # Scan for any additional injection attempts not yet flagged
            injections = scan_text(text, doc.source_url or doc.title)
            for inj in injections:
                sec_flags.append(inj.as_dict())
        sec_flags = _unique_flags(sec_flags)

        # 3. Main purpose extraction
        main_purpose = (
            profile.get("summary")
            or profile.get("description")
            or (doc_texts[0][3][:200] if doc_texts else "")
            or f"{source.kind} package {source.title}"
        )
        main_purpose = _sanitize_untrusted_text(main_purpose, 250)

        # 4. Formulate capability proposals based on source data
        capabilities = self._extract_proposals_from_source(
            source=source,
            main_purpose=main_purpose,
            license_risk=lic_risk,
            lic_notes=lic_notes,
            doc_texts=doc_texts,
            sec_flags=sec_flags,
        )

        # 5. Assess evidence gaps & completeness
        evidence_gaps: list[str] = []
        is_incomplete = False

        if source.status != "indexed":
            is_incomplete = True
            evidence_gaps.append(
                f"Source status is '{source.status}'; documentation reading was incomplete "
                "or encountered limits."
            )

        if not doc_texts:
            is_incomplete = True
            evidence_gaps.append("No indexed document revisions found for this source.")

        if sec_flags:
            evidence_gaps.append(
                f"Detected {len(sec_flags)} prompt injection or directive patterns; "
                "external text was strictly treated as passive data."
            )

        analysis = SourceCapabilityAnalysis(
            source_id=str(source.id),
            source_title=source.title,
            source_target=source.target,
            source_kind=source.kind,
            source_version=source.version,
            license=license_name,
            license_risk=lic_risk,
            main_purpose=main_purpose,
            security_flags_count=len(sec_flags),
            capabilities=capabilities,
            evidence_gaps=evidence_gaps,
            is_incomplete=is_incomplete,
            analyzed_at=utcnow(),
            status="proposal",
        )

        # Cache for reuse: a new dict (an in-place change of the JSON column would not be
        # saved), tied to the content read and the analyzer version.
        source.profile = {
            **profile,
            "capability_analysis": {
                **analysis.model_dump(mode="json"),
                "content_hash": source.content_hash,
                "analyzer_version": ANALYZER_VERSION,
            },
        }
        session.add(source)

        return analysis

    async def analyze_library(
        self,
        session: AsyncSession,
        library: KnowledgeLibrary,
    ) -> LibraryCapabilityReport:
        """Inspect all learned sources within a knowledge library, aggregate

        proposals, eliminate duplicates, and compare with EZO's active registry.
        """
        stmt = (
            select(LearnedSource)
            .where(LearnedSource.library_id == library.id)
            .order_by(LearnedSource.created_at)
        )
        sources = (await session.scalars(stmt)).all()

        if not sources:
            return LibraryCapabilityReport(
                library_id=str(library.id),
                library_name=library.name,
                sources_count=0,
                analyzed_sources_count=0,
                capabilities_count=0,
                proposals=[],
                existing_capabilities_overlap=[],
                missing_capabilities_highlight=[],
                security_warnings=[],
                evidence_limitations=[
                    (
                        "Library has no learned sources yet. Learn a website, GitHub repository, "
                        "or Python/npm package to enable capability analysis."
                    )
                ],
                status="proposal",
                generated_at=utcnow(),
            )

        all_proposals: list[ProposedCapability] = []
        security_warnings: list[str] = []
        evidence_limitations: list[str] = []
        analyzed_count = 0

        for src in sources:
            if src.status in READING:
                evidence_limitations.append(
                    f"Source '{src.title}' is still being read; analyse it again when it is done."
                )
                continue
            source_analysis = await self.analyze_source(session, src)
            analyzed_count += 1
            all_proposals.extend(source_analysis.capabilities)

            if source_analysis.security_flags_count > 0:
                security_warnings.append(
                    f"Source '{src.title}' ({src.target}) triggered "
                    f"{source_analysis.security_flags_count} security/prompt-injection flag(s)."
                )
            if source_analysis.is_incomplete:
                evidence_limitations.append(
                    f"Source '{src.title}' has incomplete evidence: "
                    f"{'; '.join(source_analysis.evidence_gaps)}"
                )

        # Deduplicate proposals across sources in the library
        deduped_proposals = self._deduplicate_proposals(all_proposals)

        # Categorize into existing vs missing capabilities
        existing_overlap: list[str] = []
        missing_highlights: list[str] = []

        for p in deduped_proposals:
            if p.is_already_supported:
                tool_names = [e.name for e in p.existing_equivalents if e.kind == "tool"]
                covered_str = ", ".join(tool_names) if tool_names else "existing tools"
                existing_overlap.append(f"{p.title} (already covered by {covered_str})")
            else:
                missing_highlights.append(f"{p.title}: {p.missing_functionality}")

        report = LibraryCapabilityReport(
            library_id=str(library.id),
            library_name=library.name,
            sources_count=len(sources),
            analyzed_sources_count=analyzed_count,
            capabilities_count=len(deduped_proposals),
            proposals=deduped_proposals,
            existing_capabilities_overlap=existing_overlap,
            missing_capabilities_highlight=missing_highlights,
            security_warnings=security_warnings,
            evidence_limitations=evidence_limitations,
            status="proposal",
            generated_at=utcnow(),
        )

        return report

    # -------------------------------------------------------------------------
    # Proposal Extraction & Heuristics (Deterministic Engine)
    # -------------------------------------------------------------------------

    def _extract_proposals_from_source(
        self,
        source: LearnedSource,
        main_purpose: str,
        license_risk: LicenseRisk,
        lic_notes: str,
        doc_texts: list[tuple[str, str, str | None, str]],
        sec_flags: list[dict[str, Any]],
    ) -> list[ProposedCapability]:
        """Formulate capability proposals from the source profile and document corpus."""
        # Combine text for topic & feature scanning
        combined_text = (main_purpose + " " + " ".join(t[3][:1000] for t in doc_texts[:5])).lower()

        proposals: list[ProposedCapability] = []

        # 1. Primary capability representing the library's core function
        primary_proposal = self._build_primary_proposal(
            source=source,
            main_purpose=main_purpose,
            license_risk=license_risk,
            lic_notes=lic_notes,
            doc_texts=doc_texts,
            combined_text=combined_text,
            sec_flags=sec_flags,
        )
        proposals.append(primary_proposal)

        # 2. Specialized sub-capabilities based on recognized features in documentation
        sub_proposals = self._extract_sub_capabilities(
            source=source,
            doc_texts=doc_texts,
            combined_text=combined_text,
            lic_notes=lic_notes,
            sec_flags=sec_flags,
        )
        proposals.extend(sub_proposals)

        return proposals

    def _build_primary_proposal(
        self,
        source: LearnedSource,
        main_purpose: str,
        license_risk: LicenseRisk,
        lic_notes: str,
        doc_texts: list[tuple[str, str, str | None, str]],
        combined_text: str,
        sec_flags: list[dict[str, Any]],
    ) -> ProposedCapability:
        """Construct the central capability proposal for the learned package/repo."""
        slug_name = _slug(source.title)
        clean_title = _sanitize_untrusted_text(
            source.title.replace("_", " ").replace("-", " "), 80
        ).title()
        registry_summary = bool((source.profile or {}).get("description"))

        # Build evidence
        evidence_list: list[SourceEvidence] = []
        if doc_texts:
            first_doc = doc_texts[0]
            excerpt = _sanitize_untrusted_text(first_doc[3], 300) or main_purpose
            evidence_list.append(
                SourceEvidence(
                    document_id=first_doc[0],
                    title=first_doc[1],
                    url=first_doc[2],
                    excerpt=excerpt,
                    # The opening of a document is context, not a stated capability.
                    evidence_level="inferred",
                    outdated_warning="Source version may differ from current release"
                    if not source.version
                    else None,
                )
            )
        else:
            evidence_list.append(
                SourceEvidence(
                    title=source.title,
                    excerpt=main_purpose,
                    evidence_level="inferred",
                    outdated_warning=(
                        "No full document text indexed; inferred from package metadata."
                    ),
                )
            )

        # Check existing equivalents in EZO registry
        profile = source.profile or {}
        raw_keywords = profile.get("keywords")
        keywords: list[str] = []
        if isinstance(raw_keywords, list):
            keywords.extend(str(k) for k in raw_keywords)
        elif isinstance(raw_keywords, str):
            keywords.extend(raw_keywords.split())
        raw_classifiers = profile.get("classifiers")
        if isinstance(raw_classifiers, list):
            keywords.extend(str(c) for c in raw_classifiers)
        equivalents = _match_ezo_equivalents(
            slug_name, main_purpose, keywords, self.registered_tools
        )

        is_already_covered = any(e.kind == "tool" and e.coverage == "full" for e in equivalents)

        # Determine relevance and domain
        category = self._detect_category(combined_text, source.kind)
        relevance = self._assess_relevance(category, combined_text)
        relevance_reason = self._explain_relevance(category, relevance)

        # Missing functionality assessment
        missing = self._determine_missing_functionality(
            source=source,
            category=category,
            equivalents=equivalents,
            is_already_covered=is_already_covered,
        )

        # Dependencies and permissions
        deps = self._extract_dependencies(source)
        permissions = self._determine_permissions(category, combined_text)

        # Security notes
        sec_notes_parts = [lic_notes]
        if sec_flags:
            sec_notes_parts.append(
                f"ATTENTION: Source contains {len(sec_flags)} untrusted instruction flag(s). "
                "Sandbox isolation mandatory."
            )
        sec_notes_parts.append(
            "Read-only proposal. Tool implementation requires validation in K4 Sandbox."
        )

        return ProposedCapability(
            id=str(uuid.uuid4()),
            name=f"{slug_name}_integration",
            title=f"{clean_title} Integration",
            # Written from a template: documentation text never becomes the description
            # (it may contain instructions); the purpose is in the evidence excerpt.
            description=(
                f"Use the {source.kind} source “{clean_title}” in EZO. What it does is "
                "described in its documentation (see the evidence excerpt); EZO has not "
                "verified it."
            ),
            category=category,
            relevance=relevance,
            relevance_reason=relevance_reason,
            is_already_supported=is_already_covered,
            existing_equivalents=equivalents,
            missing_functionality=missing,
            required_dependencies=deps,
            required_permissions=permissions,
            compatibility_notes=(
                f"Source format: {source.kind}, target: {source.target}, "
                f"version: {source.version or 'unspecified'}."
            ),
            security_notes="; ".join(sec_notes_parts),
            licensing_notes=lic_notes,
            evidence=evidence_list,
            confidence=(0.6 if registry_summary else INFERRED_CONFIDENCE) if doc_texts else 0.45,
            evidence_gaps=[]
            if doc_texts
            else ["Full documentation not indexed; proposal based on package summary."],
            recommended_next_step=(
                "Draft capability schema and permission boundary for K4 Sandbox review."
            ),
            status="proposal",
        )

    def _extract_sub_capabilities(
        self,
        source: LearnedSource,
        doc_texts: list[tuple[str, str, str | None, str]],
        combined_text: str,
        lic_notes: str,
        sec_flags: list[dict[str, Any]],
    ) -> list[ProposedCapability]:
        """Detect specialized modular capabilities documented within the source."""
        sub_caps: list[ProposedCapability] = []

        # Feature detectors: (pattern, name, title, category, description, missing_fn)
        detectors = [
            (
                r"\b(pdf|pypdf|fitz|pdfplumber|form[ _]fill|annotation|decrypt)\b",
                "pdf_advanced_ops",
                "Advanced PDF Annotation & Form Handling",
                "document",
                (
                    "Programmatically fill PDF forms, manage annotations, "
                    "and decrypt password-protected files."
                ),
                (
                    "EZO's current `pdf_tool` and `office_pdf` tools extract pages and text, "
                    "but lack interactive form filling and signature verification."
                ),
            ),
            (
                r"\b(table[ _]extract|camelot|tabula|detect[ _]table)\b",
                "high_accuracy_table_detection",
                "High-Accuracy Table Geometry Detection",
                "document",
                (
                    "Detect borderless tables and complex merged cells "
                    "in scanned and native documents."
                ),
                (
                    "EZO's `extract_tables` tool handles standard tables; this improves "
                    "recognition for unbordered and irregular data matrices."
                ),
            ),
            (
                r"\b(ast|abstract syntax tree|lint|parse[ _]code|code[ _]analysis)\b",
                "code_ast_inspection",
                "Static AST Code Inspection",
                "developer",
                (
                    "Analyze code structure, detect syntax patterns, and verify "
                    "code smells without execution."
                ),
                (
                    "EZO does not currently have static code analysis tools "
                    "(Developer Agent is planned for Phase 9)."
                ),
            ),
            (
                r"\b(audio|transcribe|speech|whisper|wav|mp3|sound)\b",
                "audio_stream_transcription",
                "Audio Stream & Speech Transcription",
                "media",
                "Process and transcribe recorded audio files into timestamped text.",
                (
                    "EZO's `VoiceService` handles live conversation audio, "
                    "but lacks offline audio file batch transcription."
                ),
            ),
            (
                r"\b(chart|plot|matplotlib|seaborn|plotly|data[ _]viz)\b",
                "advanced_data_visualization",
                "Statistical Data Chart Generation",
                "media",
                (
                    "Render complex statistical charts, boxplots, heatmaps, "
                    "and interactive distributions."
                ),
                (
                    "EZO's `create_graphic` generates infographics and flowcharts; "
                    "statistical multi-dimensional plotting would complement it."
                ),
            ),
            (
                r"\b(cryptography|cipher|signature|x509|verify[ _]cert)\b",
                "cryptographic_verification",
                "Cryptographic Signature & Certificate Verification",
                "security",
                (
                    "Inspect digital signatures, certificates, and hash validation "
                    "for signed documents."
                ),
                (
                    "EZO has `verify_official_document` for legislation text matching, "
                    "but no cryptographic digital signature tool."
                ),
            ),
        ]

        for pattern, name, title, category, description, missing_fn in detectors:
            if re.search(pattern, combined_text, re.IGNORECASE):
                # Search for supporting doc snippet
                evidence_items: list[SourceEvidence] = []
                term = ""
                for doc_id, doc_title, url, text in doc_texts:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        term = match.group(0).lower()
                        start = max(0, match.start() - 60)
                        end = min(len(text), match.end() + 150)
                        snippet = _sanitize_untrusted_text(text[start:end], 250)
                        evidence_items.append(
                            SourceEvidence(
                                document_id=doc_id,
                                title=doc_title,
                                url=url,
                                excerpt=snippet,
                                # A keyword in the text suggests the feature; a person must
                                # confirm it from the documentation.
                                evidence_level="inferred",
                            )
                        )
                        break

                if not evidence_items:
                    evidence_items.append(
                        SourceEvidence(
                            title=source.title,
                            excerpt=(
                                f"Identified from keywords and topic mentions in {source.title}."
                            ),
                            evidence_level="inferred",
                        )
                    )

                equivs = _match_ezo_equivalents(name, description, [], self.registered_tools)
                is_supported = any(e.kind == "tool" and e.coverage == "full" for e in equivs)
                mentioned = f" (the documentation mentions “{term}”)" if term else ""
                security = lic_notes
                if sec_flags:
                    security += (
                        f"; ATTENTION: the source contains {len(sec_flags)} passage(s) that "
                        "try to instruct an AI; treated as data."
                    )

                sub_caps.append(
                    ProposedCapability(
                        id=str(uuid.uuid4()),
                        name=f"{_slug(source.title)}_{name}",
                        title=title,
                        description=f"Possible capability{mentioned}: {description} "
                        "Not verified: confirm it in the documentation.",
                        category=category,
                        relevance="high"
                        if category in ("document", "developer", "media")
                        else "medium",
                        relevance_reason=(
                            f"Directly extends EZO's {category} capabilities "
                            "based on learned documentation."
                        ),
                        is_already_supported=is_supported,
                        existing_equivalents=equivs,
                        missing_functionality=missing_fn,
                        required_dependencies=[f"{source.target} (source)"],
                        required_permissions=["file_read", "isolated_sandbox"],
                        compatibility_notes=(
                            "Requires isolated execution environment with strict memory/CPU quotas."
                        ),
                        security_notes=security,
                        licensing_notes=lic_notes,
                        evidence=evidence_items,
                        confidence=INFERRED_CONFIDENCE if term else 0.4,
                        evidence_gaps=[
                            "Inferred from a keyword; the exact feature is not confirmed."
                        ],
                        recommended_next_step="Evaluate as an optional plugin in Phase K4.",
                        status="proposal",
                    )
                )

        return sub_caps

    def _deduplicate_proposals(
        self, proposals: list[ProposedCapability]
    ) -> list[ProposedCapability]:
        """Merge identical or highly similar proposals across multiple sources in a library."""
        deduped: dict[str, ProposedCapability] = {}

        for p in proposals:
            # Normalize key based on title or category
            norm_key = re.sub(r"[^a-z0-9]", "", p.title.lower())
            if norm_key in deduped:
                # Merge evidence
                existing = deduped[norm_key]
                existing.evidence.extend(p.evidence)
                # Keep the higher confidence
                existing.confidence = max(existing.confidence, p.confidence)
                # Union dependencies
                merged_deps = set(existing.required_dependencies) | set(p.required_dependencies)
                existing.required_dependencies = sorted(merged_deps)
                # Keep every source's security and licensing warnings.
                for attr in ("security_notes", "licensing_notes"):
                    notes = [n for n in (getattr(existing, attr), getattr(p, attr)) if n]
                    setattr(existing, attr, "; ".join(dict.fromkeys(notes)))
            else:
                deduped[norm_key] = p

        return list(deduped.values())

    # -------------------------------------------------------------------------
    # Heuristics & Helpers
    # -------------------------------------------------------------------------

    def _detect_category(self, text: str, kind: str) -> str:
        """Whole words only ("stable" is not "table", "rapid" is not "api")."""

        def has(*words: str) -> bool:
            return any(re.search(rf"\b{re.escape(w)}s?\b", text) for w in words)

        if has("pdf", "docx", "document", "xlsx", "table", "csv", "office"):
            return "document"
        if has("http", "api", "request", "crawl", "web", "socket", "network"):
            return "networking"
        if has("image", "photo", "chart", "diagram", "video", "audio", "media"):
            return "media"
        if has("security", "crypto", "auth", "certificate", "token", "hash"):
            return "security"
        if has("ast", "compiler", "git", "repo", "test", "lint", "code"):
            return "developer"
        if has("law", "legal", "official", "lex", "legislation"):
            return "official"
        return "data_processing"

    def _assess_relevance(self, category: str, text: str) -> RelevanceLevel:
        # High relevance categories for EZO
        if category in ("document", "official", "developer", "media"):
            return "high"
        if category in ("networking", "security", "data_processing"):
            return "medium"
        # Check for irrelevant technologies (e.g. mobile GUI, microcontroller firmware)
        if any(
            w in text for w in ("ios swift", "arduino", "stm32", "flutter widget", "android view")
        ):
            return "low"
        return "medium"

    def _explain_relevance(self, category: str, relevance: RelevanceLevel) -> str:
        relevance_map = {
            "high": (
                f"Highly relevant to EZO: directly enhances core {category} "
                "processing and user productivity."
            ),
            "medium": (
                f"Moderately relevant: provides useful utility for backend {category} "
                "tasks or data transforms."
            ),
            "low": (
                "Low relevance: outside EZO's primary server and browser AI assistant architecture."
            ),
            "irrelevant": "Not relevant to EZO's mission.",
        }
        return relevance_map.get(relevance, "Relevance based on general utility.")

    def _determine_missing_functionality(
        self,
        source: LearnedSource,
        category: str,
        equivalents: list[ExistingEquivalent],
        is_already_covered: bool,
    ) -> str:
        if is_already_covered:
            return (
                f"EZO already provides standard {category} capabilities via existing tools. "
                "Specific edge-case APIs or higher throughput parsing may be missing."
            )
        if equivalents:
            matched_names = ", ".join(e.name for e in equivalents)
            return (
                f"EZO partially supports this domain via `{matched_names}`, "
                f"but lacks the specialized, format-specific features provided by {source.title}."
            )
        return (
            f"EZO currently does not have a dedicated tool or agent for {category} "
            f"capabilities provided by {source.title}."
        )

    def _extract_dependencies(self, source: LearnedSource) -> list[str]:
        deps: list[str] = [f"{source.target} (target)"]
        profile = source.profile or {}
        req_dist = profile.get("requires_dist") or profile.get("dependencies") or []
        if isinstance(req_dist, list):
            for d in req_dist[:5]:
                deps.append(str(d))
        return deps

    def _determine_permissions(self, category: str, text: str) -> list[str]:
        perms = ["isolated_sandbox"]
        if category in ("document", "media", "data_processing"):
            perms.extend(["file_read", "file_write"])
        if category == "networking" or "network" in text or "http" in text:
            perms.append("network_outbound")
        return sorted(set(perms))


def cached_analysis(source: LearnedSource) -> SourceCapabilityAnalysis | None:
    """The stored analysis when it still matches the source's content and this analyzer."""
    cached = (source.profile or {}).get("capability_analysis")
    if (
        not isinstance(cached, dict)
        or cached.get("analyzer_version") != ANALYZER_VERSION
        or cached.get("content_hash") != source.content_hash
    ):
        return None
    data = {k: v for k, v in cached.items() if k not in ("content_hash", "analyzer_version")}
    return SourceCapabilityAnalysis.model_validate(data)
