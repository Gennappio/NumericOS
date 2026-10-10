from __future__ import annotations

import asyncio
import threading

from numericos.events.notifier import EventNotifier


def test_publish_from_another_thread_wakes_the_subscriber() -> None:
    notifier = EventNotifier()

    async def scenario() -> None:
        with notifier.subscribe("prj_1") as wake:
            assert notifier.subscriber_count("prj_1") == 1
            threading.Thread(target=notifier.publish, args=("prj_1", 7)).start()
            await asyncio.wait_for(wake.wait(), timeout=2)
        assert notifier.subscriber_count("prj_1") == 0

    asyncio.run(scenario())


def test_publish_targets_only_the_given_project() -> None:
    notifier = EventNotifier()

    async def scenario() -> None:
        with notifier.subscribe("prj_1") as wake_1, notifier.subscribe("prj_2") as wake_2:
            notifier.publish("prj_2", 1)
            await asyncio.sleep(0)
            assert not wake_1.is_set()
            assert wake_2.is_set()

    asyncio.run(scenario())
