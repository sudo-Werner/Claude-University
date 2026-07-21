import threading

import pytest

from backend import jobs


@pytest.fixture(autouse=True)
def clean_registry():
    jobs.reset()
    yield
    jobs.reset()


def test_start_runs_job_and_records_done():
    done = threading.Event()

    def run(job):
        job.emit("stage", "working")
        done.set()

    job = jobs.start("c1", "l1", run)
    assert done.wait(2)
    job.thread.join(2)
    snap = job.snapshot()
    assert snap["status"] == "done"
    assert snap["error"] is None
    assert snap["courseId"] == "c1"
    assert snap["lessonId"] == "l1"
    assert snap["events"] == [{"n": 0, "kind": "stage", "text": "working"}]
    assert snap["next"] == 1
    assert snap["elapsed"] >= 0


def test_snapshot_since_returns_only_new_events():
    def run(job):
        job.emit("stage", "one")
        job.emit("say", "two")
        job.emit("read", "three")

    job = jobs.start("c1", "l1", run)
    job.thread.join(2)
    snap = job.snapshot(since=1)
    assert [e["text"] for e in snap["events"]] == ["two", "three"]
    assert snap["next"] == 3


def test_start_joins_running_job_instead_of_duplicating():
    release = threading.Event()
    started = threading.Event()
    calls = []

    def run(job):
        calls.append(1)
        started.set()
        release.wait(5)

    first = jobs.start("c1", "l1", run)
    assert started.wait(2)
    second = jobs.start("c1", "l1", run)
    assert second is first
    release.set()
    first.thread.join(2)
    assert calls == [1]


def test_error_is_translated_by_describe_error():
    def run(job):
        raise ValueError("boom")

    job = jobs.start("c1", "l1", run, describe_error=lambda e: f"friendly: {e}")
    job.thread.join(2)
    snap = job.snapshot()
    assert snap["status"] == "error"
    assert snap["error"] == "friendly: boom"


def test_get_and_running():
    release = threading.Event()

    def run(job):
        release.wait(5)

    job = jobs.start("c1", "l1", run)
    assert jobs.get("c1", "l1") is job
    assert jobs.get("c1", "other") is None
    assert jobs.running() == [job]
    release.set()
    job.thread.join(2)
    assert jobs.running() == []


def test_finished_jobs_linger_then_prune(monkeypatch):
    def run(job):
        pass

    job = jobs.start("c1", "l1", run)
    job.thread.join(2)
    assert jobs.get("c1", "l1") is job  # lingers within the window
    job.finished_at -= jobs._LINGER + 1  # age it past the window
    assert jobs.get("c1", "l1") is None


def test_a_new_job_can_start_after_a_failed_one():
    def bad(job):
        raise RuntimeError("nope")

    first = jobs.start("c1", "l1", bad)
    first.thread.join(2)
    second = jobs.start("c1", "l1", lambda job: None)
    assert second is not first
    second.thread.join(2)
    assert second.snapshot()["status"] == "done"
