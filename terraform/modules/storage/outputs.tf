output "operations_table_name" {
  description = "Name of the operations DynamoDB table"
  value       = aws_dynamodb_table.operations.name
}

output "operations_table_arn" {
  description = "ARN of the operations DynamoDB table"
  value       = aws_dynamodb_table.operations.arn
}

output "cluster_state_table_name" {
  description = "Name of the cluster state DynamoDB table"
  value       = aws_dynamodb_table.cluster_state.name
}

output "cluster_state_table_arn" {
  description = "ARN of the cluster state DynamoDB table"
  value       = aws_dynamodb_table.cluster_state.arn
}

output "schedules_table_name" {
  description = "Name of the schedules DynamoDB table"
  value       = aws_dynamodb_table.schedules.name
}

output "schedules_table_arn" {
  description = "ARN of the schedules DynamoDB table"
  value       = aws_dynamodb_table.schedules.arn
}
