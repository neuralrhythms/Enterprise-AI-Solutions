<h1 align="center">Enterprise Knowledge Assistant — Azure</h1>

<p align="center">
  <em>A production-grade RAG architecture for enterprise knowledge management on Azure, powered by Azure OpenAI Service and Azure AI Search.</em>
</p>

<p align="center">
  <img alt="Azure" src="https://img.shields.io/badge/Microsoft-Azure-0078D4?style=flat-square&logo=microsoftazure&logoColor=white"/>
  <img alt="OpenAI" src="https://img.shields.io/badge/Azure-OpenAI-412991?style=flat-square&logo=openai&logoColor=white"/>
  <img alt="Status" src="https://img.shields.io/badge/Status-In%20Progress-yellow?style=flat-square"/>
</p>

---

## Overview

Enterprise knowledge is fragmented across SharePoint, Confluence, Azure Blob Storage, and operational databases — and retrieval is inconsistent, slow, and often unverifiable. Users get different answers depending on where they search, and there is no reliable way to attribute a response back to a source document. This architecture implements a production RAG (Retrieval-Augmented Generation) pipeline on Azure: Azure OpenAI Service (GPT-4o) handles answer generation, Azure AI Search drives document indexing and semantic retrieval across enterprise content sources, Azure Blob Storage holds unstructured documents, Azure API Management provides the API gateway layer, Azure Active Directory enforces identity and access control, and Azure Monitor with Application Insights provides end-to-end observability.

The architecture is designed for organisations with an existing Microsoft Azure estate looking to build knowledge assistants with enterprise security controls. Access to retrieved content is enforced using the caller's Entra ID identity, all generated responses are grounded in cited source documents, and the full retrieval and generation pipeline is observable and auditable — satisfying the control requirements of regulated deployments.

---

## Planned Architecture

Key components:

- **Azure OpenAI Service** — GPT-4o inference for answer generation, with managed deployment and content filtering
- **Azure AI Search** — document indexing, vector search, and semantic ranking across enterprise content sources
- **Azure Blob Storage** — document store for unstructured content, with tiered lifecycle management
- **Azure Functions** — orchestration layer handling retrieval, context assembly, and OpenAI invocation
- **Azure API Management** — API gateway providing rate limiting, authentication enforcement, and API versioning
- **Azure Active Directory** — identity and access control with Entra ID propagation to AI Search for document-level security
- **Azure Key Vault** — secrets management and encryption key lifecycle for all services
- **Azure Monitor + Application Insights** — distributed tracing, query latency monitoring, and alerting across the full pipeline

---

## Planned Documentation

| Document | Description |
|---|---|
| [`architecture/solution-design.md`](architecture/solution-design.md) | System context, RAG pipeline design, component interactions, ADRs, Well-Architected alignment |
| [`architecture/security-design.md`](architecture/security-design.md) | Threat model, IAM design, network controls, data classification, compliance mapping |
| [`architecture/operational-design.md`](architecture/operational-design.md) | CI/CD pipeline, index sync operations, observability, alerting, and recovery runbooks |

---

## Status

Architecture design in progress. Documentation and IaC will be published following the AWS variant.
