"""Tests for StateManager and UserSession."""

from src.english_practice.bot.states import StateManager, UserSession, state_manager


class TestUserSession:
    """Tests for UserSession dataclass."""

    def test_default_values(self) -> None:
        session = UserSession(user_id=1)
        assert session.user_id == 1
        assert session.current_exercise_id is None
        assert session.current_question_id is None
        assert session.current_question_db_id is None
        assert session.current_topic_id is None
        assert session.current_topic_name is None
        assert session.current_unit_number is None
        assert session.current_is_open_ended is False
        assert session.unit_shown is False
        assert session.answered is False
        assert session.available_questions == []
        assert session.show_rule is True

    def test_clear_exercise(self) -> None:
        session = UserSession(user_id=1)
        session.current_exercise_id = 5
        session.current_question_id = "2"
        session.current_question_db_id = 10
        session.current_topic_name = "Test"
        session.current_unit_number = 3
        session.current_is_open_ended = True
        session.unit_shown = True
        session.answered = True
        session.available_questions = ["1", "2"]

        session.clear_exercise()

        assert session.current_exercise_id is None
        assert session.current_question_id is None
        assert session.current_question_db_id is None
        assert session.current_topic_name is None
        assert session.current_unit_number is None
        assert session.current_is_open_ended is False
        assert session.unit_shown is False
        assert session.answered is False
        assert session.available_questions == []


class TestStateManager:
    """Tests for StateManager."""

    def test_get_session_creates_new(self) -> None:
        manager = StateManager()
        session = manager.get_session(1)
        assert isinstance(session, UserSession)
        assert session.user_id == 1

    def test_get_session_returns_same(self) -> None:
        manager = StateManager()
        session1 = manager.get_session(1)
        session2 = manager.get_session(1)
        assert session1 is session2

    def test_get_session_multiple_users(self) -> None:
        manager = StateManager()
        session1 = manager.get_session(1)
        session2 = manager.get_session(2)
        assert session1 is not session2
        assert session1.user_id == 1
        assert session2.user_id == 2

    def test_clear_session(self) -> None:
        manager = StateManager()
        manager.get_session(1)
        assert 1 in manager.sessions
        manager.clear_session(1)
        assert 1 not in manager.sessions

    def test_clear_session_nonexistent(self) -> None:
        manager = StateManager()
        manager.clear_session(999)  # Should not raise

    def test_set_exercise(self) -> None:
        manager = StateManager()
        manager.set_exercise(
            user_id=1,
            exercise_id=5,
            question_id="2",
            question_db_id=10,
            topic_id=1,
            topic_name="Present Tenses",
            unit_number=3,
            available_questions=["1", "2"],
            is_open_ended=False,
        )
        session = manager.get_session(1)
        assert session.current_exercise_id == 5
        assert session.current_question_id == "2"
        assert session.current_question_db_id == 10
        assert session.current_topic_id == 1
        assert session.current_topic_name == "Present Tenses"
        assert session.current_unit_number == 3
        assert session.current_is_open_ended is False
        assert session.unit_shown is False
        assert session.answered is False
        assert session.available_questions == ["1", "2"]

    def test_set_exercise_with_open_ended(self) -> None:
        manager = StateManager()
        manager.set_exercise(
            user_id=1,
            exercise_id=5,
            question_id="3",
            question_db_id=11,
            topic_id=None,
            topic_name="Random",
            unit_number=3,
            available_questions=["3"],
            is_open_ended=True,
        )
        session = manager.get_session(1)
        assert session.current_is_open_ended is True
        assert session.current_topic_id is None

    def test_mark_unit_shown(self) -> None:
        manager = StateManager()
        manager.get_session(1)
        manager.mark_unit_shown(1)
        assert manager.get_session(1).unit_shown is True

    def test_mark_answered(self) -> None:
        manager = StateManager()
        manager.get_session(1)
        manager.mark_answered(1)
        assert manager.get_session(1).answered is True

    def test_toggle_show_rule_default_true(self) -> None:
        manager = StateManager()
        manager.get_session(1)
        result = manager.toggle_show_rule(1)
        assert result is False
        assert manager.get_session(1).show_rule is False

    def test_toggle_show_rule_twice(self) -> None:
        manager = StateManager()
        manager.get_session(1)
        manager.toggle_show_rule(1)
        result = manager.toggle_show_rule(1)
        assert result is True

    def test_singleton_state_manager(self) -> None:
        assert isinstance(state_manager, StateManager)
        assert isinstance(StateManager(), StateManager)


class TestStateManagerSetExerciseResetsFlags:
    """Tests that set_exercise resets flags properly."""

    def test_resets_answered_and_unit_shown(self) -> None:
        manager = StateManager()
        session = manager.get_session(1)
        session.answered = True
        session.unit_shown = True

        manager.set_exercise(
            user_id=1,
            exercise_id=5,
            question_id="1",
            question_db_id=10,
            topic_id=1,
            topic_name="Test",
            unit_number=3,
            available_questions=["1"],
        )
        assert session.answered is False
        assert session.unit_shown is False
