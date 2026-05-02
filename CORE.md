# CybOS — Cybernetic Operating System

## 基本假设

任何计算过程都可以理解为"在可能性空间中施加约束，使之收敛到目标状态"的过程。

## 三层架构

```
Layer 3  控制器层  ＝  LLM + SOUL
Layer 2  控制抽象层 ＝  Agent + Skill
Layer 1  工具接口层 ＝  Tool Call / Tool Output 协议
```

### Layer 1：工具接口层

控制器与物理世界之间的接口契约。每个控制动作（Tool Call）和观测结果（Tool Output）都携带控制论元数据，形成可追踪的控制轨迹。

### Layer 2：控制抽象层

提供控制论原语作为一等公民数据类型和系统调用：
- `Space<T>`：可能性空间的表示和操作
- 系统调用：poss_space, constrain, observe, feedback, reachable, ashby_coeff
- Agent 编排控制器的运行循环
- Skill 提供可复用的控制策略

### Layer 3：控制器层

概率性推理引擎（LLM）注入 SOUL（身份 + 认知架构），在控制抽象层提供的原语之上做出控制决策。

## 核心概念

| 概念 | 定义 | 代码映射 |
|---|---|---|
| 可能性空间 | 系统当前所有可能状态的集合 | Space<T> |
| 变异度 | 可能性空间的大小/熵 | variety: float |
| 约束 | 一个控制动作对空间的限制 | constrain(action) → Space |
| 观测 | 对系统状态的带噪声测量 | observe(target) → Obs |
| 反馈 | 误差信号注入控制回路 | feedback(error) |
| 可达性 | 目标状态是否在当前控制器的能力范围内 | reachable(target) → bool |
| 收敛 | 变异度降低到目标阈值以下 | variety < epsilon |

## 控制循环

```
while space.variety > epsilon:
    obs = observe(target)
    action = controller.decide(space, obs, skills)
    space = constrain(action)
    error = compute_error(space, target)
    feedback(error)
```

## 三阶段实施路径

| Phase | 内容 | 状态 |
|---|---|---|
| 1 | Tool Layer 标准化——带控制论元数据的工具调用协议 | ← 当前 |
| 2 | Space 原语实现 + 轻量运行时核心 | |
| 3 | Agent + SOUL 集成 | |
