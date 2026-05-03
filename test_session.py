"""CybOS Phase 2 — CybosSession 端到端验证（模拟Hermes使用流程）"""
from cybos import *

print("=" * 70)
print("场景：为旧项目添加类型注解（模拟来福实际使用流程）")
print("=" * 70)

# ── Step 1: 测绘 ──
print("\n【Step 1: 测绘】")
print("  任务: 为Python项目加类型注解，10个模块，5个有循环import")

survey = survey_from_text(
    "为Python项目添加类型注解，其中5个有循环import",
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
print(f"  dimensions: {survey.num_dimensions}")
print(f"  couplings:  {len(survey.couplings)}")
print(f"  variety:    {survey.variety:.3f}")
print(f"  epiplexity: {survey.epiplexity:.3f}")
print(f"  策略建议:   {CybosSession._epi_to_strat(survey.epiplexity)}")

# ── Step 2: 开始控制会话 ──
print("\n【Step 2: 开始控制会话】")
session = CybosSession.begin(survey)
print(f"  初始Space: variety={session.current_space().variety:.3f}, "
      f"epi={session.current_space().epiplexity:.3f}")
print(f"  推荐策略:  {session.current_strategy()}")
print(f"  Ashby检查: {session.runtime.effective_ashby_coeff(Space(variety=1.0), session.current_space())['coefficient']:.3f}")

assert session.survey.epiplexity > 0.3, "中高耦合任务"
assert session.current_strategy() in ("decouple_then_divide", "mainline_first")
print("  断言通过: 测绘正确 ✓")

# ── Step 3: 执行工具调用（模拟） ──
print("\n【Step 3: 执行控制动作】")

# 动作1: 分析模块依赖（工具调用前的约束记录）
con1 = session.constrain("analyze_deps", {"scope": "all"}, expected_reduction=0.4)
print(f"  动作1: analyze_deps (constraint_id={con1.constraint_id[:12]}...)")
space1 = session.observe(con1, data={"deps": "5 modules with circular import"}, exit_code=0)
print(f"  结果: variety={space1.variety:.3f}, epi={space1.epiplexity:.3f}")

# 动作2: 解决循环import
con2 = session.constrain("refactor_imports", {"modules": ["mod_a", "mod_b"]}, expected_reduction=0.5)
print(f"  动作2: refactor_imports (constraint_id={con2.constraint_id[:12]}...)")
space2 = session.observe(con2, data={"circular_imports_resolved": 3}, exit_code=0)
print(f"  结果: variety={space2.variety:.3f}, epi={space2.epiplexity:.3f}")

# 动作3: 编写类型注解
con3 = session.constrain("add_type_hints", {"files": ["mod_a.py", "mod_b.py"]}, expected_reduction=0.3)
print(f"  动作3: add_type_hints (constraint_id={con3.constraint_id[:12]}...)")
space3 = session.observe(con3, data={"files_updated": 2, "hints_added": 47}, exit_code=0)
print(f"  结果: variety={space3.variety:.3f}, epi={space3.epiplexity:.3f}")

print(f"\n  执行后: {session}")

# ── Step 4: 复盘 ──
print("\n【Step 4: 复盘】")
report = session.end()

print(f"  步数:        {report['step_count']}")
print(f"  初始epi:     {report['survey_epiplexity']:.3f}")
print(f"  最终epi:     {report['final_epiplexity']:.3f}")
print(f"  初始策略:    {report['strat_initial']}")
print(f"  最终策略:    {report['strategy']}")
print(f"  收敛:        {report['converged']}")
print(f"  预测误差:    {report['prediction_error']:.4f}")

assert report["step_count"] == 3, "应执行3步"
assert report["survey_epiplexity"] > report["final_epiplexity"], "epi应降低"
print("  断言通过: 3步完成，epiplexity降低 ✓")

print()
print("=" * 70)
print("验证：低耦合场景 — 预测误差应小")
print("=" * 70)

survey_simple = survey_from_text(
    "给三个文件分别加注释",
    dimensions={"文件A": "中", "文件B": "中", "文件C": "中"},
    # 无耦合
)
session2 = CybosSession.begin(survey_simple)
c1 = session2.constrain("add_comment", {"file": "a.py"}, expected_reduction=0.3)
session2.observe(c1, {"done": True})
c2 = session2.constrain("add_comment", {"file": "b.py"}, expected_reduction=0.3)
session2.observe(c2, {"done": True})
c3 = session2.constrain("add_comment", {"file": "c.py"}, expected_reduction=0.3)
session2.observe(c3, {"done": True})
report2 = session2.end()
print(f"  预测epi: {report2['survey_epiplexity']:.3f}")
print(f"  实际最终epi: {report2['final_epiplexity']:.3f}")
print(f"  预测误差: {report2['prediction_error']:.4f}")

print()
print("=" * 70)
print("验证：epiplexity高 → 应降低慢（需更多步）")
print("=" * 70)

# 3步控制后，高耦合场景的epi下降幅度 vs 低耦合
high_drop = report["survey_epiplexity"] - report["final_epiplexity"]
low_drop = report2["survey_epiplexity"] - report2["final_epiplexity"]
print(f"  高耦合: epi下降 {high_drop:.3f} (3步)")
print(f"  低耦合: epi下降 {low_drop:.3f} (3步)")
assert high_drop < 0.5, "高耦合3步不应降太多"
print("  断言通过: 高耦合epi下降受限 ✓")

print()
print("=" * 70)
print("CybosSession 测试全部通过 ✓")
print("=" * 70)
