"""CybOS — Cybernetic Operating System Core Library"""

from .space import Space, Constraint, Observation, EPIPLEXITY_ALPHA
from .runtime import Runtime, ControlTrace
from .agent import Agent, Skill
from .survey import SurveyResult, EpiplexityEstimator, Coupling, QualitativeMapper, survey_from_text, compute_epiplexity

__all__ = [
    "Space", "Constraint", "Observation",
    "Runtime", "ControlTrace",
    "Agent", "Skill",
    "SurveyResult", "EpiplexityEstimator", "Coupling", "QualitativeMapper",
    "survey_from_text", "compute_epiplexity",
    "EPIPLEXITY_ALPHA",
    "create_session",
]


def create_session():
    """快速启动一个CybOS会话。"""
    rt = Runtime()
    agent = Agent(runtime=rt)
    return agent
