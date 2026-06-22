# Design Document — Enterprise AI Solutions Portfolio

## Overview

This design describes the structure, content conventions, generation approach, and correctness properties for the `Enterprise-AI-Solutions` GitHub portfolio repository. The repository is a greenfield deliverable — a structured collection of architectural documentation and Terraform scaffolding across five AI projects targeting AWS and Azure platforms. No runtime code or cloud resources are deployed; the output is entirely file-based.

---

## Architecture

The deliverable is a directory tree. The logical architecture has three layers:

```
Portfolio Root (Enterprise-AI-Solutions/)
├── Root README.md                  ← navigational index
└── [5 × Project Directories]
    ├── README.md                   ← project narrative + Mermaid diagrams
    ├── architecture/               ← three design documents
    ├── diagrams/                   ← two draw.io XML stubs
    └── terraform/                  ← scaffolding (4 modules + 1 environment)
```

### Projects

| Slug | Platform | Domain |
|---|---|---|
| `ai-platform-operations` | AWS | Shared AI platform — CI/CD, IaC governance, observability, AI lifecycle |
| `intelligent-document-processing` | AWS | Document extraction, classification, routing pipeline |
| `agentic-banking-assistant` | AWS | Autonomous multi-step banking workflow agent |
| `enterprise-knowledge-assistant-aws` | AWS | RAG-based conversational assistant |
| `enterprise-knowledge-assistant-azure` | Azure | RAG-based conversational assistant |

---

## Component Design

### 1. Root README

A single `README.md` at the repository root acts as the navigation index. It includes:
- Repository purpose and target audience
- A summary table linking to each project subdirectory
- Brief one-line description of each project

### 2. Per-Project README

Each project README follows an 8-section narrative structure:

1. **Business Problem** — Context and motivation
2. **Solution Overview** — High-level description of the approach
3. **Architecture Summary** — Key components and their relationships
4. **AWS/Azure Services** — Platform-specific service list
5. **Security Considerations** — Key security design points
6. **Cost Considerations** — Cost optimisation approach
7. **Future Enhancements** — Roadmap items
8. **Lessons Learned** — Architectural reflections

Two C4-style Mermaid diagrams are embedded inline:
- **High-Level Architecture** — System context and container view
- **Data Flow** — Primary data path through the solution

#### Mermaid Diagram Convention

All diagrams use the `graph TD` (top-down) or `flowchart TD` style, annotated with C4-inspired labels. Example pattern:

```
graph TD
    User["User\n[Person]"] -->|HTTPS| Gateway["API Gateway\n[Container]"]
    Gateway --> LLM["LLM Service\n[Container]"]
    LLM --> KB["Knowledge Base\n[Container]"]
```

### 3. Solution Design Document (`solution-design.md`)

Thirteen required sections per project:

1. Business Context
2. Functional Requirements
3. Non-Functional Requirements
4. Architecture Overview ← WAF pillar references here
5. Key Components
6. Design Decisions ← minimum two decisions with rationale
7. Trade-Offs ← minimum two trade-offs with implications
8. Future Roadmap
9. AI Security Risks and Controls
10. Observability and Alerting
11. Cost Monitoring
12. Backup Strategy
13. Disaster Recovery Considerations

**WAF Pillar Alignment** — The Architecture Overview section explicitly maps the solution against the five WAF pillars: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization.

### 4. Security Design Document (`security-design.md`)

Five required topic areas per project:

1. **Identity and Access Management** — roles, policies, RBAC, least privilege
2. **Data Protection** — encryption at rest (KMS/Key Vault), in transit (TLS), key rotation
3. **Network Security** — VPC/VNet isolation, private endpoints, security groups, WAF
4. **Threat Modelling** — STRIDE-based threat enumeration, mitigations
5. **Compliance Considerations** — relevant regulatory frameworks (e.g., SOC 2, GDPR, PCI-DSS)

AWS projects reference: AWS KMS, AWS IAM, AWS WAF, AWS GuardDuty, AWS Security Hub.  
Azure project references: Azure Key Vault, Azure AD / Entra ID, Microsoft Defender for Cloud, Microsoft Sentinel.

### 5. Operational Design Document (`operational-design.md`)

Five required topic areas per project:

1. **Monitoring and Alerting** — metrics, thresholds, alerting channels
2. **Logging Strategy** — log sources, retention, log levels, PII handling
3. **Incident Response** — runbooks, severity classification, escalation paths
4. **Change Management** — IaC workflow, branch strategy, approval gates, rollback
5. **Cost Governance** — tagging strategy, budget alerts, cost allocation

AWS projects reference: Amazon CloudWatch, AWS CloudTrail, AWS Config, AWS Cost Explorer.  
Azure project references: Azure Monitor, Azure Log Analytics, Microsoft Cost Management.

### 6. Draw.io Diagram Stubs

Each `.drawio` file is a valid XML document using the mxGraph schema. Structure:

```xml
<mxfile host="app.diagrams.net" ...>
  <diagram id="..." name="...">
    <mxGraphModel>
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- Meaningful shapes with project-relevant labels -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

Shapes use `mxCell` elements with `vertex="1"` and a `value` attribute containing a meaningful label (e.g., "API Gateway", "LLM Engine", "Knowledge Base"). Two files per project:
- `high-level-architecture.drawio` — system boundary + containers
- `data-flow.drawio` — numbered data flow steps

### 7. Terraform Scaffolding

#### Module Structure

Each of the four modules (`networking`, `compute`, `iam`, `ai-services`) contains:

- `main.tf` — structural comments describing the module's purpose and the resources that would be defined; no `resource` blocks
- `variables.tf` — variable declarations with descriptions and types; no default values that imply specific resources
- `outputs.tf` — output declarations describing what the module would export

#### Environment Structure (`environments/example/`)

- `main.tf` — four `module` blocks, one per module, with placeholder source paths and variable assignments
- `variables.tf` — variable declarations passed through to modules
- `outputs.tf` — output references from module outputs
- `terraform.tfvars` — example variable values as comments or stub string values

#### Terraform Syntax Validity

All `.tf` files use correct HCL syntax so that `terraform validate` passes. No `resource` or `provider` blocks are included in module files. The `environments/example/main.tf` references modules via relative paths (`source = "../../modules/networking"`).

#### AI Platform Operations `ai-services` Module

For `ai-platform-operations`, the `ai-services` module comments reference platform-level services: Amazon SageMaker (training jobs, endpoints), SageMaker Model Registry, SageMaker Feature Store, Amazon Bedrock (foundation model access), and MLflow for experiment tracking.

---

## Data Models

### File Inventory Model

Every project can be described by a fixed file manifest. The set of required files is identical across all five projects (path templates are project-slug-parameterised):

```
{slug}/README.md
{slug}/architecture/solution-design.md
{slug}/architecture/security-design.md
{slug}/architecture/operational-design.md
{slug}/diagrams/high-level-architecture.drawio
{slug}/diagrams/data-flow.drawio
{slug}/terraform/README.md
{slug}/terraform/modules/networking/main.tf
{slug}/terraform/modules/networking/variables.tf
{slug}/terraform/modules/networking/outputs.tf
{slug}/terraform/modules/compute/main.tf
{slug}/terraform/modules/compute/variables.tf
{slug}/terraform/modules/compute/outputs.tf
{slug}/terraform/modules/iam/main.tf
{slug}/terraform/modules/iam/variables.tf
{slug}/terraform/modules/iam/outputs.tf
{slug}/terraform/modules/ai-services/main.tf
{slug}/terraform/modules/ai-services/variables.tf
{slug}/terraform/modules/ai-services/outputs.tf
{slug}/terraform/environments/example/main.tf
{slug}/terraform/environments/example/variables.tf
{slug}/terraform/environments/example/outputs.tf
{slug}/terraform/environments/example/terraform.tfvars
```

Total: 23 files per project × 5 projects = 115 project files + 1 root README = **116 files**.

### Document Section Model

Each document type has a required section set:

| Document | Required Sections |
|---|---|
| Project README | Business Problem, Solution Overview, Architecture Summary, AWS/Azure Services, Security Considerations, Cost Considerations, Future Enhancements, Lessons Learned |
| `solution-design.md` | Business Context, Functional Requirements, Non-Functional Requirements, Architecture Overview, Key Components, Design Decisions, Trade-Offs, Future Roadmap, AI Security Risks and Controls, Observability and Alerting, Cost Monitoring, Backup Strategy, Disaster Recovery Considerations |
| `security-design.md` | Identity and Access Management, Data Protection, Network Security, Threat Modelling, Compliance Considerations |
| `operational-design.md` | Monitoring and Alerting, Logging Strategy, Incident Response, Change Management, Cost Governance |

---

## Error Handling

Since the deliverable is static file content, "error handling" means ensuring structural invariants hold:

- **Missing sections** — any document missing a required section heading is structurally incomplete; generation must include all sections
- **Invalid XML** — `.drawio` files must be well-formed XML; malformed XML renders the file unopenable in draw.io
- **Invalid HCL** — `.tf` files with syntax errors cause `terraform validate` to fail; all HCL must be syntactically valid
- **Resource blocks in modules** — any `resource` block in a module or environment `.tf` file violates the scaffolding-only constraint
- **Missing files** — any file absent from the 23-file manifest for a project is a structural gap

---

## Design Decisions

### Decision 1 — Scaffolding Only, No Resource Definitions

**Rationale:** The portfolio targets AI Architects assessing architectural thinking, not DevOps engineers auditing deployable infrastructure. Including provider configurations and resource definitions would require credential management, provider versioning, and region-specific values that add no portfolio value and introduce noise. Scaffolding demonstrates IaC literacy (module decomposition, variable contracts, output chaining) without the operational overhead.

**Trade-off:** A reviewer cannot run `terraform apply`. This is an accepted trade-off — the intent is architectural demonstration, not a deployable baseline. The `terraform validate` check still works and confirms HCL syntax correctness.

### Decision 2 — Mermaid Diagrams Embedded in Markdown Over Linked Images

**Rationale:** Mermaid diagrams render natively in GitHub Markdown without external hosting. Embedding diagrams inline means the README is fully self-contained — no broken image links, no external CDN dependency. C4-style labelling provides semantic clarity without requiring a specialised tool.

**Trade-off:** Mermaid has layout limitations compared to draw.io or Lucidchart. Complex diagrams may become cluttered. The draw.io stubs provide a richer diagramming artefact for reviewers who want to open a visual tool.

### Decision 3 — Single `example` Environment Per Project

**Rationale:** Multiple environments (dev/staging/prod) would require environment-specific variable files with realistic values, adding complexity without demonstrating additional architectural depth. A single `example` environment cleanly shows the module consumption pattern — the most valuable IaC portfolio signal.

**Trade-off:** A multi-environment setup with workspace or directory isolation is common in real deployments. Reviewers familiar with Terraform at scale may note the absence. This is documented as a known simplification.

### Decision 4 — Consistent Four-Module Decomposition Across All Projects

**Rationale:** Using the same four modules (`networking`, `compute`, `iam`, `ai-services`) across all five projects creates a recognisable pattern that reviewers can compare across projects. It also demonstrates understanding of separation of concerns in IaC design.

**Trade-off:** Real-world module decomposition would differ per project. For example, `ai-platform-operations` might have a `platform-services` module rather than `compute`. The uniform structure is a deliberate simplification for portfolio coherence.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: All Five Project Directories Exist

*For any* valid portfolio generation, the root directory SHALL contain exactly five subdirectories with slugs: `ai-platform-operations`, `intelligent-document-processing`, `agentic-banking-assistant`, `enterprise-knowledge-assistant-aws`, and `enterprise-knowledge-assistant-azure`.

**Validates: Requirements 1.1**

---

### Property 2: Consistent Top-Level Layout Across All Projects

*For any* project in the portfolio, its directory SHALL contain exactly: `README.md`, `architecture/`, `diagrams/`, and `terraform/` — no more, no less at the top level.

**Validates: Requirements 1.3, 2.1**

---

### Property 3: Complete Terraform Module File Set

*For any* project and *for any* module in `{networking, compute, iam, ai-services}`, the module directory SHALL contain exactly the files `main.tf`, `variables.tf`, and `outputs.tf`.

**Validates: Requirements 2.2, 8.1**

---

### Property 4: Complete Terraform Example Environment File Set

*For any* project, the `terraform/environments/example/` directory SHALL contain exactly the files `main.tf`, `variables.tf`, `outputs.tf`, and `terraform.tfvars`.

**Validates: Requirements 2.3**

---

### Property 5: Required README Sections Present

*For any* project README, every one of the eight required section headings SHALL appear: Business Problem, Solution Overview, Architecture Summary, AWS/Azure Services, Security Considerations, Cost Considerations, Future Enhancements, and Lessons Learned.

**Validates: Requirements 3.1**

---

### Property 6: Two Mermaid Diagrams Embedded Per README

*For any* project README, the file SHALL contain at least two fenced code blocks tagged with the `mermaid` language identifier — one for high-level architecture and one for data flow.

**Validates: Requirements 3.2, 3.3**

---

### Property 7: Platform-Appropriate Service References in README

*For any* AWS-based project README, the text SHALL contain at least one AWS service name. *For any* Azure-based project README, the text SHALL contain at least one Azure service name.

**Validates: Requirements 3.4, 3.5**

---

### Property 8: Required Solution Design Sections Present

*For any* project's `solution-design.md`, all thirteen required section headings SHALL be present: Business Context, Functional Requirements, Non-Functional Requirements, Architecture Overview, Key Components, Design Decisions, Trade-Offs, Future Roadmap, AI Security Risks and Controls, Observability and Alerting, Cost Monitoring, Backup Strategy, and Disaster Recovery Considerations.

**Validates: Requirements 4.1**

---

### Property 9: WAF Pillar References in Solution Design

*For any* project's `solution-design.md`, all five WAF pillar names SHALL appear in the document text: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization.

**Validates: Requirements 4.4, 10.1, 10.4, 10.5**

---

### Property 10: Required Security Design Sections Present

*For any* project's `security-design.md`, all five topic area headings SHALL be present: Identity and Access Management, Data Protection, Network Security, Threat Modelling, and Compliance.

**Validates: Requirements 5.1**

---

### Property 11: Platform-Appropriate Security Service References

*For any* AWS-based project's `security-design.md`, at least one of `{AWS KMS, AWS IAM, AWS WAF, AWS GuardDuty, AWS Security Hub}` SHALL appear. *For any* Azure-based project's `security-design.md`, at least one of `{Azure Key Vault, Azure AD, Azure Defender, Microsoft Sentinel}` SHALL appear.

**Validates: Requirements 5.3, 5.4**

---

### Property 12: Required Operational Design Sections Present

*For any* project's `operational-design.md`, all five topic area headings SHALL be present: Monitoring and Alerting, Logging Strategy, Incident Response, Change Management, and Cost Governance.

**Validates: Requirements 6.1**

---

### Property 13: Platform-Appropriate Operational Tooling References

*For any* AWS-based project's `operational-design.md`, at least one of `{Amazon CloudWatch, AWS CloudTrail, AWS Config, AWS Cost Explorer}` SHALL appear. *For any* Azure-based project's `operational-design.md`, at least one of `{Azure Monitor, Azure Log Analytics, Microsoft Cost Management}` SHALL appear.

**Validates: Requirements 6.2, 6.3**

---

### Property 14: Draw.io Files Exist for Every Project

*For any* project, both `diagrams/high-level-architecture.drawio` and `diagrams/data-flow.drawio` SHALL exist.

**Validates: Requirements 7.1**

---

### Property 15: Draw.io Files Are Valid XML

*For any* `.drawio` file in the portfolio, parsing it as XML SHALL succeed without errors — the file SHALL contain a root `mxfile` element with a nested `diagram` element containing an `mxGraphModel`.

**Validates: Requirements 7.2**

---

### Property 16: No Resource Blocks in Terraform Module Files

*For any* `.tf` file under any project's `terraform/modules/` directory, the file SHALL NOT contain a `resource` block (i.e., a line matching `^resource\s+"[^"]+"\s+"[^"]+"` in HCL).

**Validates: Requirements 8.2**

---

### Property 17: Example Environment Calls All Four Modules

*For any* project's `terraform/environments/example/main.tf`, the file SHALL contain four `module` blocks with names or sources referencing each of `networking`, `compute`, `iam`, and `ai-services`.

**Validates: Requirements 8.3**

---

## Testing Strategy

Given that the deliverable is static file content, the testing approach is structural verification rather than runtime execution.

### Structural / Property Tests

Property tests verify file-system invariants using a test harness that:
1. Enumerates the five project directories
2. For each project, asserts file existence against the 23-file manifest
3. For each document file, parses content and asserts required section headings are present
4. For each `.drawio` file, parses as XML and validates the mxGraph structure
5. For each `.tf` file in modules, scans for forbidden `resource` blocks

These tests correspond directly to Properties 1–17 above and can be implemented as shell scripts, Python/pytest, or any file-system traversal framework.

### Smoke Tests

- **Terraform validate**: Run `terraform init -backend=false && terraform validate` in each module directory and in `environments/example/` to confirm HCL syntax validity (Requirements 8.5).
- **Root README links**: Verify each project directory link in the root README resolves to an existing directory.

### Example-Based Unit Tests

- Verify the root README exists and contains the names of all five projects (Requirements 1.2).
- Verify each `solution-design.md` contains at least two instances of "Design Decision" subsections (Requirements 4.2).
- Verify each `solution-design.md` contains at least two instances of trade-off descriptions (Requirements 4.3).
- Verify `ai-platform-operations` README headings include CI/CD, IaC Governance, Observability, Cost Management, and AI Lifecycle Management (Requirements 9.1).
- Verify `ai-platform-operations` `solution-design.md` contains "shared platform" or equivalent language (Requirements 9.2).
- Verify `ai-platform-operations` `terraform/modules/ai-services/main.tf` contains SageMaker or Bedrock references in comments (Requirements 9.3).
