"""A yielded peer handoff does not spend B's active model time budget."""
from oscombo.collab.data_to_deck.live_pilot import _handoff_wait_budgets
from oscombo.harness.external import CodexHarness, CommandHarness


def test_yielded_wait_preserves_remaining_model_time():
    deadline, remaining = _handoff_wait_budgets(
        started=100.0, now=220.0, timeout=1200.0, pause_active_budget=True)
    assert deadline == 1420.0
    assert remaining == 1080.0


def test_legacy_wait_remains_unchanged_without_opt_in():
    deadline, remaining = _handoff_wait_budgets(
        started=100.0, now=220.0, timeout=1200.0, pause_active_budget=False)
    assert deadline == 1300.0
    assert remaining == 1080.0


def test_opt_in_tells_actor_how_to_yield_without_a_task_answer(monkeypatch):
    monkeypatch.setattr(CommandHarness, "prompt", lambda self, ctx: "Original task")
    harness = object.__new__(CodexHarness)
    harness.collaboration = {"yield_wait": True}
    prompt = harness.prompt(None)
    assert "finish your current turn" in prompt
    assert "No task answer is supplied" in prompt
