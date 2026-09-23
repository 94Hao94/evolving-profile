"""
Hindsight Extensions System.

Extensions allow customizing and extending Hindsight behavior without modifying core code.
Extensions are loaded via environment variables pointing to implementation classes.

Example:
    EVOLVING_PROFILE_API_OPERATION_VALIDATOR_EXTENSION=mypackage.validators:MyValidator
    EVOLVING_PROFILE_API_OPERATION_VALIDATOR_MAX_RETRIES=3

    EVOLVING_PROFILE_API_HTTP_EXTENSION=mypackage.http:MyHttpExtension
    EVOLVING_PROFILE_API_HTTP_SOME_CONFIG=value

Extensions receive an ExtensionContext that provides a controlled API for interacting
with the system (e.g., running migrations for tenant schemas).
"""

from evolving_profile_api.extensions.bank_tables import BankScopedTable
from evolving_profile_api.extensions.base import Extension
from evolving_profile_api.extensions.builtin import (
    ApiKeyTenantExtension,
    MemoryDefenseRegexExtension,
    SupabaseTenantExtension,
)
from evolving_profile_api.extensions.context import DefaultExtensionContext, ExtensionContext
from evolving_profile_api.extensions.http import HttpExtension
from evolving_profile_api.extensions.loader import load_extension
from evolving_profile_api.extensions.mcp import MCPExtension
from evolving_profile_api.extensions.memory_defense import (
    DefenseAction,
    DefenseDecision,
    DefensePolicy,
    MemoryDefenseExtension,
    PolicyRule,
    apply_redaction,
    parse_policy,
)
from evolving_profile_api.extensions.operation_validator import (
    # Bank Management operations
    BankListContext,
    BankListResult,
    BankReadContext,
    BankReadOperation,
    BankWriteContext,
    BankWriteOperation,
    # Consolidation operation
    ConsolidateContext,
    ConsolidateResult,
    CreateBankContext,
    # File Conversion
    FileConvertResult,
    # Mental Model operations
    MentalModelGetContext,
    MentalModelGetResult,
    MentalModelRefreshContext,
    MentalModelRefreshResult,
    # Core operations
    OperationValidationError,
    OperationValidatorExtension,
    PrecheckContext,
    PrecheckOperation,
    RecallContext,
    RecallResult,
    ReflectContext,
    ReflectResultContext,
    RetainContext,
    RetainResult,
    ValidationResult,
)
from evolving_profile_api.extensions.tenant import (
    AuthenticationError,
    Tenant,
    TenantContext,
    TenantExtension,
)
from evolving_profile_api.models import RequestContext
from evolving_profile_api.worker.exceptions import DeferOperation

__all__ = [
    # Base
    "Extension",
    "BankScopedTable",
    "load_extension",
    # Context
    "ExtensionContext",
    "DefaultExtensionContext",
    # HTTP Extension
    "HttpExtension",
    # MCP Extension
    "MCPExtension",
    # Operation Validator - Core
    "DeferOperation",
    "OperationValidationError",
    "OperationValidatorExtension",
    "PrecheckContext",
    "PrecheckOperation",
    "RecallContext",
    "RecallResult",
    "ReflectContext",
    "ReflectResultContext",
    "RetainContext",
    "RetainResult",
    "ValidationResult",
    # Operation Validator - Bank Management
    "BankListContext",
    "BankListResult",
    "BankReadContext",
    "BankReadOperation",
    "BankWriteContext",
    "BankWriteOperation",
    "CreateBankContext",
    # Operation Validator - Consolidation
    "ConsolidateContext",
    "ConsolidateResult",
    # Operation Validator - File Conversion
    "FileConvertResult",
    # Operation Validator - Mental Model
    "MentalModelGetContext",
    "MentalModelGetResult",
    "MentalModelRefreshContext",
    "MentalModelRefreshResult",
    # Tenant/Auth
    "ApiKeyTenantExtension",
    "SupabaseTenantExtension",
    "AuthenticationError",
    "RequestContext",
    "Tenant",
    "TenantContext",
    "TenantExtension",
    # Memory Defense
    "DefenseAction",
    "DefenseDecision",
    "DefensePolicy",
    "MemoryDefenseExtension",
    "MemoryDefenseRegexExtension",
    "PolicyRule",
    "apply_redaction",
    "parse_policy",
]
