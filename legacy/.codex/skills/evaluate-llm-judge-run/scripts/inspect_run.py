#!/usr/bin/env python3
"""讀取 LLM-as-a-Judge run 的結構與單題執行狀態。"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def inspect_run(run_dir: Path) -> dict:
    notebook_path = run_dir / "eval_notebook.ipynb"
    if not notebook_path.is_file():
        raise FileNotFoundError(f"找不到 notebook：{notebook_path}")

    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    questions = []
    current = None
    for index, cell in enumerate(notebook.get("cells", [])):
        source = "".join(cell.get("source", []))
        match = re.match(r"## 題號\s*(\d+)", source)
        if match:
            current = {
                "question_id": int(match.group(1)),
                "header_cell": index,
                "code_cells": [],
                "code_characters": 0,
                "execution_errors": [],
                "figure_count": 0,
            }
            questions.append(current)
            continue
        if current is None or cell.get("cell_type") != "code":
            continue
        current["code_cells"].append(index)
        current["code_characters"] += len(source)
        for output in cell.get("outputs", []):
            if output.get("output_type") == "error":
                current["execution_errors"].append(
                    f"{output.get('ename', 'Error')}: {output.get('evalue', '')}"
                )
            if "image/png" in output.get("data", {}):
                current["figure_count"] += 1

    csv_path = run_dir / "eval_results.csv"
    csv_rows = []
    if csv_path.is_file():
        with csv_path.open(encoding="utf-8-sig", newline="") as file:
            csv_rows = list(csv.DictReader(file))
    summary_path = run_dir / "summary.txt"
    return {
        "run_name": run_dir.name,
        "run_dir": str(run_dir),
        "summary": summary_path.read_text(encoding="utf-8") if summary_path.is_file() else "",
        "csv_exists": csv_path.is_file(),
        "csv_row_count": len(csv_rows),
        "questions": questions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--question", type=int)
    parser.add_argument("--show-code", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    result = inspect_run(run_dir)

    if args.question is not None and args.show_code:
        notebook = json.loads((run_dir / "eval_notebook.ipynb").read_text(encoding="utf-8"))
        selected = False
        for cell in notebook.get("cells", []):
            source = "".join(cell.get("source", []))
            match = re.match(r"## 題號\s*(\d+)", source)
            if match:
                selected = int(match.group(1)) == args.question
            elif selected and cell.get("cell_type") == "code":
                print(source)
                return
        raise ValueError(f"找不到題號 {args.question} 的程式碼")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Run: {result['run_name']}")
        print(f"題號: {[item['question_id'] for item in result['questions']]}")
        print(f"CSV: {result['csv_exists']} ({result['csv_row_count']} rows)")
        for item in result["questions"]:
            print(f"Q{item['question_id']}: code={item['code_characters']} chars, figures={item['figure_count']}, errors={len(item['execution_errors'])}")


if __name__ == "__main__":
    main()
