"""
cybos.survey — 测绘 (Survey) 子系统

连接 LLM 控制器的自然语言拆解能力与 Space 的结构化数据。
LLM 作为计算有界观察者，在拆解任务时输出测绘结果，
survey 模块将其转换为包含 Epiplexity 的 Space。

对照论文 (Finzi et al. 2026)：
  - SurveyResult.dimensions = LLM 估算的数据生成程序 P 的"结构"
  - EpiplexityEstimator.estimate() = 近似 S^T (最优程序长度 |P*|) 的启发式
  - 计算预算 T = LLM 的上下文窗口 + 推理步数
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .space import Space


# ─── 数据类型 ───


@dataclass
class Coupling:
    """维度间的耦合关系。
    
    对应论文中"维度间的交叉依赖"——即一个维度的变化会如何影响其他维度。
    """
    source: str          # 源维度
    target: str          # 目标维度
    strength: float = 0.5  # 耦合强度 [0, 1]，0=独立，1=完全耦合
    description: str = ""  # 自然语言描述


@dataclass
class SurveyResult:
    """LLM 测绘的结构化输出。
    
    LLM 在拆解自然语言任务时，将隐性知识（维度拆解、耦合判断）
    显式化为结构化数据，供 EpiplexityEstimator 计算。

    对照论文定义 8：
    - dimensions = 问题空间的维度分解（对应程序 P 的结构）
    - couplings = 维度间的交叉依赖（对应程序 P 中各模块的耦合度）
    - variety = 总不确定性（对应 MDL 中的数据编码长度）
    """
    task_description: str = ""
    dimensions: Dict[str, float] = field(default_factory=dict)
    # { "维度名": per_dim_variety (该维度的独立不确定性) }

    couplings: List[Coupling] = field(default_factory=list)
    # 维度间的耦合关系列表

    raw_text: str = ""  # LLM 的原始非结构化测绘文本（用于回退分析）

    # ── 计算后填充 ──
    epiplexity: float = 0.0
    variety: float = 1.0

    @property
    def num_dimensions(self) -> int:
        return len(self.dimensions)

    @property
    def dimension_names(self) -> List[str]:
        return list(self.dimensions.keys())

    def to_space(self) -> Space:
        """将测绘结果转换为 Space（含 epiplexity）。"""
        estimator = EpiplexityEstimator()
        epiplexity = estimator.estimate(self)
        
        # 计算总 variety（per_dim_variety 的均值，归一化）
        if self.dimensions:
            variety = sum(self.dimensions.values()) / len(self.dimensions)
            variety = max(0.01, min(1.0, variety))
        else:
            variety = 1.0
        
        # 构建耦合矩阵
        coupling_matrix: Dict[str, Dict[str, float]] = {}
        for c in self.couplings:
            if c.source not in coupling_matrix:
                coupling_matrix[c.source] = {}
            coupling_matrix[c.source][c.target] = c.strength
        
        return Space(
            variety=round(variety, 4),
            epiplexity=round(epiplexity, 4),
            dimensions=list(self.dimensions.keys()),
            per_dim_variety=self.dimensions.copy(),
            coupling_matrix=coupling_matrix,
        )

    def __repr__(self) -> str:
        return (
            f"SurveyResult(dims={self.num_dimensions}, "
            f"couplings={len(self.couplings)}, "
            f"variety={self.variety:.3f}, "
            f"epiplexity={self.epiplexity:.3f})"
        )


# ─── Epiplexity 估计器 ───


class EpiplexityEstimator:
    """从 LLM 测绘输出中估算 Epiplexity。
    
    论文定义 8 的 S^T(X) = |P*| 需要搜索整个程序空间。
    本估计器是 LLM 作为有界观察者的启发式替代：
    从维度数和耦合关系推断结构复杂度。
    
    三个估计模式，按优先级排列：
    1. 完整耦合矩阵模式（有明确 couplings）—— 最精确
    2. 维度结构模式（仅有 dimensions，无 couplings）
    3. LLM 直接估计模式（什么结构化数据都没有）
    """

    def estimate(self, survey: SurveyResult) -> float:
        """从 SurveyResult 估算 Epiplexity。"""
        if not survey.dimensions and not survey.couplings:
            return 0.0
        
        n = survey.num_dimensions
        if n == 0:
            return 0.0
        
        # 模式 1: 有明确耦合关系
        if survey.couplings:
            return self._from_couplings(n, survey.couplings)
        
        # 模式 2: 仅有维度，无耦合信息
        # LLM 拆解出维度但没有标注耦合 → 推定维度间低耦合
        return self._from_dimensions_only(n, survey.dimensions)
    
    def _from_couplings(self, n: int, couplings: List[Coupling]) -> float:
        """从耦合关系计算 epiplexity。
        
        公式：Σ(strength_ij) / max_possible_edges
        
        其中：
        - strength_ij = 每对维度间的耦合强度
        - max_possible_edges = n*(n-1)/2（无向完全图的边数）
        
        n=1 时 epiplexity=0（没有维度间耦合）
        """
        if n <= 1:
            return 0.0
        
        max_edges = n * (n - 1) / 2
        if max_edges == 0:
            return 0.0
        
        total_strength = sum(c.strength for c in couplings)
        raw = total_strength / max_edges
        
        # 非线性缩放：让中等耦合更加明显
        # 低耦合 (<0.2) → 影响小，高耦合 (>0.7) → 急剧增加
        epiplexity = math.pow(raw, 0.7)
        
        return min(1.0, epiplexity)
    
    def _from_dimensions_only(self, n: int, dimensions: Dict[str, float]) -> float:
        """从仅有维度（无耦合信息）估测 epiplexity。
        
        核心原则：没有耦合信息时，推定维度间基本独立。
        仅当维度数很多时微幅上调，表示"潜在耦合风险"。
        """
        if n <= 1:
            return 0.0
        if n <= 3:
            return 0.05  # 少量维度，无耦合标注 → 基本独立
        if n <= 6:
            return 0.10  # 中等维度数，轻微潜在耦合
        return 0.15      # 很多维度但无耦合标注，承认潜在风险但不高
    
    def quick_estimate(self, n_dims: int, n_couplings: int, 
                       avg_strength: float = 0.5) -> float:
        """快速估算（不需要 SurveyResult 对象）。
        
        用于控制循环中的实时判断。
        """
        if n_dims <= 1:
            return 0.0
        
        max_edges = n_dims * (n_dims - 1) / 2
        if max_edges == 0:
            return 0.0
        
        return min(1.0, (n_couplings * avg_strength) / max_edges)


def compute_epiplexity(
    dimensions: Dict[str, float],
    couplings: Optional[List[Coupling]] = None,
) -> float:
    """便捷函数：一步计算 epiplexity。"""
    survey = SurveyResult(
        dimensions=dimensions,
        couplings=couplings or [],
    )
    return EpiplexityEstimator().estimate(survey)


def survey_from_text(
    task_description: str,
    dimensions: Dict[str, float],
    couplings: Optional[List[Tuple[str, str, float]]] = None,
) -> SurveyResult:
    """从自然语言任务的拆解结果创建 SurveyResult。
    
    这是 LLM 控制器的标准接口：LLM 拆解任务后，
    用这个函数将拆解结果结构化为 SurveyResult。
    
    Args:
        task_description: 原始任务描述
        dimensions: {维度名: per_dim_variety}
        couplings: [(源维度, 目标维度, 强度), ...]
    
    Returns:
        SurveyResult（epiplexity 已计算）
    """
    coupling_objects = []
    if couplings:
        for src, tgt, strength in couplings:
            coupling_objects.append(Coupling(
                source=src,
                target=tgt,
                strength=min(1.0, max(0.0, strength)),
            ))
    
    survey = SurveyResult(
        task_description=task_description,
        dimensions=dimensions,
        couplings=coupling_objects,
    )
    
    # 计算 epiplexity
    estimator = EpiplexityEstimator()
    survey.epiplexity = estimator.estimate(survey)
    
    # 计算 variety
    if dimensions:
        survey.variety = sum(dimensions.values()) / len(dimensions)
    
    return survey
