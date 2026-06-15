"""Experiment 3 — factual accuracy of the AI assistant (Vyz) by grounding rate.

For each of the 100 control questions in tests/fixtures/qa_pairs.json we:
  1. build the context block the assistant grounds the LLM on (deterministic facts +
     data snapshot);
  2. get the assistant's answer (LLM via Ollama, deterministic fallback otherwise);
  3. extract every number from the answer with a regex and check it against the
     numbers in the context block.

Grounding rate = grounded numeric statements / all numeric statements. It measures
whether the assistant only states figures that exist in the data (no hallucination).

Run for the report (full 100 + figure):
    python tests/test_assistant_grounding.py
Run as a quick check:
    pytest tests/test_assistant_grounding.py
"""
import json
import os
import re
import sys

import pandas as pd

# Make the app package importable regardless of the working directory.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Use the local Ollama LLM so the experiment measures the real assistant output.
os.environ.setdefault("ASSISTANT_LLM_ENABLED", "true")
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_MODEL", "qwen2.5:7b-instruct")

from app.core.settings import get_settings  # noqa: E402
from app.services.assistant import AssistantService  # noqa: E402
from app.services.data_loader import prepare_dataframe  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "qa_pairs.json")
DATA_CSV = os.path.join(ROOT, "data", "market_data.csv")
RESULTS_DIR = os.path.join(ROOT, "tests", "results")

_NUMBER_RE = re.compile(r"\d[\d\s .,]*\d|\d")


def _extract_numbers(text: str) -> list[float]:
    # Drop markdown list ordinals ("1. ", "2) ") — they are formatting, not claims.
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", " ", text or "")
    numbers = []
    for match in _NUMBER_RE.findall(text):
        cleaned = match.replace(" ", "").replace(" ", "").replace(",", "").rstrip(".")
        try:
            numbers.append(float(cleaned))
        except ValueError:
            continue
    return numbers


def _is_year(value: float) -> bool:
    return float(value).is_integer() and 1990 <= value <= 2035


def _is_grounded(value: float, context: list[float]) -> bool:
    tolerance = max(abs(value) * 0.05, 0.5)  # tolerate rounding/formatting
    return any(abs(value - c) <= tolerance for c in context)


def _load_dataframe() -> pd.DataFrame:
    return prepare_dataframe(pd.read_csv(DATA_CSV))


def evaluate_grounding(limit: int | None = None) -> dict:
    get_settings.cache_clear()
    df = _load_dataframe()
    svc = AssistantService()
    pairs = json.load(open(FIXTURE, encoding="utf-8"))
    if limit:
        pairs = pairs[:limit]

    rows = []
    for pair in pairs:
        question = pair["question"]
        category = pair.get("category")
        snapshot = svc._build_snapshot(df, category=category)
        deterministic = svc._build_data_answer(df=df, user_message=question, category=category)
        context_block = deterministic + " " + json.dumps(snapshot, ensure_ascii=False)
        context_numbers = _extract_numbers(context_block)

        market_related = svc._is_market_related(question)
        prompt = svc._build_chat_prompt(
            user_message=question,
            history_text="Немає попередніх повідомлень.",
            snapshot=snapshot,
            deterministic_answer=deterministic,
            market_related=market_related,
        )
        llm_answer = svc._call_ollama(prompt)
        answer = llm_answer or deterministic

        # Score substantive figures only (salaries, counts, percentages >= 10);
        # years and single digits (list bullets, trivial) are not factual claims.
        answer_numbers = [n for n in _extract_numbers(answer) if not _is_year(n) and abs(n) >= 10]
        grounded = [n for n in answer_numbers if _is_grounded(n, context_numbers)]
        rows.append(
            {
                "id": pair["id"],
                "type": pair["type"],
                "question": question,
                "answer": answer,
                "llm_used": bool(llm_answer),
                "total_numbers": len(answer_numbers),
                "grounded_numbers": len(grounded),
                "fully_grounded": len(answer_numbers) > 0 and len(grounded) == len(answer_numbers),
                "has_numbers": len(answer_numbers) > 0,
            }
        )

    total_numbers = sum(r["total_numbers"] for r in rows)
    grounded_numbers = sum(r["grounded_numbers"] for r in rows)
    with_numbers = [r for r in rows if r["has_numbers"]]
    grounding_rate = (grounded_numbers / total_numbers) if total_numbers else 1.0
    fully = sum(1 for r in with_numbers if r["fully_grounded"])

    by_type = {}
    for r in rows:
        t = r["type"]
        agg = by_type.setdefault(t, {"total": 0, "grounded": 0})
        agg["total"] += r["total_numbers"]
        agg["grounded"] += r["grounded_numbers"]
    by_type_rate = {
        t: (v["grounded"] / v["total"] if v["total"] else 1.0, v["total"]) for t, v in by_type.items()
    }

    return {
        "questions": len(rows),
        "answers_with_numbers": len(with_numbers),
        "total_numbers": total_numbers,
        "grounded_numbers": grounded_numbers,
        "grounding_rate": grounding_rate,
        "fully_grounded_answers": fully,
        "llm_used_count": sum(1 for r in rows if r["llm_used"]),
        "model": get_settings().ollama_model,
        "by_type": by_type_rate,
        "rows": rows,
    }


def _print_report(res: dict) -> None:
    line = "=" * 64
    print(line)
    print(" Експеримент 3: фактологічна точність AI-асистента Vyz")
    print(" Метрика: grounding rate (числа у відповіді vs блок контексту)")
    print(line)
    print(f" Контрольних запитань:            {res['questions']}")
    print(f" LLM:                             {res['model']} ({res['llm_used_count']}/{res['questions']} через Ollama)")
    print(f" Відповідей із числами:           {res['answers_with_numbers']}")
    print(f" Усього числових тверджень:       {res['total_numbers']}")
    print(f" Заземлених тверджень:            {res['grounded_numbers']}")
    print(" " + "-" * 62)
    print(f" GROUNDING RATE:                  {res['grounding_rate'] * 100:.1f}%")
    pct = res["fully_grounded_answers"] / max(res["answers_with_numbers"], 1) * 100
    print(f" Повністю заземлених відповідей:  {res['fully_grounded_answers']}/{res['answers_with_numbers']}  ({pct:.0f}%)")
    print(line)
    print(" За типом запиту:")
    for t, (rate, total) in sorted(res["by_type"].items(), key=lambda kv: -kv[1][0]):
        print(f"   {t:<12} {rate * 100:5.1f}%   (тверджень: {total})")
    print(line)


def _save_figure(res: dict) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(RESULTS_DIR, exist_ok=True)
    types = sorted(res["by_type"], key=lambda t: -res["by_type"][t][0])
    rates = [res["by_type"][t][0] * 100 for t in types]
    overall = res["grounding_rate"] * 100

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(types, rates, color="#4f8ef7")
    ax.axhline(overall, color="#e0566b", linestyle="--", linewidth=1.5, label=f"Загальний: {overall:.1f}%")
    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, rate + 0.6, f"{rate:.1f}%", ha="center", fontsize=9)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Grounding rate, %")
    ax.set_title(f"Фактологічна точність AI-асистента Vyz (grounding rate = {overall:.1f}%)\n"
                 f"{res['questions']} контрольних запитань, модель {res['model']}")
    ax.legend(loc="lower right")
    plt.tight_layout()
    path = os.path.join(RESULTS_DIR, "grounding_rate.png")
    fig.savefig(path, dpi=130)
    plt.close(fig)

    json.dump(
        {k: v for k, v in res.items() if k != "rows"},
        open(os.path.join(RESULTS_DIR, "grounding_results.json"), "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=2,
    )
    return path


def test_grounding_rate():
    """Quick CI check on a subset — the assistant must stay well-grounded."""
    res = evaluate_grounding(limit=20)
    assert res["total_numbers"] > 0
    assert res["grounding_rate"] >= 0.8, f"grounding rate too low: {res['grounding_rate']:.2%}"


if __name__ == "__main__":
    result = evaluate_grounding()
    _print_report(result)
    figure = _save_figure(result)
    print(f" Збережено: {figure}")
    print(f"            {os.path.join(RESULTS_DIR, 'grounding_results.json')}")
