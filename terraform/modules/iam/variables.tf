variable "name_prefix" {
  description = "Prefix for resource naming"
  type        = string
}

variable "management_account_id" {
  description = "Hub management AWS account ID"
  type        = string
}

variable "spoke_role_name" {
  description = "Name of the spoke role to assume in target accounts"
  type        = string
  default     = "eks-operator-spoke"
}

variable "external_id" {
  description = "External ID for STS AssumeRole"
  type        = string
  sensitive   = true
}

variable "sns_topic_arn" {
  description = "ARN of the SNS topic for operations"
  type        = string
}

variable "sqs_queue_arn" {
  description = "ARN of the SQS queue"
  type        = string
}

variable "sqs_dlq_arn" {
  description = "ARN of the SQS dead letter queue"
  type        = string
}

variable "dynamodb_operations_table_arn" {
  description = "ARN of the operations DynamoDB table"
  type        = string
}

variable "dynamodb_cluster_state_table_arn" {
  description = "ARN of the cluster state DynamoDB table"
  type        = string
}

variable "dynamodb_schedules_table_arn" {
  description = "ARN of the schedules DynamoDB table"
  type        = string
}

variable "ecr_repository_arn" {
  description = "ARN of the ECR repository"
  type        = string
}

variable "common_tags" {
  description = "Common tags for resources"
  type        = map(string)
  default     = {}
}
