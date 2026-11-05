"""Database-backed queue metrics: accurate across multiple worker processes."""

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import func, select

from reviewer.database import session
from reviewer.models import Generation, Job, now


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
        tokens = GaugeMetricFamily(
            "diffsentry_llm_tokens",
            "Persisted provider-reported tokens; cached input is a subset of input",
            labels=["agent", "model", "type"],
        )
        cost = GaugeMetricFamily(
            "diffsentry_llm_estimated_cost_usd",
            "Known estimated cost subtotal, not provider invoice",
            labels=["agent", "model"],
        )
        unknown = GaugeMetricFamily(
            "diffsentry_llm_unpriced_calls",
            "Observed calls without a cost estimate",
            labels=["agent", "model"],
        )
        with session() as db:
            rows = db.execute(
                select(
                    Generation.agent,
                    Generation.model,
                    func.sum(Generation.input_tokens),
                    func.sum(Generation.cached_input_tokens),
                    func.sum(Generation.output_tokens),
                    func.sum(Generation.estimated_cost_usd),
                    func.count(Generation.id) - func.count(Generation.estimated_cost_usd),
                ).group_by(Generation.agent, Generation.model)
            )
            for agent, model, input_count, cached, output, subtotal, missing in rows:
                for label, value in [
                    ("input", input_count),
                    ("cached_input", cached),
                    ("output", output),
                ]:
                    if value is not None:
                        tokens.add_metric([agent, model, label], value)
                if subtotal is not None:
                    cost.add_metric([agent, model], float(subtotal))
                unknown.add_metric([agent, model], missing)
        yield tokens
        yield cost
        yield unknown


def queue_metrics():
    registry = CollectorRegistry()
    registry.register(QueueCollector())
    return generate_latest(registry)
