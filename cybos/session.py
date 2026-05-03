"""
cybos.session — Hermes 环境适配器

由来福在对话中手动管理 CybOS 控制会话。
每步控制在上下文中自然延续，不依赖自动化的循环机制。

用法：
    # 测绘阶段
    survey = survey_from_text(task, dims, couplings)
    session = CybosSession.begin(survey)
    
    # 执行阶段（每步工具调用）
    con = session.constrain("patch", {"file": "x.py"}, expected_reduction=0.5)
    # ... 执行工具 ...
    space = session.observe(con, data={"status": "ok"}, exit_code=0)
    
    # 复盘阶段
    report = session.end()
    print(report)  # 含 epiplexity 变化 + 策略 + 收敛判断
"""

from typing import Any, Dict, List, Optional

from .runtime import Runtime
from .space import Space, Constraint, Observation
from .survey import SurveyResult, survey_from_text, EpiplexityEstimator


class CybosSession:
    """Hermes 环境下的 CybOS 控制会话。
    
    由来福在每次任务中手动调用，管理控制循环的
    开始（测绘）、执行（工具记录）和结束（复盘）。
    不改造 Hermes 工具机制，只增加元数据记录。
    """

    def __init__(self, runtime: Runtime, survey: SurveyResult):
        self.runtime = runtime
        self.survey = survey
        self.initial_epiplexity = survey.epiplexity
        self.initial_variety = survey.variety
        self.step_count = 0
        self._constraints: List[Constraint] = []

    @classmethod
    def begin(cls, survey: SurveyResult, target_variety: float = 0.05) -> "CybosSession":
        """创建并启动一个控制会话。
        
        1. SurveyResult → Space（含 epiplexity）
        2. 启动 Runtime 控制循环
        3. 返回 CybosSession 供后续操作
        """
        rt = Runtime()
        initial_space = survey.to_space()
        rt.start_loop(target_variety=target_variety, initial_space=initial_space)
        return cls(runtime=rt, survey=survey)

    # ── 执行 ──

    def constrain(self, name: str, args: dict,
                  expected_reduction: float = 0.3) -> Constraint:
        """创建一个约束（工具调用前调用）。
        
        返回含 constraint_id 的 Constraint 对象，
        后续可关联观测结果。
        """
        return self.runtime.constrain(name, args, expected_reduction)

    def observe(self, constraint: Constraint, data: Any,
                exit_code: int = 0) -> Space:
        """记录观测结果（工具调用后调用）。
        
        返回更新后的 Space（含新的 variety 和 epiplexity）。
        """
        self.step_count += 1
        obs = Observation(
            constraint_id=constraint.constraint_id,
            data=data,
            exit_code=exit_code,
        )
        new_space = self.runtime.step(constraint, obs)
        self._constraints.append(constraint)
        return new_space

    # ── 查询 ──

    def current_space(self) -> Space:
        """当前可能性空间。"""
        return self.runtime.poss_space()

    def current_strategy(self) -> str:
        """根据当前 epiplexity 推荐策略。"""
        e = self.current_space().epiplexity
        if e < 0.3:
            return "parallel_decompose"
        elif e < 0.7:
            return "decouple_then_divide"
        return "mainline_first"

    # ── 复盘 ──

    def end(self) -> dict:
        """结束控制会话，返回收敛报告。"""
        trace = self.runtime.end_loop()
        report = trace.summary()

        # 补充测绘信息
        report.update({
            "step_count": self.step_count,
            "survey_variety": self.initial_variety,
            "survey_epiplexity": self.initial_epiplexity,
            "strat_initial": self._epi_to_strat(self.initial_epiplexity),
            "prediction_error": round(
                abs(self.initial_epiplexity - report.get("final_epiplexity", 0)),
                4,
            ),
        })

        return report

    @staticmethod
    def _epi_to_strat(epi: float) -> str:
        if epi < 0.3:
            return "parallel_decompose"
        elif epi < 0.7:
            return "decouple_then_divide"
        return "mainline_first"

    def __repr__(self) -> str:
        s = self.current_space()
        return (
            f"CybosSession(steps={self.step_count}, "
            f"variety={s.variety:.3f}, epi={s.epiplexity:.3f}, "
            f"strat={self.current_strategy()})"
        )
