from enum import StrEnum


class MemoryType(StrEnum):
    """
    fact: established fact about user, project, or system.
    preference: user's likes, dislikes, habits.
    instruction: persistent rule Claude must follow.
    feedback: evaluation of Claude's output.
    decision: a choice made with reasoning ('chose X over Y because Z').
    """

    fact = "fact"
    preference = "preference"
    instruction = "instruction"
    feedback = "feedback"
    decision = "decision"
