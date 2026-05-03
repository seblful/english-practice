"""Tests for ChatHistoryManager."""

from src.english_practice.services.chat_history import ChatHistoryManager


class TestChatHistoryManager:
    """Tests for ChatHistoryManager."""

    def test_initial_state_empty(self) -> None:
        manager = ChatHistoryManager()
        assert manager.get_history(1, 1) == []

    def test_add_and_get_message(self) -> None:
        manager = ChatHistoryManager()
        manager.add_message(1, 1, "user", "hello")
        history = manager.get_history(1, 1)
        assert len(history) == 1
        assert history[0] == {"role": "user", "content": "hello"}

    def test_multiple_messages_same_user_exercise(self) -> None:
        manager = ChatHistoryManager()
        manager.add_message(1, 1, "user", "hello")
        manager.add_message(1, 1, "assistant", "hi there")
        history = manager.get_history(1, 1)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_separate_exercises(self) -> None:
        manager = ChatHistoryManager()
        manager.add_message(1, 1, "user", "ex1 msg")
        manager.add_message(1, 2, "user", "ex2 msg")
        assert len(manager.get_history(1, 1)) == 1
        assert len(manager.get_history(1, 2)) == 1

    def test_separate_users(self) -> None:
        manager = ChatHistoryManager()
        manager.add_message(1, 1, "user", "user1 msg")
        manager.add_message(2, 1, "user", "user2 msg")
        assert len(manager.get_history(1, 1)) == 1
        assert len(manager.get_history(2, 1)) == 1

    def test_clear_history(self) -> None:
        manager = ChatHistoryManager()
        manager.add_message(1, 1, "user", "hello")
        manager.clear_history(1, 1)
        assert manager.get_history(1, 1) == []

    def test_clear_history_other_exercise_untouched(self) -> None:
        manager = ChatHistoryManager()
        manager.add_message(1, 1, "user", "ex1")
        manager.add_message(1, 2, "user", "ex2")
        manager.clear_history(1, 1)
        assert len(manager.get_history(1, 2)) == 1

    def test_clear_nonexistent_history(self) -> None:
        manager = ChatHistoryManager()
        manager.clear_history(999, 1)  # Should not raise

    def test_clear_user_history(self) -> None:
        manager = ChatHistoryManager()
        manager.add_message(1, 1, "user", "msg1")
        manager.add_message(1, 2, "user", "msg2")
        manager.clear_user_history(1)
        assert manager.get_history(1, 1) == []
        assert manager.get_history(1, 2) == []

    def test_clear_user_history_other_user_untouched(self) -> None:
        manager = ChatHistoryManager()
        manager.add_message(1, 1, "user", "user1 msg")
        manager.add_message(2, 1, "user", "user2 msg")
        manager.clear_user_history(1)
        assert len(manager.get_history(2, 1)) == 1

    def test_clear_nonexistent_user(self) -> None:
        manager = ChatHistoryManager()
        manager.clear_user_history(999)  # Should not raise

    def test_on_new_image_keeps_new_exercise_history(self) -> None:
        manager = ChatHistoryManager()
        manager.add_message(1, 1, "user", "ex1 msg")
        manager.add_message(1, 2, "user", "ex2 msg")
        manager.on_new_image(1, 2)
        assert manager.get_history(1, 2) == [{"role": "user", "content": "ex2 msg"}]
        assert manager.get_history(1, 1) == []

    def test_on_new_image_new_exercise_no_history(self) -> None:
        manager = ChatHistoryManager()
        manager.add_message(1, 1, "user", "ex1 msg")
        manager.on_new_image(1, 3)
        assert manager.get_history(1, 3) == []

    def test_on_new_image_nonexistent_user(self) -> None:
        manager = ChatHistoryManager()
        manager.on_new_image(999, 1)  # Should not raise
