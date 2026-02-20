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

variable "vpc_id" {
  description = "VPC ID for ECS deployment"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Fargate tasks"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for ALB"
  type        = list(string)
}

variable "ecr_repository_url" {
  description = "ECR repository URL"
  type        = string
}

variable "ecs_execution_role_arn" {
  description = "ARN of the ECS task execution role"
  type        = string
}

variable "hub_role_arn" {
  description = "ARN of the hub role for ECS tasks"
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

variable "max_discovery_workers" {
  description = "Max parallel discovery workers"
  type        = number
  default     = 10
}

variable "lambda_max_concurrency" {
  description = "Lambda max concurrency"
  type        = number
  default     = 10
}

variable "service_desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 2
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "app_hash" {
  description = "Hash of the application code"
  type        = string
  default     = ""
}

variable "target_account_ids" {
  description = "List of target account IDs"
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
