output "function_name" {
  description = "Lambda scheduler function name"
  value       = aws_lambda_function.scheduler.function_name
}

output "function_arn" {
  description = "Lambda scheduler function ARN"
  value       = aws_lambda_function.scheduler.arn
}
