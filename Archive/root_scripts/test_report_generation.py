#!/usr/bin/env python3
"""
測試報告生成功能
Test daily/weekly report generation
"""

import asyncio
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_daily_report():
    """測試每日報告生成"""
    user_id = '90693c07-6177-42df-97d9-915f3ce7c573'
    
    logger.info("=" * 60)
    logger.info("測試每日報告生成")
    logger.info("=" * 60)
    
    try:
        from src.services.workflow_service import DailyWorkflow
        
        logger.info(f"\n初始化 DailyWorkflow (User: {user_id[:8]}...)")
        workflow = DailyWorkflow(user_id)
        
        logger.info("執行工作流程 (dry_run=True)...")
        result = await workflow.run(dry_run=True, force_refresh=True)
        
        logger.info("\n執行結果:")
        logger.info(f"  狀態: {result.get('status', 'unknown')}")
        logger.info(f"  訊息: {result.get('message', 'N/A')}")
        
        if 'report' in result:
            report = result['report']
            logger.info(f"\n報告內容預覽:")
            logger.info(f"  標題: {report.get('title', 'N/A')}")
            logger.info(f"  長度: {len(report.get('content', ''))} 字元")
            
            # Save to file for inspection
            report_file = f"reports/daily_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(f"# {report.get('title', 'Daily Report')}\n\n")
                f.write(report.get('content', ''))
            logger.info(f"  已儲存至: {report_file}")
        
        logger.info("\n✅ 每日報告測試完成")
        
    except Exception as e:
        logger.error(f"\n❌ 每日報告測試失敗: {e}")
        import traceback
        traceback.print_exc()

async def test_weekly_report():
    """測試每週報告生成"""
    user_id = '90693c07-6177-42df-97d9-915f3ce7c573'
    
    logger.info("\n" + "=" * 60)
    logger.info("測試每週報告生成")
    logger.info("=" * 60)
    
    try:
        from src.services.workflow_service import WeeklyWorkflow
        
        logger.info(f"\n初始化 WeeklyWorkflow (User: {user_id[:8]}...)")
        workflow = WeeklyWorkflow(user_id)
        
        logger.info("執行工作流程 (dry_run=True)...")
        result = await workflow.run(dry_run=True, force_refresh=True)
        
        logger.info("\n執行結果:")
        logger.info(f"  狀態: {result.get('status', 'unknown')}")
        logger.info(f"  訊息: {result.get('message', 'N/A')}")
        
        if 'report' in result:
            report = result['report']
            logger.info(f"\n報告內容預覽:")
            logger.info(f"  標題: {report.get('title', 'N/A')}")
            logger.info(f"  長度: {len(report.get('content', ''))} 字元")
            
            # Save to file for inspection
            report_file = f"reports/weekly_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(f"# {report.get('title', 'Weekly Report')}\n\n")
                f.write(report.get('content', ''))
            logger.info(f"  已儲存至: {report_file}")
        
        logger.info("\n✅ 每週報告測試完成")
        
    except Exception as e:
        logger.error(f"\n❌ 每週報告測試失敗: {e}")
        import traceback
        traceback.print_exc()

async def main():
    logger.info("開始報告生成測試...\n")
    
    # Test daily report
    await test_daily_report()
    
    # Test weekly report
    await test_weekly_report()
    
    logger.info("\n" + "=" * 60)
    logger.info("所有測試完成")
    logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
