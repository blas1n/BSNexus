import argparse
import asyncio
import signal

import redis.asyncio as redis_lib

from worker.src.agent import WorkerAgent
from worker.src.config import WorkerConfig
from worker.src.consumer import TaskConsumer
from worker.src.executor import create_executor


async def main(config: WorkerConfig) -> None:
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
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--duration", type=int, default=None)
    args = parser.parse_args()

    config = WorkerConfig(
        server_url=args.server,
        duration=args.duration,
    )

    asyncio.run(main(config))


if __name__ == "__main__":
    cli_main()
