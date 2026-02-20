data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# --- ECS Task Execution Role ---

resource "aws_iam_role" "ecs_execution_role" {
  name = "${var.name_prefix}-ecs-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# --- Hub Task Role (ECS Task + Lambda shared permissions) ---

resource "aws_iam_role" "hub_role" {
  name = "${var.name_prefix}-hub"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      },
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_policy" "hub_managed" {
  name        = "${var.name_prefix}-hub-managed-policy"
  description = "Shared permissions for ECS tasks and Lambda workers"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AssumeSpoke"
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = "arn:aws:iam::*:role/${var.spoke_role_name}"
        Condition = {
          StringEquals = {
            "sts:ExternalId" = var.external_id
          }
        }
      },
      {
        Sid    = "Organizations"
        Effect = "Allow"
        Action = [
          "organizations:ListAccounts",
          "organizations:DescribeAccount"
        ]
        Resource = "*"
      },
      {
        Sid      = "SNS"
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = var.sns_topic_arn
      },
      {
        Sid    = "SQS"
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = [
          var.sqs_queue_arn,
          var.sqs_dlq_arn
        ]
      },
      {
        Sid    = "DynamoDB"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:BatchWriteItem",
          "dynamodb:DeleteItem",
          "dynamodb:Scan"
        ]
        Resource = [
          var.dynamodb_operations_table_arn,
          "${var.dynamodb_operations_table_arn}/index/*",
          var.dynamodb_cluster_state_table_arn,
          "${var.dynamodb_cluster_state_table_arn}/index/*",
          var.dynamodb_schedules_table_arn,
          "${var.dynamodb_schedules_table_arn}/index/*"
        ]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Sid    = "ECR"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = [
          var.ecr_repository_arn,
          "*"
        ]
      },
      {
        Sid    = "KMS"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = "*"
      },
      {
        Sid    = "Scheduler"
        Effect = "Allow"
        Action = [
          "scheduler:CreateSchedule",
          "scheduler:DeleteSchedule",
          "scheduler:UpdateSchedule"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "hub_role_attachment" {
  role       = aws_iam_role.hub_role.name
  policy_arn = aws_iam_policy.hub_managed.arn
}

# --- Lambda Worker Execution Role ---

resource "aws_iam_role" "lambda_worker_role" {
  name = "${var.name_prefix}-lambda-worker"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "lambda_worker_hub" {
  role       = aws_iam_role.lambda_worker_role.name
  policy_arn = aws_iam_policy.hub_managed.arn
}

# Removed redundant hub permissions (managed policy covers it)

# --- Lambda Scheduler Execution Role ---

resource "aws_iam_role" "lambda_scheduler_role" {
  name = "${var.name_prefix}-lambda-scheduler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "lambda_scheduler_policy" {
  name = "${var.name_prefix}-lambda-scheduler-policy"
  role = aws_iam_role.lambda_scheduler_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AssumeSpoke"
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = "arn:aws:iam::*:role/${var.spoke_role_name}"
        Condition = {
          StringEquals = {
            "sts:ExternalId" = var.external_id
          }
        }
      },
      {
        Sid    = "Organizations"
        Effect = "Allow"
        Action = [
          "organizations:ListAccounts",
          "organizations:DescribeAccount"
        ]
        Resource = "*"
      },
      {
        Sid      = "SNS"
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = var.sns_topic_arn
      },
      {
        Sid    = "DynamoDB"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:BatchWriteItem",
          "dynamodb:DeleteItem",
          "dynamodb:Scan"
        ]
        Resource = [
          var.dynamodb_operations_table_arn,
          "${var.dynamodb_operations_table_arn}/index/*",
          var.dynamodb_cluster_state_table_arn,
          "${var.dynamodb_cluster_state_table_arn}/index/*",
          var.dynamodb_schedules_table_arn,
          "${var.dynamodb_schedules_table_arn}/index/*"
        ]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Sid    = "SQS"
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = var.sqs_queue_arn
      }
    ]
  })
}
