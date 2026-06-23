"""appbench task specs — long-horizon, open-ended *app builds* (not algorithm puzzles).

The agent must produce a single self-contained index.html that a human can open and
play. This is the benchmark minibench/repobench can't be: multi-step, no unit test to
hill-climb, success is "does the artifact actually work when you run it." Scored by a
Playwright functional rubric (score.py), not by us reading the code.
"""

SPACE_INVADERS = {
    "id": "space_invaders",
    "artifact": "index.html",
    "prompt": (
        "Build the classic arcade game SPACE INVADERS as a SINGLE self-contained file "
        "named `index.html` in the current directory.\n\n"
        "Hard requirements:\n"
        "1. Pure HTML + CSS + JavaScript, ALL inline in index.html. NO external libraries, "
        "NO frameworks, NO build step, NO network requests. It must run by opening the file "
        "directly in a browser (file://).\n"
        "2. An HTML5 <canvas> at least 600x600 pixels.\n"
        "3. A player ship near the bottom that moves LEFT and RIGHT with the ArrowLeft and "
        "ArrowRight keys.\n"
        "4. The player fires bullets UPWARD when the Spacebar is pressed.\n"
        "5. At least 3 rows of invaders near the top that move side-to-side and advance "
        "downward over time.\n"
        "6. Bullets destroy invaders on contact; destroyed invaders disappear.\n"
        "7. A visible SCORE that increases each time an invader is destroyed.\n"
        "8. A GAME OVER state (invaders reach the bottom) and/or a WIN state (all invaders "
        "destroyed), shown on screen as text.\n"
        "9. The game must start running immediately on load using a requestAnimationFrame "
        "loop.\n\n"
        "Write the COMPLETE, working file. A reviewer will open index.html in a real browser "
        "and play it with the arrow keys and spacebar — it must actually be playable."
    ),
}

TASKS = [SPACE_INVADERS]
