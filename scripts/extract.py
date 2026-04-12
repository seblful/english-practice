import json
import sys
from enum import Enum
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from tqdm import tqdm

from config.logging import get_logger
from config.settings import settings
from english_practice.extractors import (
    AnswerExtractor,
    ExerciseOrganizer,
    ImageOcrExtractor,
    PDFHandler,
    RuleExtractor,
)
from english_practice.models.constants import (
    END_ANSWER_PAGE,
    END_CONTENT_PAGE,
    END_UNIT_PAGE,
    START_ANSWER_PAGE,
    START_CONTENT_PAGE,
    START_UNIT_PAGE,
)

logger = get_logger(__name__)

app = typer.Typer()


class SectionType(str, Enum):
    contents = "contents"
    units = "units"
    answers = "answers"


def split_short_answers(answer: str) -> list[str]:
    """Split a short answer string by / or | to get individual answers."""
    for sep in ["/", "|"]:
        if sep in answer:
            return [a.strip() for a in answer.split(sep)]
    return [answer.strip()]


def get_image_path(exercise_id: str) -> Path | None:
    """Get the image path for an exercise."""
    parts = exercise_id.split(".")
    if len(parts) != 2:
        return None

    page_num = parts[0]
    image_path = settings.paths.exercises_dir / page_num / f"{exercise_id}.png"

    if image_path.exists():
        return image_path

    image_path = (
        settings.paths.content_dir / "exercises" / page_num / f"{exercise_id}.png"
    )
    if image_path.exists():
        return image_path

    return None


def get_grammar_md(unit_number: int) -> str | None:
    """Get grammar markdown content for a unit."""
    grammar_path = settings.paths.grammar_md_dir / f"{unit_number}.md"
    if grammar_path.exists():
        return grammar_path.read_text(encoding="utf-8")

    grammar_path = settings.paths.content_dir / "grammar" / f"{unit_number}.md"
    if grammar_path.exists():
        return grammar_path.read_text(encoding="utf-8")

    return None


@app.command(
    name="cut-pdf",
    help="Cut a PDF file based on the section type provided.",
)
def cut_pdf(
    section: SectionType = typer.Argument(
        ..., help="The section of the book to cut (contents, units, answers)."
    ),
) -> None:

    page_ranges = {
        SectionType.contents: (START_CONTENT_PAGE, END_CONTENT_PAGE),
        SectionType.units: (START_UNIT_PAGE, END_UNIT_PAGE),
        SectionType.answers: (START_ANSWER_PAGE, END_ANSWER_PAGE),
    }

    start_page, end_page = page_ranges[section]

    logger.info(
        f"Cutting PDF for section '{section.value}': Pages {start_page} to {end_page}"
    )

    handler = PDFHandler()
    output_path = settings.paths.snippets_dir / f"{section.value}.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handler.cut_pdf(
        file_path=settings.paths.source_dir / settings.book.filename,
        start_page=start_page,
        end_page=end_page,
        output_path=output_path,
    )


@app.command(
    name="separate-page-images",
    help="Separate pages from a PDF file into grammar pages and exercise pages.",
)
def separate_page_images() -> None:
    handler = PDFHandler()
    handler.separate_page_images(
        file_path=settings.paths.source_dir / settings.book.filename,
        start_page=START_UNIT_PAGE,
        end_page=END_UNIT_PAGE,
        grammar_pages_dir=settings.paths.grammar_pages_dir,
        exercises_pages_dir=settings.paths.exercises_pages_dir,
        dpi=settings.images.pages_dpi,
    )


@app.command(
    name="ocr-grammar-images",
    help="Extract text from grammar page images via OCR and save to data/grammar (resumable).",
)
def ocr_grammar_images() -> None:
    """Run OCR on grammar page images; save .md to data/grammar. Skips existing."""
    extractor = ImageOcrExtractor(
        api_key=settings.ocr.api_key,
        model=settings.ocr.model,
    )
    settings.paths.grammar_md_dir.mkdir(parents=True, exist_ok=True)
    written = extractor.ocr_dir(
        settings.paths.grammar_pages_dir,
        output_dir=settings.paths.grammar_md_dir,
    )
    logger.info(
        f"Wrote {len(written)} markdown file(s) to {settings.paths.grammar_md_dir}"
    )


@app.command(
    name="organize-exercises",
    help="Organize exercise images into numbered folders.",
)
def organize_exercises() -> None:
    """Organize exercise images into separate folders."""
    organizer = ExerciseOrganizer()
    created = organizer.organize(
        file_path=settings.paths.exercises_pages_dir,
        output_dir=settings.paths.exercises_dir,
    )
    logger.info(f"Organized {len(created)} exercises to {settings.paths.exercises_dir}")


@app.command(
    name="full-answers",
    help="Extract full answers from exercise images using LLM.",
)
async def extract_full_answers(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing answers_full.json"
    ),
) -> None:
    """Extract full answers from exercise images using LLM.

    Processes all questions per exercise in a single LLM call.
    Outputs to answers_full.json.
    """
    output_path = settings.paths.metadata_dir / "answers_full.json"

    if output_path.exists() and not force:
        logger.info(f"answers_full.json already exists at {output_path}")
        logger.info("Use --force to overwrite")
        return

    answers_path = settings.paths.metadata_dir / "answers.json"
    if not answers_path.exists():
        raise FileNotFoundError(f"answers.json not found at {answers_path}")

    data = json.loads(answers_path.read_text(encoding="utf-8"))

    extractor = AnswerExtractor()
    results = {"units": []}

    for unit in tqdm(data.get("units", []), desc="Processing units"):
        unit_data = {
            "unit_id": unit["unit_id"],
            "exercises": [],
        }

        for exercise in tqdm(unit.get("exercises", []), desc=f"Unit {unit['unit_id']}"):
            exercise_id = exercise["exercise_id"]
            image_path = get_image_path(exercise_id)

            exercise_data = {
                "exercise_id": exercise_id,
                "questions": [],
            }

            if not image_path:
                logger.warning(f"Image not found for {exercise_id}, skipping")
                for question in exercise.get("questions", []):
                    question_id = question["question_id"]
                    raw_answer = question["answer"]
                    short_answers = split_short_answers(raw_answer)
                    exercise_data["questions"].append(
                        {
                            "question_id": question_id,
                            "is_open_ended": False,
                            "answers": [
                                {"short_answer": sa, "full_answer": f"[No image: {sa}]"}
                                for sa in short_answers
                            ],
                        }
                    )
                unit_data["exercises"].append(exercise_data)
                continue

            questions_for_extraction = []
            for question in exercise.get("questions", []):
                question_id = question["question_id"]
                raw_answer = question["answer"]
                short_answers = split_short_answers(raw_answer)
                questions_for_extraction.append(
                    {
                        "question_id": question_id,
                        "short_answers": short_answers,
                    }
                )

            try:
                result = await extractor.extract_exercise(
                    image_path=image_path,
                    questions=questions_for_extraction,
                    topic_name="English Grammar",
                )

                result_map = {q.question_id: q for q in result.questions}

                for q_input in questions_for_extraction:
                    question_id = q_input["question_id"]
                    short_answers = q_input["short_answers"]
                    q_result = result_map.get(question_id)

                    if not q_result:
                        exercise_data["questions"].append(
                            {
                                "question_id": question_id,
                                "is_open_ended": False,
                                "answers": [
                                    {
                                        "short_answer": sa,
                                        "full_answer": f"[Missing: {sa}]",
                                    }
                                    for sa in short_answers
                                ],
                            }
                        )
                        continue

                    if q_result.is_open_ended:
                        exercise_data["questions"].append(
                            {
                                "question_id": question_id,
                                "is_open_ended": True,
                                "answers": [],
                            }
                        )
                    else:
                        answers_list = []
                        for i, short_answer in enumerate(short_answers):
                            if i == 0 and q_result.full_answer:
                                full_answer = q_result.full_answer
                            else:
                                full_answer = (
                                    q_result.full_answer or f"[{short_answer}]"
                                )

                            answers_list.append(
                                {
                                    "short_answer": short_answer,
                                    "full_answer": full_answer,
                                }
                            )

                        exercise_data["questions"].append(
                            {
                                "question_id": question_id,
                                "is_open_ended": False,
                                "answers": answers_list,
                            }
                        )

            except Exception as e:
                logger.error(f"Error extracting full answers for {exercise_id}: {e}")
                for question in exercise.get("questions", []):
                    question_id = question["question_id"]
                    raw_answer = question["answer"]
                    short_answers = split_short_answers(raw_answer)
                    exercise_data["questions"].append(
                        {
                            "question_id": question_id,
                            "is_open_ended": False,
                            "answers": [
                                {"short_answer": sa, "full_answer": f"[Error: {e}]"}
                                for sa in short_answers
                            ],
                        }
                    )

            unit_data["exercises"].append(exercise_data)

        results["units"].append(unit_data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(f"Full answers extracted to {output_path}")


@app.command(
    name="rules",
    help="Extract grammar rules from exercises using LLM.",
)
async def extract_rules(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing rules.json"
    ),
) -> None:
    """Extract grammar rules from exercises using LLM.

    Processes all questions per exercise in a single LLM call.
    Outputs to rules.json.
    """
    output_path = settings.paths.metadata_dir / "rules.json"

    if output_path.exists() and not force:
        logger.info(f"rules.json already exists at {output_path}")
        logger.info("Use --force to overwrite")
        return

    answers_path = settings.paths.metadata_dir / "answers.json"
    if not answers_path.exists():
        raise FileNotFoundError(f"answers.json not found at {answers_path}")

    answers_full_path = settings.paths.metadata_dir / "answers_full.json"
    if answers_full_path.exists():
        answers_full = json.loads(answers_full_path.read_text(encoding="utf-8"))
    else:
        logger.warning("answers_full.json not found, using short answers only")
        answers_full = None

    data = json.loads(answers_path.read_text(encoding="utf-8"))

    answers_full_map = {}
    if answers_full:
        for u in answers_full.get("units", []):
            for e in u.get("exercises", []):
                for q in e.get("questions", []):
                    key = f"{e['exercise_id']}:{q['question_id']}"
                    answers_full_map[key] = q

    extractor = RuleExtractor()
    results = {"units": []}

    for unit in tqdm(data.get("units", []), desc="Processing units"):
        unit_number = int(unit["unit_id"])
        rules_md = get_grammar_md(unit_number)

        if not rules_md:
            logger.warning(f"Grammar markdown not found for unit {unit_number}")

        unit_data = {
            "unit_id": unit["unit_id"],
            "exercises": [],
        }

        for exercise in tqdm(unit.get("exercises", []), desc=f"Unit {unit['unit_id']}"):
            exercise_id = exercise["exercise_id"]
            image_path = get_image_path(exercise_id)

            exercise_data = {
                "exercise_id": exercise_id,
                "questions": [],
            }

            questions_for_extraction = []
            for question in exercise.get("questions", []):
                question_id = question["question_id"]
                raw_answer = question["answer"]
                short_answers = split_short_answers(raw_answer)
                short_answer_str = " / ".join(short_answers) if short_answers else ""

                key = f"{exercise_id}:{question_id}"
                full_info = answers_full_map.get(key, {})
                is_open_ended = full_info.get("is_open_ended", False)
                answers = full_info.get("answers", [])
                full_answer_str = answers[0]["full_answer"] if answers else ""

                questions_for_extraction.append(
                    {
                        "question_id": question_id,
                        "is_open_ended": is_open_ended,
                        "short_answer": short_answer_str,
                        "full_answer": full_answer_str,
                    }
                )

            if is_open_ended or not image_path or not rules_md:
                for q in questions_for_extraction:
                    exercise_data["questions"].append(
                        {
                            "question_id": q["question_id"],
                            "is_open_ended": q["is_open_ended"],
                            "section_letter": None,
                            "rule": None,
                        }
                    )
                unit_data["exercises"].append(exercise_data)
                continue

            try:
                result = await extractor.extract_exercise(
                    image_path=image_path,
                    questions=questions_for_extraction,
                    rules_md=rules_md,
                    topic_name="English Grammar",
                )

                result_map = {q.question_id: q for q in result.questions}

                for q_input in questions_for_extraction:
                    question_id = q_input["question_id"]
                    q_result = result_map.get(question_id)

                    if q_input["is_open_ended"]:
                        exercise_data["questions"].append(
                            {
                                "question_id": question_id,
                                "is_open_ended": True,
                                "section_letter": None,
                                "rule": None,
                            }
                        )
                    elif q_result:
                        exercise_data["questions"].append(
                            {
                                "question_id": question_id,
                                "is_open_ended": False,
                                "section_letter": q_result.section_letter,
                                "rule": q_result.rule,
                            }
                        )
                    else:
                        exercise_data["questions"].append(
                            {
                                "question_id": question_id,
                                "is_open_ended": False,
                                "section_letter": None,
                                "rule": "[Missing]",
                            }
                        )

            except Exception as e:
                logger.error(f"Error extracting rules for {exercise_id}: {e}")
                for q in questions_for_extraction:
                    exercise_data["questions"].append(
                        {
                            "question_id": q["question_id"],
                            "is_open_ended": q["is_open_ended"],
                            "section_letter": None,
                            "rule": f"[Error: {e}]",
                        }
                    )

            unit_data["exercises"].append(exercise_data)

        results["units"].append(unit_data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(f"Rules extracted to {output_path}")


if __name__ == "__main__":
    app()
