locals {
  name_prefix = "${var.environment}-eks-operator"

  common_tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
    Project     = "eks-operator"
  }

  app_hash = sha256(join("", [
    filesha256("${var.app_output_dir}/main.py"),
    filesha256("${var.app_output_dir}/config.py"),
    filesha256("${var.app_output_dir}/discovery.py"),
    filesha256("${var.app_output_dir}/json_logging.py"),
    filesha256("${var.app_output_dir}/requirements.txt"),
    filesha256("${var.app_output_dir}/Dockerfile"),
    filesha256("${var.app_output_dir}/state/state_manager.py"),
    filesha256("${var.app_output_dir}/state/cluster_baseline.py"),
    filesha256("${var.app_output_dir}/operations/eks_controller.py"),
    filesha256("${var.app_output_dir}/operations/operation_router.py"),
    filesha256("${var.app_output_dir}/operations/task_worker.py"),
    filesha256("${var.app_output_dir}/schedules/cron_utils.py"),
    filesha256("${var.app_output_dir}/schedules/schedule_manager.py"),
    filesha256("${var.app_output_dir}/schedules/schedule_poller.py"),
    filesha256("${var.app_output_dir}/schedules/schedule_worker.py"),
  ]))
}
