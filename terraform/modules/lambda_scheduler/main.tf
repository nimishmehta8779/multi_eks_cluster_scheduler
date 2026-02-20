# --- Lambda Scheduler Deployment Package ---

data "archive_file" "scheduler" {
  type        = "zip"
  output_path = "${path.module}/lambda_scheduler.zip"

  source {
    content  = file("${var.app_output_dir}/schedules/schedule_poller.py")
    filename = "schedule_poller.py"
  }

  source {
    content  = file("${var.app_output_dir}/schedules/schedule_worker.py")
    filename = "schedules/schedule_worker.py"
  }

  source {
    content  = file("${var.app_output_dir}/schedules/cron_utils.py")
    filename = "schedules/cron_utils.py"
  }

  source {
    content  = file("${var.app_output_dir}/schedules/schedule_manager.py")
    filename = "schedules/schedule_manager.py"
  }

  source {
    content  = file("${var.app_output_dir}/schedules/__init__.py")
    filename = "schedules/__init__.py"
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
    content  = file("${var.app_output_dir}/operations/operation_router.py")
    filename = "operations/operation_router.py"
  }

  source {
    content  = file("${var.app_output_dir}/operations/__init__.py")
    filename = "operations/__init__.py"
  }

  source {
    content  = file("${var.app_output_dir}/discovery.py")
    filename = "discovery.py"
  }

  source {
    content  = file("${var.app_output_dir}/config.py")
    filename = "config.py"
  }

  source {
    content  = file("${var.app_output_dir}/json_logging.py")
    filename = "json_logging.py"
  }
}

# --- CloudWatch Log Group ---

resource "aws_cloudwatch_log_group" "scheduler" {
  name              = "/aws/lambda/${var.name_prefix}-scheduler"
  retention_in_days = var.log_retention_days
  tags              = var.common_tags
}

# --- Lambda Function ---

resource "aws_lambda_function" "scheduler" {
  function_name    = "${var.name_prefix}-scheduler"
  filename         = data.archive_file.scheduler.output_path
  source_code_hash = data.archive_file.scheduler.output_base64sha256
  handler          = "schedule_poller.handler"
  runtime          = "python3.12"
  timeout          = 300
  memory_size      = 256
  role             = var.lambda_role_arn
  publish          = true
  layers           = var.layers

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

  depends_on = [aws_cloudwatch_log_group.scheduler]

  tags = var.common_tags
}

# Already kept warm by the 1-minute poller rule below

# --- EventBridge Rule (1 minute) ---

resource "aws_cloudwatch_event_rule" "every_minute" {
  name                = "${var.name_prefix}-schedule-poll"
  description         = "Trigger schedule poller every minute"
  schedule_expression = "rate(1 minute)"
  tags                = var.common_tags
}

resource "aws_cloudwatch_event_target" "scheduler_lambda" {
  rule      = aws_cloudwatch_event_rule.every_minute.name
  target_id = "scheduler-lambda"
  arn       = aws_lambda_function.scheduler.arn
  input     = "{}"
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.every_minute.arn
}
