output "alb_dns_name" {
  description = "ALB DNS name (API endpoint)"
  value       = module.ecs.alb_dns_name
}

output "api_base_url" {
  description = "Base URL for the API"
  value       = "http://${module.ecs.alb_dns_name}"
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = module.ecr.repository_url
}

output "sns_topic_arn" {
  description = "SNS operations topic ARN"
  value       = module.messaging.sns_topic_arn
}

output "sqs_queue_url" {
  description = "SQS tasks queue URL"
  value       = module.messaging.sqs_queue_url
}

output "sqs_dlq_url" {
  description = "SQS dead letter queue URL"
  value       = module.messaging.sqs_dlq_url
}

output "dynamodb_operations_table" {
  description = "Operations DynamoDB table name"
  value       = module.storage.operations_table_name
}

output "dynamodb_cluster_state_table" {
  description = "Cluster state DynamoDB table name"
  value       = module.storage.cluster_state_table_name
}

output "dynamodb_schedules_table" {
  description = "Schedules DynamoDB table name"
  value       = module.storage.schedules_table_name
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.ecs.cluster_name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = module.ecs.service_name
}

output "lambda_worker_function_name" {
  description = "Lambda worker function name"
  value       = module.lambda_worker.function_name
}

output "lambda_scheduler_function_name" {
  description = "Lambda scheduler function name"
  value       = module.lambda_scheduler.function_name
}

output "hub_role_arn" {
  description = "Hub IAM role ARN"
  value       = module.iam.hub_role_arn
}

output "spoke_role_trust_policy_json" {
  description = "Spoke role trust policy JSON for CloudFormation StackSets"
  value       = module.iam.spoke_role_trust_policy_json
  sensitive   = true
}

output "spoke_role_permissions_json" {
  description = "Spoke role permissions policy JSON for CloudFormation StackSets"
  value       = module.iam.spoke_role_permissions_json
  sensitive   = true
}

# --- Test Cluster Outputs ---

output "test_cluster_name" {
  description = "Test EKS cluster name"
  value       = aws_eks_cluster.test.name
}

output "test_node_group_name" {
  description = "Test cluster Managed Node Group name"
  value       = aws_eks_node_group.test.node_group_name
}

