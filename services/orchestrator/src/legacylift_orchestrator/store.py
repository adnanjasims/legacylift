"""In-memory job store for tests and when DATABASE_URL is unset."""

from __future__ import annotations

import uuid
from typing import Protocol

from legacylift_orchestrator.models import Job, JobStatus, Role, User
from legacylift_orchestrator.passwords import hash_password, verify_password


class JobStore(Protocol):
    def ensure_user(self, username: str, password: str, role: Role) -> User: ...

    def authenticate(self, username: str, password: str) -> User | None: ...

    def user_by_id(self, user_id: str) -> User | None: ...

    def create_job(self, user_id: str, source: str) -> Job: ...

    def get_job(self, job_id: str) -> Job | None: ...

    def visible_job(self, job_id: str, actor: User) -> Job | None: ...

    def set_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        attempt: int | None = None,
        error: str | None = None,
        report_dir: str | None = None,
    ) -> Job | None: ...


class MemoryJobStore:
    """Process-local users and jobs. Fine for unit tests."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._by_name: dict[str, str] = {}
        self._jobs: dict[str, Job] = {}

    def ensure_user(self, username: str, password: str, role: Role) -> User:
        existing_id = self._by_name.get(username)
        if existing_id is not None:
            return self._users[existing_id]
        user = User(
            id=uuid.uuid4().hex,
            username=username,
            password_hash=hash_password(password),
            role=role,
        )
        self._users[user.id] = user
        self._by_name[username] = user.id
        return user

    def authenticate(self, username: str, password: str) -> User | None:
        user_id = self._by_name.get(username)
        if user_id is None:
            return None
        user = self._users[user_id]
        if not verify_password(password, user.password_hash):
            return None
        return user

    def user_by_id(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def create_job(self, user_id: str, source: str) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            user_id=user_id,
            source=source,
            status="queued",
            attempt=0,
        )
        self._jobs[job.id] = job
        return job

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def visible_job(self, job_id: str, actor: User) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if actor.role == "admin" or job.user_id == actor.id:
            return job
        return None

    def set_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        attempt: int | None = None,
        error: str | None = None,
        report_dir: str | None = None,
    ) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        job.status = status
        if attempt is not None:
            job.attempt = attempt
        if error is not None:
            job.error = error
        if report_dir is not None:
            job.report_dir = report_dir
        return job
