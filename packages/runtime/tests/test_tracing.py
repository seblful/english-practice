"""Tests for the tracing decorator."""

from practice_runtime.tracing import traced


class TestTraced:
    def test_the_wrapped_function_still_runs(self) -> None:
        @traced(name="adder")
        def add(left: int, right: int) -> int:
            return left + right

        assert add(2, 3) == 5

    def test_keyword_arguments_survive_the_wrapper(self) -> None:
        """The point of the cast is that call sites stay type-checked."""

        @traced()
        def greet(*, name: str) -> str:
            return f"hello {name}"

        assert greet(name="world") == "hello world"

    async def test_an_async_function_is_still_awaitable(self) -> None:
        @traced(name="fetch")
        async def fetch() -> str:
            return "done"

        assert await fetch() == "done"
