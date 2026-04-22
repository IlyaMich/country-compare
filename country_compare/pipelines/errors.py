from __future__ import annotations


class PipelineError(RuntimeError):
    """Base error for processing-pipeline failures."""


class AcquisitionError(PipelineError):
    pass


class SourceNotFoundError(AcquisitionError):
    pass


class UnsupportedFormatError(AcquisitionError):
    pass


class AdapterExecutionError(PipelineError):
    pass


class CanonicalValidationError(PipelineError):
    pass


class PublicationError(PipelineError):
    pass
