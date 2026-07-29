import asyncio
import collections


class EventBus:
    """In-process pub/sub for broadcasting session events to connected
    WebSocket clients. No external broker needed at v1 scale (single
    process, modest number of concurrent viewers per session)."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = collections.defaultdict(list)
        self._loop: asyncio.AbstractEventLoop | None = None

    def subscribe(self, session_id: str) -> asyncio.Queue:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[session_id].append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        if queue in self._subscribers.get(session_id, []):
            self._subscribers[session_id].remove(queue)

    def publish(self, session_id: str, event: dict) -> None:
        """Safe to call from any thread (e.g. the capture supervisor's own
        watcher thread), not just the event loop thread -- asyncio.Queue is
        not thread-safe, so cross-thread puts are marshalled via
        call_soon_threadsafe."""
        if self._loop is None:
            return
        for queue in self._subscribers.get(session_id, []):
            self._loop.call_soon_threadsafe(queue.put_nowait, event)


bus = EventBus()
