import argparse
import asyncio
import json
import os
import statistics
import time
from uuid import uuid4

import httpx


async def run(url: str, key: str, requests: int, concurrency: int) -> dict[str, object]:
    semaphore = asyncio.Semaphore(concurrency)
    samples: list[float] = []
    async with httpx.AsyncClient(base_url=url, headers={'X-API-Key': key}, timeout=10) as client:

        async def create() -> None:
            async with semaphore:
                started = time.perf_counter()
                response = await client.post(
                    '/api/v1/payments',
                    headers={'Idempotency-Key': str(uuid4())},
                    json={
                        'amount': '1.00',
                        'currency': 'RUB',
                        'description': 'Local benchmark',
                        'webhook_url': 'http://webhook-receiver:8080/success',
                    },
                )
                response.raise_for_status()
                assert response.status_code == 202
                samples.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        await asyncio.gather(*(create() for _ in range(requests)))
        elapsed = time.perf_counter() - started
    quantiles = statistics.quantiles(samples, n=100, method='inclusive')
    return {
        'requests': requests,
        'concurrency': concurrency,
        'elapsed_seconds': round(elapsed, 3),
        'accepted_requests_per_second': round(requests / elapsed, 1),
        'latency_ms': {
            'p50': round(statistics.median(samples), 2),
            'p95': round(quantiles[94], 2),
            'p99': round(quantiles[98], 2),
        },
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:18081')
    parser.add_argument('--requests', type=int, default=100)
    parser.add_argument('--concurrency', type=int, default=10)
    args = parser.parse_args()
    if not 2 <= args.requests <= 1000 or not 1 <= args.concurrency <= 100:
        parser.error('Use 2-1000 requests and 1-100 concurrent requests')
    print(json.dumps(asyncio.run(run(args.url, os.environ['API_KEY'], args.requests, args.concurrency)), indent=2))
