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


def test_a_head_moved_by_another_process_wakes_every_subscriber_once() -> None:
    notifier = EventNotifier()

    async def scenario() -> None:
        with notifier.subscribe("prj_1") as wake_1, notifier.subscribe("prj_2") as wake_2:
            notifier.publish("prj_1", 5)
            await asyncio.sleep(0)
            wake_1.clear()

            known = notifier.announce_foreign(5)  # this process committed seq 5 itself
            await asyncio.sleep(0)
            assert known is False
            assert not wake_1.is_set()
            assert not wake_2.is_set()

            news = notifier.announce_foreign(8)  # somebody else wrote: whose project is unknown
            await asyncio.sleep(0)
            assert news is True
            assert wake_1.is_set()
            assert wake_2.is_set()

            assert notifier.announce_foreign(8) is False

    asyncio.run(scenario())
