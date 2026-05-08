from fastapi import Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
import redis

# Redis para tracking (producción)
redis_client = redis.Redis(host='localhost', port=6379, db=0)

limiter = Limiter(key_func=get_remote_address)


def get_rate_limit_for_plan(plan: str) -> str:
    """
    Retorna rate limit en formato slowapi
    """
    limits = {
        "FREE": "10/hour",
        "STARTER": "100/hour",
        "PRO": "500/hour",
        "BUSINESS": "2000/hour"
    }
    return limits.get(plan, "10/hour")


async def check_rate_limit(request: Request, user):
    """
    Verifica rate limit basado en plan
    """
    
    key = f"rate_limit:{user.id}"
    limit = get_rate_limit_for_plan(user.plan)
    
    # Ejemplo: "100/hour" → 100 requests
    max_requests = int(limit.split("/")[0])
    
    # Contador en Redis
    current = redis_client.get(key)
    
    if current is None:
        redis_client.setex(key, 3600, 1)  # 1 hora
    else:
        current = int(current)
        if current >= max_requests:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": limit,
                    "reset_in_seconds": redis_client.ttl(key),
                    "upgrade_to": get_next_plan(user.plan)
                },
                headers={"Retry-After": str(redis_client.ttl(key))}
            )
        redis_client.incr(key)