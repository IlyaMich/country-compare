from __future__ import annotations

from country_compare.services.errors import AppError


class ClientError(Exception):
    """Base exception for UI client failures."""


class ClientConnectionError(ClientError):
    """Raised when the HTTP backend cannot be reached."""

    def __init__(self, message: str, *, error: AppError | None = None) -> None:
        self.error = error or AppError(
            code="backend_unavailable",
            title="Backend unavailable",
            user_message="The Country Compare backend could not be reached.",
            technical_detail=message,
        )
        super().__init__(self.error.user_message)


class ClientResponseError(ClientError):
    """Raised when the backend response cannot be parsed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        self.error = AppError(
            code="backend_response_invalid",
            title="Invalid backend response",
            user_message="The Country Compare backend returned a response the UI could not read.",
            technical_detail=message,
        )
        super().__init__(self.error.user_message)


class ClientBackendError(ClientError):
    """Raised when the backend returns an application or HTTP error."""

    def __init__(self, error: AppError, *, status_code: int | None = None) -> None:
        self.error = error
        self.status_code = status_code
        super().__init__(error.user_message)
