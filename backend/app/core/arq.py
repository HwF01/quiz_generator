from arq.connections import RedisSettings

from app.core.config import settings


def redis_settings() -> RedisSettings:
    url = settings.redis_url.replace("redis://", "")
    if "@" in url:
        auth, rest = url.split("@", 1)
        password = auth.split(":")[-1] if ":" in auth else auth
        hostport, *dbpart = rest.split("/")
    else:
        password = None
        hostport, *dbpart = url.split("/")
    if ":" in hostport:
        host, port = hostport.split(":")
    else:
        host, port = hostport, "6379"
    database = int(dbpart[0]) if dbpart and dbpart[0] else 0
    return RedisSettings(host=host, port=int(port), database=database, password=password)
