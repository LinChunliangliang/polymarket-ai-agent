# Contract: config.yaml Schema

**Branch**: 002-polymarket-ai-agent

---

## 完整配置文件示例

```yaml
# Polymarket AI Agent Configuration

polymarket:
  private_key: "0x..."          # Polygon 钱包私钥（环境变量 POLY_PRIVATE_KEY 优先）
  api_key: ""                   # 由 private_key 自动派生，留空即可
  chain_id: 137                 # Polygon mainnet；沙盒用 80002

deepseek:
  api_key: "sk-..."             # DeepSeek API Key（环境变量 DEEPSEEK_API_KEY 优先）
  model: "deepseek-chat"        # V4-Flash（低成本）；可改 "deepseek-reasoner" 提升准确性

onchain:
  defillama_base_url: "https://api.defillama.com"
  github_token: ""              # 可选，有则 30 req/min，无则 10 req/min
  etherscan_api_key: ""         # 可选，有则 5 req/s，无则 1 req/s

risk:
  starting_balance_usd: 500     # 起始资金
  max_position_pct: 0.06        # 单笔最大下注比例（6%）
  daily_loss_limit_usd: 75      # 每日最大亏损
  min_bet_usd: 5                # 最小下注金额
  deviation_threshold: 0.08     # 触发信号的最小偏差
  min_liquidity_multiple: 3.0   # 市场流动性须为下注额的 N 倍
  kelly_fraction: 0.25          # 分数 Kelly 系数

scanning:
  ai_scan_interval_min: 60      # AI 全量扫描间隔
  price_check_interval_min: 10  # 快速价格检查间隔
  max_markets_per_ai_scan: 50   # 每次 AI 扫描的最大市场数（按流动性排序取前 N）
  categories: ["crypto"]        # 只分析加密类市场

logging:
  level: "INFO"                 # DEBUG / INFO / WARNING
  file: "logs/agent.log"        # 日志文件路径
  max_size_mb: 50               # 单文件最大大小
  backup_count: 7               # 保留最近 N 个日志文件
```

---

## 敏感字段优先级

私钥和 API Key 支持三种方式（优先级从高到低）：
1. 环境变量：`POLY_PRIVATE_KEY`、`DEEPSEEK_API_KEY`
2. config.yaml 中直接填写
3. 首次启动时交互式输入并加密存储

**安全要求**: `config.yaml` 不得提交到版本控制（已加入 `.gitignore`）
