"""
CybOS 控制会话 —— 实战运行
问题：人类用大模型解决复杂、长周期、多人协作工作时需要什么样的操作系统
"""
import sys
sys.path.insert(0, '/opt/data/home/cybos')

from cybos import survey_from_text, CybosSession, Space, Calibrator

print("=" * 70)
print("CYBOS 控制会话 —— 实战运行")
print("=" * 70)

# ── 测绘 ──
survey = survey_from_text(
    "人类用大模型解决复杂、长周期、多人协作的工作时需要什么样的操作系统，主要功能点",
    dimensions={
        "长周期任务管理": "高",
        "多人协作协调": "高",
        "跨会话上下文": "高",
        "工具集成编排": "中",
        "质量与审计": "中",
        "权限与安全": "低",
    },
    couplings=[
        ("长周期任务管理", "多人协作协调", "强"),
        ("长周期任务管理", "跨会话上下文", "强"),
        ("跨会话上下文", "工具集成编排", "中"),
        ("多人协作协调", "质量与审计", "中"),
        ("多人协作协调", "工具集成编排", "中"),
        ("长周期任务管理", "质量与审计", "弱"),
    ],
)
space = survey.to_space()
print(f"\n【测绘结果】")
print(f"  维度数:     {survey.num_dimensions}")
print(f"  耦合数:     {len(survey.couplings)}")
print(f"  variety:    {survey.variety:.3f}")
print(f"  epiplexity: {survey.epiplexity:.3f}")
print(f"  有效变异度: {space.effective_variety():.3f}")
print(f"  推荐策略:   decouple_then_divide")

# ── 开始控制会话 ──
print(f"\n{'=' * 70}")
print("开始控制循环...")
session = CybosSession.begin(survey)
print(f"  初始: {session}")

# Ashby 检查
ashby = session.runtime.effective_ashby_coeff(
    Space(variety=0.85),
    session.current_space()
)
print(f"  Ashby系数: {ashby['coefficient']:.3f} ({'充足' if ashby['adequate'] else '不足'})")
print(f"    任务有效变异度: {ashby['task_effective_variety']:.3f}")

# ── 执行步骤 ──
print(f"\n{'=' * 70}")
print("执行步骤...")

steps = [
    ("search_memory", {"topic": "cybos_architecture"}, 0.3, True),
    ("framework_analysis", {"lens": "cybernetic"}, 0.4, True),
    ("detail_design", {"features": 8}, 0.4, True),
    ("compose_answer", {}, 0.3, True),
]

for i, (name, args, reduction, success) in enumerate(steps):
    con = session.constrain(name, args, expected_reduction=reduction)
    space = session.observe(con, {"status": "ok"}, exit_code=0 if success else 1)
    names = ["搜索记忆", "组织框架", "展开设计", "综合回答"]
    print(f"  步骤{i+1}: {names[i]} -> epi={space.epiplexity:.4f}")

# ── 复盘 ──
print(f"\n{'=' * 70}")
print("复盘...")
report = session.end()

print(f"\n收敛报告:")
print(f"  总步数:        {report['step_count']}")
print(f"  初始variety:   {report['survey_variety']:.3f}")
print(f"  最终variety:   {report['final_variety']:.3f}")
print(f"  初始epiplexity: {report['survey_epiplexity']:.3f}")
print(f"  最终epiplexity: {report['final_epiplexity']:.3f}")
print(f"  初始策略:      {report['strat_initial']}")
print(f"  最终策略:      {report['strategy']}")
print(f"  收敛:          {report['converged']}")
print(f"  预测误差:      {report['prediction_error']:.4f}")
print(f"  耗时:          {report['duration_ms']:.1f}ms")
print(f"\n  测绘预测 epi={report['survey_epiplexity']:.3f}")
print(f"  实际最终 epi={report['final_epiplexity']:.3f}")

# 校准
cal = Calibrator()
cal.add_record(report, task_description="操作系统需求分析")
analysis = cal.analyze()
print(f"\n  校准: 已记录 {analysis['n_records']} 条 (首条)")
