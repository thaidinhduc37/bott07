"""Import every model module so SQLAlchemy's declarative registry can resolve
cross-file string relationship targets (e.g. `User.taught_courses` -> `Course`
in academic.py) at mapper-configuration time. Import this module (or anything
that imports it, like `app.db` consumers / alembic's `env.py`) before calling
`Base.metadata.create_all` or `configure_mappers()`.
"""

from app.models import (  # noqa: F401
    academic,
    audit,
    chat,
    documents,
    feedback,
    forms,
    grades,
    learning,
    notes,
    notifications,
    users,
)
from app.models.enums import (  # noqa: F401
    ApprovalActionType,
    ChatMode,
    DocumentType,
    ExamFormat,
    ExamStatus,
    IndexStatus,
    MessageRole,
    NotificationType,
    RoleCode,
    ScheduleStatus,
    SessionType,
    StepStatus,
    SubmissionStatus,
    UserStatus,
)
from app.models.academic import Course, ExamSchedule, Schedule, StudyClass  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.chat import ChatCitation, ChatConversation, ChatMessage  # noqa: F401
from app.models.documents import Document, DocumentVersion  # noqa: F401
from app.models.forms import (  # noqa: F401
    ApprovalAction,
    ApprovalStep,
    FormSubmission,
    FormTemplate,
    SubmissionSigning,
)
from app.models.learning import QuizQuestion, QuizSession, ReviewItem  # noqa: F401
from app.models.notes import StudyNote  # noqa: F401
from app.models.notifications import Notification  # noqa: F401
from app.models.users import ElectronicSignature, RefreshToken, Role, StudentProfile, User, UserRole  # noqa: F401
