# Frappe Insights Configuration

# AI Model Configuration
# API keys and model config stored in Insights Settings DocType
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Model Settings
MODEL_TIMEOUT = 30
MAX_RETRIES = 3

# Quota Management (percentages).
# Keyed by ModelType tier rather than a model id so a catalog refresh does not
# invalidate this table. Mirrors the allocations in
# AIModelRouter._initialize_quotas.
MODEL_QUOTAS = {
    "FAST": 70,
    "BALANCED": 25,
    "PREMIUM": 5,
}

# Redis Configuration
REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = None
REDIS_CACHE_DB = 1

# Cache Settings
CACHE_DEFAULT_TTL = 3600  # 1 hour
CACHE_HOT_TTL = 300       # 5 minutes
CACHE_WARM_TTL = 1800     # 30 minutes
CACHE_COLD_TTL = 86400    # 24 hours
MAX_CACHE_SIZE = "1GB"

# Processing Configuration
MAX_CONCURRENT_REQUESTS = 50
DEFAULT_QUERY_TIMEOUT = 30
STREAMING_THRESHOLD = 10000
PROGRESSIVE_CHUNK_SIZE = 1000
BATCH_SIZE = 100

# Performance Optimization
OPTIMIZATION_LEVEL = "balanced"  # aggressive, balanced, conservative
ENABLE_QUERY_CACHE = True
ENABLE_RESULT_STREAMING = True
ENABLE_PROGRESSIVE_LOADING = True
ENABLE_SMART_BATCHING = True

# Database Connection Pooling
DB_POOL_SIZE = 20
DB_MAX_OVERFLOW = 0
DB_POOL_TIMEOUT = 30
DB_POOL_RECYCLE = 3600

# WebSocket Configuration
WS_MAX_CONNECTIONS = 1000
WS_HEARTBEAT_INTERVAL = 30
WS_RECONNECT_ATTEMPTS = 5

# Security Settings
API_RATE_LIMIT = 1000  # requests per hour per user
SESSION_TIMEOUT = 3600
REQUIRE_SSL = False  # Set to True in production
ALLOWED_HOSTS = ["*"]

# Logging Configuration
LOG_LEVEL = "INFO"
ENABLE_PERFORMANCE_LOGGING = True
ENABLE_AI_USAGE_LOGGING = True
ENABLE_CACHE_METRICS = True

# File Upload Settings
MAX_FILE_SIZE = "100MB"
ALLOWED_FILE_TYPES = ["csv", "xlsx", "json", "pdf"]
UPLOAD_TIMEOUT = 300

# Export Settings
EXPORT_MAX_ROWS = 1000000
EXPORT_TIMEOUT = 600
ENABLE_BACKGROUND_EXPORTS = True

# Monitoring and Alerts
ENABLE_PERFORMANCE_MONITORING = True
ALERT_RESPONSE_TIME_THRESHOLD = 10.0
ALERT_ERROR_RATE_THRESHOLD = 0.1
ALERT_CACHE_HIT_RATE_THRESHOLD = 0.5

# Development Settings (only for development)
DEBUG_MODE = False
ENABLE_SQL_LOGGING = False
ENABLE_AI_REQUEST_LOGGING = False

# ERPNext Integration
ERPNEXT_VERSION = "15.0.0"
SYNC_INTERVAL = 3600  # seconds
ENABLE_REALTIME_SYNC = True
SUPPORTED_MODULES = [
    "accounts", "selling", "buying", "stock", 
    "manufacturing", "projects", "crm", "hr", 
    "assets", "support"
]

# Machine Learning Settings
ML_MODEL_RETRAIN_INTERVAL = 604800  # 1 week in seconds
ML_MODEL_CACHE_SIZE = "500MB"
ENABLE_AUTO_FEATURE_SELECTION = True
ENABLE_MODEL_VERSIONING = True

# Backup and Archive
ENABLE_AUTO_BACKUP = True
BACKUP_INTERVAL = 86400  # daily
BACKUP_RETENTION_DAYS = 90
COMPRESS_BACKUPS = True