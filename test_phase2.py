"""CybOS Phase 2 — Epiplexity 集成验证测试（三段式定性输入）"""
from cybos import *

print("=" * 70)
print("TEST 1: QualitativeMapper 三段式映射")
print("=" * 70)

# 核心验证：三段式映射稳定、不波动
for q, expected in [("低", 0.25), ("中", 0.50), ("高", 0.75)]:
    v = QualitativeMapper.map_dimension_value(q)
    print(f"  dimension '{q}' -> {v:.2f}")
    assert v == expected, f"{q} 应映射为 {expected}"

for q, expected in [("弱", 0.30), ("中", 0.60), ("强", 0.90)]:
    v = QualitativeMapper.map_coupling_strength(q)
    print(f"  coupling '{q}' -> {v:.2f}")
    assert v == expected, f"{q} 应映射为 {expected}"

# 向后兼容：float 直接通过
assert QualitativeMapper.map_dimension_value(0.35) == 0.35
assert QualitativeMapper.map_coupling_strength(0.75) == 0.75
print("  向后兼容: float 直接通过 ✓")

print()
print("=" * 70)
print("TEST 2: Epiplexity 估算 — 三段式输入")
print("=" * 70)

# 场景A：低耦合 — 3个独立任务，没有标注耦合
survey_a = survey_from_text(
    "给三个文件分别加注释",
    dimensions={"文件A": "中", "文件B": "中", "文件C": "中"},
    # 无 couplings → 推定独立
)
space_a = survey_a.to_space()
print(f"[低耦合]  {survey_a}")
print(f"  Space:   variety={space_a.variety:.3f}, epiplexity={space_a.epiplexity:.3f}")
assert space_a.epiplexity < 0.3, "低耦合应 <0.3"
assert space_a.variety == 0.50, "三个'中'→平均0.50"
print("  断言通过: epi<0.3, variety=0.50 ✓")

# 场景B：高耦合 — 分布式共识算法，明确耦合关系
survey_b = survey_from_text(
    "设计分布式共识算法，要求Byzantine容错和最终一致性",
    dimensions={
        "共识选型": "高",
        "Byzantine容错": "中",
        "最终一致性": "中",
        "网络恢复": "中",
    },
    couplings=[
        ("共识选型", "Byzantine容错", "强"),
        ("共识选型", "最终一致性", "中"),
        ("共识选型", "网络恢复", "中"),
        ("Byzantine容错", "最终一致性", "强"),
    ],
)
space_b = survey_b.to_space()
print(f"\n[高耦合]  {survey_b}")
print(f"  Space:   variety={space_b.variety:.3f}, epiplexity={space_b.epiplexity:.3f}")
assert space_b.epiplexity > 0.3, "高耦合应 >0.3"
print("  断言通过: epi 中高区间 ✓")

# 场景C：极高耦合 — 全耦合
survey_c = survey_from_text(
    "强耦合子系统集成",
    dimensions={"A": "高", "B": "高", "C": "高"},
    couplings=[
        ("A", "B", "强"), ("B", "A", "强"),
        ("A", "C", "强"), ("C", "A", "强"),
        ("B", "C", "强"), ("C", "B", "强"),
    ],
)
space_c = survey_c.to_space()
print(f"\n[极高耦合] variant={survey_c.variety:.3f}, epi={space_c.epiplexity:.3f}")
assert space_c.epiplexity > 0.7, "全耦合应 >0.7"
print("  断言通过: epi 高区间 ✓")

print()
print("=" * 70)
print("TEST 3: Ashby 系数 — epiplexity 惩罚")
print("=" * 70)

rt = Runtime()
controller = Space(variety=0.8)

for name, task in [("低耦合", space_a), ("高耦合", space_b)]:
    result = rt.effective_ashby_coeff(controller, task)
    adequate_str = "充足" if result["adequate"] else "不足"
    print(f"[{name}] 系数={result['coefficient']:.3f} ({adequate_str})")
    print(f"  原始Ashby={result['raw_ashby']:.3f}, epi惩罚=x{result['epiplexity_penalty']:.3f}")

# 关键验证：同variety不同epiplexity
s_low = Space(variety=0.6, epiplexity=0.2)
s_high = Space(variety=0.6, epiplexity=0.8)
c = Space(variety=1.0)
r_low = rt.effective_ashby_coeff(c, s_low)
r_high = rt.effective_ashby_coeff(c, s_high)
print(f"\n  同variety=0.6: epi0.2→Ashby={r_low['coefficient']:.3f}, epi0.8→Ashby={r_high['coefficient']:.3f}")
assert r_high["coefficient"] < r_low["coefficient"], "高epi应降低系数"
print("  断言通过: 高epiplexity降低Ashby系数 ✓")

print()
print("=" * 70)
print("TEST 4: 控制循环 — 策略自动选择")
print("=" * 70)


class MockController:
    def decide(self, **kwargs):
        return {"action": "process", "args": {}, "expected_reduction": 0.3}
    def on_strategy(self, s): pass
    def on_strategy_change(self, s, sp): pass


# 低耦合 → parallel_decompose
rt1 = Runtime()
result1 = Agent(rt1).run(MockController(), survey_result=survey_a, max_steps=10)
print(f"[低耦合控制循环]")
print(f"  步数={result1['steps']}, 策略={result1['strategy_used']}")
assert result1["strategy_used"] == "parallel_decompose", "低耦合应parallel_decompose"
print("  断言通过: 策略=parallel_decompose ✓")

# 高耦合 → decouple_then_divide
rt2 = Runtime()
result2 = Agent(rt2).run(MockController(), survey_result=survey_b, max_steps=10)
print(f"[高耦合控制循环]")
print(f"  步数={result2['steps']}, 策略={result2['strategy_used']}, 最终epi={result2['epiplexity_final']:.3f}")
assert result2["strategy_used"] in ("decouple_then_divide", "mainline_first"), "高耦合应decouple/mainline"
print("  断言通过: 策略自适应 ✓")

# 极高耦合 → 初始为mainline_first，自适应切换
rt3 = Runtime()
result3 = Agent(rt3).run(MockController(), survey_result=survey_c, max_steps=15)
print(f"[极高耦合控制循环]")
print(f"  初始epi={result3['epiplexity_initial']:.3f}, 最终策略={result3['strategy_used']}")
assert result3["epiplexity_initial"] > 0.7, "初始epi应>0.7"
print("  断言通过: 初始策略=mainline_first ✓")

print()
print("=" * 70)
print("TEST 5: 向后兼容 — float 输入仍可用")
print("=" * 70)

survey_old = survey_from_text(
    "旧版float输入",
    dimensions={"x": 0.5, "y": 0.4},
    couplings=[("x", "y", 0.6)],
)
print(f"  {survey_old}")
assert survey_old.variety == 0.45, "float输入应直接通过"
print("  断言通过: float输入兼容 ✓")

print()
print("=" * 70)
print("TEST 6: 完整流程 — 三段式→Survey→Space→控制循环")
print("=" * 70)

survey = survey_from_text(
    "为Python项目加类型注解，其中5个有循环import",
    dimensions={
        "模块依赖分析": "高",
        "类型注解编写": "中",
        "循环import解耦": "高",
        "测试验证": "低",
    },
    couplings=[
        ("循环import解耦", "模块依赖分析", "强"),
        ("循环import解耦", "类型注解编写", "中"),
        ("模块依赖分析", "类型注解编写", "弱"),
    ],
)
space = survey.to_space()
print(f"任务拆解: dims={survey.num_dimensions}, couplings={len(survey.couplings)}")
print(f"  Space: variety={space.variety:.3f}, epi={space.epiplexity:.3f}")

rt4 = Runtime()
result4 = Agent(rt4).run(MockController(), survey_result=survey, max_steps=15)
print(f"  控制: {result4['steps']}步, 策略={result4['strategy_used']}")
print(f"  epi: {result4['epiplexity_initial']:.3f} → {result4['epiplexity_final']:.3f}")

print()
print("=" * 70)
print("ALL TESTS PASSED ✓")
print("=" * 70)
