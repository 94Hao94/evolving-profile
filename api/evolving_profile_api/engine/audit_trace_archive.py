"""Content-addressed cold storage for detailed recall audit traces.

Recall responses can contain the same candidate text in several retrieval
stages.  The hot audit row retains the user-visible result and a receipt; this
module stores the detailed ``trace`` once, addressed by its canonical bytes.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

ARCHIVE_SCHEMA_VERSION = 1
GZIP_THRESHOLD_BYTES = 64 * 1024


@dataclass(frozen=True)
class TraceArchiveReceipt:
    """Immutable reference to one complete recall trace."""

    schema_version: int
    sha256: str
    bytes: int
    object_path: str
    encoding: str = "identity"
    stored_bytes: int | None = None

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-safe receipt without exposing the archive root."""
        return asdict(self)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return "<bytes>"
    if isinstance(value, set):
        return json.dumps(sorted(value), ensure_ascii=False)
    return str(value)


def canonical_trace_bytes(trace: Mapping[str, Any]) -> bytes:
    """Serialize a trace deterministically so its hash is stable across runs."""
    return json.dumps(
        dict(trace),
        default=_json_default,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


class RecallTraceArchive:
    """Local, content-addressed archive for complete recall traces."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def archive_trace(self, trace: Mapping[str, Any]) -> TraceArchiveReceipt:
        """Write a complete trace once and return a verified immutable receipt."""
        payload = canonical_trace_bytes(trace)
        digest = hashlib.sha256(payload).hexdigest()
        compressed = gzip.compress(payload, compresslevel=6, mtime=0) if len(payload) >= GZIP_THRESHOLD_BYTES else payload
        use_gzip = len(compressed) < len(payload)
        stored_payload = compressed if use_gzip else payload
        encoding = "gzip" if use_gzip else "identity"
        suffix = ".json.gz" if use_gzip else ".json"
        object_path = Path("objects") / digest[:2] / f"{digest}{suffix}"
        self._write_once(object_path, stored_payload)

        receipt = TraceArchiveReceipt(
            schema_version=ARCHIVE_SCHEMA_VERSION,
            sha256=digest,
            bytes=len(payload),
            object_path=object_path.as_posix(),
            encoding=encoding,
            stored_bytes=len(stored_payload),
        )
        manifest_path = self._manifest_path(receipt)
        self._write_once(
            manifest_path,
            json.dumps(receipt.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
        self._validate(receipt)
        return receipt

    def read_trace(self, receipt: TraceArchiveReceipt | Mapping[str, Any]) -> dict[str, Any]:
        """Read and hash-verify a trace from a receipt, never from mutable Bank state."""
        normalized = self._normalize_receipt(receipt)
        payload = self._read_verified_bytes(normalized)
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("Archived recall trace must decode to an object")
        return value

    def _validate(self, receipt: TraceArchiveReceipt) -> None:
        self._read_verified_bytes(receipt)
        manifest = self.root / self._manifest_path(receipt)
        stored = json.loads(manifest.read_bytes())
        if stored != receipt.model_dump():
            raise ValueError("Recall trace archive manifest does not match its receipt")

    def _read_verified_bytes(self, receipt: TraceArchiveReceipt) -> bytes:
        suffix = ".json.gz" if receipt.encoding == "gzip" else ".json"
        expected_path = Path("objects") / receipt.sha256[:2] / f"{receipt.sha256}{suffix}"
        if Path(receipt.object_path) != expected_path:
            raise ValueError("Recall trace archive receipt has an invalid object path")
        stored_payload = (self.root / expected_path).read_bytes()
        expected_stored_bytes = receipt.stored_bytes if receipt.stored_bytes is not None else receipt.bytes
        if len(stored_payload) != expected_stored_bytes:
            raise ValueError("Recall trace archive stored byte count does not match its receipt")
        if receipt.encoding == "gzip":
            try:
                payload = gzip.decompress(stored_payload)
            except OSError as exc:
                raise ValueError("Recall trace archive gzip payload is invalid") from exc
        elif receipt.encoding == "identity":
            payload = stored_payload
        else:
            raise ValueError("Recall trace archive uses an unknown encoding")
        if len(payload) != receipt.bytes:
            raise ValueError("Recall trace archive logical byte count does not match its receipt")
        if hashlib.sha256(payload).hexdigest() != receipt.sha256:
            raise ValueError("Recall trace archive hash does not match its receipt")
        return payload

    @staticmethod
    def _normalize_receipt(receipt: TraceArchiveReceipt | Mapping[str, Any]) -> TraceArchiveReceipt:
        if isinstance(receipt, TraceArchiveReceipt):
            return receipt
        return TraceArchiveReceipt(
            schema_version=int(receipt["schema_version"]),
            sha256=str(receipt["sha256"]),
            bytes=int(receipt["bytes"]),
            object_path=str(receipt["object_path"]),
            encoding=str(receipt.get("encoding") or "identity"),
            stored_bytes=int(receipt["stored_bytes"]) if receipt.get("stored_bytes") is not None else None,
        )

    @staticmethod
    def _manifest_path(receipt: TraceArchiveReceipt) -> Path:
        return Path("manifests") / f"{receipt.sha256}.{receipt.encoding}.json"

    def _write_once(self, relative_path: Path, payload: bytes) -> None:
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != payload:
                raise ValueError(f"Recall trace archive collision at {relative_path}")
            return

        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.read_bytes() != payload:
                    raise ValueError(f"Recall trace archive collision at {relative_path}")
            finally:
                Path(temporary).unlink(missing_ok=True)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise


def compact_recall_response(
    response: Mapping[str, Any], archive: Any
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Move a recall trace to cold storage while keeping final results hot.

    The caller writes the returned metadata alongside its audit row.  A failed
    archive operation deliberately returns the original response, including the
    detailed trace, so observability remains complete until storage is healthy.
    """
    trace = response.get("trace")
    if not isinstance(trace, Mapping):
        return dict(response), {}

    try:
        receipt = archive.archive_trace(trace)
    except Exception as exc:
        return dict(response), {
            "recall_trace_archive": {"status": "failed", "error_type": type(exc).__name__}
        }

    hot_response = dict(response)
    hot_response.pop("trace", None)
    hot_response["trace_archive"] = receipt.model_dump()
    return hot_response, {"recall_trace_archive": {"status": "archived", **receipt.model_dump()}}
