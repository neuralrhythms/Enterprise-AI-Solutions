# Contributing to AI Platform Operations

Contributions are welcome — whether that's a refined architecture decision, an improved Terraform module interface, a tighter security control, or a clearer runbook.

---

## What This Project Accepts

This is a reference architecture, not a general-purpose library. Contributions are most valuable when they:

- Improve the correctness or completeness of the architecture across one of the four domains: DevOps, Platform Engineering, Security, or Governance
- Address a real operational gap or edge case not currently covered
- Align to or extend the AWS Well-Architected Framework coverage
- Fix errors in documentation, module interfaces, or design documents

Contributions that introduce new services or major architectural changes should begin with a discussion issue before any code or documentation is written.

---

## Getting Started

**Prerequisites**

- Terraform ≥ 1.5
- AWS CLI v2
- `tflint` (latest) with the AWS ruleset
- `checkov` (latest) for security scanning
- A Markdown linter (`markdownlint-cli` or equivalent) for documentation changes

**Repository structure**

```
ai-platform-operations/
├── architecture/          Design documents — solution, security, operational
├── diagrams/              draw.io source files
├── terraform/
│   ├── environments/      Per-environment deployment configurations
│   └── modules/           Reusable Terraform modules
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

---

## Making Changes

### Architecture and Documentation

For changes to `architecture/` documents:

1. Identify which of the four operational domains the change belongs to
2. If the change represents a significant design decision, add or update an ADR in `architecture/solution-design.md`
3. Ensure all headings follow the H1 → H2 → H3 hierarchy
4. Run a Markdown linter before raising a PR
5. No placeholder text, TODO comments, or incomplete sections in merged content

### Terraform Modules

For changes to `terraform/modules/`:

1. Do not add HCL code to documentation files — module interfaces are described as input/output tables in `terraform/README.md`
2. All new variables must have a `description` and `type`; required variables must include a `validation` block where the input domain is constrained
3. Follow the naming convention: `{project_name}-{environment}-{resource_type}[-{qualifier}]`
4. Add or update the relevant input/output table in `terraform/README.md`
5. Run `terraform validate`, `terraform fmt`, `tflint`, and `checkov` before submitting

### Environment Configurations

Changes to `terraform/environments/` must:

- Not break the module interface contract (check all required variables are still supplied)
- Include a `terraform plan` output in the PR description
- Not introduce environment-specific logic into module code — differences belong in `terraform.tfvars`

---

## Pull Request Process

1. Fork the repository and create a branch from `main`: `git checkout -b feat/your-change-description`
2. Make your changes following the guidelines above
3. Fill in the PR template completely — incomplete PRs will not be reviewed
4. Request a review from a maintainer
5. Address review feedback before the PR is merged
6. PRs require at least one approval before merging to `main`

Changes affecting security design, IAM roles, or network topology require explicit sign-off from a maintainer before apply.

---

## Raising Issues

Use GitHub Issues to:

- Report errors in architecture documentation or Terraform module interfaces
- Propose new features or significant design changes (open a discussion issue first)
- Ask questions about the reference architecture

Please include enough context for a maintainer to reproduce or understand the issue without back-and-forth. For security vulnerabilities, do not open a public issue — contact the maintainers directly.

---

## Code of Conduct

This project expects all contributors to engage professionally and constructively. Disagreements about architectural approaches are welcome and expected — they should be resolved through reasoned technical discussion, not assertion.

---

## Licence

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
