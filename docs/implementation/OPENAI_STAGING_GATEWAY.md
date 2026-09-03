# OpenAI Staging Gateway

## Boundary

ALOS sends model traffic to OpenAI only through the shared Model Gateway. The
adapter sends one stateless Responses API request with `store=false`, a bounded
`max_output_tokens`, a server-generated correlation ID, and no provider-hosted
tools. ALOS, not the provider, performs source retrieval, permission checks,
budget reservation, audit writing, lifecycle transitions, approval, kill
switch, and rollback.

## VPS staging configuration

Set these values only in the VPS secret environment. Do not commit them and do
not place them in frontend variables:

```env
ALOS_ENVIRONMENT=staging
ALOS_LLM_PROVIDER=openai
ALOS_LLM_API_KEY=<project-key-kept-on-vps>
ALOS_LLM_MODEL=gpt-5.6-luna
ALOS_LLM_MODEL_LIGHT=gpt-5.6-luna
ALOS_LLM_MODEL_STANDARD=gpt-5.6-terra
ALOS_LLM_MODEL_CRITICAL=gpt-5.6-sol
ALOS_LLM_STORE_RESPONSES=false
ALOS_LLM_REASONING_EFFORT=low
ALOS_LLM_MAX_OUTPUT_TOKENS=1200
ALOS_LLM_MAX_RETRIES=1
```

`model_route` is stored in an Agent Contract as `light`, `standard`, or
`critical`; raw model names are resolved only from VPS configuration. The
current validation agents use `light`. A later Contract version and human
review are required to change a route.

## Controlled validation sequence

1. Create a dedicated OpenAI project key and a separate VPS staging database.
2. Apply migrations and start the API with staging-only secrets.
3. Run exactly one public, no-tool smoke request:

   ```powershell
   $env:PYTHONPATH = "$PWD\services\platform\src"
   & .\.venv\Scripts\python.exe -m alos.openai_smoke
   ```

4. Check the local ALOS audit, Agent Run, and usage endpoints. Do not send
   business documents or activate an agent at this point.
5. Execute the synthetic validation matrix, including provider failure,
   malformed output, budget cap, blocked tool, kill switch, and rollback.
6. Submit only a passing DRAFT through the normal human review lifecycle.

## Rollback

Set `ALOS_LLM_PROVIDER=disabled` to stop provider traffic, or restore
`ALOS_LLM_PROVIDER=gemini` only for local/test. The Agent Runtime will refuse
the unsupported provider state rather than bypassing its guardrails.
