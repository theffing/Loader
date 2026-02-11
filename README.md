# Stock Data API - Daily Stock CSV to MySQL + FastAPI

A complete system for loading stock CSV data into MySQL and serving it via a high-performance FastAPI REST API with JSON responses.

## Project Structure

```
stock-api/
├── raw/                # Place your Tiingo CSV files here
├── processed/          # Successfully processed files moved here
├── failed/             # Files that failed to process
├── .env                # Environment variables (database credentials)
├── .env.example        # Template for environment variables
├── requirements.txt    # Python dependencies
├── README.md           # This file
├── database.py         # MySQL database setup and connection manager
├── loader.py           # CSV to MySQL data loader
└── api.py              # FastAPI REST API server
```

## What This System Does

This system solves three main problems:

1. Storage: Efficiently stores large amounts of stock data (4GB+) in MySQL with proper indexing and partitioning
2. Retrieval: Provides a fast JSON API for querying stock data with various filters
3. Management: Automates the data loading process with validation and error handling

### Key Features:
- Efficient MySQL storage with yearly partitions
- Batch processing of CSV files with parallel loading
- RESTful JSON API with FastAPI
- Automatic API documentation (Swagger UI)
- Optional Redis caching for performance
- Data validation and error handling
- Health checks and monitoring endpoints
- Support for large datasets on limited hardware (2GB RAM)

## Quick Start Guide

### Step 1: Clone and Setup

```bash
# Clone or create the project directory
mkdir stock-api
cd stock-api

# Create the directory structure
mkdir -p raw processed failed
```

### Step 2: Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Or install individually:
pip install fastapi uvicorn mysql-connector-python pandas python-dotenv pydantic redis redis-server
```

### Step 3: Configure Environment

```bash
# Copy the environment template
cp .env.example .env

# Edit .env with your MySQL credentials
vi .env
```

Your .env file should look like this:

```
# Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_NAME=stock_data
DB_USER=your_mysql_username
DB_PASSWORD=your_mysql_password

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Optional Redis Cache
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
CACHE_TTL=300
```

Note: MySQL still requires `DB_USER` and `DB_PASSWORD` even when `DB_HOST=localhost`, unless you have explicitly configured passwordless access.

Example: create a local MySQL user and grant access:

```bash
sudo mysql -e "CREATE USER 'stock_user'@'localhost' IDENTIFIED BY 'strong_password';"
sudo mysql -e "GRANT ALL PRIVILEGES ON stock_data.* TO 'stock_user'@'localhost';"
sudo mysql -e "FLUSH PRIVILEGES;"
```

### Step 4: Prepare Your Data

Place your Tiingo CSV files in the raw/ directory:

```bash
# Each file should be named by its ticker symbol
# Example file names:
raw/AAPL.csv
raw/MSFT.csv
raw/GOOGL.csv
raw/TSLA.csv
# ... etc.

# CSV format should match Tiingo export:
# date,open,high,low,close,volume,adjOpen,adjHigh,adjLow,adjClose,adjVolume,divCash,splitFactor
```

If your Tiingo export is organized as one folder per ticker (for example, tiingo_us_data/<TICKER>/prices_daily.csv), you can flatten it into raw/ with:

```bash
python tiingo_to_raw.py
```

Optional flags:

```bash
python tiingo_to_raw.py --source tiingo_us_data --dest stock-api/raw --overwrite
```

Use --move to move files instead of copying them.

### Step 5: Run the System

#### Step 5.1: Setup Database
```bash
# This creates the database and tables
python database.py
```

Expected output:
```
Setting up database...
Connected to MySQL database
Database 'stock_data' is ready
Table 'ticker_data' created successfully
Table 'ticker_metadata' created successfully
Yearly partitions added to ticker_data table

Database setup complete!
Run 'python loader.py' to load your CSV files
```

#### Step 5.2: Load CSV Data

```bash
# Load all CSV files from raw/ directory
python loader.py
```

### Continuous Pipeline Mode (Redis Queue)

### Redis Setup
For improved performance with caching:

```bash
# Install Redis (Ubuntu/Debian)
sudo apt update
sudo apt install redis-server

# Start Redis
sudo systemctl start redis
sudo systemctl enable redis

# Test Redis
redis-cli ping
```

If you want the server to process CSV drops continuously, run the worker and watcher:

```bash
# Terminal 1: start the worker
python pipeline_worker.py

# Terminal 2: watch for new files
python pipeline_watch.py --scan-existing
```

To run multiple workers from one command:

```bash
python pipeline_worker.py --num-workers 4
```

By default, the watcher scans stock-api/raw. If you use per-source subfolders, drop files into:

- stock-api/raw/tiingo
- stock-api/raw/fmp
- stock-api/raw/yfinance

You can also force a source for all incoming files:

```bash
python pipeline_watch.py --source tiingo
```

#### Step 5.3: Start the API Server
```bash
python api.py

# With uvicorn directly for production:
uvicorn api:app --host 0.0.0.0 --port 8000 --workers 2
```

Expected output:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

## API Endpoints

Once running, visit: http://localhost:8000

Swagger UI (interactive API docs): http://localhost:8000/docs
ReDoc (clean docs view): http://localhost:8000/redoc

### Available Endpoints:

| Endpoint | Method | Description | Example |
|----------|--------|-------------|---------|
| / | GET | API information and endpoints list | GET / |
| /health | GET | Health check | GET /health |
| /stats | GET | Database statistics | GET /stats |
| /tickers | GET | List all available tickers | GET /tickers?limit=50 |
| /stock/{ticker} | GET | Get stock data for a ticker | GET /stock/AAPL?days=90 |
| /stock/{ticker}/range | GET | Get data for date range | GET /stock/AAPL/range?start=2024-01-01&end=2024-01-31 |
| /stocks | GET | Get multiple tickers for one date | GET /stocks?symbols=AAPL,MSFT&date=2024-01-15 |
| /metadata/{ticker} | GET | Get ticker metadata | GET /metadata/AAPL |
| /docs | GET | Interactive API documentation | GET /docs |
| /redoc | GET | Alternative API documentation | GET /redoc |

## Usage Examples

### Example 1: Get Apple stock for last 30 days
```bash
curl "http://localhost:8000/stock/AAPL?days=30"
```

Response:
```json
{
  "ticker": "AAPL",
  "days": 30,
  "count": 21,
  "data": [
    {
      "date": "2024-01-10",
      "close": 185.92,
      "volume": 52345678
    },
    {
      "date": "2024-01-09",
      "close": 185.14,
      "volume": 51234567
    }
  ]
}
```

### Example 2: Get specific fields with date range
```bash
curl "http://localhost:8000/stock/MSFT/range?start=2024-01-01&end=2024-01-10&fields=date,open,high,low,close"
```

### Example 3: Get multiple stocks for one date
```bash
curl "http://localhost:8000/stocks?symbols=AAPL,MSFT,GOOGL&date=2024-01-10&fields=ticker,close,volume"
```

### Example 4: List all available tickers
```bash
curl "http://localhost:8000/tickers?limit=20"
```

## File Details

### 1. database.py
Purpose: MySQL database setup and connection management

What it does:
- Creates the database if it doesn't exist
- Creates two tables:
  - ticker_data: Main table for stock price data
  - ticker_metadata: Table for tracking ticker information
- Adds yearly partitions to ticker_data for better performance
- Provides connection pooling for efficient database access
- Creates proper indexes for fast queries

Key features:
- Automatic table creation
- Partitioning by year (2010-2025)
- Unique constraint on (ticker, date) to prevent duplicates
- Proper indexing for common query patterns

### 2. loader.py
Purpose: Manually Load Tiingo CSV files into MySQL database

What it does:
- Scans raw/ directory for CSV files
- Validates each CSV file structure
- Processes files in parallel (configurable)
- Handles large files by processing in batches
- Moves processed files to processed/ directory
- Moves failed files to failed/ directory
- Updates metadata table with ticker information
- Provides progress reporting and summary statistics

Key features:
- Parallel processing with ThreadPoolExecutor
- Batch processing for memory efficiency
- Duplicate handling with ON DUPLICATE KEY UPDATE
- Comprehensive logging
- Error recovery and file management

### 3. api.py
Purpose: FastAPI server providing REST API for stock data

What it does:
- Provides RESTful endpoints for querying stock data
- Returns JSON responses for all queries
- Implements optional Redis caching
- Includes Swagger UI documentation
- Handles database connection pooling
- Provides health checks and monitoring
- Supports CORS for web applications
- Implements response compression

Key features:
- 8 main endpoints for different query patterns
- Field selection to reduce data transfer
- Date range filtering
- Pagination support
- Cache control headers
- Input validation with Pydantic models
- Error handling and logging

### 4. requirements.txt
Purpose: Lists all Python dependencies

Dependencies:
- fastapi: Modern, fast web framework
- uvicorn: ASGI server for FastAPI
- mysql-connector-python: MySQL database driver
- pandas: Data processing for CSV files
- python-dotenv: Environment variable management
- pydantic: Data validation
- redis: Optional caching (install Redis separately)

## Configuration

### MySQL Server Requirements
- MySQL 5.7+ or MariaDB 10.2+
- Sufficient storage for your data (4GB+ recommended)
- Remote access enabled for ai-api.umiuni.com
- User with CREATE, INSERT, SELECT privileges

### Environment Variables
See .env.example for all available options:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| DB_HOST  | Yes | - | MySQL hostname (ai-api.umiuni.com) |
| DB_PORT  | No  | 3306 | MySQL port |
| DB_NAME  | Yes | - | Database name |
| DB_USER  | Yes | - | MySQL username |
| DB_PASSWORD | Yes | - | MySQL password |
| API_HOST | No  | 0.0.0.0 | API server host |
| API_PORT | No  | 8000 | API server port |
| REDIS_HOST  | No | - | Redis host (leave empty to disable) |
| REDIS_PORT  | No | 6379 | Redis port |
| REDIS_PASSWORD | No | - | Redis password |
| CACHE_TTL   | No | 300 | Cache timeout in seconds |

## Troubleshooting

### Common Issues:

#### 1. Database Connection Failed
```
Error connecting to MySQL: Can't connect to MySQL server
```
Solution:
- Verify MySQL is running at ai-api.umiuni.com
- Check firewall settings
- Verify credentials in .env file
- Test connection manually: mysql -h ai-api.umiuni.com -u USER -p

#### 2. CSV Import Fails
```
Error: Missing required columns: ['date', 'open']
```
Solution:
- Ensure CSV files match Tiingo format
- Check file encoding (should be UTF-8)
- Verify column names in first row

#### 3. API Server Won't Start
```
Address already in use
```
Solution:
- Change port in .env: API_PORT=8001
- Kill existing process: pkill -f "python api.py"

#### 4. Out of Memory
```
Killed (server runs out of memory)
```
Solution:
- Reduce batch size in loader.py: batch_size=5000
- Load fewer files at once
- Add swap space: sudo fallocate -l 2G /swapfile

## Performance Tips

### For 2GB RAM Server:
1. Configure MySQL properly in my.cnf:
   ```
   innodb_buffer_pool_size = 768M
   max_connections = 30
   ```

2. Use query limits:
   - Always specify days parameter
   - Use limit parameter for large queries
   - Select only needed fields with fields parameter

3. Enable Redis caching for frequently accessed data

4. Archive old data:
   ```sql
   -- Remove old partitions
   ALTER TABLE ticker_data DROP PARTITION p2010, p2011;
   ```

### Monitoring:
Check API health:
```bash
curl http://localhost:8000/health
```

Check database stats:
```bash
curl http://localhost:8000/stats
```

## Updating Data

### Add New CSV Files:
1. Place new CSV files in raw/ directory
2. Run: python loader.py
3. Only new or updated data will be processed

### Incremental Updates:
The system uses ON DUPLICATE KEY UPDATE, so:
- New data: Inserted
- Existing data with same (ticker, date): Updated
- No duplicates created

## Testing

### Test the API:
```bash
# Test basic endpoint
curl http://localhost:8000/

# Test stock data retrieval
curl "http://localhost:8000/stock/AAPL?days=7"

# Test multiple stocks
curl "http://localhost:8000/stocks?symbols=AAPL,MSFT&date=2024-01-10"
```

### Check Database:
```python
# Quick database check
python -c "
from database import db_manager
stats = db_manager.get_ticker_stats()
print(f'Tickers: {stats[\"total_tickers\"]}, Rows: {stats[\"total_rows\"]:,}')
"
```

## Deployment

### Production Deployment:
1. Use a process manager:
   ```bash
   # Install supervisor
   sudo apt install supervisor
   
   # Create config: /etc/supervisor/conf.d/stock-api.conf
   [program:stock-api]
   command=/path/to/venv/bin/uvicorn api:app --host 0.0.0.0 --port 8000 --workers 2
   directory=/path/to/stock-api
   user=ubuntu
   autostart=true
   autorestart=true
   ```
   
2. Use Nginx as reverse proxy:
   ```
   server {
       listen 80;
       server_name your-domain.com;
       
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

3. Enable HTTPS with Let's Encrypt

## API Documentation

Visit the interactive documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is provided as-is for educational and practical use.

## Acknowledgments

- Tiingo for providing financial data
- FastAPI for the excellent web framework
- MySQL for reliable data storage

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review API documentation at /docs
3. Ensure all dependencies are installed
4. Verify database connection credentials