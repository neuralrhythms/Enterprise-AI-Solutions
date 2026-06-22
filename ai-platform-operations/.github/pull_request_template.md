## Summary

<!-- What does this PR change and why? One paragraph is enough. -->

## Type of Change

- [ ] Infrastructure change (Terraform module or environment)
- [ ] Architecture documentation update
- [ ] Security or IAM design change
- [ ] Operational runbook or observability update
- [ ] Dependency or provider version update
- [ ] Other (describe below)

## Checklist

**Design**
- [ ] Architecture or security design document updated if this change affects system behaviour
- [ ] ADR added or updated if this is a significant architectural decision

**Infrastructure**
- [ ] `terraform plan` reviewed and output attached or linked
- [ ] No hardcoded values — all environment-specific config is in `terraform.tfvars`
- [ ] Resource naming follows the `{project}-{environment}-{resource_type}` convention
- [ ] All new resources carry the required tag set (`Project`, `Environment`, `ManagedBy`, `Owner`, `CostCentre`)

**Security**
- [ ] IAM changes reviewed for least-privilege — no wildcard resource ARNs without justification
- [ ] No secrets, credentials, or sensitive values committed
- [ ] VPC endpoint access pattern unchanged or reviewed if network topology changes

**Validation**
- [ ] `terraform validate` passes for all modified modules
- [ ] `tflint` passes with zero violations
- [ ] `checkov` scan shows no new HIGH or CRITICAL findings

## Deployment Notes

<!-- Anything the reviewer or approver needs to know before this is applied to staging or prod. Include rollback steps if the change is high-risk. -->

## Related Issues or ADRs

<!-- Link any related issues, ADRs, or design documents -->
