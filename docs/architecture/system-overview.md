# System Overview

ALOS is an enterprise operating platform. GENESIS is its governed AI control
plane and Agent Factory.

High-level flow:

Requirement -> Factory -> Agent Contract -> Test/Eval -> Release Governance ->
Agent Runtime -> ModelGateway / ToolExecutor -> Evidence/Audit.

PydanticAI is a runtime engine component behind the ALOS-owned runtime boundary.
It is not the platform control plane.
