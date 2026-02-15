#!/usr/bin/env python3
"""Check if all exercise IDs in answers.json have corresponding files in exercises folder."""

import json
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).resolve().parent.parent


def load_answers_json(answers_path: Path) -> dict:
    """Load and parse the answers.json file."""
    with open(answers_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_exercise_ids(data: dict) -> set[str]:
    """Extract all exercise_id values from the JSON structure."""
    exercise_ids = set()

    for unit in data.get("units", []):
        for exercise in unit.get("exercises", []):
            exercise_id = exercise.get("exercise_id")
            if exercise_id:
                exercise_ids.add(exercise_id)

    return exercise_ids


def scan_exercise_files(exercises_dir: Path) -> set[str]:
    """Scan exercises directory and extract exercise IDs from filenames."""
    exercise_files = set()

    if not exercises_dir.exists():
        return exercise_files

    # Files are in format: {page}/{page}.{exercise}.png
    for page_dir in exercises_dir.iterdir():
        if page_dir.is_dir():
            for file_path in page_dir.glob("*.png"):
                # Extract exercise_id from filename like "1.1.png" -> "1.1"
                exercise_id = file_path.stem
                exercise_files.add(exercise_id)

    return exercise_files


def check_exercises() -> int:
    """Main function to check exercise coverage."""
    project_root = get_project_root()
    answers_path = project_root / "data" / "content" / "metadata" / "answers.json"
    exercises_dir = project_root / "data" / "content" / "exercises"

    print("Checking exercise coverage...")
    print()

    # Load answers.json
    if not answers_path.exists():
        print(f"Error: answers.json not found at {answers_path}")
        return 1

    data = load_answers_json(answers_path)
    json_exercises = extract_exercise_ids(data)

    print(f"Found {len(json_exercises)} exercise IDs in answers.json")

    # Scan exercise files
    file_exercises = scan_exercise_files(exercises_dir)
    print(f"Found {len(file_exercises)} exercise files in content/exercises/")
    print()

    # Find differences
    missing = sorted(json_exercises - file_exercises)
    extra = sorted(file_exercises - json_exercises)

    # Report missing exercises
    if missing:
        print(f"Missing exercises ({len(missing)}):")
        for ex_id in missing:
            print(f"  - {ex_id}")
    else:
        print("Missing exercises (0):")
        print("  - None")
    print()

    # Report extra files
    if extra:
        print(f"Extra files on disk ({len(extra)}):")
        for ex_id in extra:
            print(f"  - {ex_id}")
    else:
        print("Extra files on disk (0):")
        print("  - None")
    print()

    # Summary
    total_in_json = len(json_exercises)
    with_files = len(json_exercises & file_exercises)
    coverage = (with_files / total_in_json * 100) if total_in_json > 0 else 0

    print(f"Summary: {with_files}/{total_in_json} exercises have files ({coverage:.1f}% coverage)")

    # Return exit code based on coverage
    if missing or extra:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(check_exercises())
