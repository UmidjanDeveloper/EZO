"""ORM models. Importing this package registers every table on `Base.metadata`."""

from ezo_api.db.models.artifacts import (
    Artifact,
    ArtifactVersion,
    StoryAsset,
    StoryNarration,
    StoryProject,
    StoryScene,
    StoryTimeline,
)
from ezo_api.db.models.career import CareerProfile
from ezo_api.db.models.conversation import Conversation, Message
from ezo_api.db.models.document_jobs import DocumentJob, DocumentJobPublication
from ezo_api.db.models.knowledge import (
    DocumentRevision,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    LongDocPart,
    OcrPage,
    VectorEntry,
)
from ezo_api.db.models.language import (
    LanguageGoal,
    LanguageMetric,
    LanguageMistake,
    LanguageSession,
    LanguageTurn,
    LanguageVocabularyItem,
)
from ezo_api.db.models.learning import KnowledgeLibrary, LearnedSource
from ezo_api.db.models.memory import Memory
from ezo_api.db.models.observability import AgentRun, AuditLog, ToolCall
from ezo_api.db.models.official import LegalDocument, LegalRevision, OfficialSyncRun
from ezo_api.db.models.organization import OrganizationAsset, OrganizationProfile
from ezo_api.db.models.personal import PersonalGoal
from ezo_api.db.models.project import Project
from ezo_api.db.models.student import StudentRawRevision
from ezo_api.db.models.study import StudyCard, StudyReview
from ezo_api.db.models.translation import GlossaryTerm
from ezo_api.db.models.user import User

__all__ = [
    "AgentRun",
    "Artifact",
    "ArtifactVersion",
    "AuditLog",
    "CareerProfile",
    "Conversation",
    "DocumentJob",
    "DocumentJobPublication",
    "DocumentRevision",
    "GlossaryTerm",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeLibrary",
    "KnowledgeSource",
    "LanguageGoal",
    "LanguageMetric",
    "LanguageMistake",
    "LanguageSession",
    "LanguageTurn",
    "LanguageVocabularyItem",
    "LearnedSource",
    "LegalDocument",
    "LegalRevision",
    "LongDocPart",
    "Memory",
    "Message",
    "OcrPage",
    "OfficialSyncRun",
    "OrganizationAsset",
    "OrganizationProfile",
    "PersonalGoal",
    "Project",
    "StoryAsset",
    "StoryNarration",
    "StoryProject",
    "StoryScene",
    "StoryTimeline",
    "StudentRawRevision",
    "StudyCard",
    "StudyReview",
    "ToolCall",
    "User",
    "VectorEntry",
]
