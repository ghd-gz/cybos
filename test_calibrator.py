"""CybOS Phase 2 — 归纳校准器验证"""
from cybos import *

print("=" * 70)
print("TEST 1: Calibrator 收集记录")
print("=" * 70)

cal = Calibrator()

# 模拟添加几条记录（从实际测试数据模拟）
records_data = [
    # (epi_predicted, epi_final, steps, converged)
    (0.05, 0.038, 3, True),    # 低耦合 - 预测准
    (0.05, 0.042, 4, True),    # 低耦合 - 预测准
    (0.43, 0.29, 8, True),     # 中高耦合 - epi下降慢
    (0.43, 0.31, 7, True),     # 中高耦合 - epi下降慢
    (0.62, 0.40, 10, False),   # 高耦合 - 未收敛
    (0.62, 0.38, 9, True),     # 高耦合
    (0.97, 0.55, 15, True),    # 极高耦合 - 下降慢
    (0.97, 0.60, 12, False),   # 极高耦合 - 未收敛
]

for epi_p, epi_f, steps, conv in records_data:
    cal.add_record(
        report={
            "survey_epiplexity": epi_p,
            "final_epiplexity": epi_f,
            "step_count": steps,
            "converged": conv,
            "strategy": "decouple_then_divide",
            "prediction_error": round(abs(epi_p - epi_f), 4),
        },
        task_description="test",
    )

print(f"  已收集 {cal.count} 条记录")
assert cal.count == 8
print("  断言通过: 收集正常 ✓")

print()
print("=" * 70)
print("TEST 2: 校准分析 - 检测系统性偏差")
print("=" * 70)

analysis = cal.analyze()

print(f"  记录数: {analysis['n_records']}")
for level, data in analysis["by_epi_level"].items():
    print(f"  {level}: count={data['count']}, "
          f"avg_error={data['avg_error']:.4f}, "
          f"conv_rate={data['convergence_rate']:.2f}")

print(f"\n  系统性偏差: {analysis['systematic_bias']['has_bias']}")
for b in analysis["systematic_bias"].get("details", []):
    print(f"    {b['meaning']}")

print(f"\n  建议:")
for s in analysis["suggestions"]:
    print(f"    {s['target']}: {s['current']} → {s['suggested']}")
    print(f"      原因: {s['reason']}")

print(f"\n  阈值审查:")
for key, val in analysis["threshold_review"].items():
    print(f"    {key}: 当前={val['current']}, 建议={val['suggested']}, "
          f"需调整={val['needs_change']}")

print(f"\n  建议说明:\n{analysis['adjustment_notes']}")

# 验证：高耦合区间应有明显的系统性偏差
high_group = analysis["by_epi_level"].get("高(>0.7)", {})
assert high_group.get("count", 0) >= 2
assert high_group.get("avg_error", 0) > 0.3, "高耦合误差应显著"
print("\n  断言通过: 高耦合区间偏差显著 ✓")

print()
print("=" * 70)
print("TEST 3: 文件持久化")
print("=" * 70)

cal.save("~/.cybos/test_calibration.json")
cal2 = Calibrator.load("~/.cybos/test_calibration.json")
print(f"  保存并加载: {cal2.count} 条记录")
assert cal2.count == 8
assert cal2.records[0].epiplexity_predicted == 0.05
print("  断言通过: 持久化正常 ✓")

# 清理测试文件
import os
os.remove(os.path.expanduser("~/.cybos/test_calibration.json"))

print()
print("=" * 70)
print("TEST 4: 空校准器不报错")
print("=" * 70)

empty_cal = Calibrator()
result = empty_cal.analyze()
print(f"  {result['message']}")
assert result["n_records"] == 0
print("  断言通过: 空校准器正常 ✓")

print()
print("=" * 70)
print("ALL CALIBRATOR TESTS PASSED ✓")
print("=" * 70)
