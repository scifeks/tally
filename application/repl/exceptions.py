"""REPL-specific exceptions."""


class ReplArgumentError(ValueError):
    """Raised when a REPL command receives invalid arguments.

    Handlers catch this and print the message without killing the session.
    """
