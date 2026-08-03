from __future__ import annotations

import enum


class UserRole(enum.StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    USER = "USER"


class GroupStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REVOKED = "REVOKED"


class JobStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    DOWNLOADING = "DOWNLOADING"
    CONVERTING = "CONVERTING"
    TRANSCRIBING = "TRANSCRIBING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AttemptStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
