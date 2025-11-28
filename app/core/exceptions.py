"""
Custom Exception Classes for Exclusive-Change.

This module defines all custom exceptions used throughout the application.
Each exception maps to a specific HTTP status code and error response format.

Exception Hierarchy:
    ExclusiveChangeException (base)
    ├── AuthenticationError (401)
    ├── AuthorizationError (403)
    ├── NotFoundError (404)
    ├── ConflictError (409)
    ├── ValidationError (422)
    └── ServiceUnavailableError (503)
"""

from typing import Any


class ExclusiveChangeException(Exception):
    """
    Base exception for all Exclusive-Change errors.
    
    All custom exceptions inherit from this class to enable
    centralized exception handling in FastAPI.
    
    Attributes:
        message: Human-readable error description.
        error_code: Machine-readable error identifier.
        status_code: HTTP status code for the response.
        details: Additional error context (optional).
    """
    
    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert exception to API response format."""
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            }
        }


# =============================================================================
# Authentication & Authorization Errors (4xx)
# =============================================================================

class AuthenticationError(ExclusiveChangeException):
    """
    Raised when authentication fails (invalid/missing credentials).
    
    HTTP Status: 401 Unauthorized
    
    Examples:
        - Invalid JWT token
        - Expired token
        - Missing Authorization header
    """
    
    def __init__(
        self,
        message: str = "Authentication required",
        error_code: str = "AUTHENTICATION_FAILED",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=401,
            details=details,
        )


class AuthorizationError(ExclusiveChangeException):
    """
    Raised when user lacks permission for the requested action.
    
    HTTP Status: 403 Forbidden
    
    Examples:
        - User accessing another tenant's data
        - Insufficient role/permissions
        - API key without required scope
    """
    
    def __init__(
        self,
        message: str = "You do not have permission to perform this action",
        error_code: str = "FORBIDDEN",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=403,
            details=details,
        )


class InvalidAPIKeyError(AuthenticationError):
    """
    Raised when an API key is invalid or revoked.
    
    HTTP Status: 401 Unauthorized
    """
    
    def __init__(
        self,
        message: str = "Invalid or expired API key",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="INVALID_API_KEY",
            details=details,
        )


# =============================================================================
# Resource Errors (4xx)
# =============================================================================

class NotFoundError(ExclusiveChangeException):
    """
    Raised when a requested resource does not exist.
    
    HTTP Status: 404 Not Found
    
    Examples:
        - Flag with given key not found
        - Tenant not found
        - Environment not found
    """
    
    def __init__(
        self,
        resource: str,
        identifier: str | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        default_message = f"{resource} not found"
        if identifier:
            default_message = f"{resource} with identifier '{identifier}' not found"
        
        super().__init__(
            message=message or default_message,
            error_code=f"{resource.upper().replace(' ', '_')}_NOT_FOUND",
            status_code=404,
            details=details or {"resource": resource, "identifier": identifier},
        )


class ConflictError(ExclusiveChangeException):
    """
    Raised when an action conflicts with existing state.
    
    HTTP Status: 409 Conflict
    
    Examples:
        - Flag with same key already exists
        - Duplicate tenant name
        - Concurrent modification detected
    """
    
    def __init__(
        self,
        resource: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message or f"{resource} already exists",
            error_code=f"{resource.upper().replace(' ', '_')}_ALREADY_EXISTS",
            status_code=409,
            details=details,
        )


class ValidationError(ExclusiveChangeException):
    """
    Raised when request data fails validation.
    
    HTTP Status: 422 Unprocessable Entity
    
    Examples:
        - Invalid flag percentage (not 0-100)
        - Invalid flag key format
        - Missing required fields
    """
    
    def __init__(
        self,
        message: str = "Validation failed",
        error_code: str = "VALIDATION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=422,
            details=details,
        )


# =============================================================================
# Service Errors (5xx)
# =============================================================================

class ServiceUnavailableError(ExclusiveChangeException):
    """
    Raised when an external service is unavailable.
    
    HTTP Status: 503 Service Unavailable
    
    Examples:
        - Database connection failed
        - Redis connection failed
        - Supabase Auth service down
    """
    
    def __init__(
        self,
        service: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message or f"{service} is currently unavailable",
            error_code="SERVICE_UNAVAILABLE",
            status_code=503,
            details=details or {"service": service},
        )


class DatabaseError(ExclusiveChangeException):
    """
    Raised when a database operation fails.
    
    HTTP Status: 500 Internal Server Error
    
    Examples:
        - Query execution failed
        - Transaction rollback
        - Connection pool exhausted
    """
    
    def __init__(
        self,
        message: str = "Database operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            status_code=500,
            details=details,
        )


class CacheError(ExclusiveChangeException):
    """
    Raised when a cache operation fails (non-fatal, logged only).
    
    HTTP Status: 500 Internal Server Error
    
    Note: Cache errors are typically logged and not propagated to users,
    as the system should gracefully degrade to database queries.
    """
    
    def __init__(
        self,
        message: str = "Cache operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="CACHE_ERROR",
            status_code=500,
            details=details,
        )
