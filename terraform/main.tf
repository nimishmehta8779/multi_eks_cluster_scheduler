terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.2"
    }
    local = {
      source  = "hashicorp/local"
      version = ">= 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

provider "aws" {
  alias  = "secondary"
  region = var.secondary_aws_region

  default_tags {
    tags = local.common_tags
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ── Messaging (SNS + SQS) ─────────────────────────────────────────

module "messaging" {
  source = "./modules/messaging"

  name_prefix = local.name_prefix
  environment = var.environment
  common_tags = local.common_tags
}

# ── Storage (DynamoDB) ─────────────────────────────────────────────

module "storage" {
  source = "./modules/storage"

  name_prefix                  = local.name_prefix
  dynamodb_operations_table    = var.dynamodb_operations_table
  dynamodb_cluster_state_table = var.dynamodb_cluster_state_table
  dynamodb_schedules_table     = var.dynamodb_schedules_table
  common_tags                  = local.common_tags
}

# ── ECR ────────────────────────────────────────────────────────────

module "ecr" {
  source = "./modules/ecr"

  name_prefix = local.name_prefix
  common_tags = local.common_tags
}

# ── IAM ────────────────────────────────────────────────────────────

module "iam" {
  source = "./modules/iam"

  name_prefix                      = local.name_prefix
  management_account_id            = var.management_account_id
  spoke_role_name                  = var.spoke_role_name
  external_id                      = var.external_id
  sns_topic_arn                    = module.messaging.sns_topic_arn
  sqs_queue_arn                    = module.messaging.sqs_queue_arn
  sqs_dlq_arn                      = module.messaging.sqs_dlq_arn
  dynamodb_operations_table_arn    = module.storage.operations_table_arn
  dynamodb_cluster_state_table_arn = module.storage.cluster_state_table_arn
  dynamodb_schedules_table_arn     = module.storage.schedules_table_arn
  ecr_repository_arn               = module.ecr.repository_arn
  common_tags                      = local.common_tags
}

# ── Docker Build + ECR Push ────────────────────────────────────────

resource "null_resource" "docker_build_push" {
  triggers = {
    app_hash = local.app_hash
    ecr_url  = module.ecr.repository_url
  }

  provisioner "local-exec" {
    command = <<-EOT
      aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${module.ecr.repository_url}
      docker build -t ${module.ecr.repository_url}:latest ${var.app_output_dir}
      docker push ${module.ecr.repository_url}:latest
    EOT
  }

  depends_on = [module.ecr]
}

# ── ECS (Fargate + ALB) ───────────────────────────────────────────

module "ecs" {
  source = "./modules/ecs"

  name_prefix                  = local.name_prefix
  environment                  = var.environment
  aws_region                   = var.aws_region
  vpc_id                       = var.vpc_id
  private_subnet_ids           = var.private_subnet_ids
  public_subnet_ids            = var.public_subnet_ids
  ecr_repository_url           = module.ecr.repository_url
  ecs_execution_role_arn       = module.iam.ecs_execution_role_arn
  hub_role_arn                 = module.iam.hub_role_arn
  management_account_id        = var.management_account_id
  operator_role_name           = var.spoke_role_name
  external_id                  = var.external_id
  sns_topic_arn                = module.messaging.sns_topic_arn
  sqs_queue_url                = module.messaging.sqs_queue_url
  dynamodb_operations_table    = module.storage.operations_table_name
  dynamodb_cluster_state_table = module.storage.cluster_state_table_name
  dynamodb_schedules_table     = module.storage.schedules_table_name
  service_desired_count        = var.service_desired_count
  log_retention_days           = var.log_retention_days
  common_tags                  = local.common_tags
  target_account_ids           = var.target_account_ids
  target_regions               = var.target_regions
  app_hash                     = local.app_hash

  depends_on = [null_resource.docker_build_push]
}

# ── Lambda Worker ──────────────────────────────────────────────────

module "lambda_worker" {
  source = "./modules/lambda_worker"

  name_prefix                  = local.name_prefix
  environment                  = var.environment
  aws_region                   = var.aws_region
  app_output_dir               = var.app_output_dir
  lambda_role_arn              = module.iam.lambda_worker_role_arn
  sqs_queue_arn                = module.messaging.sqs_queue_arn
  sqs_dlq_arn                  = module.messaging.sqs_dlq_arn
  sns_alerts_topic_arn         = module.messaging.sns_alerts_topic_arn
  management_account_id        = var.management_account_id
  operator_role_name           = var.spoke_role_name
  external_id                  = var.external_id
  sns_topic_arn                = module.messaging.sns_topic_arn
  sqs_queue_url                = module.messaging.sqs_queue_url
  dynamodb_operations_table    = module.storage.operations_table_name
  dynamodb_cluster_state_table = module.storage.cluster_state_table_name
  dynamodb_schedules_table     = module.storage.schedules_table_name
  lambda_max_concurrency       = var.lambda_max_concurrency
  log_retention_days           = var.log_retention_days
  common_tags                  = local.common_tags
  target_account_ids           = var.target_account_ids
  target_regions               = var.target_regions
  layers                       = [aws_lambda_layer_version.dependencies.arn]

  depends_on = [null_resource.docker_build_push]
}

# ── Lambda Scheduler ───────────────────────────────────────────────

module "lambda_scheduler" {
  source = "./modules/lambda_scheduler"

  name_prefix                  = local.name_prefix
  environment                  = var.environment
  aws_region                   = var.aws_region
  app_output_dir               = var.app_output_dir
  lambda_role_arn              = module.iam.lambda_scheduler_role_arn
  management_account_id        = var.management_account_id
  operator_role_name           = var.spoke_role_name
  external_id                  = var.external_id
  sns_topic_arn                = module.messaging.sns_topic_arn
  sqs_queue_url                = module.messaging.sqs_queue_url
  dynamodb_operations_table    = module.storage.operations_table_name
  dynamodb_cluster_state_table = module.storage.cluster_state_table_name
  dynamodb_schedules_table     = module.storage.schedules_table_name
  log_retention_days           = var.log_retention_days
  common_tags                  = local.common_tags
  target_account_ids           = var.target_account_ids
  target_regions               = var.target_regions
  layers                       = [aws_lambda_layer_version.dependencies.arn]

  depends_on = [null_resource.docker_build_push]
}

# ── README (generated as local_file) ──────────────────────────────

resource "local_file" "readme" {
  filename = "${path.root}/../README.md"
  content  = file("${path.module}/templates/README.md")
}
