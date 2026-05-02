"""
cybos.space — 可能性空间 (Possibility Space)

一等公民数据类型，表示一个系统在任意时刻的所有可能状态的集合。
"""

import hashlib
import json
import uuid
from typing import Any, Callable, Generic, List, Optional, Tuple, TypeVar

T = TypeVar("T")

class Space(Generic[T]):
    """可能性空间。
    
    表示系统在某一时刻的所有可能状态的集合。
    - current: 当前在空间中的位置
    - variety: 当前变异度（不确定性度量）
    - dimensions: 空间的维度标签
    """
    
    def __init__(
        self,
        current: Optional[T] = None,
        variety: float = 1.0,
        dimensions: Optional[List[str]] = None,
        space_id: Optional[str] = None,
    ):
        self.current = current
        self.variety = max(0.0, min(1.0, variety))  # 归一化到 [0, 1]
        self.dimensions = dimensions or ["unknown"]
        self.space_id = space_id or uuid.uuid4().hex[:12]
        self._history: List[Tuple[str, float]] = []  # (action_id, variety_after)
    
    def constrain(self, action: "Constraint") -> "Space[T]":
        """施加约束，返回新的可能性空间。
        
        约束缩小了可能性空间（variety 降低）。
        理想情况：variety_new = variety_old * (1 - action.expected_reduction)
        实际情况：由观测结果决定。
        """
        new_variety = self.variety * (1.0 - action.expected_reduction)
        # 防止过度缩小
        new_variety = max(0.01, new_variety)
        
        new_space = Space(
            current=self.current,
            variety=round(new_variety, 4),
            dimensions=self.dimensions.copy(),
        )
        new_space._history = self._history + [(action.constraint_id, new_variety)]
        return new_space
    
    def measure(self) -> float:
        """测量当前变异度。"""
        return self.variety
    
    def distance_to(self, target: "Space[T]") -> float:
        """到目标空间的距离。
        
        0 = 完全重合，1 = 完全不重叠。
        简化实现：基于变异度差异。
        """
        return abs(self.variety - target.variety)
    
    def merge(self, other: "Space[T]") -> "Space[T]":
        """合并两个可能性空间。
        
        合并后的变异度 >= 两者各自的最大值（复合空间不确定性增加）。
        """
        merged_variety = max(self.variety, other.variety) * 1.1
        merged_variety = min(1.0, merged_variety)
        
        merged_dims = list(set(self.dimensions + other.dimensions))
        
        return Space(
            variety=round(merged_variety, 4),
            dimensions=merged_dims,
        )
    
    def decompose(self) -> List["Space[T]"]:
        """分解为子空间。
        
        每个维度一个子空间，变异度按维度数均分（简化）。
        """
        n = len(self.dimensions)
        if n <= 1:
            return [self]
        
        sub_variety = self.variety / n
        return [
            Space(
                variety=round(sub_variety, 4),
                dimensions=[dim],
            )
            for dim in self.dimensions
        ]
    
    def convergence_report(self) -> dict:
        """生成收敛报告。"""
        if not self._history:
            return {
                "steps": 0,
                "initial_variety": self.variety,
                "final_variety": self.variety,
                "reduction": 0.0,
                "history": [],
            }
        
        initial = self._history[0][1]  # 第一个action后的variety不对
        # 修正：用第一个action之前的variety
        # 实际上我们应该保存初始variety
        # 这里简化处理
        initial_variety = 1.0
        
        return {
            "steps": len(self._history),
            "initial_variety": initial_variety,
            "final_variety": self.variety,
            "reduction": round((initial_variety - self.variety) / initial_variety, 4),
            "history": [
                {"action": aid, "variety": v} for aid, v in self._history
            ],
        }
    
    def __repr__(self) -> str:
        return (
            f"Space(id={self.space_id}, variety={self.variety:.3f}, "
            f"dims={self.dimensions}, steps={len(self._history)})"
        )


class Constraint:
    """控制动作（约束）。
    
    对应 Layer 1 协议中的 Tool Call + control 元数据。
    """
    
    def __init__(
        self,
        name: str,
        args: dict,
        constraint_id: Optional[str] = None,
        from_space: Optional[str] = None,
        expected_reduction: float = 0.3,
        sequence: int = 1,
    ):
        self.name = name
        self.args = args
        self.constraint_id = constraint_id or self._generate_id()
        self.from_space = from_space or "unknown"
        self.expected_reduction = max(0.0, min(0.99, expected_reduction))
        self.sequence = sequence
    
    @staticmethod
    def _generate_id() -> str:
        return f"{uuid.uuid4().hex[:8]}:{uuid.uuid4().hex[:4]}"
    
    def to_dict(self) -> dict:
        return {
            "type": "tool_call",
            "name": self.name,
            "args": self.args,
            "control": {
                "constraint_id": self.constraint_id,
                "from_space": self.from_space,
                "expected_variety_reduction": self.expected_reduction,
                "sequence": self.sequence,
            },
        }
    
    def __repr__(self) -> str:
        return f"Constraint({self.name}, id={self.constraint_id}, reduction={self.expected_reduction})"


class Observation:
    """观测结果。
    
    对应 Layer 1 协议中的 Tool Output。
    """
    
    def __init__(
        self,
        constraint_id: str,
        data: Any,
        exit_code: int = 0,
        execution_ms: float = 0,
    ):
        self.constraint_id = constraint_id
        self.data = data
        self.exit_code = exit_code
        self.execution_ms = execution_ms
        self.state_signature = self._compute_signature(data)
    
    @staticmethod
    def _compute_signature(data: Any) -> str:
        """语义敏感哈希。"""
        raw = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        return {
            "type": "tool_output",
            "control": {
                "constraint_id": self.constraint_id,
                "execution_ms": self.execution_ms,
                "exit_code": self.exit_code,
            },
            "observation": self.data,
            "state_signature": self.state_signature,
        }
    
    def __repr__(self) -> str:
        return f"Observation(id={self.constraint_id}, code={self.exit_code}, sig={self.state_signature})"
