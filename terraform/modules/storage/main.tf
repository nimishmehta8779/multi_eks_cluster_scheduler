# --- TABLE 1: eks-operations ---

resource "aws_dynamodb_table" "operations" {
  name         = var.dynamodb_operations_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "updated_at"
    type = "S"
  }

  attribute {
    name = "schedule_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  global_secondary_index {
    name            = "status-index"
    hash_key        = "status"
    range_key       = "updated_at"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "schedule-ops-index"
    hash_key        = "schedule_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  tags = var.common_tags
}

# --- TABLE 2: eks-cluster-state ---

resource "aws_dynamodb_table" "cluster_state" {
  name         = var.dynamodb_cluster_state_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "cluster_id"
  range_key    = "nodegroup_name"

  attribute {
    name = "cluster_id"
    type = "S"
  }

  attribute {
    name = "nodegroup_name"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = var.common_tags
}

# --- TABLE 3: eks-schedules ---

resource "aws_dynamodb_table" "schedules" {
  name         = var.dynamodb_schedules_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "enabled"
    type = "S"
  }

  attribute {
    name = "schedule_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  global_secondary_index {
    name            = "enabled-schedules-index"
    hash_key        = "enabled"
    range_key       = "schedule_id"
    projection_type = "ALL"
  }

  tags = var.common_tags
}
