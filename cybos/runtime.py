"""
cybos.runtime — CybOS 运行时核心

提供控制论原语的系统调用实现。
"""

import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from .space import Space, Constraint, Observation
from .survey import SurveyResult, EpiplexityEstimator


@dataclass
class ControlTrace:
    """控制轨迹——一次控制循环的完整记录。"""
    session_id: str
    initial_space: Space
    target_space: Space
    constraints: List[Constraint] = field(default_factory=list)
    observations: List[Observation] = field(default_factory=list)
    spaces: List[Space] = field(default_factory=list)
    errors: List[float] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    converged: bool = False
    
    def add_step(self, constraint: Constraint, observation: Observation, new_space: Space, error: float):
        self.constraints.append(constraint)
        self.observations.append(observation)
        self.spaces.append(new_space)
        self.errors.append(error)
    
    def complete(self, converged: bool):
        self.end_time = time.time()
        self.converged = converged
    
    @property
    def duration_ms(self) -> float:
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000
    
    def summary(self) -> dict:
        return {
            "session_id": self.session_id,
            "steps": len(self.constraints),
            "duration_ms": round(self.duration_ms, 1),
            "initial_variety": self.initial_space.variety,
            "initial_epiplexity": round(self.initial_space.epiplexity, 4),
            "final_variety": self.spaces[-1].variety if self.spaces else self.initial_space.variety,
            "final_epiplexity": round(self.spaces[-1].epiplexity, 4) if self.spaces else self.initial_space.epiplexity,
            "converged": self.converged,
            "avg_error": round(sum(self.errors) / len(self.errors), 4) if self.errors else 0,
            "final_error": round(self.errors[-1], 4) if self.errors else 0,
            "strategy": self._infer_strategy(),
        }
    
    def _infer_strategy(self) -> str:
        """从轨迹推断控制策略。"""
        if not self.spaces:
            return "unknown"
        initial_e = self.initial_space.epiplexity
        if initial_e < 0.3:
            return "parallel_decompose"
        elif initial_e < 0.7:
            return "decouple_then_divide"
        else:
            return "mainline_first"


class Runtime:
    """CybOS 运行时核心。
    
    管理控制循环的状态、暴露系统调用。
    """
    
    def __init__(self):
        self._current_space: Optional[Space] = None
        self._target_space: Optional[Space] = None
        self._trace: Optional[ControlTrace] = None
        self._sequence: int = 0
        self._histories: Dict[str, ControlTrace] = {}  # 跨会话存档
    
    # ── 系统调用 ──
    
    def poss_space(self) -> Space:
        """查询当前可能性空间。"""
        if self._current_space is None:
            self._current_space = Space(variety=1.0, dimensions=["unknown"])
        return self._current_space
    
    def survey(self, survey_result: SurveyResult) -> Space:
        """系统调用: 测绘。
        
        将 LLM 控制器对自然语言任务的拆解结果（SurveyResult）
        转换为正式的 Space（含 epiplexity）。
        
        Layer 3 (LLM) → SurveyResult → Layer 2 (Space)
        
        这是 LLM 作为有界观察者估算 Epiplexity 的标准接口。
        """
        space = survey_result.to_space()
        self._current_space = space
        return space
    
    def constrain(self, name: str, args: dict, expected_reduction: float = 0.3) -> Constraint:
        """创建一个控制动作（不执行，只生成协议对象）。"""
        self._sequence += 1
        space = self.poss_space()
        
        constraint = Constraint(
            name=name,
            args=args,
            from_space=space.space_id,
            expected_reduction=expected_reduction,
            sequence=self._sequence,
        )
        return constraint
    
    def observe(self, data: Any, exit_code: int = 0, execution_ms: float = 0) -> Observation:
        """创建一个观测结果。"""
        # 需要知道对应哪个constraint——由上层传入
        # 这里只创建对象
        return Observation(
            constraint_id="",  # 后续设置
            data=data,
            exit_code=exit_code,
            execution_ms=execution_ms,
        )
    
    def feedback(self, error: float) -> None:
        """注入误差信号。
        
        误差 < 0.1: 收敛良好，继续当前策略
        0.1 ≤ 误差 < 0.5: 存在偏差，调整控制参数
        误差 ≥ 0.5: 策略失效，需要切换或重新测绘
        """
        if self._trace:
            self._trace.errors[-1] = error
        
        # 触发自适应行为
        if error >= 0.5:
            return "STRATEGY_CHANGE"  # 信号量
        elif error >= 0.1:
            return "ADJUST"
        else:
            return "CONTINUE"
    
    def reachable(self, target: Space) -> Tuple[bool, float]:
        """可达性分析。
        
        判断目标空间是否在当前控制器的能力范围内。
        返回 (是否可达, 置信度)。
        """
        if self._current_space is None:
            return (False, 0.0)
        
        distance = self._current_space.distance_to(target)
        # 简化判据：距离 < 0.8 视为可达
        return (distance < 0.8, 1.0 - distance)
    
    def ashby_coeff(self, controller_variety: float, task: Optional[Space] = None,
                    task_variety: Optional[float] = None) -> float:
        """Ashby 系数 —— 必要变异度定律。
        
        控制器变异度 / 系统有效变异度。
        
        升级：考虑 epiplexity。
        system_effective = task_variety × (1 + α × task_epiplexity)
        
        >= 1.0: 控制器足够强（满足必要变异度定律）
        < 1.0: 控制器不足，需要分解或升级
        """
        if task is not None:
            effective = task.effective_variety()
        elif task_variety is not None:
            effective = task_variety
        else:
            effective = 1.0
        
        if effective <= 0:
            return float("inf")
        return controller_variety / effective
    
    def effective_ashby_coeff(self, controller: Space, task: Space) -> dict:
        """带详细分解的 Ashby 系数报告。
        
        返回各组分的贡献，帮助理解系数来源。
        """
        raw = controller.variety / max(task.variety, 0.001)
        effective = self.ashby_coeff(controller_variety=controller.variety, task=task)
        return {
            "coefficient": round(effective, 4),
            "controller_variety": controller.variety,
            "task_variety": task.variety,
            "task_epiplexity": task.epiplexity,
            "task_effective_variety": round(task.effective_variety(), 4),
            "raw_ashby": round(raw, 4),
            "epiplexity_penalty": round(effective / raw, 4) if raw > 0 else 0,
            "adequate": effective >= 1.0,
        }
    
    # ── 控制循环管理 ──
    
    def start_loop(self, target_variety: float = 0.05,
                   initial_space: Optional[Space] = None) -> None:
        """启动一个新的控制循环。
        
        升级：支持传入带 epiplexity 的初始 Space（从 survey 获得）。
        """
        self._sequence = 0
        if initial_space is not None:
            self._current_space = initial_space
        else:
            self._current_space = Space(variety=1.0, dimensions=["task"])
        
        self._target_space = Space(variety=target_variety, dimensions=["task"])
        
        session_id = uuid.uuid4().hex[:12]
        self._trace = ControlTrace(
            session_id=session_id,
            initial_space=self._current_space,
            target_space=self._target_space,
        )
    
    def step(self, constraint: Constraint, observation: Observation) -> Space:
        """执行一个控制步。
        
        1. 用观测结果更新当前空间（variety + epiplexity）
        2. 计算误差
        3. 记录轨迹
        """
        # 计算实际变异度变化
        if observation.exit_code == 0:
            new_variety = self._current_space.variety * (1.0 - constraint.expected_reduction)
            # 成功执行也降低 epiplexity（解耦合作用）
            new_epiplexity = self._current_space.epiplexity * (1.0 - 0.3 * constraint.expected_reduction)
        else:
            new_variety = min(1.0, self._current_space.variety * 1.2)  # 失败膨胀
            # 失败时 epiplexity 可能上升（控制失控增加耦合）
            new_epiplexity = min(1.0, self._current_space.epiplexity * 1.1)
        
        new_variety = max(0.01, new_variety)
        new_epiplexity = max(0.0, new_epiplexity)
        
        new_space = Space(
            variety=round(new_variety, 4),
            epiplexity=round(new_epiplexity, 4),
            dimensions=self._current_space.dimensions,
            per_dim_variety=self._current_space.per_dim_variety.copy(),
            coupling_matrix=self._current_space.coupling_matrix.copy(),
        )
        
        # 计算误差
        error = new_space.distance_to(self._target_space)
        
        # 记录
        self._trace.add_step(constraint, observation, new_space, error)
        self._current_space = new_space
        
        return new_space
    
    def end_loop(self) -> ControlTrace:
        """结束当前控制循环。"""
        if self._trace is None:
            raise RuntimeError("没有正在运行的控制循环")
        
        converged = self._current_space.variety <= self._target_space.variety if self._target_space else False
        self._trace.complete(converged)
        
        # 存档
        self._histories[self._trace.session_id] = self._trace
        
        trace = self._trace
        self._trace = None
        self._current_space = None
        self._target_space = None
        
        return trace
    
    # ── 跨会话 ──
    
    def list_histories(self) -> List[str]:
        """列出所有已存档的控制循环。"""
        return list(self._histories.keys())
    
    def get_history(self, session_id: str) -> Optional[ControlTrace]:
        """获取指定控制循环的完整记录。"""
        return self._histories.get(session_id)
    
    def analyze_pattern(self) -> dict:
        """分析历史控制模式的规律。"""
        if not self._histories:
            return {"message": "没有历史数据"}
        
        converged_count = sum(1 for t in self._histories.values() if t.converged)
        total_count = len(self._histories)
        
        return {
            "total_sessions": total_count,
            "converged": converged_count,
            "convergence_rate": round(converged_count / total_count, 2) if total_count > 0 else 0,
            "avg_steps": round(sum(t.summary()["steps"] for t in self._histories.values()) / total_count, 1) if total_count > 0 else 0,
        }
