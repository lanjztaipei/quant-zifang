"""Domain exception hierarchy mapped to standardized API errors."""

from __future__ import annotations


class DomainError(Exception):
    """Base domain error with HTTP status code and machine-readable code."""

    status_code: int = 400
    code: str = "DOMAIN_ERROR"

    def __init__(
        self, message: str, *, code: str | None = None, status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class ValidationError(DomainError):
    """HTTP 422 validation error."""

    status_code = 422
    code = "VALIDATION_ERROR"


class NotFoundError(DomainError):
    """HTTP 404 resource not found error."""

    status_code = 404
    code = "NOT_FOUND"


class BaseLotExistsError(DomainError):
    """HTTP 409 conflict when a symbol already has a base lot."""

    status_code = 409
    code = "BASE_LOT_EXISTS"
