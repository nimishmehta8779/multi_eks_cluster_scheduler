resource "aws_lambda_layer_version" "dependencies" {
  filename            = "lambda_layer/lambda_dependencies.zip"
  layer_name          = "${local.name_prefix}-dependencies"
  compatible_runtimes = ["python3.12"]

  # Force update if the zip changes
  source_code_hash = filebase64sha256("lambda_layer/lambda_dependencies.zip")
}
