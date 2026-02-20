output "ecs_execution_role_arn" {
  description = "ARN of the ECS task execution role"
  value       = aws_iam_role.ecs_execution_role.arn
}

output "hub_role_arn" {
  description = "ARN of the hub role for ECS tasks"
  value       = aws_iam_role.hub_role.arn
}

output "lambda_worker_role_arn" {
  description = "ARN of the Lambda worker execution role"
  value       = aws_iam_role.lambda_worker_role.arn
}

output "lambda_scheduler_role_arn" {
  description = "ARN of the Lambda scheduler execution role"
  value       = aws_iam_role.lambda_scheduler_role.arn
}

output "spoke_role_trust_policy_json" {
  description = "Trust policy JSON for the spoke role (deploy via StackSets)"
  value       = jsonencode(local.spoke_role_trust_policy)
}

output "spoke_role_permissions_json" {
  description = "Permissions policy JSON for the spoke role (deploy via StackSets)"
  value       = jsonencode(local.spoke_role_permissions)
}
