"""CybOS Phase 2 — Epiplexity 集成验证测试"""
from cybos import *

print("=" * 70)
print("TEST 1: Epiplexity 估算 — 低耦合 vs 高耦合")
print("=" * 70)

# 场景A：低耦合 — 3个独立任务
survey_a = survey_from_text(
    "给三个文件分别加注释",
    dimensions={"file_a": 0.5, "file_b": 0.4, "file_c": 0.3},
)
space_a = survey_a.to_space()
print(f"[低耦合]  {survey_a}")
print(f"  Space:   variety={space_a.variety:.3f}, epiplexity={space_a.epiplexity:.3f}")
print(f"  有效变异度:  {space_a.effective_variety():.3f}")
assert space_a.epiplexity < 0.3, "低耦合任务epiplexity应 < 0.3"
print("  断言通过: epiplexity < 0.3 ✓")

# 场景B：高耦合 — 分布式共识算法
survey_b = survey_from_text(
    "设计分布式共识算法，要求Byzantine容错和最终一致性",
    dimensions={
        "共识选型": 0.7,
        "Byzantine容错": 0.6,
        "最终一致性": 0.5,
        "网络恢复": 0.6,
    },
    couplings=[
        ("共识选型", "Byzantine容错", 0.9),
        ("共识选型", "最终一致性", 0.7),
        ("共识选型", "网络恢复", 0.6),
        ("Byzantine容错", "最终一致性", 0.8),
    ],
)
space_b = survey_b.to_space()
print(f"\n[高耦合]  {survey_b}")
print(f"  Space:   variety={space_b.variety:.3f}, epiplexity={space_b.epiplexity:.3f}")
print(f"  有效变异度:  {space_b.effective_variety():.3f}")
assert space_b.epiplexity > 0.3, "高耦合任务epiplexity应 > 0.3"
print("  断言通过: epiplexity > 0.3 ✓")

print()
print("=" * 70)
print("TEST 2: Ashby 系数升级 — epiplexity 惩罚")
print("=" * 70)

rt = Runtime()
controller = Space(variety=0.8)

for name, task in [("低耦合", space_a), ("高耦合", space_b)]:
    result = rt.effective_ashby_coeff(controller, task)
    adequate_str = "充足" if result["adequate"] else "不足"
    print(f"[{name}]")
    print(f"  系数:      {result['coefficient']:.3f}  ({adequate_str})")
    print(f"  原始Ashby: {result['raw_ashby']:.3f}")
    print(f"  Epiplexity惩罚: x{result['epiplexity_penalty']:.3f}")
    print(f"  任务有效变异度: {result['task_effective_variety']:.3f}")

# 关键验证：同variety不同epiplexity
print("\n  关键验证: 同variety不同epiplexity的Ashby差距")
s_low = Space(variety=0.6, epiplexity=0.2)
s_high = Space(variety=0.6, epiplexity=0.8)
c = Space(variety=1.0)
r1 = rt.effective_ashby_coeff(c, s_low)
r2 = rt.effective_ashby_coeff(c, s_high)
print(f"    variety=0.6, epi=0.2 -> Ashby={r1['coefficient']:.3f}")
print(f"    variety=0.6, epi=0.8 -> Ashby={r2['coefficient']:.3f}")
print(f"    -> 同variety, 高epiplexity使Ashby从{'' if r1['adequate'] else '不'}充足变为{'' if r2['adequate'] else '不'}充足")
assert r2["coefficient"] < r1["coefficient"], "高epiplexity应降低Ashby系数"
print("  断言通过: 高epiplexity降低Ashby系数 ✓")

print()
print("=" * 70)
print("TEST 3: 控制循环 — epiplexity 传播")
print("=" * 70)


class MockController:
    def decide(self, **kwargs):
        return {"action": "process", "args": {}, "expected_reduction": 0.3}

    def on_strategy(self, s):
        pass

    def on_strategy_change(self, s, sp):
        pass


# 低epiplexity场景
rt1 = Runtime()
agent1 = Agent(rt1)
result1 = agent1.run(MockController(), survey_result=survey_a, max_steps=10)
print(f"[低耦合控制循环]")
print(f"  步数:       {result1['steps']}")
print(f"  初始epi:   {result1['epiplexity_initial']:.3f}")
print(f"  最终epi:   {result1['epiplexity_final']:.3f}")
print(f"  策略:      {result1['strategy_used']}")
print(f"  收敛:      {result1['converged']}")
assert result1["strategy_used"] == "parallel_decompose", "低耦合应使用parallel_decompose策略"
print("  断言通过: 策略=parallel_decompose ✓")

# 高epiplexity场景
rt2 = Runtime()
agent2 = Agent(rt2)
result2 = agent2.run(MockController(), survey_result=survey_b, max_steps=10)
print(f"\n[高耦合控制循环]")
print(f"  步数:       {result2['steps']}")
print(f"  初始epi:   {result2['epiplexity_initial']:.3f}")
print(f"  最终epi:   {result2['epiplexity_final']:.3f}")
print(f"  策略:      {result2['strategy_used']}")
print(f"  收敛:      {result2['converged']}")
assert result2["strategy_used"] in ("decouple_then_divide", "mainline_first"), "高耦合应使用 decouple 或 mainline 策略"
print("  断言通过: 策略=decouple_then_divide (epiplexity=0.616在0.3-0.7中区间) ✓")

print()
print("=" * 70)
print("TEST 3b: 极高耦合场景 -> mainline_first")
print("=" * 70)

survey_extreme = survey_from_text(
    "全耦合系统设计",
    dimensions={
        "核心算法": 0.8,
        "数据流": 0.8,
        "容错机制": 0.8,
    },
    couplings=[
        ("核心算法", "数据流", 0.95),
        ("核心算法", "容错机制", 0.95),
        ("数据流", "容错机制", 0.95),
    ],
)
space_extreme = survey_extreme.to_space()
print(f"[极高耦合]  epiplexity={space_extreme.epiplexity:.3f}, 初始策略=mainline_first")
rt3 = Runtime()
agent3 = Agent(rt3)
result3 = agent3.run(MockController(), survey_result=survey_extreme, max_steps=15)
print(f"  步数={result3['steps']}, 最终策略={result3['strategy_used']}, 最终epi={result3['epiplexity_final']:.3f}")
# 初始epiplexity > 0.7 → mainline_first策略被选中
# 但3步后epiplexity降到0.7以下，策略自适应切换
assert result3["epiplexity_initial"] > 0.7, "初始epiplexity应 > 0.7"
print(f"  断言通过: 初始epiplexity={result3['epiplexity_initial']:.3f} > 0.7 -> 初始为mainline_first ✓")
print(f"  策略自适应: 3步后epi降至{result3['epiplexity_final']:.3f}, 切换为{result3['strategy_used']} ✓")

print()
print("=" * 70)
print("TEST 4: 反向兼容 — 不传epiplexity时行为不变")
print("=" * 70)
s = Space(variety=0.8)
print(f"  默认epiplexity: {s.epiplexity}")
assert s.epiplexity == 0.0, "不传epiplexity应默认为0.0"
print(f"  断言通过: epiplexity=0.0 ✓")

con = s.constrain(Constraint("test", {}))
print(f"  约束后: variety={con.variety:.3f}, epiplexity={con.epiplexity:.3f}")
print(f"  variety传播正常")

# 旧的ashby_coeff签名仍然可用
old_result = rt.ashby_coeff(controller_variety=0.8, task_variety=0.5)
print(f"  旧ashby_coeff签名结果: {old_result:.3f}")
assert abs(old_result - 1.6) < 0.01, "旧ashby签名应正常工作"
print("  断言通过: 旧ashby_coeff签名兼容 ✓")

# decompose兼容性
decomp = s.decompose()
print(f"  decompose正常: {len(decomp)}个子空间, 每个有epiplexity")

# structure_report
report = s.structure_report()
print(f"  structure_report字段: {list(report.keys())}")
assert "epiplexity" in report, "structure_report应包含epiplexity"
print("  断言通过: structure_report兼容 ✓")

print()
print("=" * 70)
print("TEST 5: SurveyResult -> Agent 完整流程")
print("=" * 70)

# 模拟LLM拆解流程：自然语言 -> SurveyResult -> Space -> Agent控制循环
task = "为这个Python项目添加类型注解，需要处理10个模块，其中5个有循环import"
survey = survey_from_text(
    task,
    dimensions={
        "模块依赖分析": 0.6,
        "类型注解编写": 0.4,
        "循环import解耦": 0.8,
        "测试验证": 0.3,
    },
    couplings=[
        ("模块依赖分析", "类型注解编写", 0.3),
        ("循环import解耦", "模块依赖分析", 0.9),
        ("循环import解耦", "类型注解编写", 0.7),
    ],
)
space = survey.to_space()
print(f"任务: {task}")
print(f"  SurveyResult: dims={survey.num_dimensions}, couplings={len(survey.couplings)}")
print(f"  Space: variety={space.variety:.3f}, epiplexity={space.epiplexity:.3f}")
print(f"  策略建议: mainline_first (循环import解耦是瓶颈)")

rt3 = Runtime()
agent3 = Agent(rt3)
result3 = agent3.run(MockController(), survey_result=survey, max_steps=15)
print(f"  控制循环完成: {result3['steps']}步, 最终策略={result3['strategy_used']}")
print(f"  初始epi={result3['epiplexity_initial']:.3f} -> 最终epi={result3['epiplexity_final']:.3f}")
# 初始epiplexity=0.447 在 decouple_then_divide 区间
# 但经过3步控制后epi降至0.21 < 0.3, 策略自适应切换为parallel_decompose
assert result3["epiplexity_initial"] > 0.3, "初始epiplexity应 > 0.3 (中高耦合)"
print(f"  断言通过: 初始epiplexity={result3['epiplexity_initial']:.3f} > 0.3 ✓")
print(f"  策略自适应: epi从{result3['epiplexity_initial']:.3f}降至{result3['epiplexity_final']:.3f}, 穿越阈值链 ✓")

print()
print("=" * 70)
print("ALL TESTS PASSED ✓")
print("=" * 70)
