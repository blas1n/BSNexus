import argparse
import asyncio
import signal

import redis.asyncio as redis_lib

from worker.src.agent import WorkerAgent
from worker.src.config import WorkerConfig
from worker.src.consumer import TaskConsumer
from worker.src.executor import create_executor


async def run(config: WorkerConfig) -> None:
    """Register the worker and start the main event loop."""
    agent = WorkerAgent(config)
    await agent.register()

    redis_client = redis_lib.from_url(config.redis_url, decode_responses=True)
    executor = create_executor(config.executor_type)
    consumer = TaskConsumer(redis_client, agent, executor)

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(agent.shutdown()))

    tasks = [
        asyncio.create_task(agent.heartbeat_loop()),
        asyncio.create_task(consumer.task_loop()),
        asyncio.create_task(consumer.qa_loop()),
    ]

    if config.duration:
        tasks.append(asyncio.create_task(asyncio.sleep(config.duration)))
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        await agent.shutdown()
    else:
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass

    await redis_client.close()


def cli_main() -> None:
    parser = argparse.ArgumentParser(description="BSNexus Worker")
    subparsers = parser.add_subparsers(dest="command")

    # --- register subcommand ---
    reg_parser = subparsers.add_parser("register", help="Register this machine as a worker and start")
    reg_parser.add_argument("--url", required=True, help="BSNexus server URL (e.g. http://localhost:8000)")
    reg_parser.add_argument("--token", required=True, help="Registration token from the admin UI")
    reg_parser.add_argument("--redis-url", default=None, help="Redis URL (default: redis://localhost:6379)")
    reg_parser.add_argument("--executor", default="claude-code", help="Executor type (default: claude-code)")
    reg_parser.add_argument("--name", default=None, help="Worker display name (auto-generated if omitted)")
    reg_parser.add_argument("--duration", type=int, default=None, help="Max run time in seconds (default: infinite)")

    # --- run subcommand (legacy / re-run) ---
    run_parser = subparsers.add_parser("run", help="Start worker with environment config")
    run_parser.add_argument("--server", default="http://localhost:8000", help="BSNexus server URL")
    run_parser.add_argument("--duration", type=int, default=None, help="Max run time in seconds")

    args = parser.parse_args()

    if args.command == "register":
        kwargs: dict = {
            "server_url": args.url,
            "registration_token": args.token,
            "executor_type": args.executor,
            "worker_name": args.name,
            "duration": args.duration,
        }
        if args.redis_url:
            kwargs["redis_url"] = args.redis_url
        config = WorkerConfig(**kwargs)
        asyncio.run(run(config))

    elif args.command == "run":
        config = WorkerConfig(
            server_url=args.server,
            duration=args.duration,
        )
        asyncio.run(run(config))

    else:
        parser.print_help()


if __name__ == "__main__":
    cli_main()
