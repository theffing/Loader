"""
database.py - SQLite connection and table setup

IMPORTANT: This file serves TWO purposes:

1. ONE-TIME SETUP (run as script):
   Run this ONCE to create database tables:
   $ python3 database.py
   
   After tables are created, you never need to run this again.

2. RUNTIME MODULE (imported by other scripts):
   This file provides the DatabaseManager class and db_manager instance
   used by loader.py and pipeline_jobs.py for database connections.
   DO NOT DELETE THIS FILE - it's needed for the pipeline to work.

Summary:
- Run ONCE: python3 database.py (creates tables)
- Keep FOREVER: Required by loader.py for database connections
"""
import sqlite3
import os
from dotenv import load_dotenv
import logging
from .sources import get_tables, DATA_TABLE, METADATA_TABLE

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.db_path = os.getenv('DB_PATH', 'data/stock_data.db')
        
        # Ensure database directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    
    def get_connection(self):
        """Create and return a SQLite connection"""
        try:
            logger.info(f"Connecting to SQLite database at {self.db_path}...")
            connection = sqlite3.connect(self.db_path, timeout=30.0)
            # Enable foreign keys and other optimizations
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.row_factory = sqlite3.Row
            
            logger.info(f"✓ Connected to SQLite database at {self.db_path}")
            return connection
        except sqlite3.Error as e:
            logger.error(f"✗ Error connecting to SQLite at {self.db_path}: {e}")
            raise
    
    def setup_database(self):
        """Create database and tables if they don't exist"""
        try:
            logger.info(f"Setting up local SQLite database: {self.db_path}")
            
            # Connect to the database (will create if doesn't exist)
            conn = self.get_connection()
            cursor = conn.cursor()
            
            data_table, meta_table = get_tables()
            self._create_ticker_tables(cursor, data_table, meta_table)

            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info("✓ Database setup completed successfully")
            
        except sqlite3.Error as e:
            logger.error(f"✗ Error setting up database at {self.db_path}: {e}")
            raise

    def _create_ticker_tables(self, cursor, data_table: str, meta_table: str):
        create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {data_table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                date TEXT NOT NULL,
                
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                
                volume INTEGER,
                vwap REAL,
                
                change_value REAL,
                changePercent REAL,
                
                unadjustedVolume INTEGER,
                
                adjOpen REAL,
                adjHigh REAL,
                adjLow REAL,
                adjClose REAL,
                adjVolume REAL,
                
                symbol TEXT NOT NULL,
                
                UNIQUE(symbol, date)
            );
            """
        
        cursor.execute(create_table_sql)
        
        # Create indices for better performance
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_symbol_date ON {data_table}(symbol, date);")
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_date ON {data_table}(date);")
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_symbol ON {data_table}(symbol);")
        
        logger.info("Table '%s' created successfully", data_table)
        
        metadata_sql = f"""
            CREATE TABLE IF NOT EXISTS {meta_table} (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                first_date TEXT,
                last_date TEXT,
                total_rows INTEGER DEFAULT 0,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        
        cursor.execute(metadata_sql)
        logger.info("Table '%s' created successfully", meta_table)
    
    def add_partitions(self):
        """SQLite doesn't support partitions - this method is a no-op for compatibility"""
        logger.info("SQLite doesn't use partitions - skipping")
    
    def get_ticker_list(self):
        """Get list of all tickers in database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT DISTINCT symbol FROM {DATA_TABLE} ORDER BY symbol")
            tickers = [row[0] for row in cursor.fetchall()]
            
            cursor.close()
            conn.close()
            
            return tickers
            
        except sqlite3.Error as e:
            logger.error(f"Error getting ticker list: {e}")
            return []
    
    def get_ticker_stats(self):
        """Get statistics about the database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT 
                    COUNT(*) as total_rows,
                    COUNT(DISTINCT symbol) as total_tickers,
                    MIN(date) as earliest_date,
                    MAX(date) as latest_date
                FROM {DATA_TABLE}
            """)
            
            result = cursor.fetchone()
            stats = {
                'total_rows': result[0],
                'total_tickers': result[1],
                'earliest_date': result[2],
                'latest_date': result[3]
            }
            
            cursor.close()
            conn.close()
            
            return stats
            
        except sqlite3.Error as e:
            logger.error(f"Error getting stats: {e}")
            return {}

# Create a global instance
db_manager = DatabaseManager()

if __name__ == "__main__":
    print("="*70)
    print("DATABASE INITIAL SETUP - Run this ONCE to create tables")
    print("="*70)
    print("\nThis script will:")
    print("  1. Create SQLite database file")
    print("  2. Create table 'ticker_data'")
    print("  3. Create table 'ticker_metadata'")
    print("  4. Create indices for better performance")
    print("\nYou only need to run this ONCE for initial setup.")
    print("After tables exist, the pipeline will use them automatically.")
    print("="*70)
    print(f"\nDatabase location: {db_manager.db_path}")
    print()
    
    try:
        db_manager.setup_database()
        
        print("\n" + "="*70)
        print("✓ Database setup complete!")
        print("="*70)
        print(f"Database file: {db_manager.db_path}")
        print("\n⚠️  You do NOT need to run this script again.")
        print("\nNext steps:")
        print("  1. Place your CSV files in the 'raw/' directory")
        print("  2. Run: ./run_pipeline.sh")
        print("     (or manually: python3 pipeline_worker.py & python3 pipeline_watch.py)")
        print("\nTo verify tables were created:")
        print(f"  sqlite3 {db_manager.db_path} '.tables'")
        print("="*70)
    except Exception as e:
        print("\n" + "="*70)
        print("✗ Database setup failed!")
        print("="*70)
        print(f"Error: {e}")
        print("\nPlease check:")
        print("  1. DB_PATH is set correctly in .env file")
        print("  2. Directory has write permissions")
        print("  3. Sufficient disk space available")
        print("="*70)
        raise