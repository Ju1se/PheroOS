# Value Investing Reference Protocol

Value investing is a reference decision protocol. Its domain labels are valid
only because the active capability declares them.

```json
{
  "id": "value-investing-research",
  "protocol": {
    "intents": ["investment_analysis", "portfolio_review", "financial_data_retrieval"],
    "required_capability_types_by_intent": {
      "investment_analysis": ["financial_fundamentals"],
      "portfolio_review": []
    },
    "targets": [
      {
        "target": "decision:formal_valuation",
        "aliases": ["target price", "investment recommendation"],
        "compatible_intents": ["investment_analysis"]
      },
      {
        "target": "decision:portfolio_review",
        "compatible_intents": ["portfolio_review"]
      }
    ],
    "candidates": [
      {"candidate": "candidate:investment:buy", "label": "Buy"},
      {"candidate": "candidate:investment:watch", "label": "Watch"},
      {"candidate": "candidate:investment:avoid", "label": "Avoid"},
      {
        "candidate": "candidate:investment:insufficient_data",
        "label": "Insufficient Data",
        "safe_fallback": true
      }
    ],
    "tool_policy": {
      "source_mode": "WRDS_ONLY",
      "source_policy_blocked_tool_targets": ["tool:web_search", "tool:provider_web_search"]
    },
    "output_policy": {
      "writer_can_create_facts": false,
      "required_caveats": ["WRDS-only preliminary view"]
    }
  }
}
```

Core quorum and writer code must not hard-code these labels. The capability
declares them, and governance can commit or reject them only within that active
protocol.
