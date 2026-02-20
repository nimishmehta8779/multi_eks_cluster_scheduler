variable "name_prefix" {
  description = "Prefix for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "app_output_dir" {
  description = "Directory containing Python application files"
  type        = string
}

variable "lambda_role_arn" {
  description = "ARN of the Lambda execution role"
  type        = string
}

variable "management_account_id" {
  description = "Management AWS account ID"
  type        = string
}

variable "operator_role_name" {
  description = "Name of the spoke role"
  type        = string
}

variable "external_id" {
  description = "External ID for STS AssumeRole"
  type        = string
  sensitive   = true
}

variable "sns_topic_arn" {
  description = "SNS topic ARN"
  type        = string
}

variable "sqs_queue_url" {
  description = "SQS queue URL"
  type        = string
}

variable "dynamodb_operations_table" {
  description = "Operations DynamoDB table name"
  type        = string
}

variable "dynamodb_cluster_state_table" {
  description = "Cluster state DynamoDB table name"
  type        = string
}

variable "dynamodb_schedules_table" {
  description = "Schedules DynamoDB table name"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "target_account_ids" {
  description = "List of target account IDs"
  type        = list(string)
  default     = []
}

variable "layers" {
  description = "List of Lambda Layer ARNs"
  type        = list(string)
  default     = []
}

variable "common_tags" {
  description = "Common tags for resources"
  type        = map(string)
  default     = {}
}

variable "target_regions" {
  description = "List of target regions"
  type        = list(string)
  default     = []
}
