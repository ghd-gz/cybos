"""
cybos.calibrator — 归纳校准器

从控制循环的实际收敛数据反向校准 QualitativeMapper 的映射表。
这是 CybOS 控制论闭环的关键环节——测绘预测 → 实际执行 → 误差分析 → 修正参数。

校准流程：
1. 每个任务完成后，从 CybosSession.end() 报告中提取 CalibrationRecord
2. Calibrator 累积记录
3. 分析记录 → 输出映射表调整建议
4. 人工确认后更新 QualitativeMapper
"""

import json
import math
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .survey import QualitativeMapper


# ─── 校准记录 ───


@dataclass
class CalibrationRecord:
    """一次控制循环的校准记录。
    
    从 CybosSession.end() 报告中提取，用于反向校准。
    """
    # 时间戳（用于去重和排序）
    timestamp: float = field(default_factory=time.time)

    # 测绘信息
    task_description: str = ""
    n_dimensions: int = 0
    categories: Dict[str, str] = field(default_factory=dict)
    # {"维度名": "低|中|高"}
    coupling_pairs: List[Tuple[str, str, str]] = field(default_factory=list)
    # [("源", "目标", "弱|中|强")]

    # 预测值（由 QualitativeMapper 算出）
    epiplexity_predicted: float = 0.0
    variety_predicted: float = 0.0

    # 实际值（从控制循环报告）
    epiplexity_final: float = 0.0
    steps: int = 0
    converged: bool = False
    strategy_used: str = ""

    # 误差
    prediction_error: float = 0.0
    # prediction_error > 0 → epi 被低估（实际比预测难收敛）
    # prediction_error < 0 → epi 被高估（实际比预测容易）


# ─── 校准器 ───


class Calibrator:
    """从多个控制循环记录中分析模式，输出映射表调整建议。

    用法：
        calibrator = Calibrator()
        
        # 每次任务完成后添加记录
        calibrator.add_record(report_dict)
        
        # 分析并输出建议
        suggestion = calibrator.analyze()
        print(suggestion["adjustment_notes"])
    """

    def __init__(self):
        self.records: List[CalibrationRecord] = []

    def add_record(self, report: dict,
                   task_description: str = "",
                   dims: Optional[Dict[str, str]] = None,
                   couplings: Optional[List[Tuple[str, str, str]]] = None) -> None:
        """从 CybosSession.end() 报告创建并添加校准记录。

        Args:
            report: CybosSession.end() 的返回字典
            task_description: 任务文本
            dims: 测绘时的维度标注 {维度名: "低|中|高"}
            couplings: 测绘时的耦合标注 [(源, 目标, "弱|中|强")]
        """
        record = CalibrationRecord(
            task_description=task_description,
            n_dimensions=report.get("steps", 0),  # 暂用steps，后面修正
            categories=dims or {},
            coupling_pairs=couplings or [],
            epiplexity_predicted=report.get("survey_epiplexity", 0),
            variety_predicted=report.get("survey_variety", 0),
            epiplexity_final=report.get("final_epiplexity", 0),
            steps=report.get("step_count", report.get("steps", 0)),
            converged=report.get("converged", False),
            strategy_used=report.get("strategy", report.get("strategy_used", "")),
            prediction_error=report.get("prediction_error", 0),
        )
        # 修正维度数：如果没传 explicit dims，从 categories 推断
        if dims:
            record.n_dimensions = len(dims)
        self.records.append(record)

    @property
    def count(self) -> int:
        return len(self.records)

    def clear(self) -> None:
        """清空所有记录。"""
        self.records.clear()

    # ── 分析 ──

    def analyze(self) -> dict:
        """分析所有校准记录，输出校准建议。

        返回包含以下字段的字典：
        - n_records: 分析了多少条记录
        - by_dimension_category: 按维度三段标签分组的误差统计
        - by_coupling_category: 按耦合三段标签分组的误差统计
        - systematic_bias: 是否发现系统性偏差
        - suggestions: 映射表调整建议
        - threshold_review: 策略阈值（0.3/0.7）是否需调整
        - adjustment_notes: 可读的建议说明
        """
        if not self.records:
            return {
                "n_records": 0,
                "message": "没有足够记录进行分析，继续收集。",
            }

        # 按测绘 epi 分组
        groups = self._group_by_epi_level()

        # 计算每组误差
        group_analysis = {}
        for level, recs in groups.items():
            errors = [r.prediction_error for r in recs]
            conv_rate = sum(1 for r in recs if r.converged) / len(recs)
            avg_steps = sum(r.steps for r in recs) / len(recs)
            group_analysis[level] = {
                "count": len(recs),
                "avg_error": round(sum(errors) / len(errors), 4),
                "errors": [round(e, 4) for e in errors],
                "convergence_rate": round(conv_rate, 2),
                "avg_steps": round(avg_steps, 1),
            }

        # 检测系统性偏差
        bias = self._detect_bias(group_analysis)
        suggestions = self._generate_suggestions(group_analysis, bias)

        # 阈值审查建议
        threshold_review = self._review_thresholds(group_analysis)

        return {
            "n_records": self.count,
            "by_epi_level": group_analysis,
            "systematic_bias": bias,
            "suggestions": suggestions,
            "threshold_review": threshold_review,
            "adjustment_notes": self._format_notes(suggestions, threshold_review),
        }

    def _group_by_epi_level(self) -> Dict[str, List[CalibrationRecord]]:
        """按测绘时的 epiplexity 三段级分组。"""
        groups = {
            "低(<0.3)": [],
            "中(0.3-0.7)": [],
            "高(>0.7)": [],
        }
        for r in self.records:
            e = r.epiplexity_predicted
            if e < 0.3:
                groups["低(<0.3)"].append(r)
            elif e < 0.7:
                groups["中(0.3-0.7)"].append(r)
            else:
                groups["高(>0.7)"].append(r)
        return groups

    def _detect_bias(self, group_analysis: dict) -> dict:
        """检测系统性偏差。"""
        biases = []
        for level, data in group_analysis.items():
            if data["count"] < 2:
                continue
            avg_err = data["avg_error"]

            # 误差正或负超过0.05视为系统性偏差
            if avg_err > 0.05:
                biases.append({
                    "level": level,
                    "direction": "underestimated",
                    "magnitude": round(avg_err, 4),
                    "meaning": f"{level} 任务被系统性低估了 {avg_err:.3f}",
                })
            elif avg_err < -0.05:
                biases.append({
                    "level": level,
                    "direction": "overestimated",
                    "magnitude": round(abs(avg_err), 4),
                    "meaning": f"{level} 任务被系统性高估了 {abs(avg_err):.3f}",
                })

        return {
            "has_bias": len(biases) > 0,
            "details": biases,
        }

    def _generate_suggestions(self, group_analysis: dict, bias: dict) -> List[dict]:
        """生成映射表调整建议。"""
        suggestions = []

        # 只对有系统性偏差的级别生成建议
        for b in bias.get("details", []):
            level = b["level"]
            direction = b["direction"]
            mag = b["magnitude"]

            if "低" in level:
                if direction == "underestimated":
                    # 低估了 → 应该更高 → 调高映射值
                    suggestions.append({
                        "target": "DIMENSION_VALUES['低']",
                        "current": QualitativeMapper.DIMENSION_VALUES["低"],
                        "suggested": round(
                            QualitativeMapper.DIMENSION_VALUES["低"] + min(mag, 0.15), 3
                        ),
                        "reason": f"{level}任务被系统性低估{mag:.3f}",
                    })
                else:
                    suggestions.append({
                        "target": "DIMENSION_VALUES['低']",
                        "current": QualitativeMapper.DIMENSION_VALUES["低"],
                        "suggested": 0.15,  # 最小不低于0.15
                        "reason": f"{level}任务被系统性高估{mag:.3f}",
                    })
            elif "中" in level:
                adj = min(mag * 0.5, 0.15)  # 减缓调整幅度
                if direction == "underestimated":
                    suggestions.append({
                        "target": "DIMENSION_VALUES['中']",
                        "current": QualitativeMapper.DIMENSION_VALUES["中"],
                        "suggested": round(
                            QualitativeMapper.DIMENSION_VALUES["中"] + adj, 3
                        ),
                        "reason": f"{level}任务被系统性低估{mag:.3f}",
                    })
                else:
                    suggestions.append({
                        "target": "DIMENSION_VALUES['中']",
                        "current": QualitativeMapper.DIMENSION_VALUES["中"],
                        "suggested": round(
                            QualitativeMapper.DIMENSION_VALUES["中"] - adj, 3
                        ),
                        "reason": f"{level}任务被系统性高估{mag:.3f}",
                    })
            elif "高" in level:
                adj = min(mag * 0.4, 0.15)
                if direction == "underestimated":
                    suggestions.append({
                        "target": "DIMENSION_VALUES['高']",
                        "current": QualitativeMapper.DIMENSION_VALUES["高"],
                        "suggested": round(
                            QualitativeMapper.DIMENSION_VALUES["高"] + adj, 3
                        ),
                        "reason": f"{level}任务被系统性低估{mag:.3f}",
                    })
                else:
                    suggestions.append({
                        "target": "DIMENSION_VALUES['高']",
                        "current": QualitativeMapper.DIMENSION_VALUES["高"],
                        "suggested": round(
                            QualitativeMapper.DIMENSION_VALUES["高"] - adj, 3
                        ),
                        "reason": f"{level}任务被系统性高估{mag:.3f}",
                    })

        return suggestions

    def _review_thresholds(self, group_analysis: dict) -> dict:
        """审查策略阈值（0.3/0.7）是否合理。"""
        result = {
            "threshold_03": {"current": 0.3, "suggested": 0.3, "needs_change": False},
            "threshold_07": {"current": 0.7, "suggested": 0.7, "needs_change": False},
        }

        # 检查低/中边界附近的收敛率差异
        low_group = group_analysis.get("低(<0.3)", {})
        mid_group = group_analysis.get("中(0.3-0.7)", {})

        if low_group.get("count", 0) >= 3 and mid_group.get("count", 0) >= 3:
            low_conv = low_group.get("convergence_rate", 0)
            mid_conv = mid_group.get("convergence_rate", 0)
            # 如果收敛率接近，说明两个区间的区分度不够
            if abs(low_conv - mid_conv) < 0.1:
                result["threshold_03"]["needs_change"] = True
                result["threshold_03"]["suggested"] = round(0.2, 1)
                result["threshold_03"]["reason"] = (
                    f"低收敛率={low_conv:.2f} 与中收敛率={mid_conv:.2f} 差异不足")

        return result

    def _format_notes(self, suggestions: list, threshold_review: dict) -> str:
        """生成可读的建议说明。"""
        lines = [f"共有 {self.count} 条校准记录。", ""]

        if not suggestions:
            lines.append("未检测到明显的系统性偏差，当前映射表可用。")
        else:
            lines.append("检测到系统性偏差，建议调整映射表：")
            for s in suggestions:
                lines.append(
                    f"  - {s['target']}: {s['current']} → {s['suggested']}"
                )
                lines.append(f"    原因: {s['reason']}")

        for key, val in threshold_review.items():
            if val["needs_change"]:
                lines.append(
                    f"\n建议调整策略阈值: {val['current']} → {val['suggested']}"
                )
                lines.append(f"  原因: {val.get('reason', '')}")

        if not lines[-1]:
            lines.pop()
        return "\n".join(lines)

    def save(self, path: str = "~/.cybos/calibration_records.json") -> None:
        """保存校准记录到文件。"""
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "records": [asdict(r) for r in self.records],
            "count": self.count,
        }
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))

    @classmethod
    def load(cls, path: str = "~/.cybos/calibration_records.json") -> "Calibrator":
        """从文件加载校准记录。"""
        p = Path(path).expanduser()
        if not p.exists():
            return cls()

        data = json.loads(p.read_text())
        cal = cls()
        for r_data in data.get("records", []):
            # 过滤掉多余字段
            keys = CalibrationRecord.__dataclass_fields__.keys()
            filtered = {k: r_data[k] for k in keys if k in r_data}

            # Tuple 类型需要特殊处理
            coupling_pairs_data = filtered.pop("coupling_pairs", [])
            record = CalibrationRecord(**filtered)
            record.coupling_pairs = [
                (c[0], c[1], c[2]) for c in coupling_pairs_data
            ]
            cal.records.append(record)

        return cal
