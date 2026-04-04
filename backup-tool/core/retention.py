import logging

def run_retention(backend, logger: logging.LoggerAdapter, job_name: str, retention_count: int):
    """Lists backups from the backend and deletes the oldest ones exceeding retention_count."""
    # Prefix typically used is the job name
    prefix = f"{job_name}/"
    try:
        backups = backend.list_backups(prefix)
    except Exception as e:
        logger.error(f"[{backend.__class__.__name__}] Failed to list backups for retention: {e}")
        return

    # Sort backups by LastModified date (oldest first)
    backups.sort(key=lambda x: x["last_modified"])
    
    if len(backups) <= retention_count:
        logger.info(f"[{backend.__class__.__name__}] Retention: {len(backups)} backups exist, keeping all.")
        return
        
    to_delete = backups[:-retention_count]
    deleted_count = 0
    for b in to_delete:
        try:
            backend.delete_backup(b["key"])
            deleted_count += 1
        except Exception as e:
            logger.error(f"[{backend.__class__.__name__}] Failed to delete old backup {b['key']}: {e}")
            
    logger.info(f"[{backend.__class__.__name__}] Retention: {deleted_count} old backups deleted, {retention_count} kept.")
