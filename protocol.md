# CybOS Layer 1 协议规范 v0.1

## 概述

本协议定义控制器（Layer 3）与工具接口层（Layer 1）之间的契约。任何实现 CybOS 的系统都应当遵循此协议进行工具调用和观测。

## 控制动作（Tool Call）

控制器向世界施加约束的请求。

```
{
  "type": "tool_call",
  "name": "<工具名称>",
  "args": { <工具参数> },
  "control": {
    "constraint_id": "<uuid>",         // 控制轨迹追踪ID
    "from_space": "<space_id>",        // 调用的起点空间
    "expected_variety_reduction": 0.0, // 控制器预期能缩小多少变异度
    "sequence": 1                      // 本次控制循环中的第几个动作
  }
}
```

### constraint_id 生成规则

格式：`{session_id}:{sequence}`

- session_id：同一控制循环的持续会话标识
- sequence：单调递增，从1开始

### 命名惯例

工具名称应当反映其对可能性空间的影响：

- `read_*` / `observe_*`：观测型工具，不改变空间
- `write_*` / `create_*`：约束型工具，缩小空间
- `exec_*` / `run_*`：变换型工具，将空间映射到新区域

## 观测结果（Tool Output）

世界对控制动作的响应。

```
{
  "type": "tool_output",
  "control": {
    "constraint_id": "<uuid>",           // 对应哪个控制动作
    "execution_ms": 123,                 // 执行耗时
    "exit_code": 0                       // 0=成功，非0=控制失败
  },
  "observation": { <工具返回数据> },
  "state_signature": "<hash>"           // 执行后状态的指纹
}
```

### state_signature 生成规则

对 `observation` 内容做语义敏感哈希（Semantic Hash），用于后续变异度计算和变化检测。相同结果返回相同签名。

算法（初始版本）：
1. 将 observation 序列化为 JSON（key排序）
2. SHA256 取前16字符

## 错误语义

| exit_code | 含义 | 控制论解释 |
|---|---|---|
| 0 | 成功 | 约束正常施加 |
| 1 | 参数错误 | 控制动作格式不正确 |
| 2 | 资源不存在 | 目标状态不可达 |
| 3 | 超时 | 控制动作超出时限 |
| 4 | 变异度溢出 | 工具无法处理当前输入（Ashby违规） |
| 5+ | 系统错误 | 确定性内核异常 |

## 控制轨迹（Control Trace）

同一 session_id 下所有 constraint_id 的有序集合构成一条**控制轨迹**。

一条轨迹记录了：
- 从初始状态到目标状态的全部控制动作序列
- 每一步的变异度变化
- 每一步的误差信号
- 最终收敛结果

轨迹可被序列化、存档、回放——这是 CybOS "状态空间即内存" 理念的基础设施。
