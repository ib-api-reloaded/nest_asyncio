import asyncio
import pathlib
import subprocess
import sys
import textwrap
import unittest
from contextvars import ContextVar

import nest_asyncio


def exception_handler(loop, context):
    print("Exception:", context)


class NestTest(unittest.TestCase):
    @staticmethod
    def run_snippet(snippet):
        repo_root = pathlib.Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, "-Wdefault", "-c", textwrap.dedent(snippet)],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"snippet failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        nest_asyncio.apply(self.loop)
        asyncio.set_event_loop(self.loop)
        self.loop.set_debug(True)
        self.loop.set_exception_handler(exception_handler)

    def tearDown(self):
        self.assertIsNone(asyncio._get_running_loop())
        self.loop.close()
        del self.loop

    async def coro(self):
        await asyncio.sleep(0.01)
        return 42

    def test_nesting(self):
        async def f1():
            result = self.loop.run_until_complete(self.coro())
            self.assertEqual(result, await self.coro())
            return result

        async def f2():
            result = self.loop.run_until_complete(f1())
            self.assertEqual(result, await f1())
            return result

        result = self.loop.run_until_complete(f2())
        self.assertEqual(result, 42)

    def test_ensure_future_with_run_until_complete(self):
        async def f():
            task = asyncio.ensure_future(self.coro())
            return self.loop.run_until_complete(task)

        result = self.loop.run_until_complete(f())
        self.assertEqual(result, 42)

    def test_ensure_future_with_run_until_complete_with_wait(self):
        async def f():
            task = asyncio.ensure_future(self.coro())
            done, pending = self.loop.run_until_complete(
                asyncio.wait([task], return_when=asyncio.ALL_COMPLETED)
            )
            task = done.pop()
            return task.result()

        result = self.loop.run_until_complete(f())
        self.assertEqual(result, 42)

    def test_timeout(self):
        async def f1():
            await asyncio.sleep(0.1)

        async def f2():
            asyncio.run(asyncio.wait_for(f1(), 0.01))

        with self.assertRaises(asyncio.TimeoutError):
            self.loop.run_until_complete(f2())

    def test_two_run_until_completes_in_one_outer_loop(self):
        async def f1():
            self.loop.run_until_complete(asyncio.sleep(0.02))
            return 4

        async def f2():
            self.loop.run_until_complete(asyncio.sleep(0.01))
            return 2

        result = self.loop.run_until_complete(asyncio.gather(f1(), f2()))
        self.assertEqual(result, [4, 2])

    def test_contextvars(self):
        var = ContextVar("var")
        var.set(0)

        async def set_val():
            var.set(42)

        async def coro():
            await set_val()
            await asyncio.sleep(0.01)
            return var.get()

        result = self.loop.run_until_complete(coro())
        self.assertEqual(result, 42)

    @unittest.skipIf(sys.version_info < (3, 12, 0), "No loop_factory support")
    def test_asyncio_run_accepts_loop_factory(self):
        self.run_snippet(
            """
            import asyncio
            import nest_asyncio

            nest_asyncio.apply()
            asyncio.set_event_loop(None)
            made = []

            def loop_factory():
                loop = asyncio.new_event_loop()
                made.append(loop)
                return loop

            async def work():
                return asyncio.get_running_loop()

            ran_on = asyncio.run(work(), loop_factory=loop_factory)
            assert len(made) == 1, made
            assert ran_on is made[0]
            assert made[0].is_closed()

            try:
                current = asyncio.get_event_loop()
            except RuntimeError:
                current = None
            assert current is not made[0]
            if current is not None:
                current.close()
            asyncio.set_event_loop(None)
            """
        )

    @unittest.skipIf(sys.version_info < (3, 12, 0), "No loop_factory support")
    def test_asyncio_run_loop_factory_overrides_current_loop(self):
        self.run_snippet(
            """
            import asyncio
            import nest_asyncio

            current = asyncio.new_event_loop()
            asyncio.set_event_loop(current)
            nest_asyncio.apply()
            made = []

            def loop_factory():
                loop = asyncio.new_event_loop()
                made.append(loop)
                return loop

            async def work():
                return asyncio.get_running_loop()

            async def outer():
                return asyncio.run(work(), loop_factory=loop_factory)

            ran_on = asyncio.run(work(), loop_factory=loop_factory)
            assert len(made) == 1, made
            assert ran_on is made[0]
            assert made[0].is_closed()
            assert asyncio.get_event_loop() is current

            ran_on = current.run_until_complete(outer())
            assert len(made) == 2, made
            assert ran_on is made[1]
            assert made[1].is_closed()
            assert asyncio.get_event_loop() is current

            current.close()
            asyncio.set_event_loop(None)
            """
        )

    @unittest.skipIf(sys.version_info < (3, 12, 0), "No loop_factory support")
    def test_asyncio_run_closes_loop_factory_loop_it_cannot_patch(self):
        self.run_snippet(
            """
            import asyncio
            import nest_asyncio

            nest_asyncio.apply()
            asyncio.set_event_loop(None)

            class UnpatchableLoop(asyncio.AbstractEventLoop):
                closed = False

                def close(self):
                    self.closed = True

            made = []

            def loop_factory():
                loop = UnpatchableLoop()
                made.append(loop)
                return loop

            async def work():
                pass

            coro = work()
            try:
                asyncio.run(coro, loop_factory=loop_factory)
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")
            coro.close()
            assert len(made) == 1, made
            assert made[0].closed

            try:
                current = asyncio.get_event_loop()
            except RuntimeError:
                current = None
            assert current is not made[0]
            if current is not None:
                current.close()
            asyncio.set_event_loop(None)
            """
        )

    def test_run_until_complete_runs_again_after_stop(self):
        fut = self.loop.create_future()
        self.loop.call_soon(self.loop.stop)
        with self.assertRaisesRegex(RuntimeError, "stopped before Future completed"):
            self.loop.run_until_complete(fut)
        fut.cancel()
        self.assertEqual(self.loop.run_until_complete(self.coro()), 42)

    def test_nested_run_leaves_outer_loop_debug_alone(self):
        async def inner():
            return asyncio.get_running_loop().get_debug()

        async def outer():
            return asyncio.run(inner())

        self.assertTrue(self.loop.get_debug())
        self.assertTrue(self.loop.run_until_complete(outer()))
        self.assertTrue(self.loop.get_debug())

    @unittest.skipIf(sys.version_info < (3, 14, 0), "Python 3.14+ only")
    def test_apply_inside_running_task_preserves_current_task(self):
        self.run_snippet(
            """
            import asyncio
            import warnings
            import nest_asyncio

            warnings.filterwarnings("default")

            async def work():
                with warnings.catch_warnings(record=True) as caught:
                    nest_asyncio.apply()
                    assert asyncio.tasks.current_task() is not None
                    assert not caught, [str(item.message) for item in caught]

            asyncio.run(work())
            """
        )

    def test_nested_run_drains_call_soon_done_callbacks(self):
        self.run_snippet(
            """
            import asyncio
            import nest_asyncio

            nest_asyncio.apply()
            seen = []

            async def work():
                loop = asyncio.get_running_loop()
                task = asyncio.create_task(asyncio.sleep(0))
                task.add_done_callback(
                    lambda _: loop.call_soon(lambda: seen.append("soon"))
                )
                await task

            async def outer():
                asyncio.run(work())

            asyncio.run(outer())
            assert seen == ["soon"], seen
            """
        )

    def test_apply_registers_the_asyncio_future_with_an_imported_tornado(self):
        self.run_snippet(
            """
            import asyncio
            import sys
            import types

            tornado = types.ModuleType("tornado")
            concurrent = types.ModuleType("tornado.concurrent")
            concurrent.Future = object
            concurrent.FUTURES = (object,)
            tornado.concurrent = concurrent
            sys.modules["tornado"] = tornado
            sys.modules["tornado.concurrent"] = concurrent

            import nest_asyncio

            nest_asyncio.apply(asyncio.new_event_loop())
            assert concurrent.Future is asyncio.Future
            assert concurrent.FUTURES == (object, asyncio.Future)
            nest_asyncio.apply(asyncio.new_event_loop())
            assert concurrent.FUTURES == (object, asyncio.Future)
            """
        )

    def test_apply_leaves_tornado_alone_unless_imported(self):
        self.run_snippet(
            """
            import asyncio
            import sys
            import nest_asyncio

            nest_asyncio.apply(asyncio.new_event_loop())
            assert "tornado" not in sys.modules
            """
        )


if __name__ == "__main__":
    unittest.main()
