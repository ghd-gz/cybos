"""
cybos.agent — 控制循环编排器

连接 LLM+SOUL 控制器与 cybos 运行时核心。
"""

from typing import Any, Callable, Dict, List, Optional

from .space import Space, Constraint, Observation
from .runtime import Runtime, ControlTrace


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
    
    def run(
        self,
        controller: Any,  # Layer 3: LLM + SOUL
        target_variety: float = 0.05,
        max_steps: int = 20,
    ) -> dict:
        """运行一个完整的控制循环。"""
        self.runtime.start_loop(target_variety=target_variety)
        space = self.runtime.poss_space()
        
        step = 0
        while space.variety > target_variety and step < max_steps:
            step += 1
            
            # 1. 选择技能
            matched_skill = self._select_skill(space)
            
            # 2. 控制器决策（LLM+SOUL）
            #    在实际实现中，这里调用LLM
            decision = controller.decide(
                space=space,
                skills=[matched_skill] if matched_skill else [],
            )
            
            # 3. 创建约束并执行
            constraint = self.runtime.constrain(
                name=decision.get("action", "unknown"),
                args=decision.get("args", {}),
                expected_reduction=decision.get("expected_reduction", 0.3),
            )
            
            # 4. 执行工具调用（实际调用由上层实现）
            #    这里用虚拟执行做演示
            observation = self._execute_tool(constraint)
            
            # 5. 更新空间
            space = self.runtime.step(constraint, observation)
            
            # 6. 计算和注入反馈
            error = space.variety  # 简化的误差
            feedback_signal = self.runtime.feedback(error)
            
            # 7. 策略切换检查
            if feedback_signal == "STRATEGY_CHANGE":
                # 通知控制器策略需要切换
                controller.on_strategy_change(space)
        
        # 结束控制循环
        trace = self.runtime.end_loop()
        return trace.summary()
    
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
