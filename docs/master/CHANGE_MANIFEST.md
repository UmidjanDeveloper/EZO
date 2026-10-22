# Master candidate change manifest

Foundation: Draft PR21 at `3ec6cf1cfc7e90588f8c3c2a033a255c3ff70c0b` is preserved. The list below is the
master candidate delta, not a claim that the entire prior PR is independently approved.
New candidate commits are based on PR21; comparing against integration also shows
PR21’s preserved provider/IELTS/beta changes. No frontend file is changed here.

- [.github/workflows/ci.yml](../../.github/workflows/ci.yml)
- [.github/workflows/security.yml](../../.github/workflows/security.yml)
- [apps/api/migrations/versions/0019_student_review_cards.py](../../apps/api/migrations/versions/0019_student_review_cards.py)
- [apps/api/pyproject.toml](../../apps/api/pyproject.toml)
- [apps/api/src/ezo_api/api/routes/improvements.py](../../apps/api/src/ezo_api/api/routes/improvements.py)
- [apps/api/src/ezo_api/api/routes/student_study.py](../../apps/api/src/ezo_api/api/routes/student_study.py)
- [apps/api/src/ezo_api/db/models/__init__.py](../../apps/api/src/ezo_api/db/models/__init__.py)
- [apps/api/src/ezo_api/db/models/study.py](../../apps/api/src/ezo_api/db/models/study.py)
- [apps/api/src/ezo_api/deployment.py](../../apps/api/src/ezo_api/deployment.py)
- [apps/api/src/ezo_api/main.py](../../apps/api/src/ezo_api/main.py)
- [apps/api/src/ezo_api/student/learning.py](../../apps/api/src/ezo_api/student/learning.py)
- [apps/api/src/ezo_api/student/provenance.py](../../apps/api/src/ezo_api/student/provenance.py)
- [apps/api/src/ezo_api/student/study.py](../../apps/api/src/ezo_api/student/study.py)
- [apps/api/src/ezo_api/student/synthesis.py](../../apps/api/src/ezo_api/student/synthesis.py)
- [apps/api/tests/integration/test_database_readiness.py](../../apps/api/tests/integration/test_database_readiness.py)
- [apps/api/tests/integration/test_improvement_proposals.py](../../apps/api/tests/integration/test_improvement_proposals.py)
- [apps/api/tests/integration/test_student_flashcards.py](../../apps/api/tests/integration/test_student_flashcards.py)
- [apps/api/tests/integration/test_student_study.py](../../apps/api/tests/integration/test_student_study.py)
- [apps/api/tests/integration/test_student_synthesis.py](../../apps/api/tests/integration/test_student_synthesis.py)
- [apps/api/uv.lock](../../apps/api/uv.lock)
- [docs/FULL_OWNER_SETUP_UZ.md](../../docs/FULL_OWNER_SETUP_UZ.md)
- [docs/integration/MASTER_API_CONTRACT.md](../../docs/integration/MASTER_API_CONTRACT.md)
- [docs/master/ACCEPTANCE_MATRIX.md](../../docs/master/ACCEPTANCE_MATRIX.md)
- [docs/master/CHANGE_MANIFEST.md](../../docs/master/CHANGE_MANIFEST.md)
- [docs/master/EXECUTION_GATES.md](../../docs/master/EXECUTION_GATES.md)
- [docs/master/OWNER_STATUS_UZ.md](../../docs/master/OWNER_STATUS_UZ.md)
- [docs/master/SECURITY_REMAINDERS.md](../../docs/master/SECURITY_REMAINDERS.md)
- [docs/master/UPSTREAM_REVIEW.md](../../docs/master/UPSTREAM_REVIEW.md)
- [docs/master/VALIDATION.md](../../docs/master/VALIDATION.md)
- [docs/master/api-high-vulnerabilities.json](../../docs/master/api-high-vulnerabilities.json)
- [docs/third-party/LLAMAINDEX_LICENSE.txt](../../docs/third-party/LLAMAINDEX_LICENSE.txt)
