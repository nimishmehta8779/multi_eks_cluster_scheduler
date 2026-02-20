variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (e.g., prod, staging, dev)"
  type        = string
  default     = "prod"
}

variable "management_account_id" {
  description = "AWS account ID of the management/hub account"
  type        = string
}

variable "target_account_ids" {
  description = "List of target AWS account IDs (empty = use Organizations auto-discovery)"
  type        = list(string)
  default     = []
}

variable "spoke_role_name" {
  description = "Name of the IAM role to assume in spoke accounts"
  type        = string
  default     = "eks-operator-spoke"
}

variable "external_id" {
  description = "External ID for STS AssumeRole"
  type        = string
  sensitive   = true
}

variable "dynamodb_operations_table" {
  description = "Name of the operations DynamoDB table"
  type        = string
  default     = "eks-operations"
}

variable "dynamodb_cluster_state_table" {
  description = "Name of the cluster state DynamoDB table"
  type        = string
  default     = "eks-cluster-state"
}

variable "dynamodb_schedules_table" {
  description = "Name of the schedules DynamoDB table"
  type        = string
  default     = "eks-schedules"
}

variable "lambda_max_concurrency" {
  description = "Reserved concurrent executions for Lambda worker"
  type        = number
  default     = 10
}

variable "service_desired_count" {
  description = "Desired number of ECS Fargate tasks"
  type        = number
  default     = 2
}

variable "vpc_id" {
  description = "VPC ID for ECS and ALB deployment"
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

variable "app_output_dir" {
  description = "Directory where Python application files are written"
  type        = string
  default     = "../app"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "secondary_aws_region" {
  description = "Secondary AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "secondary_vpc_id" {
  description = "Secondary VPC ID for EKS deployment"
  type        = string
}

variable "secondary_public_subnet_ids" {
  description = "Secondary Public subnet IDs for EKS"
  type        = list(string)
}

variable "target_regions" {
  description = "List of AWS regions to scan for resources"
  type        = list(string)
  default     = []
}
