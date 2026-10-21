"""Pipeline errors that should be shown to the caller as-is."""


class PipelineError(RuntimeError):
    """A stage failed in a way the CLI should report and exit non-zero."""
