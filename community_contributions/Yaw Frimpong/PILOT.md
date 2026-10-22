# Week 1 Day 3: My pilot build

I forked the repo and built the pilot by following the steps in the instructions and the video, just as you did. Everything worked, and the UnderCover Agent processed every claim in the queue except one.

## The one claim that got stuck

CLM-1016 (Robert Haines) stayed on **In progress**. I asked Claude to look into it. Twice, the agent had finished with its decision written in a message instead of recording it with the `decide_claim` tool, so the claim was never actually decided.

The fix was a small change to the agent's instructions in `backend/instructions.md`. They now say a claim is decided only when the agent calls `decide_claim`, so it must always call it before it finishes and must never end with its decision written in a message. Claude also added a test in `backend/tests/test_workflow.py` to check the instructions say this.

I re-ran the claim with:

    uv run -m agent CLM-1016

This time it was processed and **Declined**, and the whole queue was done.

## Thank you

I can't wait to go through the rest of the course. I'm super excited, and thank you for all you do. I have all your courses, and you are my go-to instructor for AI knowledge.
