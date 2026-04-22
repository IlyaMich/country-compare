from __future__ import annotations


class PipelineError(RuntimeError):
    """Base error for processing-pipeline failures."""


class SourceNotFoundError(PipelineError):
    """Raised when a source file cannot be found."""


class UnsupportedFormatError(PipelineError):
    """Raised when a source file format is unsupported."""


class AdapterExecutionError(PipelineError):
    """Raised when an adapter fails to transform an acquired asset."""


class CanonicalValidationError(PipelineError):
    """Raised when canonical validation fails."""


class PublicationError(PipelineError):
    """Raised when publication to the data layer fails."""
