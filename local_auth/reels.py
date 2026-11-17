"""Authenticated, owner-scoped video streaming from the private reels service."""
import asyncio
from pathlib import Path
import sqlite3

from aiohttp import web

from .store import DOMAIN, AuthError


def owner_of(database, job_id):
    try:
        with sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True, timeout=5) as db:
            row = db.execute("SELECT email FROM local_reel_jobs WHERE server='badminton-reels' AND job_id=?", (job_id,)).fetchone()
            return row[0] if row else None
    except sqlite3.OperationalError:
        return None


def install(app, identity, upstream, ledger_path):
    async def video(request):
        user = identity(request)
        if not user:
            raise AuthError("請先登入。", 401)
        job = request.match_info["job_id"]
        owner = await asyncio.to_thread(owner_of, ledger_path, job)
        if owner != user["username"] + "@" + DOMAIN:
            raise AuthError("找不到影片。", 404)
        headers = {key: request.headers[key] for key in ("Range", "If-Range") if key in request.headers}
        headers["Host"] = "localhost:8900"
        try:
            async with app["client"].get(upstream.rstrip("/") + f"/files/{job}.mp4",
                                         headers=headers, allow_redirects=False) as response:
                forwarded = {k: v for k, v in response.headers.items() if k.lower() in {
                    "content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified"}}
                forwarded.update({"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
                result = web.StreamResponse(status=response.status, headers=forwarded)
                await result.prepare(request)
                async for chunk in response.content.iter_chunked(256 * 1024):
                    await result.write(chunk)
                await result.write_eof()
                return result
        except (OSError, asyncio.TimeoutError):
            raise AuthError("影片服務暫時無法連線。", 502) from None

    app.router.add_get(r"/reels/files/{job_id:[A-Za-z0-9_-]{1,240}}.mp4", video)
