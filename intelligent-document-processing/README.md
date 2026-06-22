<h1 align="center">Intelligent Document Processing</h1>

<p align="center">
  <em>An AWS reference architecture for automating document extraction, classification, and workflow routing using Amazon Textract and Amazon Comprehend.</em>
</p>

<p align="center">
  <img alt="AWS" src="https://img.shields.io/badge/AWS-Cloud%20Native-FF9900?style=flat-square&logo=amazonaws&logoColor=white"/>
  <img alt="Status" src="https://img.shields.io/badge/Status-In%20Progress-yellow?style=flat-square"/>
</p>

---

## Overview

Organisations process thousands of documents daily — invoices, contracts, forms, compliance reports — through manual review or brittle rule-based systems that break under volume and variation. This architecture automates the full document lifecycle: ingestion, classification, extraction, validation, and downstream routing. Built on Amazon Textract for OCR and structured field extraction, Amazon Comprehend for NLP-based classification and named entity recognition, AWS Step Functions for workflow orchestration, and Amazon S3 for document storage with lifecycle policies, the pipeline handles both synchronous and asynchronous document processing at scale.

The architecture is designed for financial services, insurance, and public sector organisations where accuracy, auditability, and integration with downstream systems are critical. Every document processing event is traceable end-to-end, extracted fields are validated against configurable business rules before routing, and the system is built to handle variable document quality and format without requiring manual intervention for each exception.

---

## Planned Architecture

Key components:

- **Amazon S3** — document ingestion bucket with event-driven triggers and lifecycle policies for tiered retention
- **Amazon Textract** — OCR, form extraction, and table detection for structured and semi-structured documents
- **Amazon Comprehend** — document classification, named entity recognition, and PII detection
- **AWS Step Functions** — end-to-end workflow orchestration covering extraction, validation, exception handling, and routing
- **Amazon DynamoDB** — processing state store for tracking document status and extracted field data
- **AWS Lambda** — transformation functions for field normalisation, validation logic, and downstream integration calls
- **Amazon SNS / SQS** — event-driven routing for downstream system notifications and exception queues
- **Amazon CloudWatch** — pipeline observability, processing latency metrics, and extraction accuracy tracking
- **AWS KMS** — encryption at rest for S3 document buckets, DynamoDB tables, and SQS queues

---

## Planned Documentation

| Document | Description |
|---|---|
| [`architecture/solution-design.md`](architecture/solution-design.md) | System context, processing pipeline design, component interactions, ADRs, Well-Architected alignment |
| [`architecture/security-design.md`](architecture/security-design.md) | Threat model, IAM design, PII handling, data classification, compliance mapping |
| [`architecture/operational-design.md`](architecture/operational-design.md) | CI/CD pipeline, pipeline monitoring, alerting thresholds, and exception handling runbooks |

---

## Status

Architecture design in progress.
