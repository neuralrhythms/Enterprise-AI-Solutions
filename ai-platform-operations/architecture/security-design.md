# Security Design — AI Platform Operations

## Overview

This document defines the security architecture for the AI Platform Operations framework. It covers the threat model, IAM design, data protection, network security, compliance controls, and incident response posture.

Security is treated as a first-class architectural concern, not a post-deployment audit. Every design decision in this document is traceable to a specific threat, control objective, or compliance requirement.

---

## Threat Model

### Assets Under Protection

| Asset | Classification | Protection Objective |
|---|---|---|
| Model inference inputs (prompts) | Confidential | Prevent interception, logging beyond retention policy, and exfiltration |
| Model inference outputs | Confidential | Prevent unauthorised access and storage beyond approved destinations |
| Model weights and artefacts (S3) | Restricted | Prevent exfiltration, tampering, and unauthorised access |
| Terraform state files | Restricted | Prevent exposure of infrastructure configuration and ARNs |
| IAM credentials and role sessions | Critical | Prevent misuse for privilege escalation or lateral movement |
| CloudTrail and Config logs | Critical | Prevent tampering, deletion, or unauthorised access |

### AI-Specific Threat Model

Enterprise AI platforms face a distinct set of threats beyond standard cloud infrastructure risks. The following threats are specific to AI inference workloads and inform the controls described in this document.

**Prompt Injection:**  
An adversary crafts inputs that cause the model to ignore instructions, reveal system prompts, or perform unintended actions. Mitigations: input validation and sanitisation in the orchestrator; prompt template immutability through IAM-controlled configuration; output filtering for PII patterns.

**Model Extraction:**  
An adversary makes a large number of inference requests to reconstruct model weights or decision boundaries. Mitigations: per-consumer rate limiting in the orchestrator; CloudWatch alarm on abnormal `InvocationCount` patterns; Bedrock account-level quota enforcement.

**Data Leakage Through Inference APIs:**  
Training data or proprietary content is elicited through carefully constructed prompts. Mitigations: network isolation on SageMaker model containers (no outbound calls); Bedrock model access scoped to approved models only via IAM; audit logging of all inference requests.

**Supply Chain Risk (Container Images):**  
Compromised base images or model containers introduce malicious code into the inference path. Mitigations: Amazon ECR image scanning on push; only images from the organisation's private ECR registry are accepted by ECS task definitions; SageMaker container images are pinned to verified DLC (Deep Learning Container) digests.

**Credential Compromise:**  
A stolen or misconfigured IAM role session is used to invoke AI models at scale or exfiltrate model artefacts. Mitigations: least-privilege role design with resource-level conditions; short session durations (1 hour maximum); CloudTrail anomaly detection via Amazon GuardDuty.

### Threat Matrix

| Threat | Likelihood | Impact | Primary Control | Secondary Control |
|---|---|---|---|---|
| Prompt injection | High | Medium | Input validation in orchestrator | Output filtering |
| Model extraction via query flooding | Medium | High | Rate limiting per consumer | CloudWatch `InvocationCount` alarm |
| Data leakage through inference | Medium | High | SageMaker network isolation | Audit logging |
| Container supply chain compromise | Low | Critical | ECR image scanning | Image digest pinning |
| IAM credential theft | Medium | Critical | Least-privilege + condition keys | GuardDuty anomaly detection |
| Terraform state exfiltration | Low | High | S3 bucket access policy (IAM-only) | KMS encryption |
| CloudTrail log tampering | Low | Critical | S3 object lock (WORM) on trail bucket | Config rule: CloudTrail enabled |

---

## Identity and Access Management

### Design Principles

1. **Least privilege:** Every principal receives only the permissions required for its specific function, scoped to specific resources where possible.
2. **No wildcard resources:** IAM policies reference explicit resource ARNs or use tag-based conditions. Wildcard `*` resources are prohibited except where AWS does not support resource-level permissions.
3. **Separation of duty:** The CI/CD deployment role cannot assume runtime roles; runtime roles cannot modify IAM policies; the SageMaker execution role cannot invoke Bedrock.
4. **Traceability:** Every role name includes the project name and environment. All role creation events are recorded in CloudTrail.

### Role Design

#### ECS Task Execution Role

Trust principal: `ecs-tasks.amazonaws.com`

This role is used by the ECS agent, not the application code. It authorises ECS to pull container images from ECR, send logs to CloudWatch, and retrieve secrets from Secrets Manager before the task starts.

| Permission | Resource Scope | Justification |
|---|---|---|
| `ecr:GetAuthorizationToken` | `*` (AWS does not support resource-level) | Required for ECR authentication |
| `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` | Organisation ECR registry ARNs only | Scope to approved registries |
| `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` | Platform log group ARN pattern | Scope to platform log groups |
| `secretsmanager:GetSecretValue` | Secrets tagged `Project=ai-platform` | Tag-based condition scoping |

Condition keys: `aws:RequestedRegion` restricts all actions to the deployment region.

#### ECS Task Runtime Role

Trust principal: `ecs-tasks.amazonaws.com`

This is the role assumed by application code running inside the ECS container. It has no access to ECR or CloudWatch Logs directly — those are handled by the execution role.

| Permission | Resource Scope | Justification |
|---|---|---|
| `bedrock:InvokeModel` | Specific foundation model ARNs | Scoped to approved models; no wildcard |
| `sagemaker:InvokeEndpoint` | Specific endpoint ARNs | Scoped to platform endpoints |
| `secretsmanager:GetSecretValue` | API key secrets only | Runtime credential access |

Condition keys: `aws:ResourceTag/Project` restricts Bedrock and SageMaker invocations to resources tagged with the platform project.

#### SageMaker Execution Role

Trust principal: `sagemaker.amazonaws.com`

Used during model training, endpoint creation, and batch transform jobs.

| Permission | Resource Scope | Justification |
|---|---|---|
| `s3:GetObject`, `s3:PutObject` | Model artefact bucket + path | Scoped to model artefact prefix |
| `ecr:BatchGetImage` | DLC/custom image registry | Model container image pull |
| `logs:CreateLogStream`, `logs:PutLogEvents` | SageMaker log group | Training and endpoint logs |
| `kms:GenerateDataKey`, `kms:Decrypt` | Platform KMS key | Volume encryption for endpoint |

#### CI/CD Deployment Role

Trust principal: Cross-account STS from the tooling account, restricted to specific IAM principals in that account.

This role is assumed by the CI/CD pipeline to execute Terraform plan and apply operations. It is explicitly prohibited from assuming any runtime role.

| Permission Set | Scope | Constraint |
|---|---|---|
| ECS resource management | Platform ECS cluster and services | `aws:ResourceTag/Project` condition |
| SageMaker resource management | Platform endpoints and models | `aws:ResourceTag/Project` condition |
| VPC resource management | Platform VPC and subnets | Tag condition |
| IAM `PassRole` | Platform roles only | `iam:PassedToService` restricted to `ecs-tasks.amazonaws.com` and `sagemaker.amazonaws.com` |
| IAM role creation | Prohibited — roles are pre-created | No IAM write permissions in CI/CD role |

The CI/CD role explicitly denies `sts:AssumeRole` for runtime role ARNs, preventing the pipeline from escalating to a runtime permission set.

---

## Data Protection

### Encryption at Rest

| Data Store | Encryption | Key Management |
|---|---|---|
| Terraform state (S3) | SSE-KMS | Customer-managed KMS key, automatic rotation enabled |
| Model artefacts (S3) | SSE-KMS | Customer-managed KMS key |
| SageMaker endpoint volume | KMS | Customer-managed KMS key passed via `kms_key_arn` variable |
| CloudWatch Log Groups | KMS | Customer-managed KMS key on log group creation |
| Secrets Manager secrets | AWS-managed KMS | Default AWS-managed key (customer-managed available) |
| ECR container images | AWS-managed encryption | Default encryption, immutable tags enforced |

### Encryption in Transit

All data in transit is encrypted using TLS 1.2 minimum. TLS 1.3 is preferred where AWS service endpoints support it.

| Path | Protocol | Certificate |
|---|---|---|
| Consumer → ALB | TLS 1.2+ | ACM-managed certificate |
| ALB → ECS task | Plain HTTP/8080 (VPC-internal) | Accepted: traffic stays within VPC |
| ECS → Bedrock (VPC endpoint) | TLS 1.2+ | AWS-managed endpoint certificate |
| ECS → SageMaker Runtime (VPC endpoint) | TLS 1.2+ | AWS-managed endpoint certificate |
| CI/CD → S3 backend | TLS 1.2+ | AWS-managed |

The ALB → ECS path uses plain HTTP because all traffic is contained within the VPC private subnets and never leaves the AWS network. For organisations with compliance requirements mandating end-to-end TLS, the ECS task can be configured to serve HTTPS with an internal ACM certificate.

### Secrets Management

All credentials, API keys, and sensitive configuration values are stored in AWS Secrets Manager. The orchestrator container retrieves secrets at startup via the ECS secrets injection feature — values are passed as environment variables and are not present in task definition JSON or container logs.

Secret rotation is configured for long-lived API keys. Rotation Lambda functions are deployed separately from the platform IaC.

---

## Network Security

### VPC Design

All AI Platform workloads operate within a single VPC with two subnet tiers:

- **Public subnets** — host the Application Load Balancer and NAT gateways only. No application workloads run in public subnets.
- **Private subnets** — host ECS Fargate tasks and SageMaker VPC endpoints. No direct internet access; outbound traffic routes through NAT gateways.

### Security Group Design

| Security Group | Inbound | Outbound |
|---|---|---|
| `alb-sg` | HTTPS 443 from `0.0.0.0/0` | All traffic (to ECS tasks and VPC endpoints) |
| `ecs-tasks-sg` | TCP 8080 from `alb-sg` only | All traffic (for VPC endpoint access) |
| `vpc-endpoint-sg` | HTTPS 443 from `ecs-tasks-sg` | None (endpoints are inbound only) |

The ECS tasks security group explicitly denies all inbound traffic except from the ALB security group. This prevents any lateral movement from another workload in the same VPC.

### VPC Endpoints

VPC interface endpoints are provisioned for all AWS services accessed by platform workloads:

| Endpoint | Type | Purpose |
|---|---|---|
| `com.amazonaws.*.bedrock-runtime` | Interface | Foundation model inference API |
| `com.amazonaws.*.sagemaker.runtime` | Interface | Custom model inference |
| `com.amazonaws.*.ecr.dkr` | Interface | Container image pull |
| `com.amazonaws.*.ecr.api` | Interface | ECR API operations |
| `com.amazonaws.*.logs` | Interface | CloudWatch Logs delivery |
| `com.amazonaws.*.secretsmanager` | Interface | Secrets retrieval at startup |
| `com.amazonaws.*.s3` | Gateway | Model artefact access, state backend |

All interface endpoints are deployed into the private subnets and are associated with the `vpc-endpoint-sg` security group. Private DNS is enabled on all endpoints so that SDK calls to standard AWS hostnames resolve to endpoint ENIs automatically.

---

## Compliance Controls

### AWS-Native Controls

| Service | Control | Scope |
|---|---|---|
| AWS CloudTrail | Management and data events | All API calls in the platform account; data events on S3 state bucket and model artefact bucket |
| AWS Config | Resource configuration recording | All resource types; change history available for 7 years |
| Amazon GuardDuty | Threat detection | Account-level; ML-based anomaly detection on CloudTrail, VPC Flow Logs, and DNS logs |
| AWS Security Hub | Finding aggregation | Consolidated view of GuardDuty, Config, and Inspector findings |
| Amazon Inspector | Container vulnerability scanning | ECS task definition container images; triggered on ECR push |

### AWS Config Rules

The following Config rules are enforced in the platform account:

| Rule | Description |
|---|---|
| `REQUIRED_TAGS` | All resources must carry `Project`, `Environment`, `ManagedBy`, and `Owner` tags |
| `ENCRYPTED_VOLUMES` | EBS volumes must be encrypted |
| `S3_BUCKET_SERVER_SIDE_ENCRYPTION_ENABLED` | All S3 buckets must have SSE enabled |
| `IAM_NO_INLINE_POLICY` | IAM roles and users must not use inline policies (except where required by AWS service) |
| `VPC_FLOW_LOGS_ENABLED` | VPC Flow Logs must be enabled for all VPCs |
| `CLOUD_TRAIL_ENABLED` | CloudTrail must be active in the account |
| `SAGEMAKER_ENDPOINT_CONFIG_KMS_KEY_CONFIGURED` | SageMaker endpoints must reference a KMS key |

Non-compliant resources are surfaced as Config findings, aggregated in Security Hub, and trigger SNS notifications to the platform team.

### Service Control Policies

At the AWS Organisation level, SCPs applied to the AI Platform OU enforce the following guardrails:

- Deny creation of any IAM role with `"*"` in the `Principal` trust policy element
- Deny `s3:DeleteBucket` on the state bucket and CloudTrail bucket
- Deny `cloudtrail:StopLogging` and `cloudtrail:DeleteTrail`
- Deny EC2 instance creation in public subnets for the platform account

These SCPs cannot be overridden by account-level IAM policies, regardless of the permissions of the actor.

---

## Incident Response

### Classification

| Severity | Definition | Response SLA |
|---|---|---|
| P1 — Critical | Inference service unavailable; data breach confirmed or suspected | Acknowledge in 15 min; resolution in 1 hour |
| P2 — High | Degraded inference performance; unauthorised access detected | Acknowledge in 30 min; resolution in 4 hours |
| P3 — Medium | Non-critical component failure; compliance rule violation | Acknowledge in 2 hours; resolution in 24 hours |
| P4 — Low | Advisory findings; performance optimisation opportunities | Acknowledge in 1 business day |

### Response Playbooks

**Suspected credential compromise:**
1. Identify the affected role via CloudTrail `AssumeRole` events (filter by `sourceIPAddress` anomaly)
2. Revoke all active sessions for the role: attach an inline deny-all policy immediately
3. Notify the security team via the incident management channel
4. Review CloudTrail for any actions taken under the compromised session
5. Replace the role and re-issue credentials via the normal IaC change process
6. Remove the deny-all policy once the new role is verified

**Inference service outage (P1):**
1. Check ALB `UnhealthyHostCount` in CloudWatch — if non-zero, ECS tasks are failing
2. Check ECS service events for deployment circuit-breaker activations
3. If a recent deployment is active, rollback: force a new ECS service deployment with the previous task definition ARN
4. If no recent deployment, check ECS task logs in CloudWatch Logs Insights for exception patterns
5. Escalate to AWS Support if GuardDuty findings suggest external activity contributing to the outage

**GuardDuty high-severity finding:**
1. Findings are automatically pushed to Security Hub and trigger SNS → incident management tool
2. Review the finding detail in Security Hub (source IP, affected resource, event time)
3. If the finding is confirmed malicious: isolate the affected ECS task by modifying its security group to deny all inbound and outbound traffic
4. Collect forensic data from CloudWatch Logs before any remediation action
5. Execute the credential compromise playbook if IAM credentials are involved
