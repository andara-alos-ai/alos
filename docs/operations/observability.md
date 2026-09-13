# Observability

Execution material harus dapat ditelusuri melalui correlation ID, exact Agent/capability
version, environment, actor/system identity, organization/workspace/tenant scope,
provider route/model, tool decision, usage/cost, evidence, status, dan timestamp.

Log tidak boleh memuat secret, raw credential, unrestricted prompt/document content,
atau private provider error. Metric minimum mencakup run outcome/latency, model usage and
failure, tool allowed/denied, budget rejection, job health, cancellation, kill/suspend,
release/activation, dan rollback. Alert threshold dan backend sink spesifik environment
belum distandardisasi dalam v1 dan harus ditentukan melalui operations review.
