#!/usr/bin/env python3
"""將人工複核結果寫入 summary.txt 與 run 同名 Markdown 報告。"""
from __future__ import annotations

import argparse
from pathlib import Path

from inspect_run import inspect_run

REVIEW_MARKER = "\n\n人工複核結果："


def parse_ids(value: str) -> list[int]:
    return sorted({int(item.strip()) for item in value.split(",") if item.strip()})


def parse_findings(values: list[str]) -> dict[int, str]:
    findings = {}
    for value in values:
        question, separator, reason = value.partition("=")
        if not separator or not question.strip() or not reason.strip():
            raise ValueError("--finding 格式必須為 題號=原因")
        findings[int(question.strip())] = reason.strip()
    return findings


def strip_review(summary: str) -> str:
    return summary.split(REVIEW_MARKER, 1)[0].rstrip()


def render_report(run: dict, correct: list[int], incorrect: list[int], findings: dict[int, str]) -> str:
    questions = run["questions"]
    details = {item["question_id"]: item for item in questions}
    rows = []
    for question_id in sorted(details):
        item = details[question_id]
        status = "正確" if question_id in correct else "錯誤"
        execution = "正常" if not item["execution_errors"] else "失敗"
        note = "符合題意與可接受範例邏輯" if status == "正確" else findings[question_id]
        rows.append(f"| {question_id} | {status} | {execution} | {note} |")
    total = len(questions)
    accuracy = len(correct) / total if total else 0
    return "\n".join([
        f"# {run['run_name']}", "", "## Run 資訊", "", "```text", strip_review(run["summary"]), "```", "",
        "## 人工複核統計", "",
        f"- 正確題目數：{len(correct)}/{total} ({accuracy:.2%})",
        f"- 錯誤題目數：{len(incorrect)}/{total}",
        f"- 正確題目：{correct}",
        f"- 錯誤題目：{incorrect}", "",
        "## 逐題統整", "",
        "| 題號 | 判定 | 程式執行 | 審核摘要 |",
        "| ---: | --- | --- | --- |", *rows, "",
        "## 判定說明", "",
        "依 `example_new.ipynb` 的所有可接受範例與題意判定。題意未明確時，允許合理的分析條件與代理定義；不因圖表形式或實作細節不同判錯。", "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--correct", required=True)
    parser.add_argument("--incorrect", required=True)
    parser.add_argument("--finding", action="append", default=[])
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    run = inspect_run(run_dir)
    question_ids = sorted(item["question_id"] for item in run["questions"])
    correct = parse_ids(args.correct)
    incorrect = parse_ids(args.incorrect)
    findings = parse_findings(args.finding)
    if set(correct) & set(incorrect):
        raise ValueError("正確與錯誤題號不可重複")
    if sorted(correct + incorrect) != question_ids:
        raise ValueError("正確與錯誤題號的聯集必須與 notebook 題號完全一致")
    if set(findings) != set(incorrect):
        raise ValueError("每一題錯誤題目都必須有且只能有一個 --finding")

    review = "\n".join([
        "人工複核結果：",
        f"- 正確題目數：{len(correct)}/{len(question_ids)}",
        f"- 錯誤題目數：{len(incorrect)}/{len(question_ids)}",
        f"- 正確題目：{correct}",
        f"- 錯誤題目：{incorrect}",
    ])
    (run_dir / "summary.txt").write_text(strip_review(run["summary"]) + "\n\n" + review + "\n", encoding="utf-8", newline="\n")
    report_path = run_dir.parent / f"{run_dir.name}.md"
    report_path.write_text(render_report(run, correct, incorrect, findings), encoding="utf-8", newline="\n")
    print(f"已更新：{run_dir / 'summary.txt'}")
    print(f"已建立：{report_path}")


if __name__ == "__main__":
    main()
