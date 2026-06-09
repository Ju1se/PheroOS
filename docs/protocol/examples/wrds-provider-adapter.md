# WRDS Provider Adapter Example

WRDS is a reference data-provider capability, not a core runtime concept. The
capability declares provider metadata through `data_sources`; runtime nodes and
tools remain capability/provider-owned.

```json
{
  "id": "wrds-financial-data",
  "capability_types": [
    "financial_fundamentals",
    "market_prices",
    "professional_financial_database"
  ],
  "required_connections": ["wrds"],
  "tools": ["wrds_status", "wrds_company_search", "wrds_company_financials"],
  "data_sources": [
    {
      "provider_id": "wrds",
      "source_kind": "professional_database",
      "dataset_kind": "financial_fundamentals",
      "normalized_result_schema": "open-multi-agent.data_source_result.v0.1",
      "license": {
        "kind": "restricted",
        "raw_data_publication": "prohibited_by_runtime_output_policy"
      },
      "adapter_entrypoint": "runtime_nodes.py:build_data_provider_descriptor",
      "provenance_policy": {
        "include_tool_name": true,
        "include_table_names": true,
        "exclude_raw_rows_from_public_results": true
      },
      "adapter_metadata": {"legacy_alias": "wrds_result"}
    }
  ],
  "entrypoints": {
    "data_provider": "runtime_nodes.py:build_data_provider_descriptor",
    "runtime_nodes": "runtime_nodes.py:build_runtime_node_descriptor"
  }
}
```

The WRDS adapter may still expose `wrds_result` for old clients. New clients
should read `data_source_results` or `provider_results`, which use the generic
`DataSourceResult` envelope.
