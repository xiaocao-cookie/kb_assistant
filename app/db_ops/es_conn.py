from functools import lru_cache

from elasticsearch.client import Elasticsearch

from app.config import settings


@lru_cache(maxsize=1)
def es_client() -> Elasticsearch:
    return Elasticsearch(
        hosts=[settings.es_url],
        request_timeout=30,
        retry_on_timeout=True,
        max_retries=3,
    )