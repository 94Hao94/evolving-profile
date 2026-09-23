"""The only local entry point that can make guidance active."""
from __future__ import annotations

from repository import GuidanceRepository
from schemas import review_contract_accepts, validate_proposal


class PublicationError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def prepare_publication(repo: GuidanceRepository, proposal: dict, review: dict, owner_token: str) -> dict:
    checked = validate_proposal(proposal)
    if checked["status"] != "supported":
        repo.record_job("publication", checked["status"], {"proposal": proposal, "reason": checked["reason"]})
        raise PublicationError(checked["reason"])
    if not review_contract_accepts(review):
        repo.record_job("publication", "held", {"proposal": proposal, "reason": "review_contract_rejected"})
        raise PublicationError("review_contract_rejected")
    return repo.prepare(proposal, review, checked["proposal_sha256"], owner_token)


def commit_publication(repo: GuidanceRepository, publication_id: str, expected_active_revision: str | None,
                       expected_source_tokens: dict, owner_token: str) -> dict:
    try:
        return repo.activate(publication_id, expected_active_revision, expected_source_tokens, owner_token)
    except PermissionError as error:
        raise PublicationError("owner_conflict") from error
    except RuntimeError as error:
        raise PublicationError("revision_conflict") from error
    except (KeyError, ValueError) as error:
        raise PublicationError(str(error)) from error
