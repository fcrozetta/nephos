from __future__ import annotations

import asyncio

from nephos_api.reconciler import Reconciler


class ReconcilerWorker:
    def __init__(
        self,
        reconciler: Reconciler,
        *,
        interval_seconds: float,
    ) -> None:
        self._reconciler = reconciler
        self._interval_seconds = interval_seconds
        self._stop = asyncio.Event()

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                processed = await asyncio.to_thread(self._reconciler.run_once)
            except Exception:
                await self._wait()
                continue
            if processed:
                await asyncio.sleep(0)
                continue
            await self._wait()

    async def _wait(self) -> None:
        try:
            await asyncio.wait_for(
                self._stop.wait(),
                timeout=self._interval_seconds,
            )
        except TimeoutError:
            return

    async def stop(self) -> None:
        self._stop.set()
