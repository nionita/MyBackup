import sys
import argparse
import logging
from core import platform_utils, config_loader, logging_setup

VERSION = "1.0.0"

def get_parser():
    parser = argparse.ArgumentParser(description="Backup-Tool CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run parser
    run_parser = subparsers.add_parser("run", help="Run backup jobs")
    run_parser.add_argument("--job", help="Run a specific job by name")

    # list-jobs parser
    subparsers.add_parser("list-jobs", help="List all configured jobs")

    # validate parser
    subparsers.add_parser("validate", help="Validate configuration")

    # cleanup parser
    cleanup_parser = subparsers.add_parser("cleanup", help="Run retention cleanup manually")
    cleanup_parser.add_argument("--job", help="Run cleanup for a specific job", required=True)

    # version parser
    subparsers.add_parser("version", help="Print version")
    
    # setup parser
    subparsers.add_parser("setup", help="Initial setup")

    # install-scheduler parser
    install_parser = subparsers.add_parser("install-scheduler", help="Install a background task scheduler")
    install_group = install_parser.add_mutually_exclusive_group(required=True)
    install_group.add_argument("--job", help="Job name")
    install_group.add_argument("--all", action="store_true", help="All jobs")
    install_parser.add_argument("--schedule", choices=["daily", "hourly", "weekly"], required=True)
    install_parser.add_argument("--time", help="Time (e.g. 03:00)")
    install_parser.add_argument("--interval", type=int, help="Interval in hours")
    install_parser.add_argument("--day", help="Day of week (MON-SUN)")

    # uninstall-scheduler parser
    uninstall_parser = subparsers.add_parser("uninstall-scheduler", help="Uninstall background task scheduler")
    uninstall_group = uninstall_parser.add_mutually_exclusive_group(required=True)
    uninstall_group.add_argument("--job", help="Job name")
    uninstall_group.add_argument("--all", action="store_true", help="All jobs")

    return parser

def main():
    if sys.version_info < (3, 12):
        print("ERROR: Python 3.12 or higher is required.", file=sys.stderr)
        sys.exit(1)

    parser = get_parser()
    args = parser.parse_args()

    if args.command == "version":
        print(f"Backup-Tool version {VERSION}")
        sys.exit(0)

    try:
        global_config = config_loader.load_global_config()
        logger = logging_setup.setup_logger(
            log_level=global_config.get("log_level", "INFO"),
            log_file=global_config.get("log_file"),
            max_bytes=global_config.get("log_max_bytes", 10485760),
            backup_count=global_config.get("log_backup_count", 5)
        )
    except config_loader.ConfigError as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        sys.exit(1)
        
    global_logger = logging_setup.get_job_logger("global")

    try:
        if args.command == "validate":
            jobs = config_loader.load_job_configs()
            global_logger.info(f"Loaded {len(jobs)} valid jobs.")
            print("Validation successful.")
            
        elif args.command == "list-jobs":
            jobs = config_loader.load_job_configs()
            print(f"Found {len(jobs)} jobs:")
            for j in jobs:
                print(f"- {j['name']} ({len(j['sources'])} sources, {len(j['backends'])} backends)")
                
        elif args.command == "run":
            jobs = config_loader.load_job_configs()
            if args.job:
                jobs = [j for j in jobs if j["name"] == args.job]
                if not jobs:
                    global_logger.error(f"Job '{args.job}' not found.")
                    sys.exit(1)
            
            from core import job_runner
            success_count = 0
            for job in jobs:
                if job_runner.run_job(job):
                    success_count += 1
                    
            global_logger.info(f"All jobs completed. {success_count} successful, {len(jobs) - success_count} failed.")
            if success_count < len(jobs):
                sys.exit(1)

        elif args.command == "cleanup":
            jobs = config_loader.load_job_configs()
            job = next((j for j in jobs if j["name"] == args.job), None)
            if not job:
                global_logger.error(f"Job '{args.job}' not found.")
                sys.exit(1)
                
            from core import job_runner
            job_runner.run_retention_only(job)
            
        elif args.command == "setup":
            print("Setup not fully implemented yet.")
            
        elif args.command in ["install-scheduler", "uninstall-scheduler"]:
            if not platform_utils.is_windows():
                print("Scheduler commands only supported on Windows right now (Linux uses cron).")
                sys.exit(1)
            print("Windows scheduler config not fully implemented yet.")

    except Exception as e:
        global_logger.exception("Unexpected error occurred")
        sys.exit(1)

if __name__ == "__main__":
    main()
