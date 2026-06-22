<h1 align="center">Enterprise Knowledge Assistant — AWS</h1>

<p align="center">
  <em>A production-grade RAG architecture for enterprise knowledge management on AWS, powered by Amazon Bedrock and Amazon Kendra.</em>
</p>

<p align="center">
  <img alt="AWS" src="https://img.shields.io/badge/AWS-Cloud%20Native-FF9900?style=flat-square&logo=amazonaws&logoColor=white"/>
  <img alt="Bedrock" src="https://img.shields.io/badge/Amazon-Bedrock-232F3E?style=flat-square&logo=amazonaws&logoColor=white"/>
  <img alt="Status" src="https://img.shields.io/badge/Status-In%20Progress-yellow?style=flat-square"/>
</p>

---

## Overview

Enterprise knowledge is fragmented across SharePoint, Confluence, S3, and operational databases — and retrieval is inconsistent, slow, and often unverifiable. Users get different answers depending on where they search, and there is no reliable way to attribute a response back to a source document. This architecture implements a production RAG (Retrieval-Augmented Generation) pipeline on AWS: Amazon Kendra handles enterprise search and document indexing across heterogeneous content sources, Amazon Bedrock drives answer generation using foundation models, and a secure API layer exposes the capability to consuming applications without surfacing the underlying model or index directly.

The architecture is designed for regulated industries where answer provenance, access control, and audit trails are non-negotiable. Every generated response is grounded in retrieved source documents, citations are preserved end-to-end, and access to content is enforced at the index level using the caller's identity — ensuring users can only retrieve information they are already authorised to see.

---

## Planned Architecture

Key components:

- **Amazon Kendra** — enterprise search, document indexing, and connector-based ingestion from SharePoint, S3, and Confluence
- **Amazon Bedrock** — foundation model inference for answer generation, with support for model selection and prompt management
- **Amazon S3** — document store for unstructured content, with lifecycle policies for tiered retention
- **AWS Lambda** — orchestration layer handling retrieval, context assembly, and model invocation
- **Amazon Cognito** — user authentication and identity propagation to the Kendra index for access-controlled retrieval
- **VPC + PrivateLink** — network isolation ensuring Bedrock and Kendra are not reachable over the public internet
- **Amazon CloudWatch** — observability across Lambda, Kendra query metrics, and Bedrock invocation latency
- **AWS KMS** — encryption at rest for S3, Kendra index, and DynamoDB session state

---

## Planned Documentation

| Document | Description |
|---|---|
| [`architecture/solution-design.md`](architecture/solution-design.md) | System context, RAG pipeline design, component interactions, ADRs, Well-Architected alignment |
| [`architecture/security-design.md`](architecture/security-design.md) | Threat model, IAM design, network controls, data classification, compliance mapping |
| [`architecture/operational-design.md`](architecture/operational-design.md) | CI/CD pipeline, index sync operations, observability, alerting, and recovery runbooks |

---

## Status

Architecture design in progress. Documentation and IaC will be published incrementally.
