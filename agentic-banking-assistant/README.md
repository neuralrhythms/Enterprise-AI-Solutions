<h1 align="center">Agentic Banking Assistant</h1>

<p align="center">
  <em>An AWS reference architecture for a multi-agent AI system serving retail banking use cases — balance enquiries, transaction analysis, and financial product guidance.</em>
</p>

<p align="center">
  <img alt="AWS" src="https://img.shields.io/badge/AWS-Cloud%20Native-FF9900?style=flat-square&logo=amazonaws&logoColor=white"/>
  <img alt="Bedrock" src="https://img.shields.io/badge/Amazon-Bedrock%20Agents-232F3E?style=flat-square&logo=amazonaws&logoColor=white"/>
  <img alt="Status" src="https://img.shields.io/badge/Status-In%20Progress-yellow?style=flat-square"/>
</p>

---

## Overview

Retail banking customers expect instant, accurate, and contextual responses across a growing range of financial queries — but building reliable AI assistants in a regulated environment requires more than a conversational interface. This architecture implements a multi-agent system using Amazon Bedrock Agents: a supervisor agent handles intent classification and task routing, while specialist sub-agents manage domain-specific tasks including account services, transaction analysis, and financial product guidance. All agent actions are grounded in customer data retrieved via secure API integrations, and no agent can take an action outside the scope of its defined action group.

The architecture is built for financial services compliance from the ground up. All agent actions and tool invocations are logged to AWS CloudTrail, PII is handled through a dedicated data classification layer using Amazon Macie, and the design satisfies the control requirements of regulated AI deployments including DORA operational resilience obligations, FCA AI principles, and internal model risk governance frameworks. The multi-agent pattern also supports human-in-the-loop escalation for queries that exceed the confidence threshold of any specialist agent.

---

## Planned Architecture

Key components:

- **Amazon Bedrock Agents** — multi-agent orchestration with a supervisor agent and domain-specialist sub-agents for account services, transaction analysis, and product guidance
- **Amazon Bedrock Knowledge Bases** — product catalogue and policy document retrieval, grounding agent responses in verified source content
- **AWS Lambda** — action groups executing tool calls for core banking API integration, balance retrieval, and transaction queries
- **Amazon DynamoDB** — session state management for multi-turn conversations and agent context persistence
- **Amazon API Gateway** — secure API layer exposing the assistant endpoint to web and mobile channels
- **Amazon Cognito** — customer identity and authentication, propagating verified identity to downstream action groups
- **AWS CloudTrail** — immutable audit log of all agent actions, tool invocations, and data access events
- **AWS KMS + Amazon Macie** — encryption at rest and in transit, with automated PII discovery and classification across data stores

---

## Planned Documentation

| Document | Description |
|---|---|
| [`architecture/solution-design.md`](architecture/solution-design.md) | System context, multi-agent design, action group definitions, ADRs, Well-Architected alignment |
| [`architecture/security-design.md`](architecture/security-design.md) | Threat model, IAM design, PII handling, agent guardrails, regulatory compliance mapping |
| [`architecture/operational-design.md`](architecture/operational-design.md) | CI/CD pipeline, agent monitoring, escalation handling, and incident response runbooks |

---

## Status

Architecture design in progress. This project will be published following the knowledge assistant series.
