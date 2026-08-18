"""Redis worker: `python -m app.worker` (CL_JOB_BACKEND=redis).

- Pulls job IDs from civiclens:jobs
- Re-schedules delayed (backoff) jobs from civiclens:jobs:delayed
- Recovers jobs stuck in `running` (worker crash) back to queued on startup
- Heartbeats to civiclens:worker:heartbeat
"""
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from .config import settings
from .db import SessionLocal
from .jobs import execute_job
from .models import Job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("civiclens.worker")


def recover_stuck_jobs():
    """A crashed worker leaves jobs 'running'; requeue anything stale."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        stuck = db.query(Job).filter(Job.status == "running", Job.started_at < cutoff).all()
        for j in stuck:
            log.warning("recovering stuck job %s (%s)", j.id, j.name)
            j.status = "queued"
        db.commit()
        return [j.id for j in stuck]
    finally:
        db.close()


def main():
    import redis
    from concurrent.futures import ThreadPoolExecutor
    # socket_timeout must exceed the BLPOP block time (redis-py 8.x enforces
    # the socket deadline during blocking commands)
    r = redis.from_url(settings.redis_url, socket_timeout=10, socket_connect_timeout=5,
                       health_check_interval=30)
    for jid in recover_stuck_jobs():
        r.rpush("civiclens:jobs", json.dumps({"job_id": jid}))
    concurrency = max(1, settings.worker_concurrency)
    pool = ThreadPoolExecutor(max_workers=concurrency,
                              thread_name_prefix="civiclens-job")
    inflight: set = set()
    log.info("worker started (queue: civiclens:jobs, concurrency: %d)", concurrency)
    last_delayed_check = 0.0
    last_sla_check = 0.0
    while True:
        try:
            r.set("civiclens:worker:heartbeat", datetime.now(timezone.utc).isoformat(), ex=60)

            # promote delayed jobs whose backoff has elapsed
            if time.time() - last_delayed_check > 5:
                last_delayed_check = time.time()
                for _ in range(100):
                    item = r.lpop("civiclens:jobs:delayed")
                    if not item:
                        break
                    d = json.loads(item)
                    if datetime.fromisoformat(d["run_after"]) <= datetime.now(timezone.utc):
                        r.rpush("civiclens:jobs", json.dumps({"job_id": d["job_id"]}))
                    else:
                        r.rpush("civiclens:jobs:delayed", item)
                        break

            # periodic SLA sweep (every 5 minutes)
            if time.time() - last_sla_check > 300:
                last_sla_check = time.time()
                try:
                    from .sla import check_slas
                    db = SessionLocal()
                    n = check_slas(db)
                    from .routers.uploads import cleanup_stale_sessions
                    stale = cleanup_stale_sessions(db)
                    db.close()
                    if n:
                        log.info("SLA sweep created %d escalation(s)", n)
                    if stale:
                        log.info("cleaned %d abandoned upload session(s)", stale)
                except Exception:
                    log.exception("SLA sweep failed")

            # reap finished futures, then only pull work if we have capacity
            inflight = {f for f in inflight if not f.done()}
            if len(inflight) >= concurrency:
                time.sleep(0.2)
                continue
            item = r.blpop("civiclens:jobs", timeout=5)
            if not item:
                continue
            payload = json.loads(item[1])
            log.info("executing job %s (inflight: %d/%d)",
                     payload.get("job_id"), len(inflight) + 1, concurrency)
            inflight.add(pool.submit(execute_job, payload["job_id"]))
        except KeyboardInterrupt:
            break
        except Exception:
            log.exception("worker loop error")
            time.sleep(2)


if __name__ == "__main__":
    main()
