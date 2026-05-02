"""CybOS — Cybernetic Operating System Core Library"""

from .space import Space, Constraint, Observation
from .runtime import Runtime, ControlTrace
from .agent import Agent, Skill

__all__ = [
    "Space", "Constraint", "Observation",
    "Runtime", "ControlTrace",
    "Agent", "Skill",
    "create_session",
]


def create_session():
    """快速启动一个CybOS会话。"""
    rt = Runtime()
    agent = Agent(runtime=rt)
    return agent
