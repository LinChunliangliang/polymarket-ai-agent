# Contract: AI 概率估算 Prompt

**Branch**: 002-polymarket-ai-agent

定义系统与 DeepSeek API 交互的输入输出格式。

---

## System Prompt（固定，可缓存）

```
You are a prediction market analyst specializing in cryptocurrency markets.
Your task is to estimate the true probability of a binary prediction market resolving YES.

Guidelines:
- Base your estimate on the market question, current context, and any on-chain data provided
- Be calibrated: if you're uncertain, say so via confidence level
- Avoid anchoring to the current market price
- Return ONLY valid JSON, no explanation text outside the JSON structure
```

---

## User Prompt 结构

```json
{
  "market": {
    "question": "Will Ethereum complete the Pectra upgrade before July 1, 2026?",
    "end_date": "2026-07-01",
    "current_yes_price": 0.72,
    "volume_24h_usd": 45200
  },
  "onchain_signals": {
    "available": true,
    "tvl_change_7d_pct": -3.2,
    "github_commits_30d": 187,
    "large_transfers_24h": 12,
    "notes": "GitHub activity high; no significant TVL decline"
  },
  "context_date": "2026-06-11"
}
```

`onchain_signals.available` 为 false 时，省略其余 onchain 字段，AI 仅依据市场描述推断。

---

## 期望输出格式

```json
{
  "estimated_probability": 0.81,
  "confidence": "high",
  "reasoning_summary": "Pectra upgrade is in final testnet phase with high GitHub activity. Historical Ethereum upgrade delays averaged 3-6 weeks. High confidence the deadline will be met.",
  "key_factors": [
    "High development velocity (187 commits/30d)",
    "No major TVL outflows suggesting community confidence",
    "Upgrade announced for May, already delayed once"
  ],
  "data_gaps": []
}
```

| 字段 | 类型 | 约束 |
|------|------|------|
| `estimated_probability` | float | (0.01, 0.99)，拒绝极端值 |
| `confidence` | string | 枚举："high" / "medium" / "low" |
| `reasoning_summary` | string | 最多 200 字 |
| `key_factors` | array[string] | 2-4 条关键理由 |
| `data_gaps` | array[string] | 列出影响判断的缺失信息 |

---

## 错误处理

- 输出不是合法 JSON → 重试一次，仍失败则跳过该市场
- `estimated_probability` 超出 (0.01, 0.99) → 截断并记录警告
- `confidence` 为 "low" → 仍可生成信号，但下注额乘以 0.5 系数
