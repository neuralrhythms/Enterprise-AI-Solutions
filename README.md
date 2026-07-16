<h1 align="center">Enterprise AI Solutions</h1>

<p align="center">
  <em>A progressive series of AI systems — from transparent local pipelines to production-grade cloud deployments.</em>
</p>

<p align="center">
  <img alt="AWS" src="https://img.shields.io/badge/AWS-Cloud%20Native-FF9900?style=flat-square&logo=amazonaws&logoColor=white"/>
  <img alt="Azure" src="https://img.shields.io/badge/Azure-Cloud%20Native-0078D4?style=flat-square&logo=microsoftazure&logoColor=white"/>
  <img alt="Terraform" src="https://img.shields.io/badge/IaC-Terraform-7B42BC?style=flat-square&logo=terraform&logoColor=white"/>
  <img alt="License" src="https://img.shields.io/badge/License-MIT-green?style=flat-square"/>
</p>

---

## About

These projects are built with incremental learning in mind. Each one introduces new layers of complexity — starting from simple, fully transparent AI systems that run locally, and progressing toward enterprise-grade architectures deployable on AWS, Azure, or across both.

The goal is to build solid conceptual foundations at every step. Rather than jumping straight to managed services and abstractions, each project exposes the mechanics underneath: how retrieval works, how infrastructure is composed, how security and governance are applied at scale. Solutions are designed to run locally for development and exploration, and to scale to cloud when production patterns are needed.

---

## Projects

| Project | Domain | Status | Deployment |
|---|---|---|---|
| [Simple RAG Demo](simple-rag-demo/) | Generative AI · RAG · Local LLM | ![Status](https://img.shields.io/badge/Status-Complete-brightgreen?style=flat-square) | Local |
| [AI Platform Operations](ai-platform-operations/) | DevOps · Platform Engineering · Security · Governance | ![Status](https://img.shields.io/badge/Status-Complete-brightgreen?style=flat-square) | AWS |

---

## Repository Structure

```
Enterprise-AI-Solutions/
├── simple-rag-demo/            # Local RAG pipeline — LangChain, FAISS, Ollama, Streamlit
└── ai-platform-operations/     # AWS operational framework — Terraform, Bedrock, SageMaker
```

---

## License

MIT — see individual project directories for full license text.
