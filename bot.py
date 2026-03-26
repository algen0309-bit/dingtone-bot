"""
bot.py - Dingtone math-solver bot.

Automates the "Games for 100 Credits" mini-game in the Dingtone app via ADB
using uiautomator2. No mouse/keyboard focus is required; all interaction is
sent directly to the Android device over ADB.

Usage (LDPlayer on PC):
    python bot.py                  # LDPlayer instance 0  (127.0.0.1:5555)
    python bot.py --instance 1     # LDPlayer instance 1  (127.0.0.1:5557)
    python bot.py -s 127.0.0.1:5555  # explicit serial

Prerequisites:
    pip install -r requirements.txt
    # In LDPlayer: Settings → Others → enable ADB debugging
    adb connect 127.0.0.1:5555    # connect once; verify with: adb devices

Game flow automated:
    1. LOBBY     → click "Start Game", wait 3 s for game to load
    2. PLAYING   → read equation, evaluate, click ✔ or ✗
    3. GAME_OVER → click "Play again from the start"
    4. WIN       → click "Play again"
    Loop forever.
"""

import argparse
import logging
import re
import time
from enum import Enum

import uiautomator2 as u2

from math_solver import solve

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State detection
# ---------------------------------------------------------------------------
# Regex that matches a math equation like "1+8=11", "15÷3=5", "7×8=56"
_EQ_RE = re.compile(r'[\d].*=[\d]')


class State(str, Enum):
    LOBBY     = 'LOBBY'
    PLAYING   = 'PLAYING'
    GAME_OVER = 'GAME_OVER'
    WIN       = 'WIN'
    UNKNOWN   = 'UNKNOWN'


def _texts(d: u2.Device) -> set[str]:
    """Return all non-empty text strings visible on screen right now."""
    try:
        xml = d.dump_hierarchy(compressed=True)
    except Exception as exc:
        log.debug("dump_hierarchy failed: %s", exc)
        return set()
    # Quick regex scan — much faster than parsing the full XML tree
    return set(re.findall(r'text="([^"]+)"', xml))


def get_state(d: u2.Device) -> State:
    texts = _texts(d)
    if "Play again from the start" in texts:
        return State.GAME_OVER
    if "Play again" in texts:
        return State.WIN
    if "Start Game" in texts:
        return State.LOBBY
    if any("Correctly Answered" in t for t in texts):
        return State.PLAYING
    return State.UNKNOWN


# ---------------------------------------------------------------------------
# Equation extraction
# ---------------------------------------------------------------------------

def get_equation(d: u2.Device) -> str:
    """
    Find and return the math equation text currently shown on screen.
    Raises RuntimeError if no equation is found.
    """
    for text in _texts(d):
        if _EQ_RE.search(text):
            return text.strip()
    raise RuntimeError("No equation found on screen")


# ---------------------------------------------------------------------------
# Button clicks
# ---------------------------------------------------------------------------

def _click_answer_button(d: u2.Device, is_true: bool) -> None:
    """
    Click the True (✔, left) or False (✗, right) answer button.

    Detection strategy (in order of preference):
    1. content-desc attribute ("True"/"False", "Correct"/"Wrong", "Yes"/"No")
    2. Fallback: tap left or right half of the lower portion of the screen
       (the two large square buttons are always in the bottom ~40% of the game area)
    """
    # Strategy 1: content-desc
    candidates_true  = ("True",  "Correct", "Yes", "Right", "✓")
    candidates_false = ("False", "Wrong",   "No",  "X",     "✗")
    candidates = candidates_true if is_true else candidates_false
    for label in candidates:
        el = d(descriptionContains=label)
        if el.exists(timeout=0.5):
            log.debug("Clicking button via content-desc=%r", label)
            el.click()
            return

    # Strategy 2: positional tap
    # Equation buttons are large squares side-by-side in the lower portion.
    # Left = True (✔), Right = False (✗).
    info = d.info
    w = info['displayWidth']
    h = info['displayHeight']
    # The button row sits roughly between 65 % and 90 % of screen height
    y = int(h * 0.77)
    if is_true:
        x = int(w * 0.28)   # left button centre
        log.debug("Clicking TRUE via tap (%d, %d)", x, y)
    else:
        x = int(w * 0.72)   # right button centre
        log.debug("Clicking FALSE via tap (%d, %d)", x, y)
    d.click(x, y)


def click_true(d: u2.Device) -> None:
    _click_answer_button(d, is_true=True)


def click_false(d: u2.Device) -> None:
    _click_answer_button(d, is_true=False)


# ---------------------------------------------------------------------------
# Main automation loop
# ---------------------------------------------------------------------------

def run_loop(d: u2.Device) -> None:
    """Run the game automation loop forever."""
    session_count = 0
    question_count = 0

    while True:
        state = get_state(d)

        # ── LOBBY ──────────────────────────────────────────────────────────
        if state == State.LOBBY:
            log.info("LOBBY — clicking 'Start Game'")
            d(text="Start Game").click()
            time.sleep(3.0)   # wait for the game to load

        # ── PLAYING ────────────────────────────────────────────────────────
        elif state == State.PLAYING:
            try:
                eq = get_equation(d)
            except RuntimeError:
                log.warning("PLAYING — no equation found yet, waiting…")
                time.sleep(0.5)
                continue

            try:
                answer = solve(eq)
            except ValueError as exc:
                log.error("Could not evaluate %r: %s — defaulting to False", eq, exc)
                answer = False

            question_count += 1
            verdict = "TRUE  ✔" if answer else "FALSE ✗"
            log.info("Q%-2d  %s  →  %s", question_count, eq, verdict)

            if answer:
                click_true(d)
            else:
                click_false(d)
            time.sleep(0.9)   # brief pause; game animates between questions

        # ── GAME OVER (wrong answer) ───────────────────────────────────────
        elif state == State.GAME_OVER:
            log.info("GAME OVER — clicking 'Play again from the start'")
            question_count = 0
            d(text="Play again from the start").click()
            time.sleep(1.5)

        # ── WIN (all 10 correct) ───────────────────────────────────────────
        elif state == State.WIN:
            session_count += 1
            log.info("WIN! Session #%d complete — clicking 'Play again'", session_count)
            question_count = 0
            # "Play again" text might match "Play again from the start" too,
            # so prefer the shorter exact match first.
            btn = d(text="Play again")
            if not btn.exists(timeout=1.0):
                btn = d(textContains="Play again")
            btn.click()
            time.sleep(1.5)

        # ── UNKNOWN ────────────────────────────────────────────────────────
        else:
            log.debug("UNKNOWN state — waiting 1 s")
            time.sleep(1.0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# LDPlayer ADB ports: instance 0→5555, instance 1→5557, instance 2→5559, …
_LDPLAYER_BASE_PORT = 5555


def ldplayer_serial(instance: int = 0) -> str:
    """Return the ADB serial for a given LDPlayer instance index (0-based)."""
    port = _LDPLAYER_BASE_PORT + instance * 2
    return f"127.0.0.1:{port}"


def connect(serial: str | None = None) -> u2.Device:
    log.info("Connecting to device%s…", f" ({serial})" if serial else "")
    d = u2.connect(serial)
    d.implicitly_wait(5.0)
    info = d.info
    log.info(
        "Connected: %s  %dx%d",
        info.get('productName', 'unknown'),
        info['displayWidth'],
        info['displayHeight'],
    )
    return d


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dingtone math-solver bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "LDPlayer examples:\n"
            "  python bot.py                  # LDPlayer instance 0 (port 5555)\n"
            "  python bot.py --instance 1     # LDPlayer instance 1 (port 5557)\n"
            "  python bot.py -s 127.0.0.1:5555\n"
        ),
    )
    parser.add_argument(
        "--serial", "-s",
        default=None,
        help="ADB serial override (e.g. 127.0.0.1:5555). "
             "If omitted, uses LDPlayer instance selected by --instance.",
    )
    parser.add_argument(
        "--instance", "-i",
        type=int,
        default=0,
        help="LDPlayer instance index (0-based). Instance 0 → port 5555, "
             "instance 1 → port 5557, etc. Ignored if --serial is given.",
    )
    args = parser.parse_args()

    serial = args.serial or ldplayer_serial(args.instance)
    log.info(
        "Target: LDPlayer instance %d  (%s)",
        args.instance if not args.serial else -1,
        serial,
    )

    d = connect(serial)
    log.info("Starting automation loop. Press Ctrl+C to stop.")
    try:
        run_loop(d)
    except KeyboardInterrupt:
        log.info("Stopped by user.")


if __name__ == '__main__':
    main()
