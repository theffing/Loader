"""
api.py - FastAPI server for stock data API
Returns JSON responses for all queries
"""
from fastapi import FastAPI, Query, HTTPException, Depends, Path
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
import sqlite3
import json
import logging
from contextlib import contextmanager
import os
from dotenv import load_dotenv
import redis
import uvicorn
from pydantic import BaseModel
from .sources import get_tables, DATA_TABLE, METADATA_TABLE

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Stock Data API",
    description="API for accessing Tiingo stock data",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection manager
class Database:
    _db_path = None
    
    @classmethod
    def get_db_path(cls):
        if cls._db_path is None:
            cls._db_path = os.getenv('DB_PATH', 'data/stock_data.db')
        return cls._db_path
    
    @contextmanager
    def get_connection(self):
        """Get a SQLite database connection with Row factory"""
        connection = sqlite3.connect(self.get_db_path(), timeout=30.0)
        connection.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
        finally:
            connection.close()

# Redis cache (optional)
class Cache:
    _client = None
    
    @classmethod
    def get_client(cls):
        if cls._client is None and os.getenv('REDIS_HOST'):
            try:
                cls._client = redis.Redis(
                    host=os.getenv('REDIS_HOST'),
                    port=int(os.getenv('REDIS_PORT', 6379)),
                    password=os.getenv('REDIS_PASSWORD') or None,
                    decode_responses=True
                )
                # Test connection
                cls._client.ping()
                logger.info("Redis cache connected")
            except Exception as e:
                logger.warning(f"Redis not available: {e}")
                cls._client = None
        return cls._client

# Pydantic models for request/response validation
class StockData(BaseModel):
    date: date
    symbol: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    vwap: Optional[float] = None
    change_value: Optional[float] = None
    changePercent: Optional[float] = None
    unadjustedVolume: Optional[int] = None
    adjOpen: Optional[float] = None
    adjHigh: Optional[float] = None
    adjLow: Optional[float] = None
    adjClose: Optional[float] = None
    adjVolume: Optional[int] = None

class TickerResponse(BaseModel):
    ticker: str
    days: int
    count: int
    data: List[Dict[str, Any]]

class MetadataResponse(BaseModel):
    ticker: str
    name: Optional[str] = None
    first_date: date
    last_date: date
    total_rows: int
    last_updated: datetime

# Database and cache instances
db = Database()
cache = Cache()

# Helper functions
def format_date(dt):
    """Format date for SQL query"""
    if isinstance(dt, str):
        return dt
    elif isinstance(dt, date):
        return dt.strftime('%Y-%m-%d')
    return dt

def build_cache_key(endpoint: str, **kwargs):
    """Build cache key from endpoint and parameters"""
    key_parts = [endpoint]
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}:{v}")
    return ":".join(key_parts)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_date_values(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not record:
        return record
    for key, value in list(record.items()):
        record[key] = _serialize_value(value)
    return record


def _serialize_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for row in records:
        for key, value in list(row.items()):
            row[key] = _serialize_value(value)
    return records


# API Endpoints
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
    return JSONResponse(content={
        "message": "Stock Data API",
        "version": "1.0.0",
        "endpoints": {
            "get_ticker": "/stock/{ticker}?days=30",
            "get_ticker_range": "/stock/{ticker}/range?start_date=2024-01-01&end_date=2024-01-31",
            "get_multiple_tickers": "/stocks?symbols=AAPL,MSFT&date=2024-01-10",
            "get_metadata": "/metadata/{ticker}",
            "list_tickers": "/tickers",
            "health": "/health",
            "stats": "/stats"
        },
        "docs": "/docs"
    })

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            db_healthy = cursor.fetchone() is not None
            cursor.close()
        
        redis_client = cache.get_client()
        redis_healthy = redis_client.ping() if redis_client else True
        
        return JSONResponse(content={
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": "connected" if db_healthy else "disconnected",
            "cache": "connected" if redis_healthy and redis_client else "disabled"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@app.get("/stats", tags=["Statistics"])
async def get_database_stats():
    """Get database statistics"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT 
                    COUNT(*) as total_rows,
                    COUNT(DISTINCT symbol) as total_tickers,
                    MIN(date) as earliest_date,
                    MAX(date) as latest_date
                FROM {DATA_TABLE}
            """)
            
            stats_row = cursor.fetchone()
            stats = {
                'total_rows': stats_row[0],
                'total_tickers': stats_row[1],
                'earliest_date': stats_row[2],
                'latest_date': stats_row[3]
            }
            
            cursor.execute(
                f"SELECT COUNT(*) as recent_rows FROM {DATA_TABLE} WHERE date >= date('now', '-30 days')"
            )
            recent_row = cursor.fetchone()
            recent = {'recent_rows': recent_row[0]}
            
            cursor.close()
        
        return JSONResponse(content={
            "database_stats": _serialize_date_values(stats),
            "recent_data": _serialize_date_values(recent),
            "cache_enabled": cache.get_client() is not None
        })
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8000)),
        workers=int(os.getenv("API_WORKERS", 1)),
    )

@app.get("/tickers", tags=["Tickers"])
async def list_all_tickers(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of tickers to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """Get list of all available tickers"""
    cache_key = build_cache_key("tickers", limit=limit, offset=offset)
    redis_client = cache.get_client()
    
    if redis_client:
        cached = redis_client.get(cache_key)
        if cached:
            return JSONResponse(content=json.loads(cached))
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                f"""
                SELECT DISTINCT symbol 
                FROM {DATA_TABLE}
                ORDER BY symbol 
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            
            tickers = [row[0] for row in cursor.fetchall()]
            
            cursor.execute(f"SELECT COUNT(DISTINCT symbol) as total FROM {DATA_TABLE}")
            total = cursor.fetchone()[0]
            
            cursor.close()
        
        response = {
            "tickers": tickers,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
                "returned": len(tickers)
            }
        }
        
        if redis_client:
            redis_client.setex(cache_key, 3600, json.dumps(response))  # Cache for 1 hour
        
        return JSONResponse(content=response)
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/stock/{ticker}", response_model=TickerResponse, tags=["Stock Data"])
async def get_ticker_data(
    ticker: str = Path(..., description="Stock ticker symbol (e.g., AAPL, MSFT)"),
    days: int = Query(30, ge=1, le=3650, description="Number of days of data to return (max 10 years)"),
    fields: Optional[str] = Query(None, description="Comma-separated list of fields to return (date,open,high,low,close,volume,adjClose)"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of records to return")
):
    """
    Get stock data for a specific ticker.
    
    Returns JSON with:
    - ticker: The requested stock symbol
    - days: Number of days requested
    - count: Number of records returned
    - data: Array of stock data records
    """
    ticker = ticker.upper()
    cache_key = build_cache_key("stock", ticker=ticker, days=days, fields=fields, limit=limit)
    redis_client = cache.get_client()
    
    # Try cache first
    if redis_client:
        cached = redis_client.get(cache_key)
        if cached:
            logger.info(f"Cache hit for {ticker} ({days} days)")
            return JSONResponse(content=json.loads(cached))
    
    # Determine which fields to select
    if fields:
        field_list = [f.strip() for f in fields.split(',')]
        # Validate fields
        valid_fields = {'date', 'open', 'high', 'low', 'close', 'volume', 
                       'adjOpen', 'adjHigh', 'adjLow', 'adjClose', 'adjVolume',
                       'vwap', 'change_value', 'changePercent', 'unadjustedVolume'}
        selected_fields = [f for f in field_list if f in valid_fields]
        if not selected_fields:
            selected_fields = ['date', 'close', 'volume']
    else:
        selected_fields = ['date', 'close', 'volume']
    
    # Always include date
    if 'date' not in selected_fields:
        selected_fields.insert(0, 'date')
    
    field_str = ', '.join(selected_fields)
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            query = f"""
            SELECT {field_str}
            FROM {DATA_TABLE}
            WHERE symbol = ?
            AND date >= date('now', '-' || ? || ' days')
            ORDER BY date DESC
            LIMIT ?
            """
            
            cursor.execute(query, (ticker, days, limit))
            # Convert Row objects to dicts
            results = [dict(row) for row in cursor.fetchall()]
            
            results = _serialize_records(results)
            
            cursor.close()
        
        response = {
            "ticker": ticker,
            "days": days,
            "count": len(results),
            "data": results
        }
        
        # Cache the response (5 minutes for dynamic data)
        if redis_client:
            redis_client.setex(cache_key, 300, json.dumps(response))
        
        return JSONResponse(content=response)
    except sqlite3.Error as e:
        logger.error(f"Database error for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/stock/{ticker}/range", tags=["Stock Data"])
async def get_ticker_date_range(
    ticker: str = Path(..., description="Stock ticker symbol"),
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    fields: Optional[str] = Query(None, description="Comma-separated list of fields to return")
):
    """Get stock data for a specific date range"""
    ticker = ticker.upper()
    
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    
    cache_key = build_cache_key(
        "stock_range",
        ticker=ticker,
        start=start_date,
        end=end_date,
        fields=fields,
    )
    redis_client = cache.get_client()
    
    if redis_client:
        cached = redis_client.get(cache_key)
        if cached:
            return JSONResponse(content=json.loads(cached))
    
    # Field selection (same as above)
    if fields:
        field_list = [f.strip() for f in fields.split(',')]
        valid_fields = {'date', 'open', 'high', 'low', 'close', 'volume', 
                       'adjOpen', 'adjHigh', 'adjLow', 'adjClose', 'adjVolume',
                       'vwap', 'change_value', 'changePercent', 'unadjustedVolume'}
        selected_fields = [f for f in field_list if f in valid_fields]
        if not selected_fields:
            selected_fields = ['date', 'close', 'volume']
    else:
        selected_fields = ['date', 'close', 'volume']
    
    if 'date' not in selected_fields:
        selected_fields.insert(0, 'date')
    
    field_str = ', '.join(selected_fields)
    
    try:
        with db.get_connection() )
            
            query = f"""
            SELECT {field_str}
            FROM {DATA_TABLE}
            WHERE symbol = ?
            AND date BETWEEN ? AND ?
            ORDER BY date ASC
            """
            
            cursor.execute(query, (ticker, start_date, end_date))
            results = [dict(row) for row in cursor.fetchall()]
            
            results = _serialize_records(results)
            
            cursor.close()
        
        response = {
            "ticker": ticker,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "count": len(results),
            "data": results
        }
        
        if redis_client:
            redis_client.setex(cache_key, 300, json.dumps(response))
        
        return JSONResponse(content=response)
    except sqlite3.urn JSONResponse(content=response)
    except Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/stocks", tags=["Stock Data"])
async def get_multiple_tickers(
    symbols: str = Query(..., description="Comma-separated list of ticker symbols"),
    date: date = Query(..., description="Specific date to get data for (YYYY-MM-DD)"),
    fields: Optional[str] = Query(None, description="Comma-separated list of fields to return")
):
    """Get data for multiple tickers on a specific date"""
    tickers = [s.strip().upper() for s in symbols.split(',')]
    
    if len(tickers) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 tickers per request")
    
    cache_key = build_cache_key("stocks", symbols=symbols, date=date, fields=fields)
    redis_client = cache.get_client()
    
    if redis_client:
        cached = redis_client.get(cache_key)
        if cached:
            return JSONResponse(content=json.loads(cached))
    
    # Field selection
    if fields:
        field_list = [f.strip() for f in fields.split(',')]
        valid_fields = {'date', 'open', 'high', 'low', 'close', 'volume', 
                       'adjOpen', 'adjHigh', 'adjLow', 'adjClose', 'adjVolume',
                       'vwap', 'change_value', 'changePercent', 'unadjustedVolume'}
        selected_fields = [f for f in field_list if f in valid_fields]
        if not selected_fields:
            selected_fields = ['symbol', 'date', 'close', 'volume']
    else:
        selected_fields = ['symbol', 'date', 'close', 'volume']
    
    if 'symbol' not in selected_fields:
        selected_fields.insert(0, 'symbol')
    if 'date' not in selected_fields:
        selected_fields.insert(1, 'date')
    
    field_str = ', '.join(selected_fields)
    
    # Create placeholders for tickers
    placeholders = ', '.join(['?'] * len(tickers))
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            query = f"""
            SELECT {field_str}
            FROM {DATA_TABLE}
            WHERE symbol IN ({placeholders})
            AND date = ?
            ORDER BY symbol
            """
            
            params = tickers + [date]
            cursor.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
            
            results = _serialize_records(results)
            
            cursor.close()
        
        response = {
            "date": date.isoformat(),
            "tickers_requested": len(tickers),
            "tickers_found": len(results),
            "data": results
        }
        
        if redis_client:
            redis_client.setex(cache_key, 300, json.dumps(response))

        return JSONResponse(content=response)
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/metadata/{ticker}", response_model=MetadataResponse, tags=["Metadata"])
async def get_ticker_metadata(
    ticker: str = Path(..., description="Stock ticker symbol"),
):
    """Get metadata for a ticker"""
    ticker = ticker.upper()

    cache_key = build_cache_key("metadata", ticker=ticker)
    redis_client = cache.get_client()

    if redis_client:
        cached = redis_client.get(cache_key)
        if cached:
            return JSONResponse(content=json.loads(cached))

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                f"""
                SELECT symbol, name, first_date, last_date, total_rows, last_updated
                FROM {METADATA_TABLE}
                WHERE symbol = ?
                """,
                (ticker,),
            )
            row = cursor.fetchone()
            cursor.close()

        if not row:
            raise HTTPException(status_code=404, detail="Ticker not found")

        result = dict(row)
        
        if result.get("first_date"):
            result["first_date"] = result["first_date"]
        if result.get("last_date"):
            result["last_date"] = result["last_date"]
        if result.get("last_updated"):
            result["last_updated"] = result["last_updated"]

        response = result

        if redis_client:
            redis_client.setex(cache_key, 3600, json.dumps(response))

        return JSONResponse(content=response)
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")