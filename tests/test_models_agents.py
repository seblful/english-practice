"""Tests for agent I/O Pydantic models."""

from src.english_practice.models.agents import (
    AnswersContext,
    AssistantContext,
    AssistantOutput,
    ChatMessage,
    EvaluateAnswerInput,
    EvaluateAnswerOutput,
    ExerciseAnswersOutput,
    ExerciseRulesOutput,
    QuestionAnswerItem,
    QuestionRuleItem,
    RulesContext,
)


class TestEvaluateAnswerInput:
    """Tests for EvaluateAnswerInput."""

    def test_minimal_fields(self) -> None:
        model = EvaluateAnswerInput(
            question_number="1",
            user_input="my answer",
            short_answers=["a"],
            full_answers=["b"],
            is_open_ended=False,
            topic_name="Test",
        )
        assert model.question_number == "1"
        assert model.rule is None

    def test_with_rule(self) -> None:
        model = EvaluateAnswerInput(
            question_number="2",
            user_input="answer",
            short_answers=["a"],
            full_answers=["b"],
            is_open_ended=False,
            topic_name="Test",
            rule="Use present tense",
        )
        assert model.rule == "Use present tense"


class TestEvaluateAnswerOutput:
    """Tests for EvaluateAnswerOutput."""

    def test_correct_with_indexes(self) -> None:
        model = EvaluateAnswerOutput(is_correct=True, answer_idx=[0, 2])
        assert model.is_correct is True
        assert model.answer_idx == [0, 2]

    def test_incorrect_empty_indexes(self) -> None:
        model = EvaluateAnswerOutput(is_correct=False)
        assert model.is_correct is False
        assert model.answer_idx == []


class TestQuestionAnswerItem:
    """Tests for QuestionAnswerItem."""

    def test_minimal(self) -> None:
        item = QuestionAnswerItem(question_id="1", is_open_ended=False)
        assert item.short_answers == []
        assert item.full_answers == []

    def test_with_answers(self) -> None:
        item = QuestionAnswerItem(
            question_id="2",
            is_open_ended=False,
            short_answers=["yes", "no"],
            full_answers=["Yes, I do", "No, I don't"],
        )
        assert len(item.short_answers) == 2
        assert item.full_answers[1] == "No, I don't"


class TestExerciseAnswersOutput:
    """Tests for ExerciseAnswersOutput."""

    def test_empty_questions(self) -> None:
        model = ExerciseAnswersOutput(questions=[])
        assert model.questions == []

    def test_with_questions(self) -> None:
        q = QuestionAnswerItem(question_id="1", is_open_ended=False)
        model = ExerciseAnswersOutput(questions=[q])
        assert len(model.questions) == 1


class TestAnswersContext:
    """Tests for AnswersContext."""

    def test_fields(self) -> None:
        ctx = AnswersContext(questions=[{"id": "1"}], topic_name="Grammar")
        assert ctx.topic_name == "Grammar"
        assert ctx.questions == [{"id": "1"}]


class TestQuestionRuleItem:
    """Tests for QuestionRuleItem."""

    def test_minimal(self) -> None:
        item = QuestionRuleItem(question_id="1")
        assert item.section_letter is None
        assert item.rule is None

    def test_full(self) -> None:
        item = QuestionRuleItem(
            question_id="2", section_letter="A", rule="Use present continuous"
        )
        assert item.section_letter == "A"
        assert item.rule == "Use present continuous"


class TestExerciseRulesOutput:
    """Tests for ExerciseRulesOutput."""

    def test_with_rules(self) -> None:
        r = QuestionRuleItem(question_id="1", section_letter="A", rule="rule")
        model = ExerciseRulesOutput(questions=[r])
        assert len(model.questions) == 1


class TestRulesContext:
    """Tests for RulesContext."""

    def test_fields(self) -> None:
        ctx = RulesContext(questions=[{"id": "1"}], rules_md="# Rules", topic_name="Tenses")
        assert ctx.rules_md == "# Rules"


class TestChatMessage:
    """Tests for ChatMessage."""

    def test_fields(self) -> None:
        msg = ChatMessage(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"


class TestAssistantContext:
    """Tests for AssistantContext."""

    def test_minimal(self) -> None:
        ctx = AssistantContext(
            question_number="1", user_input="help", topic_name="Test"
        )
        assert ctx.chat_history == []

    def test_with_history(self) -> None:
        history = [ChatMessage(role="user", content="hi")]
        ctx = AssistantContext(
            question_number="1",
            user_input="help",
            topic_name="Test",
            chat_history=history,
        )
        assert len(ctx.chat_history) == 1


class TestAssistantOutput:
    """Tests for AssistantOutput."""

    def test_fields(self) -> None:
        out = AssistantOutput(answer="Here is help")
        assert out.answer == "Here is help"
