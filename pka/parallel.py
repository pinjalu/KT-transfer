"""Small, bounded pipelines; results are published by one coordinator."""
import asyncio
import os


def concurrency(name, default, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(1, min(maximum, value))


async def process_parallel(items, work, publish, limit, stopped=lambda: False):
    """Keep at most limit requests in flight and publish each completed result.

    Stop scheduling after failure/cancellation, and drain existing requests before the
    caller releases its job lock. Application shutdown cancels and joins the children.
    Publishing is serial, even when requests complete together.
    """
    remaining = iter(items)
    pending = {}

    def fill():
        while len(pending) < limit and not stopped():
            try:
                item = next(remaining)
            except StopIteration:
                break
            pending[asyncio.create_task(work(item))] = item

    try:
        fill()
        while pending:
            completed, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            # Dict order keeps ties deterministic without making a fast result wait
            # for an earlier, slower request.
            for task in list(pending):
                if task not in completed:
                    continue
                result = task.result()
                item = pending.pop(task)
                await publish(item, result)
            fill()
    except asyncio.CancelledError:
        for task in pending:
            task.cancel()
        raise
    finally:
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
