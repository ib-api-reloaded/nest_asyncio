import asyncio
import pathlib
import subprocess
import sys
import textwrap
import unittest

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

    @unittest.skipIf(sys.version_info < (3, 7, 0), "No contextvars module")
    def test_contextvars(self):
        from contextvars import ContextVar

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
            state = {"hit": False}

            def loop_factory():
                state["hit"] = True
                return asyncio.new_event_loop()

            async def work():
                assert asyncio.get_running_loop() is not None

            asyncio.run(work(), loop_factory=loop_factory)
            assert state["hit"], state

            loop = asyncio.get_event_loop()
            loop.close()
            asyncio.set_event_loop(None)
            """
        )

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


if __name__ == "__main__":
    unittest.main()
