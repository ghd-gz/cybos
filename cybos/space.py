"""
cybos.space — 可能性空间 (Possibility Space)

一等公民数据类型，表示一个系统在任意时刻的所有可能状态的集合。
"""

import hashlib
import json
import math
import uuid
from typing import Any, Callable, Dict, Generic, List, Optional, Tuple, TypeVar

T = TypeVar("T")


# ─── Epiplexity 计算常量 ───
EPIPLEXITY_ALPHA = 1.0  # 耦合惩罚系数：effective_variety = variety × (1 + α × epiplexity)


class Space(Generic[T]):
    """可能性空间。
    
    表示系统在某一时刻的所有可能状态的集合。
    - current: 当前在空间中的位置
    - variety: 当前变异度（不确定性度量）[0, 1]
    - epiplexity: 维度间交叉耦合度 [0, 1] — 新增
    - dimensions: 空间的维度标签
    - per_dim_variety: 每个维度的独立变异度 — 新增
    - coupling_matrix: 维度间的耦合关系 — 新增
    """
    
    def __init__(
        self,
        current: Optional[T] = None,
        variety: float = 1.0,
        epiplexity: float = 0.0,
        dimensions: Optional[List[str]] = None,
        per_dim_variety: Optional[Dict[str, float]] = None,
        coupling_matrix: Optional[Dict[str, Dict[str, float]]] = None,
        space_id: Optional[str] = None,
    ):
        self.current = current
        self.variety = max(0.0, min(1.0, variety))  # 归一化到 [0, 1]
        self.epiplexity = max(0.0, min(1.0, epiplexity))  # [0, 1]
        self.dimensions = dimensions or ["unknown"]
        self.per_dim_variety = per_dim_variety or {}
        self.coupling_matrix = coupling_matrix or {}
        self.space_id = space_id or uuid.uuid4().hex[:12]
        self._history: List[Tuple[str, float]] = []  # (action_id, variety_after)
    
    # ── 核心操作 ──
    
    def constrain(self, action: "Constraint") -> "Space[T]":
        """施加约束，返回新的可能性空间。
        
        约束缩小了可能性空间（variety 降低）。
        同时，施加约束的解耦合作用也使 epiplexity 可能降低。
        """
        new_variety = self.variety * (1.0 - action.expected_reduction)
        new_variety = max(0.01, new_variety)
        
        # 约束对 epiplexity 的影响：
        # 成功降低一个维度的变异度，可能也解耦了它与其他维度的关系
        new_epiplexity = self.epiplexity * (1.0 - 0.5 * action.expected_reduction)
        new_epiplexity = max(0.0, new_epiplexity)
        
        new_space = Space(
            current=self.current,
            variety=round(new_variety, 4),
            epiplexity=round(new_epiplexity, 4),
            dimensions=self.dimensions.copy(),
            per_dim_variety=self.per_dim_variety.copy() if self.per_dim_variety else {},
            coupling_matrix=self.coupling_matrix.copy() if self.coupling_matrix else {},
        )
        new_space._history = self._history + [(action.constraint_id, new_variety)]
        return new_space
    
    def measure(self) -> float:
        """测量当前变异度。"""
        return self.variety
    
    def effective_variety(self, alpha: float = EPIPLEXITY_ALPHA) -> float:
        """有效变异度 = variety × (1 + α × epiplexity)
        
        反映控制器需要应对的真实复杂度。
        两个 variety 相同的 Space，epiplexity 越高，有效变异度越大。
        """
        return min(1.0, self.variety * (1.0 + alpha * self.epiplexity))
    
    def distance_to(self, target: "Space[T]") -> float:
        """到目标空间的距离。
        
        0 = 完全重合，1 = 完全不重叠。
        升级：基于有效变异度差异，而非原始 variety。
        """
        return abs(self.effective_variety() - target.effective_variety())
    
    def merge(self, other: "Space[T]") -> "Space[T]":
        """合并两个可能性空间。
        
        合并后的有效变异度 >= 两者各自的最大值。
        """
        merged_ev = max(self.effective_variety(), other.effective_variety()) * 1.1
        merged_ev = min(1.0, merged_ev)
        
        merged_dims = list(set(self.dimensions + other.dimensions))
        
        return Space(
            variety=round(merged_ev, 4),
            dimensions=merged_dims,
        )
    
    def decompose(self) -> List["Space[T]"]:
        """分解为子空间。
        
        升级：考虑 epiplexity —— 高耦合度时分解效果差，
        因为子空间之间仍共享不确定性。
        
        返回子空间列表，每个保留耦合信息。
        """
        n = len(self.dimensions)
        if n <= 1:
            return [self]
        
        # 耦合衰减因子：epiplexity 越高，decompose 的效果越差
        # 因为耦合的维度之间无法真正独立
        decoupling_factor = 1.0 - self.epiplexity * 0.7  # [0.3, 1.0]
        sub_variety = self.variety / n * decoupling_factor
        
        return [
            Space(
                variety=round(sub_variety, 4),
                epiplexity=round(self.epiplexity * 0.5, 4),  # 子空间耦合度降低
                dimensions=[dim],
                per_dim_variety={dim: self.per_dim_variety.get(dim, sub_variety)},
            )
            for dim in self.dimensions
        ]
    
    # ── 结构分析 ──
    
    def structure_report(self) -> dict:
        """生成完整结构分析报告（含 epiplexity）。"""
        return {
            "space_id": self.space_id,
            "variety": self.variety,
            "epiplexity": self.epiplexity,
            "effective_variety": round(self.effective_variety(), 4),
            "dimensions": self.dimensions,
            "num_dimensions": len(self.dimensions),
            "per_dim_variety": self.per_dim_variety,
            "coupling_density": self._coupling_density(),
            "steps": len(self._history),
        }
    
    def _coupling_density(self) -> float:
        """计算耦合密度：实际耦合边数 / 最大可能边数。"""
        if len(self.dimensions) <= 1:
            return 0.0
        max_edges = len(self.dimensions) * (len(self.dimensions) - 1) / 2
        if max_edges == 0:
            return 0.0
        
        edge_count = sum(
            1 for src in self.coupling_matrix
            for tgt, strength in self.coupling_matrix[src].items()
            if strength > 0
        )
        return round(edge_count / max_edges, 4)
    
    def convergence_report(self) -> dict:
        """生成收敛报告。"""
        if not self._history:
            return {
                "steps": 0,
                "initial_variety": self.variety,
                "initial_epiplexity": self.epiplexity,
                "final_variety": self.variety,
                "final_epiplexity": self.epiplexity,
                "reduction": 0.0,
                "epiplexity_reduction": 0.0,
                "history": [],
            }
        
        # 从第一个 step 之前的 state 推算初始值
        initial_variety = 1.0
        initial_epiplexity = self._history[0][1] if self._history else 1.0
        
        return {
            "steps": len(self._history),
            "initial_variety": initial_variety,
            "initial_epiplexity": initial_epiplexity,
            "final_variety": self.variety,
            "final_epiplexity": self.epiplexity,
            "variety_reduction": round((initial_variety - self.variety) / initial_variety, 4),
            "epiplexity_reduction": round(max(0, (initial_epiplexity - self.epiplexity) / initial_epiplexity), 4),
            "history": [
                {"action": aid, "variety": v} for aid, v in self._history
            ],
        }
    
    def __repr__(self) -> str:
        return (
            f"Space(id={self.space_id}, variety={self.variety:.3f}, "
            f"epiplexity={self.epiplexity:.3f}, "
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
