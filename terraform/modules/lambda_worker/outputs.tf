output "function_name" {
  description = "Lambda worker function name"
  value       = aws_lambda_function.worker.function_name
}

output "function_arn" {
  description = "Lambda worker function ARN"
  value       = aws_lambda_function.worker.arn
}
