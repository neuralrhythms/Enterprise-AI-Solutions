# Terraform — AI Platform Operations

This directory contains the Infrastructure as Code for the AI Platform Operations framework. All infrastructure is managed through Terraform. No manual console changes are permitted in staging or production environments.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Terraform | ≥ 1.5 |
| AWS Provider | ≥ 5.0 |
| AWS CLI | ≥ 2.x (for credential configuration) |
| tflint | Latest (for pre-commit static analysis) |
| checkov | Latest (for security scanning) |

---

## Directory Structure

```
terraform/
├── environments/
│   ├── dev/                  Low-cost configuration for development
│   │   ├── main.tf           Module calls and provider configuration
│   │   ├── variables.tf      Variable declarations
│   │   ├── outputs.tf        Aggregated outputs
│   │   └── terraform.tfvars  Concrete values for dev environment
│   ├── staging/              Production-equivalent sizing, approval gates
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── terraform.tfvars
│   └── prod/                 Full HA, deletion protection, all alarms active
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       └── terraform.tfvars
└── modules/
    ├── networking/            VPC, subnets, NAT gateways, VPC endpoints
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── compute/               ECS Fargate, ALB, auto scaling
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── iam/                   IAM roles and policies, least-privilege design
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    └── ai-services/           SageMaker endpoints, CloudWatch observability
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

---

## Remote State Backend

All environments use an S3 remote backend with DynamoDB state locking. This configuration must be bootstrapped before the first `terraform init`.

**S3 bucket:** `ai-platform-terraform-state-<account-id>`  
**DynamoDB table:** `ai-platform-terraform-locks`  
**Encryption:** SSE-KMS with customer-managed key

State file layout:
```
s3://ai-platform-terraform-state-<account-id>/
  ai-platform-operations/
    dev/terraform.tfstate
    staging/terraform.tfstate
    prod/terraform.tfstate
```

Each environment has an isolated state file. A failure in one environment's state cannot block operations in another.

**Bootstrapping:** The S3 bucket and DynamoDB table are created via a minimal Terraform configuration in `bootstrap/`. This is the only configuration that uses local state and is applied once per account.

---

## Environment Promotion Model

Environments are separate directory trees, not Terraform workspaces. Each environment directory has its own backend configuration and `terraform.tfvars` file with environment-specific values. This makes environment differences explicit in code review and eliminates workspace-level state isolation issues.

| Environment | Purpose | Notable Differences |
|---|---|---|
| `dev` | Feature development and integration testing | Single NAT gateway, smaller ECS tasks, no deletion protection |
| `staging` | Pre-production validation, performance testing | Production-equivalent sizing, approval gate before apply |
| `prod` | Live inference traffic | Full HA (2× NAT GW), all alarms active, ALB deletion protection, longer log retention |

Module source references use relative paths within the repository:

```
source = "../../modules/networking"
```

For organisations publishing modules to a private Terraform registry, module sources are updated to registry references with pinned version constraints (e.g., `version = "~> 1.2"`) before reaching production.

---

## Module Reference

### networking

**Responsibility:** VPC, public and private subnets across multiple AZs, internet gateway, NAT gateways, route tables, and VPC interface/gateway endpoints for all AWS services used by the platform.

**Input variables:**

| Variable | Type | Default | Description |
|---|---|---|---|
| `project_name` | string | — | Resource name prefix |
| `environment` | string | — | Deployment stage: dev, staging, prod |
| `vpc_cidr` | string | `10.0.0.0/16` | VPC CIDR block |
| `public_subnet_cidrs` | list(string) | `["10.0.1.0/24","10.0.2.0/24"]` | Public subnet CIDRs, one per AZ |
| `private_subnet_cidrs` | list(string) | `["10.0.11.0/24","10.0.12.0/24"]` | Private subnet CIDRs, one per AZ |
| `availability_zones` | list(string) | — | AZ names to deploy into |
| `enable_nat_gateway` | bool | `true` | Whether to create NAT gateways |
| `single_nat_gateway` | bool | `false` | Share one NAT GW (cost trade-off for non-prod) |

**Outputs:**

| Output | Type | Description |
|---|---|---|
| `vpc_id` | string | ID of the VPC |
| `public_subnet_ids` | list(string) | IDs of all public subnets |
| `private_subnet_ids` | list(string) | IDs of all private subnets |
| `nat_gateway_ids` | list(string) | IDs of NAT gateways |
| `vpc_cidr_block` | string | VPC CIDR for security group rules |

---

### compute

**Responsibility:** ECS Fargate cluster, task definition, ECS service with rolling deployment, Application Load Balancer, security groups, and target tracking auto scaling.

**Input variables:**

| Variable | Type | Default | Description |
|---|---|---|---|
| `project_name` | string | — | Resource name prefix |
| `environment` | string | — | Deployment stage |
| `vpc_id` | string | — | VPC ID from networking module |
| `private_subnet_ids` | list(string) | — | Subnets for ECS tasks |
| `public_subnet_ids` | list(string) | — | Subnets for the ALB |
| `container_image` | string | — | ECR image URI for the inference orchestrator |
| `container_port` | number | `8080` | Port exposed by the container |
| `desired_count` | number | `2` | Initial ECS task count |
| `task_cpu` | number | `1024` | vCPU units (1024 = 1 vCPU) |
| `task_memory` | number | `2048` | Memory in MiB |
| `ecs_task_execution_role_arn` | string | — | ECS execution role ARN (from iam module) |
| `ecs_task_role_arn` | string | — | ECS task runtime role ARN (from iam module) |
| `min_capacity` | number | `2` | Minimum task count for Auto Scaling |
| `max_capacity` | number | `20` | Maximum task count for Auto Scaling |
| `scale_up_threshold` | number | `1000` | ALB requests per target triggering scale-out |

**Outputs:**

| Output | Type | Description |
|---|---|---|
| `ecs_cluster_arn` | string | ARN of the ECS cluster |
| `ecs_service_name` | string | Name of the ECS service |
| `alb_dns_name` | string | DNS name of the Application Load Balancer |
| `alb_arn` | string | ARN of the ALB |
| `ecs_security_group_id` | string | Security group ID of ECS tasks |

---

### iam

**Responsibility:** All IAM roles and policies for the platform. No other module creates IAM resources. Centralising IAM in one module makes privilege escalation paths auditable in a single location.

**Input variables:**

| Variable | Type | Default | Description |
|---|---|---|---|
| `project_name` | string | — | Resource name prefix |
| `environment` | string | — | Deployment stage |
| `bedrock_model_arns` | list(string) | — | Bedrock model ARNs the runtime may invoke |
| `sagemaker_endpoint_arns` | list(string) | — | SageMaker endpoint ARNs the runtime may invoke |
| `cicd_trusted_account_id` | string | — | AWS account ID trusted for CI/CD role assumption |

**Outputs:**

| Output | Type | Description |
|---|---|---|
| `ecs_task_execution_role_arn` | string | Allows ECS agent to pull images and write logs |
| `ecs_task_role_arn` | string | Runtime permissions: Bedrock + SageMaker access |
| `sagemaker_execution_role_arn` | string | SageMaker model training and endpoint execution |
| `cicd_deployment_role_arn` | string | Cross-account Terraform deployment permissions |

---

### ai-services

**Responsibility:** SageMaker model resource, endpoint configuration, and real-time inference endpoint. CloudWatch log groups and metric alarms for AI inference observability.

**Input variables:**

| Variable | Type | Default | Description |
|---|---|---|---|
| `project_name` | string | — | Resource name prefix |
| `environment` | string | — | Deployment stage |
| `execution_role_arn` | string | — | SageMaker execution role ARN (from iam module) |
| `model_data_url` | string | — | S3 URI for model artefacts (.tar.gz) |
| `container_image` | string | — | ECR/DLC image URI for the model container |
| `instance_type` | string | `ml.g5.2xlarge` | SageMaker instance type |
| `initial_instance_count` | number | `1` | Instances behind the endpoint |
| `log_retention_days` | number | `30` | CloudWatch log retention for inference logs |
| `kms_key_arn` | string | `""` | KMS key ARN for SageMaker volume encryption |

**Outputs:**

| Output | Type | Description |
|---|---|---|
| `sagemaker_endpoint_name` | string | Name of the SageMaker real-time endpoint |
| `sagemaker_endpoint_arn` | string | ARN of the SageMaker endpoint |
| `cloudwatch_log_group_name` | string | CloudWatch log group for inference logs |
| `sagemaker_model_name` | string | Name of the SageMaker model resource |

---

## Naming Convention

All resources follow the pattern: `{project_name}-{environment}-{resource_type}[-{qualifier}]`

| Example | Resource |
|---|---|
| `ai-platform-prod-vpc` | VPC |
| `ai-platform-prod-private-subnet-0` | First private subnet |
| `ai-platform-prod-ecs-cluster` | ECS cluster |
| `ai-platform-prod-ecs-task-runtime-role` | ECS task IAM role |
| `ai-platform-prod-sagemaker-endpoint` | SageMaker endpoint |

The qualifier is used for multi-instance resources (e.g., `subnet-0`, `subnet-1` for multi-AZ subnets).

---

## Tagging Strategy

All resources carry a mandatory tag set enforced via AWS Config rule `REQUIRED_TAGS`. Resources missing required tags are flagged as non-compliant.

| Tag Key | Value | Purpose |
|---|---|---|
| `Project` | `ai-platform` | Cost allocation and resource grouping |
| `Environment` | `dev` / `staging` / `prod` | Environment segmentation |
| `ManagedBy` | `Terraform` | Identify IaC-managed resources |
| `Owner` | `platform-team` | Ownership contact |
| `CostCentre` | `<cost-centre-id>` | Finance chargeback |
| `DataClassification` | `internal` / `confidential` | Data handling requirements |
