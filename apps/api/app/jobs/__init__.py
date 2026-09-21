"""Background jobs that run workflows (reports) outside the request cycle.

The API image also runs the ``querion-jobs`` RQ worker (``python -m app.jobs.worker``) because
a report needs the whole runtime: the tool registry, retrieval, the LLM providers, MinIO and
token metering. The indexing worker (apps/worker) stays a separate, smaller image.
"""
