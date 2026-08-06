"""Controlled file intake.

Safe, bounded acceptance of a source file before any parsing happens: an extension allowlist, a bounded
size, filename sanitization (no path traversal, no executable handling), a content hash, duplicate
detection (never a silent overwrite), and quarantine for rejected files. Upload requires authorization +
scope. Nothing here interprets data; it only decides whether a file may enter the pipeline and records a
receipt referencing the retained raw evidence.
"""
from __future__ import annotations

import hashlib
import os
import re

from ..errors import ValidationError
from .models import ALLOWED_EXTENSIONS, DISALLOWED_EXTENSIONS, DEFAULT_MAX_UPLOAD_BYTES

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_filename(name):
    """Strip any directory component and unsafe characters. Refuses path-traversal attempts outright."""
    if not isinstance(name, str) or not name.strip():
        raise ValidationError(message="A filename is required.", technical_detail="empty_filename")
    if "\x00" in name:
        raise ValidationError(message="Invalid filename.", technical_detail="null_byte_in_filename")
    base = os.path.basename(name.replace("\\", "/"))
    if base in ("", ".", "..") or ".." in name:
        raise ValidationError(message="Invalid filename.",
                              technical_detail=f"path_traversal_attempt: {name!r}")
    safe = _SAFE_NAME.sub("_", base)
    return safe


def _ext(name):
    _, ext = os.path.splitext(name.lower())
    return ext


def content_hash(payload):
    data = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    return "sha256:" + hashlib.sha256(data).hexdigest()


class FileIntake:
    def __init__(self, store, *, max_bytes=DEFAULT_MAX_UPLOAD_BYTES, allowed=None):
        self.store = store
        self.max_bytes = max_bytes
        self.allowed = set(allowed) if allowed else set(ALLOWED_EXTENSIONS)

    def _size(self, payload):
        return len(payload.encode("utf-8")) if isinstance(payload, str) else len(payload)

    def accept(self, *, filename, payload, source_id=None, scope=None, received_by=None,
               correlation_id=None):
        """Validate + record a file receipt. On a policy violation the file is QUARANTINED (a receipt is
        still written, referencing the rejection reason) and a ValidationError is raised — the file never
        enters the pipeline. Returns the 'received' receipt on success."""
        safe_name = sanitize_filename(filename)
        ext = _ext(safe_name)
        size = self._size(payload)
        chash = content_hash(payload)

        def quarantine(reason, detail):
            self.store.add_file_receipt(
                source_id=source_id, original_filename=filename[:200], sanitized_filename=safe_name,
                content_hash=chash, size_bytes=size, media_type=ext, store_scope=scope,
                received_by=received_by, status="quarantined", quarantine_reason=reason,
                stored_ref=None, correlation_id=correlation_id)
            raise ValidationError(message="The file was rejected and quarantined.", technical_detail=detail)

        if ext in DISALLOWED_EXTENSIONS:
            quarantine("disallowed_extension", f"disallowed_extension: {ext}")
        if ext not in self.allowed:
            quarantine("extension_not_allowed", f"extension_not_allowed: {ext}")
        if size == 0:
            quarantine("empty_file", "empty_file")
        if size > self.max_bytes:
            quarantine("file_too_large", f"file_too_large: {size} > {self.max_bytes}")

        dup = self.store.find_receipt_by_hash(chash)
        receipt = self.store.add_file_receipt(
            source_id=source_id, original_filename=filename[:200], sanitized_filename=safe_name,
            content_hash=chash, size_bytes=size, media_type=ext, store_scope=scope, received_by=received_by,
            status="received", quarantine_reason=("duplicate_of:" + dup["id"]) if dup else None,
            stored_ref="raw:" + chash, correlation_id=correlation_id)
        receipt["_duplicate_of"] = dup["id"] if dup else None
        return receipt
