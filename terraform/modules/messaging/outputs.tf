output "sns_topic_arn" {
  description = "ARN of the operations SNS topic"
  value       = aws_sns_topic.operations.arn
}

output "sqs_queue_arn" {
  description = "ARN of the tasks SQS queue"
  value       = aws_sqs_queue.tasks.arn
}

output "sqs_queue_url" {
  description = "URL of the tasks SQS queue"
  value       = aws_sqs_queue.tasks.url
}

output "sqs_dlq_arn" {
  description = "ARN of the tasks SQS dead letter queue"
  value       = aws_sqs_queue.dlq.arn
}

output "sqs_dlq_url" {
  description = "URL of the tasks SQS dead letter queue"
  value       = aws_sqs_queue.dlq.url
}

output "sns_alerts_topic_arn" {
  description = "ARN of the alerts SNS topic"
  value       = aws_sns_topic.alerts.arn
}
