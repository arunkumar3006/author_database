# ================================================================
# IMPORTANT: This tool uses Skribe's internal API endpoints.
# For use by authorized subscribers only.
# Review Skribe's Terms of Service before use.
# Use responsibly. Do not exceed reasonable daily usage limits.
# ================================================================

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
import pandas as pd
from loguru import logger

from config import (
    INPUT_FILE, OUTPUT_FILE, CHECKPOINT_FILE, USAGE_LOG_FILE,
    MAX_SESSION_REQUESTS, MAX_DAILY_REQUESTS, TRACKING_CALL_EVERY_N
)
from token_manager import TokenManager, TokenExpiredError
from api_client import SkribeAPIClient, AccountFlaggedError
from rate_limiter import RateLimiter, DailyCapReachedError, SessionCapReachedError
from tracking import post_tracking
from outlet_resolver import OutletResolver
from journalist_processor import JournalistProcessor
from excel_handler import ExcelHandler
from utils import normalize_text

class ScraperOrchestrator:
    def __init__(self, args):
        self.args = args
        self.logger = logger
        self.rate_limiter = RateLimiter()
        self.client = SkribeAPIClient(self.rate_limiter)
        self.outlet_resolver = OutletResolver(self.client)
        self.processor = JournalistProcessor()
        self.excel = ExcelHandler()
        self.checkpoint = {}
        self.start_time = datetime.now()
        
    def load_checkpoint(self):
        if self.args.resume and os.path.exists(CHECKPOINT_FILE):
            try:
                with open(CHECKPOINT_FILE, "r") as f:
                    self.checkpoint = json.load(f)
                self.logger.info(f"Loaded checkpoint with {len(self.checkpoint)} processed items.")
            except Exception as e:
                self.logger.error(f"Failed to load checkpoint: {e}")

    def save_checkpoint(self):
        os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
        with open(CHECKPOINT_FILE, "w") as f:
            json.dump(self.checkpoint, f, indent=2)

    async def run(self):
        # 1. Startup checks
        valid, token_info = TokenManager.check_expiry()
        if not valid:
            self.logger.critical(token_info)
            TokenManager.print_refresh_instructions()
            return

        if self.args.check_token:
            print(f"Token valid until: {token_info}")
            return

        # 2. Load input
        try:
            df, name_col, pub_col = self.excel.read_input(self.args.input)
        except Exception as e:
            self.logger.error(f"Startup error: {e}")
            return

        if df.empty:
            self.logger.error("Input file is empty.")
            return

        # 3. Resume logic
        self.load_checkpoint()
        
        self.logger.info("4. Initializing outlet resolver...")
        # Pre-load or fetch outlets
        await self.outlet_resolver._load_or_fetch(force_refresh=getattr(self.args, "refresh_outlets", False))
        
        # 5. Display plan
        remaining_daily = MAX_DAILY_REQUESTS - self.rate_limiter.daily_count
        to_process = [idx for idx in df.index if str(idx) not in self.checkpoint or self.checkpoint[str(idx)].get("Scrape_Status", self.checkpoint[str(idx)].get("status")) != "SUCCESS"]
        num_to_run = len(to_process)
        
        if self.args.limit:
            num_to_run = min(num_to_run, self.args.limit)
            to_process = to_process[:num_to_run]

        print(f"\nPLAN: {num_to_run} journalists to process | Token valid: {token_info} | Daily budget remains: {remaining_daily}")
        if not self.args.dry_run and num_to_run > 50:
            confirm = input(f"About to process {num_to_run} journalists. Continue? [y/N]: ")
            if confirm.lower() != 'y':
                return
        
        if self.args.dry_run:
            print("DRY RUN: Validation complete. Exiting.")
            return

        # 5. Initialization tracking
        await post_tracking(self.client, "journalist-search")
        
        # Ensure output structure is ready
        results_df = df.copy()
        for col in self.excel.output_cols:
            if col not in results_df.columns:
                results_df[col] = ""
                
        # Pre-fill already checkpointed data so it isn't blank
        for idx in df.index:
            cpt = self.checkpoint.get(str(idx))
            if cpt:
                # Handle old checkpoints
                if "status" in cpt and "Scrape_Status" not in cpt:
                    cpt["Scrape_Status"] = cpt.get("status")
                    cpt["Match_Score"] = cpt.get("match_score", 0)
                    cpt["Scraped_At"] = cpt.get("scraped_at", "")
                for k, v in cpt.items():
                    if k in results_df.columns:
                        results_df.at[idx, k] = v

        # 6. Main processing loop
        try:
            for idx in to_process:
                name = results_df.at[idx, name_col]
                pub = results_df.at[idx, pub_col]
                
                print(f"[{idx+1}/{len(df)}] Processing: {name} ({pub})...", end="\r")
                
                try:
                    result = await self.processor.process_item(self.client, name, pub, self.outlet_resolver)
                    
                    # Map the internal lowercase keys to the Excel specific column names
                    mapped = dict(result)
                    mapped["Scrape_Status"] = result.get("status", "NOT_FOUND")
                    mapped["Match_Score"] = result.get("match_score", 0)
                    mapped["Scraped_At"] = result.get("scraped_at", datetime.now().isoformat())
                    
                    # Update row
                    for k, v in mapped.items():
                        if k in results_df.columns:
                            results_df.at[idx, k] = v
                    
                    # Status emoji
                    status = mapped["Scrape_Status"]
                    score = mapped["Match_Score"]
                    emoji = {"SUCCESS": "✅", "PARTIAL": "⚠️", "NOT_FOUND": "❌", "ERROR": "🔴"}.get(status, "❓")
                    
                    self.logger.info(f"[{idx+1}/{len(df)}] {emoji} {name} -> {status} | score:{score:.0f} | RL:{self.rate_limiter.remaining} | today:{self.rate_limiter.daily_count}/{MAX_DAILY_REQUESTS}")
                    
                    # Store in checkpoint
                    self.checkpoint[str(idx)] = mapped
                    self.save_checkpoint()
                    
                except (DailyCapReachedError, SessionCapReachedError) as e:
                    self.logger.warning(f"Cap reached: {e}")
                    break
                except AccountFlaggedError as e:
                    self.logger.critical(f"ABORTING: Account flagged! {e}")
                    break
                except TokenExpiredError as e:
                    self.logger.critical(f"ABORTING: Token expired mid-run. {e}")
                    TokenManager.print_refresh_instructions()
                    break
                except Exception as e:
                    self.logger.error(f"Error processing {name}: {e}")
                    results_df.at[idx, "Scrape_Status"] = "ERROR"
                    results_df.at[idx, "Scrape_Error"] = str(e)
                    self.checkpoint[str(idx)] = {"Scrape_Status": "ERROR", "Scrape_Error": str(e)}
                    self.save_checkpoint()

        except KeyboardInterrupt:
            self.logger.warning("Interrupted by user. Shutting down gracefully...")

        finally:
            # 7. Finalize and save
            duration = datetime.now() - self.start_time
            stats = self.calculate_stats(results_df)
            summary = {
                "Run Date": self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "Duration": str(duration).split(".")[0],
                "Total Input": len(df),
                "Processed": len(self.checkpoint),
                "SUCCESS": stats["SUCCESS"],
                "PARTIAL": stats["PARTIAL"],
                "NOT_FOUND": stats["NOT_FOUND"],
                "ERROR": stats["ERROR"],
                "Daily Budget Used": self.rate_limiter.daily_count,
                "Output File": self.args.output
            }
            
            self.excel.write_output(results_df, self.args.output, summary)
            await self.client.close()
            print(f"\nCompleted in {duration}. Summary saved to {self.args.output}")

    def calculate_stats(self, results_df):
        counts = results_df["Scrape_Status"].value_counts().to_dict()
        return {s: counts.get(s, 0) for s in ["SUCCESS", "PARTIAL", "NOT_FOUND", "ERROR"]}

async def main():
    parser = argparse.ArgumentParser(description="Mavericks API Journalist Enrichment System")
    parser.add_argument("--input", default=INPUT_FILE, help="Path to input Excel file")
    parser.add_argument("--output", default=OUTPUT_FILE, help="Path to output Excel file")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--limit", type=int, help="Limit number of journalists to process this session")
    parser.add_argument("--dry-run", action="store_true", help="Validate without making API calls")
    parser.add_argument("--check-token", action="store_true", help="Check token expiry and exit")
    parser.add_argument("--refresh-outlets", action="store_true", help="Force refresh of outlet ID cache")
    
    args = parser.parse_args()
    
    # Configure logging
    log_file = f"logs/scraper_{int(time.time())}.log"
    os.makedirs("logs", exist_ok=True)
    logger.remove() # Remove default
    logger.add(sys.stderr, level="INFO", colorize=True, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")
    logger.add(log_file, level="DEBUG", rotation="50 MB", format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}")

    orchestrator = ScraperOrchestrator(args)
    await orchestrator.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
