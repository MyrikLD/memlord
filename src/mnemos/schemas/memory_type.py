from enum import StrEnum


class MemoryType(StrEnum):
    observation = "observation"
    feedback = "feedback"
    fact = "fact"
    preference = "preference"
    instruction = "instruction"
    task = "task"
    plan = "plan"
