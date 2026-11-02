"""Database-backed queue metrics: accurate across multiple worker processes."""

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import func, select

from reviewer.database import session
from reviewer.models import Job, now


class QueueCollector:
    def collect(self):
        counts = GaugeMetricFamily(
            "diffsentry_jobs", "Durable job count", labels=["status", "kind"]
        )
        age = GaugeMetricFamily(
            "diffsentry_overdue_seconds", "Oldest overdue job lease or dispatch", labels=[]
        )
        with session() as db:
            for status, kind, count in db.execute(
                select(Job.status, Job.kind, func.count()).group_by(Job.status, Job.kind)
            ):
                counts.add_metric([status, kind], count)
            oldest = db.scalar(
                select(func.min(Job.available_at)).where(
                    Job.status.in_(["pending", "queued", "running"])
                )
            )
            if oldest and oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=now().tzinfo)
            age.add_metric([], max(0, (now() - oldest).total_seconds()) if oldest else 0)
        yield counts
        yield age


def queue_metrics():
    registry = CollectorRegistry()
    registry.register(QueueCollector())
    return generate_latest(registry)
