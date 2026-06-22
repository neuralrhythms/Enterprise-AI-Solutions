<h1 align="center">Enterprise AI Solutions</h1>

<p align="center">
  <em>A collection of AWS reference architectures for designing, deploying, and operating enterprise AI systems at scale.</em>
</p>

<p align="center">
  <img alt="AWS" src="https://img.shields.io/badge/AWS-Cloud%20Native-FF9900?style=flat-square&logo=amazonaws&logoColor=white"/>
  <img alt="Terraform" src="https://img.shields.io/badge/IaC-Terraform-7B42BC?style=flat-square&logo=terraform&logoColor=white"/>
  <img alt="Well-Architected" src="https://img.shields.io/badge/AWS-Well--Architected-232F3E?style=flat-square&logo=amazonaws&logoColor=white"/>
  <img alt="License" src="https://img.shields.io/badge/License-MIT-green?style=flat-square"/>
</p>

---

## About

Each project in this repository is a self-contained reference architecture covering four dimensions: solution design, security design, operational design, and Infrastructure as Code. Every design decision is grounded in the AWS Well-Architected Framework six pillars.

These are not proof-of-concept demos. They are production-grade patterns for teams building AI platforms on AWS.

---

## Projects

| Project | Domain | Status | Cloud |
|---|---|---|---|
| [AI Platform Operations](ai-platform-operations/) | DevOps · Platform Engineering · Security · Governance | ![Status](https://img.shields.io/badge/Status-Complete-brightgreen?style=flat-square) | AWS |
| [Enterprise Knowledge Assistant — AWS](enterprise-knowledge-assistant-aws/) | Generative AI · RAG · Knowledge Management | ![Status](https://img.shields.io/badge/Status-In%20Progress-yellow?style=flat-square) | AWS |
| [Enterprise Knowledge Assistant — Azure](enterprise-knowledge-assistant-azure/) | Generative AI · RAG · Knowledge Management | ![Status](https://img.shields.io/badge/Status-In%20Progress-yellow?style=flat-square) | Azure |
| [Intelligent Document Processing](intelligent-document-processing/) | Document AI · OCR · Workflow Automation | ![Status](https://img.shields.io/badge/Status-In%20Progress-yellow?style=flat-square) | AWS |
| [Agentic Banking Assistant](agentic-banking-assistant/) | Agentic AI · Financial Services · Compliance | ![Status](https://img.shields.io/badge/Status-In%20Progress-yellow?style=flat-square) | AWS |

---

## Architecture Approach

All projects follow a consistent documentation structure: README → Solution Design → Security Design → Operational Design → Terraform IaC. This ensures that every architecture can be evaluated, reviewed, and extended using the same mental model — regardless of the domain or cloud provider.

Infrastructure is described using Terraform with four reusable modules per project: networking, compute, iam, and ai-services (or equivalent). No HCL implementation code appears in the documentation itself — module interfaces are described as input and output tables, keeping the architecture documentation readable for both engineers and architects.

All architectures align to the AWS Well-Architected Framework six pillars: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimisation, and Sustainability. Each design document includes an explicit Well-Architected alignment section that maps design decisions to the relevant pillar and justifies the trade-offs made.

---

## Repository Structure

```
Enterprise-AI-Solutions/
├── ai-platform-operations/          # Complete
│   ├── architecture/
│   ├── diagrams/
│   └── terraform/
├── enterprise-knowledge-assistant-aws/   # In progress
├── enterprise-knowledge-assistant-azure/ # In progress
├── intelligent-document-processing/      # In progress
└── agentic-banking-assistant/            # In progress
```

---

## Documentation Standards

| Document | Purpose | Audience |
|---|---|---|
| `README.md` | Platform overview, architecture summary, getting started | All technical stakeholders |
| `architecture/solution-design.md` | System context, component design, ADRs, Well-Architected alignment | AI Architects, Cloud Architects |
| `architecture/security-design.md` | Threat model, IAM design, network security, compliance controls | Security Architects, Cloud Leads |
| `architecture/operational-design.md` | CI/CD pipeline, observability, alerting, recovery runbooks | Platform Engineers, SREs |
| `terraform/README.md` | IaC structure, module interfaces, naming conventions, environment promotion | Platform Engineers |

---

## License

MIT — see individual project directories for full license text.

---

<p align="center">
  Built on the <a href="https://aws.amazon.com/architecture/well-architected/">AWS Well-Architected Framework</a>
</p>
