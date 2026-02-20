# --- SNS Topic ---

resource "aws_sns_topic" "operations" {
  name              = "eks-operations-${var.environment}"
  kms_master_key_id = "alias/aws/sns"
  tags              = var.common_tags
}

# --- SQS Dead Letter Queue ---

resource "aws_sqs_queue" "dlq" {
  name                      = "eks-cluster-tasks-dlq-${var.environment}"
  message_retention_seconds = 1209600 # 14 days
  kms_master_key_id         = "alias/aws/sqs"
  tags                      = var.common_tags
}

# --- SQS Queue ---

resource "aws_sqs_queue" "tasks" {
  name                       = "eks-cluster-tasks-${var.environment}"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 86400 # 1 day
  receive_wait_time_seconds  = 20    # long polling
  kms_master_key_id          = "alias/aws/sqs"

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })

  tags = var.common_tags
}

# --- SQS Queue Policy (allow SNS to send messages) ---

resource "aws_sqs_queue_policy" "tasks_policy" {
  queue_url = aws_sqs_queue.tasks.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowSNSPublish"
        Effect    = "Allow"
        Principal = { Service = "sns.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.tasks.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_sns_topic.operations.arn
          }
        }
      }
    ]
  })
}

# --- SNS Subscription (SNS → SQS) ---

resource "aws_sns_topic_subscription" "sqs" {
  topic_arn            = aws_sns_topic.operations.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.tasks.arn
  raw_message_delivery = false # keep SNS envelope
}

# --- SNS Alerts Topic (for DLQ alarms) ---

resource "aws_sns_topic" "alerts" {
  name = "eks-alerts-${var.environment}"
  tags = var.common_tags
}
