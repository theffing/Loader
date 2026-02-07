"""
database.py - MySQL connection and table setup
"""
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.host = os.getenv('DB_HOST')
        self.port = os.getenv('DB_PORT', 3306)
        self.database = os.getenv('DB_NAME')
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        
        if not all([self.host, self.database, self.user, self.password]):
            raise ValueError("Missing database configuration in .env file")
    
    def get_connection(self):
        """Create and return a MySQL connection"""
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connection_timeout=10
            )
            
            if connection.is_connected():
                logger.info("Connected to MySQL database")
                return connection
                
        except Error as e:
            logger.error(f"Error connecting to MySQL: {e}")
            raise
    
    def setup_database(self):
        """Create database and tables if they don't exist"""
        try:
            # First connect without database to create it
            admin_conn = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password
            )
            admin_cursor = admin_conn.cursor()
            
            # Create database if not exists
            admin_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
            logger.info(f"Database '{self.database}' is ready")
            
            admin_cursor.close()
            admin_conn.close()
            
            # Now connect to the database
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Create main ticker data table
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS ticker_data (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                ticker VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                open DECIMAL(12,4),
                high DECIMAL(12,4),
                low DECIMAL(12,4),
                close DECIMAL(12,4),
                volume BIGINT,
                adj_open DECIMAL(12,4),
                adj_high DECIMAL(12,4),
                adj_low DECIMAL(12,4),
                adj_close DECIMAL(12,4),
                adj_volume BIGINT,
                div_cash DECIMAL(12,4),
                split_factor DECIMAL(10,6),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                UNIQUE KEY uniq_ticker_date (ticker, date),
                INDEX idx_ticker_date (ticker, date),
                INDEX idx_date (date),
                INDEX idx_ticker (ticker)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            
            cursor.execute(create_table_sql)
            logger.info("Table 'ticker_data' created successfully")
            
            # Create metadata table for tracking
            metadata_sql = """
            CREATE TABLE IF NOT EXISTS ticker_metadata (
                ticker VARCHAR(20) PRIMARY KEY,
                name VARCHAR(100),
                first_date DATE,
                last_date DATE,
                total_rows INT DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            );
            """
            
            cursor.execute(metadata_sql)
            logger.info("Table 'ticker_metadata' created successfully")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info("Database setup completed successfully")
            
        except Error as e:
            logger.error(f"Error setting up database: {e}")
            raise
    
    def add_partitions(self):
        """Add yearly partitions to the table for better performance"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Check if table is already partitioned
            cursor.execute("""
                SELECT PARTITION_NAME 
                FROM INFORMATION_SCHEMA.PARTITIONS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'ticker_data'
                AND PARTITION_NAME IS NOT NULL
            """, (self.database,))
            
            existing_partitions = cursor.fetchall()
            
            if not existing_partitions:
                # Add partitions for years 2010-2025
                partition_sql = """
                ALTER TABLE ticker_data 
                PARTITION BY RANGE (YEAR(date)) (
                    PARTITION p2010 VALUES LESS THAN (2011),
                    PARTITION p2011 VALUES LESS THAN (2012),
                    PARTITION p2012 VALUES LESS THAN (2013),
                    PARTITION p2013 VALUES LESS THAN (2014),
                    PARTITION p2014 VALUES LESS THAN (2015),
                    PARTITION p2015 VALUES LESS THAN (2016),
                    PARTITION p2016 VALUES LESS THAN (2017),
                    PARTITION p2017 VALUES LESS THAN (2018),
                    PARTITION p2018 VALUES LESS THAN (2019),
                    PARTITION p2019 VALUES LESS THAN (2020),
                    PARTITION p2020 VALUES LESS THAN (2021),
                    PARTITION p2021 VALUES LESS THAN (2022),
                    PARTITION p2022 VALUES LESS THAN (2023),
                    PARTITION p2023 VALUES LESS THAN (2024),
                    PARTITION p2024 VALUES LESS THAN (2025),
                    PARTITION p_future VALUES LESS THAN MAXVALUE
                )
                """
                
                cursor.execute(partition_sql)
                logger.info("Yearly partitions added to ticker_data table")
            else:
                logger.info("Table is already partitioned")
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Error as e:
            logger.error(f"Error adding partitions: {e}")
            # Don't raise error, partitions are optional for functionality
    
    def get_ticker_list(self):
        """Get list of all tickers in database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT DISTINCT ticker FROM ticker_data ORDER BY ticker")
            tickers = [row[0] for row in cursor.fetchall()]
            
            cursor.close()
            conn.close()
            
            return tickers
            
        except Error as e:
            logger.error(f"Error getting ticker list: {e}")
            return []
    
    def get_ticker_stats(self):
        """Get statistics about the database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_rows,
                    COUNT(DISTINCT ticker) as total_tickers,
                    MIN(date) as earliest_date,
                    MAX(date) as latest_date
                FROM ticker_data
            """)
            
            stats = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return stats
            
        except Error as e:
            logger.error(f"Error getting stats: {e}")
            return {}

# Create a global instance
db_manager = DatabaseManager()

if __name__ == "__main__":
    print("Setting up database...")
    db_manager.setup_database()
    db_manager.add_partitions()
    
    print("\nDatabase setup complete!")
    print("Run 'python loader.py' to load CSV files")