"""In-memory lesson-generation jobs. One job per (course_id, lesson_id); a second
start while one is running joins it — a mid-wait refresh must never spawn a second
nine-minute generation. In-memory on purpose: a service restart kills the underlying
claude process anyway, so surviving rows could only ever say "interrupted"; the
routes' `none` answer says that without the ceremony."""
import threading
import time
import traceback

_lock = threading.Lock()
_jobs = {}

# Finished jobs linger so a briefly-disconnected client can still read the outcome.
_LINGER = 600


class Job:
    def __init__(self, course_id, lesson_id):
        self.course_id = course_id
        self.lesson_id = lesson_id
        self.status = "running"
        self.error = None
        self.started_at = time.time()
        self.finished_at = None
        self.thread = None
        self._events = []
        self._elock = threading.Lock()

    def emit(self, kind, text):
        with self._elock:
            self._events.append({"n": len(self._events), "kind": kind, "text": text})

    def snapshot(self, since=0):
        since = max(0, since)  # a negative cursor would slice-overlap events and produce an incoherent next
        with self._elock:
            events = self._events[since:]
        end = self.finished_at or time.time()
        return {
            "status": self.status,
            "error": self.error,
            "courseId": self.course_id,
            "lessonId": self.lesson_id,
            "elapsed": end - self.started_at,
            "events": events,
            "next": since + len(events),
        }


def start(course_id, lesson_id, run, describe_error=str):
    with _lock:
        _prune()
        existing = _jobs.get((course_id, lesson_id))
        if existing is not None and existing.status == "running":
            return existing
        job = Job(course_id, lesson_id)
        _jobs[(course_id, lesson_id)] = job

    def _worker():
        try:
            run(job)
            job.status = "done"
        except Exception as exc:
            # The learner only ever sees the translated message below; the operator
            # needs the real traceback in journalctl to diagnose what actually broke.
            traceback.print_exc()
            job.error = describe_error(exc)
            job.status = "error"
        finally:
            job.finished_at = time.time()

    job.thread = threading.Thread(target=_worker, daemon=True)
    job.thread.start()
    return job


def get(course_id, lesson_id):
    with _lock:
        _prune()
        return _jobs.get((course_id, lesson_id))


def running():
    with _lock:
        _prune()
        return [j for j in _jobs.values() if j.status == "running"]


def _prune():
    # Callers hold _lock. Drop finished jobs older than the linger window.
    now = time.time()
    for key, job in list(_jobs.items()):
        if job.status != "running" and job.finished_at and now - job.finished_at > _LINGER:
            del _jobs[key]


def reset():
    """Test helper: forget every job."""
    with _lock:
        _jobs.clear()
