# Conditional Moonshot CN adapter review

Checked **2026-09-14 01:25 UTC**. This is a public-document review and an offline
design proposal. No provider API, credential, model listing, balance, token
estimation or inference request was accessed. It does not authorize or replace
the local-only next-cycle campaign.

## Verified current API facts

The CN base is `https://api.moonshot.cn/v1`; chat uses
`POST /chat/completions`. Keep this exact origin; the international `.ai`
endpoint is a different configuration. [Official API overview](https://platform.kimi.com/docs/api/overview).

| Explicit model ID | Documented context | Relevant behavior |
| --- | --- | --- |
| `kimi-k2.6` | 256K | Thinking may be disabled; its simplest short-action profile needs an explicit disabled setting. |
| `kimi-k2.7-code` / `kimi-k2.7-code-highspeed` | 256K | Thinking and preserved reasoning are always enabled. |
| `kimi-k3` | 1M | Always reasons; effort is `low`, `high` or `max`, with `max` default. |

These are explicit supported names, **not verified immutable backend revisions**.
Current docs mark K2.5 and Moonshot V1 retired on 2026-08-31, and K2 models on
2026-05-25. Several search-engine snippets still show the older catalog; the live
model page supersedes them. [Models](https://platform.kimi.com/docs/models),
[model parameters](https://platform.kimi.com/docs/api/models-overview).

Use an explicit `max_completion_tokens`; `max_tokens` is deprecated. K3 documents
a default of 131072 and maximum 1048576, still constrained by input plus output
context. K2.6/K2.7 guides document a 32768 default under the older parameter name,
but this review did not establish their independent maximum-output limits.
Do not inherit these large defaults. [Chat reference](https://platform.kimi.com/docs/api/chat),
[K2.6 guide](https://platform.kimi.com/docs/guide/kimi-k2-6-quickstart),
[K2.7 guide](https://platform.kimi.com/docs/guide/kimi-k2-7-code-quickstart).

Preserve complete raw `usage`: documented fields include `prompt_tokens`,
`completion_tokens`, `total_tokens`, and `cached_tokens`. Reasoning content is
metered and shares the output bound with final content; preserved reasoning also
costs later input tokens. No guaranteed separate numeric `reasoning_tokens` field
was established. Missing cache/reasoning breakdown stays unknown, not zero.
[Chat usage](https://platform.kimi.com/docs/api/chat),
[thinking behavior](https://platform.kimi.com/docs/guide/use-thinking-models).

Automatic prefix caching is provider-managed and can affect cost and latency
across arms. Log cache usage and predeclare request order/cache-key policy rather
than attributing provider cache effects to coordination.
[Caching](https://platform.kimi.com/docs/guide/use-context-caching-feature-of-kimi-api).

An official `POST /v1/tokenizers/estimate-token-count` accepts model/messages and
returns `data.total_tokens`. It is an **estimate**, not a documented promise of
exact equality with the eventual billing receipt. The current documentation index
links it, but direct page reads timed out; the official indexed page provides the
route and schema with an older model enum. Current K3/K2.7 support remains
unverified. [Token estimation](https://platform.kimi.com/docs/api/estimate),
[current index](https://platform.kimi.com/docs/llms.txt).

No current numeric model rate with a clear effective date/currency was recovered
from the pricing page's rendered table. Rates, currency and monetary caps remain
unset; no exchange conversion or assumed free call is justified.
[Pricing](https://platform.kimi.com/docs/pricing/chat).

## Minimal conditional design

`SessionDriver.generate` calls `count_tokens` before reservation, and Session v1
settlement requires actual prompt tokens to equal that reservation. A remote
estimate may differ. Returning the estimate as actual usage, changing historical
Session semantics, or dropping a mismatching paid receipt would be incorrect.

If a remote consumer becomes authorized, add a separately versioned external
runtime profile with **one** ledger owning prompt estimate, reserved input upper
bound, output upper bound, actual provider usage and unresolved liability. An
estimate is not itself a safe upper bound: admission needs a justified bound or
must stop. Preserve an over-bound receipt as a recorded violation. Retain the
original Session cohort and keep protocol-core unchanged.

Use explicit preflight/dispatch/settlement rather than hidden network calls inside
`count_tokens`. Meter token-estimation requests separately. A small direct HTTP
transport can issue exactly one POST, disable redirects and automatic retries,
bound response bytes/time, and retain request digest, response ID/model, raw body,
usage and finish reason. Do not automatically retry an uncertain request, reconnect
via continuation, or switch models. Unknown liability remains reserved; this
proposal makes no claim about provider-side idempotency.

Freeze all request parameters and preserve optional provider reasoning as private
raw output, never verified task evidence. JSON constraints may restrict public
syntax/target IDs equally for every arm; they must not encode answers. The
inspected Chat specification did not establish deterministic seed support, so
local seeds cannot be presented as matched remote random streams. Reproducibility
must disclose this provider limitation and any unpinned backend revision.

Offline tests can exercise differing estimated/actual usage, missing/partial
usage, malformed replies, reasoning truncation, rate limits/timeouts, byte caps,
model drift, cancellation and late settlement without any remote request. An
eventual remote arm is a separate capability/cost factor, not an unreported local
model replacement.

## Missing authorization/configuration fields

Before any provider operation, resolve the exact model and thinking profile;
outbound data scope; explicit maximum spend and currency; dispatch and token caps
(including estimation/diagnostic branches); timeout/unknown-liability stopping
rule; and authorization to depart from the local-only goal. A reasonable proposed
data scope is only these synthetic public task prompts and acquired fixture
receipts, excluding repository files, user attachments and unrelated logs. This
is a proposal for review, not presumed permission.
