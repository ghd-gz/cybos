"""
cybos.agent — 控制循环编排器

连接 LLM+SOUL 控制器与 cybos 运行时核心。
升级：控制策略依赖 epiplexity。
"""

from typing import Any, Callable, Dict, List, Optional

from .space import Space, Constraint, Observation
from .runtime import Runtime, ControlTrace
from .survey import SurveyResult, EpiplexityEstimator


# Epiplexity 策略阈值
EPI_LOW = 0.3       # 低耦合 → 并行分解
EPI_MEDIUM = 0.7    # 中耦合 → 解耦后分治
# 高耦合 (>=0.7) → 主线优先


class Skill:
    """控制策略。
    
    在特定空间状态下选择特定控制动作的模板。
    """

    def __init__(
        self,
        name: str,
        match_fn: Callable[[Space], bool],
        plan_fn: Callable[[Space], List[Constraint]],
        expected_reduction: float = 0.3,
        ashby_requirement: float = 0.8,
    ):
        self.name = name
        self.match_fn = match_fn       # 判定是否适用
        self.plan_fn = plan_fn         # 生成控制动作序列
        self.expected_reduction = expected_reduction
        self.ashby_requirement = ashby_requirement  # 需要控制器Ashby系数>=此值

    def matches(self, space: Space) -> bool:
        return self.match_fn(space)

    def plan(self, space: Space) -> List[Constraint]:
        return self.plan_fn(space)


class Agent:
    """控制器编排器。
    
    管理 Layer 2 → Layer 3 → Layer 1 的完整控制循环。
    升级：根据 Space.epiplexity 选择控制策略。
    """

    def __init__(
        self,
        runtime: Runtime,
        skills: Optional[List[Skill]] = None,
    ):
        self.runtime = runtime
        self.skills = skills or []
        self.current_trace: Optional[ControlTrace] = None

    def register_skill(self, skill: Skill):
        self.skills.append(skill)

    # ── 策略选择 ──

    def _select_strategy(self, space: Space) -> dict:
        """根据 epiplexity 选择控制策略。

        三种策略模式：
        - parallel_decompose: 低耦合 → 分解为子空间并行处理
        - decouple_then_divide: 中耦合 → 先处理耦合约束再分治
        - mainline_first: 高耦合 → 找主线先收敛，支线随主线自然降低
        """
        e = space.epiplexity

        if e < EPI_LOW:
            return {
                "name": "parallel_decompose",
                "description": "低耦合 → 分解为独立子空间，并行收敛",
                "suggested_ashby_target": space.variety,  # 每个子空间独立处理
                "allow_parallel": True,
            }
        elif e < EPI_MEDIUM:
            return {
                "name": "decouple_then_divide",
                "description": "中耦合 → 先识别耦合约束集中处理，再分解",
                "suggested_ashby_target": space.effective_variety() * 1.2,
                "allow_parallel": False,
            }
        else:
            return {
                "name": "mainline_first",
                "description": "高耦合 → 识别核心瓶颈维度，主线收敛带动支线",
                "suggested_ashby_target": space.effective_variety() * 1.5,
                "allow_parallel": False,
            }

    def _suggest_decomposition(self, space: Space) -> Dict[str, Space]:
        """为低 epiplexity 空间生成分解建议。"""
        sub_spaces = space.decompose()
        return {sub.dimensions[0]: sub for sub in sub_spaces if len(sub.dimensions) == 1}

    def _identify_mainline(self, space: Space) -> Optional[str]:
        """为高 epiplexity 空间识别主线维度。
        
        选择 per_dim_variety 最高或耦合度最强的维度作为主线。
        """
        if not space.per_dim_variety:
            return space.dimensions[0] if space.dimensions else None

        # 找 per_dim_variety 最高的维度 —— 不确定最大的就是瓶颈
        main_dim = max(space.per_dim_variety, key=space.per_dim_variety.get)
        return main_dim

    # ── 控制循环 ──

    def run(
        self,
        controller: Any,  # Layer 3: LLM + SOUL
        target_variety: float = 0.05,
        max_steps: int = 20,
        survey_result: Optional[SurveyResult] = None,
    ) -> dict:
        """运行一个完整的控制循环。

        升级：支持从 survey_result 初始化空间。
        """
        if survey_result is not None:
            # 从测绘结果初始化空间（含 epiplexity）
            initial_space = self.runtime.survey(survey_result)
            self.runtime.start_loop(target_variety=target_variety, initial_space=initial_space)
        else:
            self.runtime.start_loop(target_variety=target_variety)

        space = self.runtime.poss_space()
        
        # 测绘阶段：选择策略
        strategy = self._select_strategy(space)
        controller.on_strategy(strategy)  # 通知控制器当前策略
        
        step = 0
        while space.effective_variety() > target_variety and step < max_steps:
            step += 1

            # 1. 选择技能
            matched_skill = self._select_skill(space)

            # 2. 控制器决策（LLM+SOUL）
            decision_context = {
                "space": space,
                "strategy": strategy,
                "skills": [matched_skill] if matched_skill else [],
                "decomposition": self._suggest_decomposition(space) if strategy["allow_parallel"] else None,
                "mainline": self._identify_mainline(space) if strategy["name"] == "mainline_first" else None,
            }
            decision = controller.decide(**decision_context)

            # 3. 创建约束并执行
            constraint = self.runtime.constrain(
                name=decision.get("action", "unknown"),
                args=decision.get("args", {}),
                expected_reduction=decision.get("expected_reduction", 0.3),
            )

            # 4. 执行工具调用
            observation = self._execute_tool(constraint)

            # 5. 更新空间
            space = self.runtime.step(constraint, observation)

            # 6. 计算和注入反馈
            error = space.effective_variety()
            feedback_signal = self.runtime.feedback(error)

            # 7. 策略重估（每3步检查是否需切换）
            if step % 3 == 0:
                new_strategy = self._select_strategy(space)
                if new_strategy["name"] != strategy["name"]:
                    strategy = new_strategy
                    controller.on_strategy_change(strategy, space)

            if feedback_signal == "STRATEGY_CHANGE":
                controller.on_strategy_change(strategy, space)

        # 结束控制循环
        trace = self.runtime.end_loop()
        result = trace.summary()
        result.update({
            "strategy_used": strategy["name"],
            "epiplexity_initial": trace.initial_space.epiplexity,
            "epiplexity_final": trace.spaces[-1].epiplexity if trace.spaces else 0,
        })
        return result

    def _select_skill(self, space: Space) -> Optional[Skill]:
        """选择最匹配的控制策略。"""
        for skill in self.skills:
            if skill.matches(space):
                return skill
        return None

    def _execute_tool(self, constraint: Constraint) -> Observation:
        """执行工具调用并返回观测结果。

        实际实现中，这里对接Hermes的tool系统。
        目前是虚拟实现用于测试。
        """
        # TODO: 对接真实工具执行
        return Observation(
            constraint_id=constraint.constraint_id,
            data={"status": "ok"},
            exit_code=0,
            execution_ms=0,
        )
