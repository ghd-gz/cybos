"""验证 Phase 2.4 — 收敛控制 A)观测驱动更新 B)约束依赖"""
from cybos import *

print("=" * 70)
print("TEST A: 观测驱动更新 — variety_reduction 优先")
print("=" * 70)

rt = Runtime()
rt.start_loop(target_variety=0.05)
space = rt.poss_space()
print(f"初始: variety={space.variety:.4f}")

# 带 variety_reduction 的观测（实际收敛 0.1，但预设是 0.5）
con = rt.constrain("test", {}, expected_reduction=0.5)
obs = Observation(con.constraint_id, {"done": True}, exit_code=0, variety_reduction=0.1)
space = rt.step(con, obs)
print(f"预设0.5, 观测0.1 → variety={space.variety:.4f}")
assert abs(space.variety - 0.9) < 0.01, f"应用了观测值0.1: 1.0→{space.variety}"
# new_variety = 1.0 * (1 - 0.1) = 0.9
print("  断言通过: 从1.0降低到0.9 = 降低了10% ✓")

# 无 variety_reduction 时: fallback 到 expected_reduction
con2 = rt.constrain("test2", {}, expected_reduction=0.4)
obs2 = Observation(con2.constraint_id, {"done": True}, exit_code=0)  # 无 variety_reduction
space2 = rt.step(con2, obs2)
print(f"\n无观测值, fallback到预设0.4 → variety={space2.variety:.4f}")
# new_variety = 0.9 * (1 - 0.4) = 0.54
assert abs(space2.variety - 0.54) < 0.01
print("  断言通过: fallback到 expected_reduction ✓")

# 失败时 variety_reduction 被忽略
con3 = rt.constrain("fail_test", {}, expected_reduction=0.5)
obs3 = Observation(con3.constraint_id, {"error": "fail"}, exit_code=1, variety_reduction=0.3)
space3 = rt.step(con3, obs3)
print(f"\n失败时: exit_code=1, variety膨胀到={space3.variety:.4f}")
assert space3.variety > space2.variety  # 失败导致膨胀
print("  断言通过: 失败时variety膨胀 ✓")

trace = rt.end_loop()
print(f"\n轨迹步数: {trace.summary()['steps']}")

print()
print("=" * 70)
print("TEST B: 约束依赖 — 依赖链和依赖失败")
print("=" * 70)

rt2 = Runtime()
rt2.start_loop()

# B1: 正常依赖链
con_b1 = rt2.constrain("search", {"q": "data"}, expected_reduction=0.3)
obs_b1 = Observation(con_b1.constraint_id, {"files": ["a.py"]}, exit_code=0,
                     variety_reduction=0.2)
space_b1 = rt2.step(con_b1, obs_b1)
print(f"[正常链] search: variety={space_b1.variety:.4f}")

con_b2 = rt2.constrain("analyze", {"file": "a.py"}, expected_reduction=0.4,
                        depends_on=con_b1.constraint_id)
obs_b2 = Observation(con_b2.constraint_id, {"bugs": 3}, exit_code=0,
                     variety_reduction=0.3)
space_b2 = rt2.step(con_b2, obs_b2)
print(f"[正常链] analyze(依赖search): variety={space_b2.variety:.4f}")
assert space_b2.variety < space_b1.variety  # 依赖满足，正常收敛
print("  断言通过: 依赖满足，正常收敛 ✓")

# B2: 依赖未满足
con_b3 = rt2.constrain("patch", {"fix": "bug"}, expected_reduction=0.5,
                        depends_on="nonexistent_constraint")  # 不存在的依赖
obs_b3 = Observation(con_b3.constraint_id, {}, exit_code=0)
space_b3 = rt2.step(con_b3, obs_b3)
print(f"\n[依赖失败] patch(依赖不存在): variety={space_b3.variety:.4f}")
assert space_b3.variety > space_b2.variety  # 依赖失败→膨胀
print("  断言通过: 依赖未满足导致variety膨胀 ✓")

trace2 = rt2.end_loop()
print(f"\n轨迹步数: {trace2.summary()['steps']}")

print()
print("=" * 70)
print("TEST A+B: 集成 — CybosSession 收敛路径")
print("=" * 70)

survey = survey_from_text(
    "重构代码—搜索→分析→修改",
    dimensions={
        "找出问题": "中",
        "分析影响": "中",
        "执行修改": "中",
    },
    couplings=[
        ("找出问题", "分析影响", "强"),
        ("分析影响", "执行修改", "强"),
    ],
)
session = CybosSession.begin(survey)
print(f"测绘: epi={survey.epiplexity:.3f}")

# 链式路径：search → analyze → patch
con1 = session.constrain("search_files", {"pattern": "bug"}, 0.3)
s1 = session.observe(con1, {"files": ["x.py"]}, 0, variety_reduction=0.2)
print(f"1. search_files: variety={s1.variety:.4f}, epi={s1.epiplexity:.4f}")

con2 = session.constrain("read_file", {"files": ["x.py"]}, 0.4,
                          depends_on=con1.constraint_id)
s2 = session.observe(con2, {"bugs": ["line 42"]}, 0, variety_reduction=0.3)
print(f"2. read_file(依赖search): variety={s2.variety:.4f}, epi={s2.epiplexity:.4f}")

con3 = session.constrain("patch", {"path": "x.py", "fix": "line 42"}, 0.5,
                          depends_on=con2.constraint_id)
s3 = session.observe(con3, {"patched": True}, 0, variety_reduction=0.4)
print(f"3. patch(依赖read_file): variety={s3.variety:.4f}, epi={s3.epiplexity:.4f}")

report = session.end()
print(f"\n复盘: {report['step_count']}步, "
      f"variety {report['survey_variety']:.3f}→{report['final_variety']:.3f}, "
      f"epi {report['survey_epiplexity']:.3f}→{report['final_epiplexity']:.3f}")
assert report["step_count"] == 3
assert report["survey_variety"] > report["final_variety"]
print("断言通过: 链式收敛路径完整 ✓")

print()
print("=" * 70)
print("ALL CONVERGENCE CONTROL TESTS PASSED ✓")
print("=" * 70)
