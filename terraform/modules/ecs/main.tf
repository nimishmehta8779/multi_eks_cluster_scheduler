# --- CloudWatch Log Group ---

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/eks-operator-${var.environment}"
  retention_in_days = var.log_retention_days
  tags              = var.common_tags
}

# --- ALB Security Group ---

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb-sg"
  description = "Security group for ALB"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-alb-sg"
  })
}

# --- ECS Security Group ---

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.name_prefix}-ecs-sg"
  description = "Security group for ECS Fargate tasks"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Allow traffic from ALB"
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-ecs-sg"
  })
}

# --- ALB ---

resource "aws_lb" "main" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  tags = var.common_tags
}

resource "aws_lb_target_group" "app" {
  name        = "${var.name_prefix}-tg"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/health"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 10
    matcher             = "200"
  }

  tags = var.common_tags
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }

  tags = var.common_tags
}

# --- ECS Cluster ---

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = var.common_tags
}

resource "aws_ecs_cluster_capacity_providers" "fargate" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# --- ECS Task Definition ---

resource "aws_ecs_task_definition" "app" {
  family                   = var.name_prefix
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = var.ecs_execution_role_arn
  task_role_arn            = var.hub_role_arn

  container_definitions = jsonencode([
    {
      name      = var.name_prefix
      image     = "${var.ecr_repository_url}:latest"
      essential = true

      portMappings = [
        {
          containerPort = 8080
          hostPort      = 8080
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "MANAGEMENT_ACCOUNT_ID", value = var.management_account_id },
        { name = "OPERATOR_ROLE_NAME", value = var.operator_role_name },
        { name = "EXTERNAL_ID", value = var.external_id },
        { name = "SNS_TOPIC_ARN", value = var.sns_topic_arn },
        { name = "SQS_QUEUE_URL", value = var.sqs_queue_url },
        { name = "DYNAMODB_OPERATIONS_TABLE", value = var.dynamodb_operations_table },
        { name = "DYNAMODB_CLUSTER_STATE_TABLE", value = var.dynamodb_cluster_state_table },
        { name = "DYNAMODB_SCHEDULES_TABLE", value = var.dynamodb_schedules_table },
        { name = "AWS_DEFAULT_REGION", value = var.aws_region },
        { name = "MAX_DISCOVERY_WORKERS", value = tostring(var.max_discovery_workers) },
        { name = "LAMBDA_MAX_CONCURRENCY", value = tostring(var.lambda_max_concurrency) },
        { name = "TARGET_ACCOUNT_IDS", value = join(",", var.target_account_ids) },
        { name = "TARGET_REGIONS", value = join(",", var.target_regions) },
        { name = "IMAGE_HASH", value = var.app_hash },
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
        interval    = 30
        timeout     = 10
        retries     = 3
        startPeriod = 5
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])

  tags = var.common_tags
}

# --- ECS Service ---

resource "aws_ecs_service" "app" {
  name            = var.name_prefix
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.service_desired_count
  launch_type     = "FARGATE"

  enable_execute_command = true

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = var.name_prefix
    container_port   = 8080
  }

  depends_on = [aws_lb_listener.http]

  tags = var.common_tags
}
