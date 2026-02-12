"""
loader.py - Load Tiingo CSV files to MySQL
"""
import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from database import db_manager
from sources import get_tables, DATA_TABLE, METADATA_TABLE
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CSVLoader:
    def __init__(
        self,
        csv_dir='raw',
        processed_dir='processed',
        failed_dir='failed',
    ):
        self.csv_dir = csv_dir
        self.processed_dir = processed_dir
        self.failed_dir = failed_dir
        self.table_name = DATA_TABLE
        self.metadata_table = METADATA_TABLE
        
        # Create directories if they don't exist
        os.makedirs(self.processed_dir, exist_ok=True)
        os.makedirs(self.failed_dir, exist_ok=True)
        
        # Column mapping from Tiingo CSV
        self.column_map = {
            'date': 'date',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume',
            'adjOpen': 'adj_open',
            'adjHigh': 'adj_high',
            'adjLow': 'adj_low',
            'adjClose': 'adj_close',
            'adjVolume': 'adj_volume',
            'divCash': 'div_cash',
            'splitFactor': 'split_factor'
        }
    
    def find_csv_files(self):
        """Find all CSV files in the directory"""
        pattern = os.path.join(self.csv_dir, '*.csv')
        csv_files = glob.glob(pattern)
        
        logger.info(f"Found {len(csv_files)} CSV files in '{self.csv_dir}'")
        return csv_files
    
    def validate_csv(self, file_path):
        """Validate CSV file structure"""
        try:
            # Quick check - read first few rows
            df_sample = pd.read_csv(file_path, nrows=5)
            
            # Check required columns
            required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
            missing_cols = [col for col in required_cols if col not in df_sample.columns]
            
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")
            
            # Check date format
            try:
                pd.to_datetime(df_sample['date'].iloc[0])
            except:
                raise ValueError("Invalid date format in first row")
            
            return True
            
        except Exception as e:
            logger.error(f"Validation failed for {os.path.basename(file_path)}: {e}")
            return False
    
    def process_csv_file(self, csv_path, batch_size=10000):
        """Process and load a single CSV file"""
        ticker = os.path.basename(csv_path).replace('.csv', '').upper()
        
        try:
            logger.info(f"Processing {ticker}...")
            
            # Read CSV file
            df = pd.read_csv(csv_path)
            
            # Validate data
            if df.empty:
                logger.warning(f"{ticker}: CSV file is empty")
                return False
            
            # Rename columns
            df = df.rename(columns=self.column_map)
            
            # Add ticker column
            df['ticker'] = ticker
            
            # Convert date column
            df['date'] = pd.to_datetime(df['date']).dt.date
            
            # Fill NaN values with NULL for SQL
            df = df.replace({np.nan: None})
            
            # Get date range for metadata
            first_date = df['date'].min()
            last_date = df['date'].max()
            total_rows = len(df)
            
            # Split into batches for large files
            batches = [df[i:i+batch_size] for i in range(0, len(df), batch_size)]
            
            # Database connection
            conn = db_manager.get_connection()
            cursor = conn.cursor()
            
            # Prepare insert query
            columns = ['ticker', 'date', 'open', 'high', 'low', 'close', 'volume',
                      'adj_open', 'adj_high', 'adj_low', 'adj_close', 'adj_volume',
                      'div_cash', 'split_factor']
            
            placeholders = ', '.join(['%s'] * len(columns))
            insert_sql = f"""
            INSERT INTO {self.table_name} ({', '.join(columns)})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE
                open = VALUES(open),
                high = VALUES(high),
                low = VALUES(low),
                close = VALUES(close),
                volume = VALUES(volume),
                adj_open = VALUES(adj_open),
                adj_high = VALUES(adj_high),
                adj_low = VALUES(adj_low),
                adj_close = VALUES(adj_close),
                adj_volume = VALUES(adj_volume),
                div_cash = VALUES(div_cash),
                split_factor = VALUES(split_factor)
            """
            
            # Insert batches
            rows_inserted = 0
            for batch in batches:
                # Convert batch to list of tuples
                data_tuples = [tuple(row) for row in batch[columns].itertuples(index=False, name=None)]
                
                # Execute batch insert
                cursor.executemany(insert_sql, data_tuples)
                rows_inserted += cursor.rowcount
            
            # Update metadata
            metadata_sql = f"""
            INSERT INTO {self.metadata_table} (ticker, first_date, last_date, total_rows)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                first_date = LEAST(first_date, VALUES(first_date)),
                last_date = GREATEST(last_date, VALUES(last_date)),
                total_rows = VALUES(total_rows),
                last_updated = CURRENT_TIMESTAMP
            """
            
            cursor.execute(metadata_sql, (ticker, first_date, last_date, total_rows))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            # Move processed file
            processed_path = os.path.join(self.processed_dir, os.path.basename(csv_path))
            os.rename(csv_path, processed_path)
            
            logger.info(f"✓ {ticker}: Inserted {rows_inserted} rows ({first_date} to {last_date})")
            return True
            
        except Exception as e:
            logger.error(f"✗ {ticker}: Failed with error: {str(e)}")
            
            # Move failed file
            failed_path = os.path.join(self.failed_dir, os.path.basename(csv_path))
            try:
                os.rename(csv_path, failed_path)
            except:
                pass
            
            return False
    
    def load_all_files(self, max_workers=4):
        """Load all CSV files with parallel processing"""
        csv_files = self.find_csv_files()
        
        if not csv_files:
            logger.error(f"No CSV files found in '{self.csv_dir}'")
            logger.info("Please place your Tiingo CSV files in the 'raw' directory")
            return
        
        # First validate all files
        valid_files = []
        for csv_file in csv_files:
            if self.validate_csv(csv_file):
                valid_files.append(csv_file)
            else:
                logger.warning(f"Skipping invalid file: {os.path.basename(csv_file)}")
        
        if not valid_files:
            logger.error("No valid CSV files to process")
            return
        
        logger.info(f"Processing {len(valid_files)} valid CSV files...")
        
        # Process files in parallel
        successful = 0
        failed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(self.process_csv_file, csv_file): csv_file 
                for csv_file in valid_files
            }
            
            # Process as they complete
            for future in as_completed(future_to_file):
                csv_file = future_to_file[future]
                try:
                    if future.result():
                        successful += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"Error processing {csv_file}: {e}")
                    failed += 1
        
        # Print summary
        logger.info("\n" + "="*50)
        logger.info("LOADING SUMMARY")
        logger.info("="*50)
        logger.info(f"Total files processed: {len(valid_files)}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info("="*50)
        
        if successful > 0:
            # Show database statistics
            stats = db_manager.get_ticker_stats(table_name=self.table_name)
            if stats:
                logger.info(f"Total rows in database: {stats['total_rows']:,}")
                logger.info(f"Total tickers: {stats['total_tickers']}")
                logger.info(f"Date range: {stats['earliest_date']} to {stats['latest_date']}")
        
        return successful, failed


def main():
    """Main function to run the loader"""
    import argparse

    parser = argparse.ArgumentParser(description="Load CSV files into MySQL")
    parser.add_argument("--source", default="tiingo", help="Data source name")
    parser.add_argument("--csv-dir", default="raw", help="Directory with CSV files")
    parser.add_argument("--processed-dir", default="processed", help="Processed output directory")
    parser.add_argument("--failed-dir", default="failed", help="Failed output directory")
    parser.add_argument("--workers", type=int, default=2, help="Number of worker threads")
    args = parser.parse_args()

    print("\n" + "="*60)
    print(f"CSV to MySQL Loader ({args.source})")
    print("="*60)
    
    if not os.path.exists(args.csv_dir):
        print(f"\n Creating '{args.csv_dir}' directory...")
        os.makedirs(args.csv_dir)
        print("Please place your CSV files in the directory above")
        print("Each file should be named like 'AAPL.csv', 'MSFT.csv', etc.")
        return
    
    loader = CSVLoader(
        csv_dir=args.csv_dir,
        processed_dir=args.processed_dir,
        failed_dir=args.failed_dir,
        source=args.source,
    )
    
    print("\n Starting CSV import...")
    print("This may take several minutes depending on the number of files")
    print("Progress will be shown below:\n")
    
    start_time = time.time()
    successful, failed = loader.load_all_files(max_workers=args.workers)
    end_time = time.time()
    
    elapsed = end_time - start_time
    
    print("\n" + "="*60)
    print(f"✅ Import completed in {elapsed:.2f} seconds")
    print(f"   {successful} files imported successfully")
    
    if failed > 0:
        print(f"   ⚠️  {failed} files failed (check '{args.failed_dir}' directory)")
    
    print("\n📊 Next steps:")
    print("   1. Check database statistics: python database.py")
    print("   2. Start API server: python api.py")
    print("   3. Test API: http://localhost:8000/stock/AAPL?days=30")
    print("="*60)


if __name__ == "__main__":
    main()