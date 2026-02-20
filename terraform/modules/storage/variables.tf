variable "name_prefix" {
  description = "Prefix for resource naming"
  type        = string
}

variable "dynamodb_operations_table" {
  description = "Name for the operations table"
  type        = string
  default     = "eks-operations"
}

variable "dynamodb_cluster_state_table" {
  description = "Name for the cluster state table"
  type        = string
  default     = "eks-cluster-state"
}

variable "dynamodb_schedules_table" {
  description = "Name for the schedules table"
  type        = string
  default     = "eks-schedules"
}

variable "common_tags" {
  description = "Common tags for resources"
  type        = map(string)
  default     = {}
}
