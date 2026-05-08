from __future__ import annotations


class PipelineError(RuntimeError):
    """Base error raised by the processing pipeline."""


class SourceNotFoundError(PipelineError):
    """Raised when a configured source file cannot be located."""


class UnsupportedFormatError(PipelineError):
    """Raised when an acquired asset has an unsupported format."""


class SourcePullError(PipelineError):
    """Raised when a non-local source cannot be downloaded or materialized."""


class AdapterExecutionError(PipelineError):
    """Raised when a source adapter cannot produce a canonical dataframe."""


class CanonicalValidationError(PipelineError):
    """Raised when canonical validation fails before publication."""


class PublicationError(PipelineError):
    """Raised when the validated dataset cannot be published."""
