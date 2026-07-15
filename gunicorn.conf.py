"""Gunicorn configuration for Event Sync Service on EC2."""

import multiprocessing

# Socket
bind = "unix:/run/event-sync/gunicorn.sock"

# Workers
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
timeout = 30

# Logging
accesslog = "/var/log/event-sync/access.log"
errorlog = "/var/log/event-sync/error.log"
loglevel = "info"

# Process naming
proc_name = "event-sync-service"

# Security
umask = 0o007
