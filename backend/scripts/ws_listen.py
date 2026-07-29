import asyncio
import sys

import websockets


async def main():
    session_id = sys.argv[1]
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    uri = f"ws://localhost:8787/api/sessions/{session_id}/events"
    async with websockets.connect(uri) as ws:
        try:
            async with asyncio.timeout(duration):
                async for message in ws:
                    print(message)
        except TimeoutError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
