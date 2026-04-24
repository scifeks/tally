from __future__ import annotations


class BusError(Exception):
    pass


class UnknownJob(BusError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Unknown job: {job_id!r}")
        self.job_id = job_id


class SubscriberClosed(BusError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job {job_id!r} is already closed")
        self.job_id = job_id
