import asyncio
import os
import signal
import sys
from pathlib import Path

import redis.asyncio as redis

from ..utils.logger import setup_logger

log = setup_logger("tg-bot.worker.dispatcher")


class Dispatcher:
    """
    Watches Redis queues and spawns worker processes on-demand.

    - One worker per profile at a time (sequential dialog execution)
    - Spawns subprocess for each task
    - Workers exit after completing their task
    """

    def __init__(
        self,
        profiles: list[str],
        redis_url: str,
        result_ttl: int = 300,
    ):
        self.profiles = profiles
        self.redis_url = redis_url
        self.result_ttl = result_ttl

        self._redis: redis.Redis | None = None
        self._active_workers: dict[str, asyncio.subprocess.Process] = {}
        self._running = False

    @property
    def queues(self) -> list[str]:
        """Task queue names for all profiles."""
        return [f"tasks:{p}" for p in self.profiles]

    async def start(self) -> None:
        """Start the dispatcher."""
        log.info(f"Starting dispatcher for profiles: {', '.join(self.profiles)}")
        log.info(f"Redis: {self.redis_url}")

        self._redis = await redis.from_url(self.redis_url, decode_responses=False)
        try:
            await self._redis.ping()
            log.info("Connected to Redis")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Redis: {e}")

        self._running = True

    async def stop(self) -> None:
        """Stop dispatcher and wait for active workers."""
        log.info("Stopping dispatcher...")
        self._running = False

        # Wait for active workers to finish
        if self._active_workers:
            log.info(f"Waiting for {len(self._active_workers)} active worker(s)...")
            for profile, proc in list(self._active_workers.items()):
                try:
                    await asyncio.wait_for(proc.wait(), timeout=30)
                except asyncio.TimeoutError:
                    log.warning(f"Terminating worker for {profile}")
                    proc.terminate()

        if self._redis:
            await self._redis.close()

        log.info("Dispatcher stopped")

    async def run(self) -> None:
        """Main dispatcher loop."""
        if not self._running:
            await self.start()

        log.info(f"Watching queues: {', '.join(self.queues)}")

        # Start worker monitor task
        monitor_task = asyncio.create_task(self._monitor_workers())

        try:
            while self._running:
                # Get available profiles (not currently running a worker)
                available_queues = [
                    f"tasks:{p}" for p in self.profiles
                    if p not in self._active_workers
                ]

                if not available_queues:
                    # All profiles busy, wait a bit
                    await asyncio.sleep(0.1)
                    continue

                # Check for tasks (short timeout to stay responsive)
                result = await self._redis.blpop(available_queues, timeout=1)

                if result is None:
                    continue

                queue_name, task_data = result
                queue_name = queue_name.decode() if isinstance(queue_name, bytes) else queue_name
                profile = queue_name.split(":", 1)[1]

                # Push task back and spawn worker
                # Worker will pop it (this ensures task isn't lost if spawn fails)
                await self._redis.lpush(queue_name, task_data)

                await self._spawn_worker(profile)

        finally:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

    async def _spawn_worker(self, profile: str) -> None:
        """Spawn a worker subprocess for the given profile."""
        if profile in self._active_workers:
            log.warning(f"Worker already active for {profile}")
            return

        log.info(f"Spawning worker for {profile}")

        # Spawn subprocess
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "tgbot.cli",
            "run-task",
            "--profile", profile,
            "--redis", self.redis_url,
            "--result-ttl", str(self.result_ttl),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._active_workers[profile] = proc
        log.debug(f"Worker spawned for {profile} (PID: {proc.pid})")

    async def _monitor_workers(self) -> None:
        """Monitor and cleanup finished workers."""
        while self._running:
            finished = []

            for profile, proc in self._active_workers.items():
                if proc.returncode is not None:
                    finished.append(profile)

            for profile in finished:
                proc = self._active_workers.pop(profile)
                stdout, stderr = await proc.communicate()

                if proc.returncode == 0:
                    log.debug(f"Worker for {profile} completed successfully")
                elif proc.returncode == 1:
                    log.debug(f"Worker for {profile} found no tasks")
                else:
                    log.warning(f"Worker for {profile} failed (exit: {proc.returncode})")
                    if stderr:
                        log.warning(f"Worker stderr: {stderr.decode()}")

            await asyncio.sleep(0.1)


async def run_dispatcher(
    profiles: list[str],
    redis_url: str,
    result_ttl: int = 300,
) -> None:
    """Run dispatcher with graceful shutdown support."""
    dispatcher = Dispatcher(
        profiles=profiles,
        redis_url=redis_url,
        result_ttl=result_ttl,
    )

    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def signal_handler():
        log.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await dispatcher.start()

        dispatcher_task = asyncio.create_task(dispatcher.run())
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        done, pending = await asyncio.wait(
            [dispatcher_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

    finally:
        await dispatcher.stop()


def discover_profiles(base_dir: str | None = None) -> list[str]:
    """Discover all available profiles in the base directory."""
    base_path = Path(base_dir or os.getenv("BASE_DIR", "."))
    profiles = []

    for json_file in base_path.glob("*.json"):
        profile_name = json_file.stem
        session_file = base_path / f"{profile_name}.session"
        if session_file.exists():
            profiles.append(profile_name)

    return profiles
