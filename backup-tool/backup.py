import sys
import argparse
import logging
import os
from core import platform_utils, config_loader, logging_setup

VERSION = "1.1.0"

def get_parser():
    parser = argparse.ArgumentParser(
        description="Backup-Tool CLI: A native Python utility to archive and push payloads securely.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument("--config-dir", default="config", help="Absolute or relative path to the configuration directory holding 'global.json' and 'jobs/'. Defaults to 'config'.")
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run parser
    run_parser = subparsers.add_parser("run", help="Executes the archiving and backend uploading pipeline.")
    run_parser.add_argument("--job", help="Run a specific job by its name (e.g., 'webserver' for 'job_webserver.json'). If omitted, runs all enabled jobs.")
    run_parser.add_argument("--force", action="store_true", help="Create and upload a fresh backup even when sources are unchanged.")

    # list-jobs parser
    subparsers.add_parser("list-jobs", help="Discovers and lists all properly configured '.json' jobs in the config/jobs directory.")

    # validate parser
    subparsers.add_parser("validate", help="Runs standard JSON schemas constraints over all jobs to ensure nothing is broken structurally.")

    # cleanup parser
    cleanup_parser = subparsers.add_parser("cleanup", help="Manually trigger backend retention rules (deleting old backups) without creating a new archive.")
    cleanup_parser.add_argument("--job", help="Run cleanup exclusively for a specific job", required=True)

    # version parser
    subparsers.add_parser("version", help="Print the active software version of the Backup-Tool.")
    
    # setup parser
    subparsers.add_parser("setup", help="Scaffolds a fresh configuration directory (with jobs/ folders and a global.json skeleton) at your specified --config-dir.")

    # setup-gdrive parser
    setup_gd_parser = subparsers.add_parser("setup-gdrive", help="Launch a local native browser flow to authenticate Google Drive.")
    setup_gd_parser.add_argument("--port", type=int, default=8080, help="Local port for the authentication server (default 8080)")

    # install-scheduler parser
    install_parser = subparsers.add_parser("install-scheduler", help="Registers a scheduled Task/Cron background worker mapping to these configurations.")
    install_group = install_parser.add_mutually_exclusive_group(required=True)
    install_group.add_argument("--job", help="Schedule only a specific job.")
    install_group.add_argument("--all", action="store_true", help="Schedule all enabled jobs.")
    install_parser.add_argument("--schedule", choices=["daily", "hourly", "weekly"], required=True)
    install_parser.add_argument("--time", help="Target time for the daily/weekly run (e.g. 03:00)")
    install_parser.add_argument("--interval", type=int, help="Interval loop in hours (if using hourly)")
    install_parser.add_argument("--day", help="Target day of week (MON-SUN) (if using weekly)")

    # uninstall-scheduler parser
    uninstall_parser = subparsers.add_parser("uninstall-scheduler", help="Purges previously installed task schedulers.")
    uninstall_group = uninstall_parser.add_mutually_exclusive_group(required=True)
    uninstall_group.add_argument("--job", help="Uninstall scheduled constraints for a specific job.")
    uninstall_group.add_argument("--all", action="store_true", help="Uninstall all scheduler hooks.")

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
        global_config = config_loader.load_global_config(args.config_dir)
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
            jobs = config_loader.load_job_configs(args.config_dir)
            global_logger.info(f"Loaded {len(jobs)} valid jobs.")
            print("Validation successful.")
            
        elif args.command == "list-jobs":
            jobs = config_loader.load_job_configs(args.config_dir)
            print(f"Found {len(jobs)} jobs inside layout:")
            for j in jobs:
                print(f"- {j['name']} ({len(j['sources'])} sources, {len(j['backends'])} backends)")
                
        elif args.command == "run":
            creds = config_loader.load_backend_credentials(args.config_dir)
            jobs = config_loader.load_job_configs(args.config_dir)
            if args.job:
                jobs = [j for j in jobs if j["name"] == args.job]
                if not jobs:
                    global_logger.error(f"Job '{args.job}' not found.")
                    sys.exit(1)
            
            from core import job_runner
            success_count = 0
            state_dir = os.path.join(args.config_dir, "state")
            for job in jobs:
                if job_runner.run_job(job, creds, state_dir=state_dir, force=args.force):
                    success_count += 1
                    
            global_logger.info(f"All jobs completed. {success_count} successful, {len(jobs) - success_count} failed.")
            if success_count < len(jobs):
                sys.exit(1)

        elif args.command == "cleanup":
            creds = config_loader.load_backend_credentials(args.config_dir)
            jobs = config_loader.load_job_configs(args.config_dir)
            job = next((j for j in jobs if j["name"] == args.job), None)
            if not job:
                global_logger.error(f"Job '{args.job}' not found.")
                sys.exit(1)
                
            from core import job_runner
            job_runner.run_retention_only(job, creds)
            
        elif args.command == "setup":
            import os
            import json
            os.makedirs(os.path.join(args.config_dir, "jobs"), exist_ok=True)
            global_path = os.path.join(args.config_dir, "global.json")
            if not os.path.exists(global_path):
                with open(global_path, "w") as f:
                    json.dump({
                        "version": VERSION,
                        "log_level": "INFO",
                        # Ask the user internally to update this if they want it centralized
                        "log_file": "C:\\Users\\nicu\\backup\\logs\\backup.log" if platform_utils.is_windows() else "/var/log/backup.log",
                        "log_max_bytes": 10485760,
                        "log_backup_count": 5,
                        "temp_dir": None
                    }, f, indent=2)
                print(f"Created Global config locally: {global_path}")
            
            print(f"-- Setup Finished --\nYour active workspace scaffolding is mapped at: {os.path.abspath(args.config_dir)}")
            
        elif args.command == "setup-gdrive":
            import os
            import json
            from core import gdrive_auth
            
            print("\n" + "="*60)
            print("Google Drive Consumer Authentication Menu")
            print("="*60)
            
            p_client_id = input("Enter your OAuth Client ID > ").strip()
            p_client_secret = input("Enter your OAuth Client Secret > ").strip()
            
            if not p_client_id or not p_client_secret:
                print("Client ID and Client Secret are strictly required!")
                sys.exit(1)
                
            refresh_token = gdrive_auth.run_local_auth_flow(p_client_id, p_client_secret, args.port)
            
            creds_dir = os.path.join(args.config_dir, "credentials")
            os.makedirs(creds_dir, exist_ok=True)
            
            gdrive_creds_path = os.path.join(creds_dir, "google_drive.json")
            
            # Write with restricted permissions (0o600) to prevent other users from reading secrets
            creds_payload = json.dumps({
                "gd_client_id": p_client_id,
                "gd_client_secret": p_client_secret,
                "gd_refresh_token": refresh_token
            }, indent=2)
            fd = os.open(gdrive_creds_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, creds_payload.encode("utf-8"))
            finally:
                os.close(fd)
                
            print("\n" + "="*60)
            print("OAUTH SETUP COMPLETE!")
            print(f"A permanent refresh_token mapped to your Consumer Identity has been successfully generated.")
            print(f"It is securely saved alongside your Client IDs at: {gdrive_creds_path}")
            print("When defining a Job, simple add '\"backend_type\": \"google_drive\"' and it will dynamically pull these secure tokens at runtime.")
            print("="*60 + "\n")
            
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
