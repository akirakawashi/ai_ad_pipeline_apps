from __future__ import annotations


class PipelineRunError(Exception):
    """Base exception for pipeline run access."""


class PipelineRunNotFoundError(PipelineRunError):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Pipeline run not found: {run_id}")


class PipelineArtifactNotFoundError(PipelineRunError):
    def __init__(self, run_id: str, relative_path: str) -> None:
        self.run_id = run_id
        self.relative_path = relative_path
        super().__init__(f"Pipeline artifact not found: {run_id}/{relative_path}")


class InvalidPipelineArtifactPathError(PipelineRunError):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        super().__init__(f"Invalid pipeline artifact path: {relative_path}")


class PipelineRunDataError(PipelineRunError):
    def __init__(self, run_id: str, message: str) -> None:
        self.run_id = run_id
        self.message = message
        super().__init__(f"Invalid pipeline run data for {run_id}: {message}")

