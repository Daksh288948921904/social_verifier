"""Standalone test for step 3: run the real Groq boundary-detection LLM
against a real transcript captured from a live news broadcast (via
scripts/test_transcription.py), to sanity-check the prompt contract and
JSON parsing against live output.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.segmentation.boundary_detector import check_boundary

# Real transcript captured from Sky News (scripts/test_transcription.py output),
# a single continuous story about Andy Burnham becoming Labour leader --
# no story boundary should be detected within it.
SINGLE_STORY_TRANSCRIPT = """\
[00:00:00] This is a last chance to change and we must take it together, united together.
[00:00:10] Moving into number 10 Downing Street on Monday Andy Burnham insists he will be a
[00:00:15] leader for the north the south the east and the west
[00:00:20] Hello. Welcome to our special program. We're live from Westminster on the day that Andy
[00:00:27] Burnham has now officially been made leader of the Labour Party.
[00:00:30] Next week on Monday, he's going to take the keys to number 10 from Keir Starmer,
[00:00:35] as we say farewell to yet another Prime Minister. Well, Andy Burnham, former Manchester
[00:00:40] mayor just delivered a speech, he vowed to unite the country.
"""

# A synthetic two-story transcript to check the LLM actually detects a real
# boundary when there is one (anchor transition phrase + topic switch).
TWO_STORY_TRANSCRIPT = """\
[00:00:00] Andy Burnham has now officially been made leader of the Labour Party.
[00:00:05] He's going to take the keys to number 10 from Keir Starmer next Monday,
[00:00:10] as we say farewell to yet another Prime Minister.
[00:00:15] Well, Andy Burnham, former Manchester mayor, just delivered a speech,
[00:00:20] he vowed to unite the country after months of political turmoil.
[00:00:25] Now, moving on to other news, flooding has forced hundreds of residents
[00:00:30] to evacuate their homes in Yorkshire this morning after the river Ouse
[00:00:35] burst its banks overnight following days of heavy rain.
[00:00:40] Emergency services say water levels are still rising and more
[00:00:45] evacuations may be needed later today as the region braces for further downpours.
"""


def main():
    print("--- Check 1: single continuous story (expect boundary_detected=False) ---")
    result = check_boundary(SINGLE_STORY_TRANSCRIPT, last_confirmed_boundary_ts=None)
    print(result)
    assert not result.boundary_detected, "Expected no boundary in a single continuous story"
    print("PASS\n")

    print("--- Check 2: two distinct stories (expect boundary_detected=True) ---")
    result = check_boundary(TWO_STORY_TRANSCRIPT, last_confirmed_boundary_ts=None)
    print(result)
    if result.boundary_detected:
        print(f"PASS -- detected boundary at {result.boundary_timestamp}, "
              f"closed_segment={result.closed_segment}")
    else:
        print("NOTE: no boundary detected -- inspect confidence/reasoning above, "
              "may need prompt tuning")


if __name__ == "__main__":
    main()
