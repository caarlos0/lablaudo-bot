#!/usr/bin/env python3
"""Tests for overdue handling: clearing the status once fixed and giving up."""

from datetime import datetime, timedelta

from lablaudo.bot import _abandoned_exams, _format_exams_md, _GIVE_UP_AFTER
from lablaudo.crawler import ExamDetail


NOW = datetime(2026, 6, 22, 12, 0)


def _rows(exams: list[ExamDetail]) -> list[tuple]:
    """Convert ExamDetail list to the (name, status, expected_date) rows the DB stores."""
    return [
        (
            e.name,
            e.status,
            e.expected_date.strftime("%d/%m/%Y %H:%M") if e.expected_date else None,
        )
        for e in exams
    ]


def test_give_up_threshold_is_one_week():
    assert _GIVE_UP_AFTER == timedelta(days=7)


def test_abandoned_after_one_week():
    """An exam more than a week past its estimate is abandoned."""
    exams = [
        ExamDetail("Teste do Pezinho", "Em Análise", NOW - timedelta(days=8)),
    ]
    assert [e.name for e in _abandoned_exams(exams, NOW)] == ["Teste do Pezinho"]


def test_not_abandoned_within_one_week():
    """An exam overdue by less than a week is not abandoned yet."""
    exams = [
        ExamDetail("Hemograma", "Em Análise", NOW - timedelta(days=3)),
    ]
    assert _abandoned_exams(exams, NOW) == []


def test_ready_exam_never_abandoned():
    """A ready exam is never abandoned, even with an old estimate."""
    exams = [
        ExamDetail("Glicose", "Liberado", NOW - timedelta(days=30)),
    ]
    assert _abandoned_exams(exams, NOW) == []


def test_overdue_shows_warning():
    exams = [ExamDetail("Pezinho", "Em Análise", NOW - timedelta(days=2))]
    assert "atrasado" in _format_exams_md(_rows(exams), NOW)


def test_overdue_clears_when_rescheduled():
    """Once the estimate moves to the future, the overdue warning clears."""
    exams = [ExamDetail("Pezinho", "Em Análise", NOW + timedelta(days=5))]
    summary = _format_exams_md(_rows(exams), NOW)
    assert "atrasado" not in summary
    assert "pendente" in summary


def test_overdue_clears_when_delivered():
    """Once the exam is ready, the overdue warning clears."""
    exams = [ExamDetail("Pezinho", "Liberado", NOW - timedelta(days=2))]
    summary = _format_exams_md(_rows(exams), NOW)
    assert "atrasado" not in summary
    assert "pronto" in summary


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("All overdue tests passed!")
