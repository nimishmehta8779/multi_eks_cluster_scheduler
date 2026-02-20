# --- Lambda Worker Deployment Package ---

data "archive_file" "worker" {
  type        = "zip"
  output_path = "${path.module}/lambda_worker.zip"

  source {
    content  = file("${var.app_output_dir}/operations/task_worker.py")
    filename = "task_worker.py"
  }

  source {
    content  = file("${var.app_output_dir}/operations/eks_controller.py")
    filename = "operations/eks_controller.py"
  }

  source {
    content  = file("${var.app_output_dir}/operations/__init__.py")
    filename = "operations/__init__.py"
  }

  source {
    content  = file("${var.app_output_dir}/state/state_manager.py")
    filename = "state/state_manager.py"
  }

  source {
    content  = file("${var.app_output_dir}/state/cluster_baseline.py")
    filename = "state/cluster_baseline.py"
  }

  source {
    content  = file("${var.app_output_dir}/state/__init__.py")
    filename = "state/__init__.py"
  }

  source {
    content  = file("${var.app_output_dir}/config.py")
    filename = "config.py"
  }

  source {
    content  = file("${var.app_output_dir}/json_logging.py")
    filename = "json_logging.py"
  }

  source {
    content  = file("${var.app_output_dir}/discovery.py")
    filename = "discovery.py"
  }
}

# --- CloudWatch Log Group ---

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${var.name_prefix}-worker"
  retention_in_days = var.log_retention_days
  tags              = var.common_tags
}

# --- Lambda Function ---

resource "aws_lambda_function" "worker" {
  function_name    = "${var.name_prefix}-worker"
  filename         = data.archive_file.worker.output_path
  source_code_hash = data.archive_file.worker.output_base64sha256
  handler          = "task_worker.handler"
  runtime          = "python3.12"
  timeout          = 900
  memory_size      = 256
  role             = var.lambda_role_arn
  publish          = true
  layers           = var.layers

  # reserved_concurrent_executions = var.lambda_max_concurrency

  environment {
    variables = {
      MANAGEMENT_ACCOUNT_ID        = var.management_account_id
      OPERATOR_ROLE_NAME           = var.operator_role_name
      EXTERNAL_ID                  = var.external_id
      SNS_TOPIC_ARN                = var.sns_topic_arn
      SQS_QUEUE_URL                = var.sqs_queue_url
      DYNAMODB_OPERATIONS_TABLE    = var.dynamodb_operations_table
      DYNAMODB_CLUSTER_STATE_TABLE = var.dynamodb_cluster_state_table
      DYNAMODB_SCHEDULES_TABLE     = var.dynamodb_schedules_table
      TARGET_ACCOUNT_IDS           = join(",", var.target_account_ids)
      TARGET_REGIONS               = join(",", var.target_regions)
    }
  }

  depends_on = [aws_cloudwatch_log_group.worker]

  tags = var.common_tags
}

resource "aws_cloudwatch_event_rule" "warm_worker" {
  name                = "${var.name_prefix}-worker-warm"
  description         = "Keep the worker Lambda warm"
  schedule_expression = "rate(5 minutes)"
  tags                = var.common_tags
}

resource "aws_cloudwatch_event_target" "warm_worker" {
  rule      = aws_cloudwatch_event_rule.warm_worker.name
  target_id = "warm-worker"
  arn       = aws_lambda_function.worker.arn
  input     = jsonencode({ "warm" = true })
}

resource "aws_lambda_permission" "allow_warm_eventbridge" {
  statement_id  = "AllowWarmEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.worker.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.warm_worker.arn
}

# --- SQS Event Source Mapping ---

resource "aws_lambda_event_source_mapping" "sqs" {
  event_source_arn                   = var.sqs_queue_arn
  function_name                      = aws_lambda_function.worker.arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  enabled                            = true

  function_response_types = ["ReportBatchItemFailures"]
}

# --- DLQ Alarm ---

resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${var.name_prefix}-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "DLQ has messages — indicates failed nodegroup operations"
  alarm_actions       = [var.sns_alerts_topic_arn]
  ok_actions          = [var.sns_alerts_topic_arn]

  dimensions = {
    QueueName = element(split("/", var.sqs_dlq_arn), length(split("/", var.sqs_dlq_arn)) - 1)
  }

  tags = var.common_tags
}
