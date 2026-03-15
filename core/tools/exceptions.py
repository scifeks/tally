class InvalidSegmentError(ValueError):
    """Raised when an unknown scan segment name is requested."""

    def __init__(self, segment_name: str, valid_segments: list[str]) -> None:
        self.segment_name = segment_name
        self.valid_segments = valid_segments
        super().__init__(
            f"Unknown segment: {segment_name!r}. Valid segments: {valid_segments}"
        )
