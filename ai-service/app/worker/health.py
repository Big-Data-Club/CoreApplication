"""Small event-loop health endpoint; no model or database work per probe."""

from __future__ import annotations

import asyncio


async def serve_health(is_ready, *, port=8091):
    async def respond(reader, writer):
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
            path = request.split(b" ", 2)[1]
            ok = path == b"/health" or path == b"/ready" and is_ready()
            code = b"200 OK" if ok else b"503 Service Unavailable"
            writer.write(
                b"HTTP/1.1 "
                + code
                + b"\r\nContent-Length: 2\r\nConnection: close\r\n\r\n"
                + (b"ok" if ok else b"no")
            )
            await writer.drain()
        except (
            ValueError,
            IndexError,
            TimeoutError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            ConnectionError,
        ):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    return await asyncio.start_server(respond, "0.0.0.0", port, limit=4096)
