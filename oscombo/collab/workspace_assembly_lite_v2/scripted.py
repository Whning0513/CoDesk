"""GUI actions for deterministic controls; never used by model Actors."""
from __future__ import annotations


def a_move(task_root: str) -> list[str]:
    return [
        "import pyautogui, time; pyautogui.hotkey('ctrl','x'); time.sleep(2)",
        f"import pyautogui, time; pyautogui.hotkey('ctrl','l'); pyautogui.write({(task_root + '/outputs/agent_A')!r}, 0.01); pyautogui.press('enter'); time.sleep(2)",
        "import pyautogui, time; pyautogui.hotkey('ctrl','v'); time.sleep(3)", "DONE"]


def b_prepare(audience: str) -> list[str]:
    return [
        f"import pyautogui, time; pyautogui.write({('Audience: ' + audience + '.')!r}, 0.03); time.sleep(1)",
        "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(3)", "DONE"]


def b_read(view_path: str) -> list[str]:
    return [
        "import pyautogui, time; pyautogui.hotkey('ctrl','o'); time.sleep(2)",
        f"import pyautogui, time; pyautogui.hotkey('ctrl','l'); pyautogui.write({view_path!r}, 0.01); pyautogui.press('enter'); time.sleep(6)", "DONE"]


def b_finish(tag: str) -> list[str]:
    sentence = f"Attachment: inspection_note.txt; tag {tag}."
    return [
        "import pyautogui, time; pyautogui.hotkey('ctrl','w'); time.sleep(3)",
        "import pyautogui, time; pyautogui.press('enter'); time.sleep(1)",
        f"import pyautogui, time; pyautogui.write({sentence!r}, 0.03); time.sleep(1)",
        "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(3)", "DONE"]


def a_probe_change() -> list[str]:
    """Optional saved-file revision probe; outside the task's critical path."""
    return [
        "import pyautogui, time; pyautogui.hotkey('ctrl','end'); pyautogui.press('enter'); pyautogui.write('Control revision probe', 0.02); time.sleep(1)",
        "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(3)", "DONE"]


def a_probe_restore(original: str) -> list[str]:
    pieces = original.split("\n")
    typing = []
    for index, line in enumerate(pieces):
        if line:
            typing.append(f"pyautogui.write({line!r}, 0.01)")
        if index < len(pieces) - 1:
            typing.append("pyautogui.press('enter')")
    return [
        "import pyautogui, time; pyautogui.hotkey('ctrl','a'); time.sleep(1)",
        "import pyautogui, time; " + "; ".join(typing) + "; time.sleep(1)",
        "import pyautogui, time; pyautogui.hotkey('ctrl','s'); time.sleep(3)", "DONE"]
