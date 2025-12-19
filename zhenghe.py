#!/usr/bin/env python3
"""
Clash 规则合并与更新脚本
功能：合并多个规则源，去重，自动提交更新
支持强制刷新模式
"""

import os
import sys
import asyncio
import aiohttp
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Set, Tuple, Dict, Optional
from urllib.parse import urlparse
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 📁 路径配置
RULES_DIR = Path("rules")
OUTPUT_DIR = Path("Clash")
MAX_RETRIES = 3
TIMEOUT = 15
MAX_CONCURRENT_REQUESTS = 10  # 并发请求限制

class RuleProcessor:
    """规则处理器"""
    
    def __init__(self):
        self.has_changes = False
        self.session: Optional[aiohttp.ClientSession] = None
        # 获取强制刷新标志
        self.force_refresh = os.getenv("FORCE_REFRESH", "false").lower() == "true"
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.setup()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.cleanup()
        
    async def setup(self):
        """初始化设置"""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # 创建 aiohttp 会话
        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS, ssl=False)
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        
    async def cleanup(self):
        """清理资源"""
        if self.session:
            await self.session.close()
            
    @staticmethod
    def normalize_content(content: str) -> str:
        """标准化内容（统一换行符、去除首尾空白）"""
        return content.strip().replace("\r\n", "\n").replace("\r", "\n")
    
    @staticmethod
    def calculate_hash(content: str) -> str:
        """计算内容的哈希值"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def split_comment_and_urls(self, lines: List[str]) -> Tuple[List[str], List[str]]:
        """分割注释行和URL行"""
        comments = []
        urls = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                comments.append(stripped)
            else:
                urls.append(stripped)
                
        return comments, urls
    
    def deduplicate_urls(self, urls: List[str]) -> Tuple[List[str], int]:
        """去重URL并保持原始顺序"""
        seen: Set[str] = set()
        deduped = []
        
        for url in urls:
            # 标准化URL
            normalized_url = url.strip()
            if not normalized_url:
                continue
                
            if normalized_url not in seen:
                seen.add(normalized_url)
                deduped.append(normalized_url)
                
        return deduped, len(urls) - len(deduped)
    
    async def fetch_url_content(self, url: str, retry_count: int = 0) -> str:
        """异步获取URL内容（支持重试）"""
        if not self.session:
            return f"# Error: Session not initialized for {url}"
            
        try:
            async with self.session.get(url) as response:
                response.raise_for_status()
                content = await response.text()
                return content
                
        except asyncio.TimeoutError:
            if retry_count < MAX_RETRIES:
                logger.warning(f"Timeout fetching {url}, retrying ({retry_count + 1}/{MAX_RETRIES})")
                await asyncio.sleep(1)  # 等待1秒后重试
                return await self.fetch_url_content(url, retry_count + 1)
            logger.error(f"Timeout fetching {url} after {MAX_RETRIES} retries")
            return f"# Timeout fetching {url}\n"
            
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching {url}: {e}")
            return f"# Network error fetching {url}: {e}\n"
            
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
            return f"# Error fetching {url}: {e}\n"
    
    async def download_and_merge(self, urls: List[str]) -> str:
        """并发下载并合并所有URL内容"""
        if not urls:
            return ""
            
        logger.info(f"正在下载 {len(urls)} 个规则源...")
        
        # 创建下载任务
        tasks = [self.fetch_url_content(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        merged_parts = []
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                logger.error(f"下载失败 {url}: {result}")
                merged_parts.append(f"# Error fetching {url}: {result}\n")
            else:
                merged_parts.append(result)
                
        return "\n".join(merged_parts)
    
    def process_rule_file(self, input_file: Path) -> Tuple[Path, List[str], List[str], int]:
        """处理单个规则文件"""
        logger.info(f"📄 处理规则文件: {input_file.name}")
        
        # 读取文件内容
        try:
            content = input_file.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            logger.warning(f"文件编码异常，尝试其他编码: {input_file}")
            content = input_file.read_text(encoding='gbk')
            
        # 分割行
        lines = [line.rstrip('\n') for line in content.splitlines()]
        comments, urls = self.split_comment_and_urls(lines)
        
        # URL去重
        deduped_urls, duplicates = self.deduplicate_urls(urls)
        
        # 生成新内容
        new_lines = []
        if comments:
            new_lines.extend(comments)
            if deduped_urls:
                new_lines.append("")  # 注释和URL之间的空行
        if deduped_urls:
            new_lines.extend(deduped_urls)
            
        new_content = "\n".join(new_lines) + "\n"
        
        # 检查是否需要更新源文件
        should_update = False
        update_reason = ""
        
        if self.force_refresh:
            should_update = True
            update_reason = "强制刷新模式"
            logger.info(f"🔧 强制刷新：源文件 {input_file.name}")
        elif content != new_content:
            should_update = True
            update_reason = f"内容变化（移除 {duplicates} 个重复项）"
        
        if should_update:
            input_file.write_text(new_content, encoding='utf-8', newline='\n')
            self.git_add(input_file)
            logger.info(f"✅ 已更新源文件，原因: {update_reason}")
            self.has_changes = True
        else:
            logger.info(f"🔄 源文件无需更新")
            
        logger.info(f"🔍 原始链接: {len(urls)}，去重后: {len(deduped_urls)}")
        
        return input_file, comments, deduped_urls, duplicates
    
    async def process_output_file(self, input_file: Path, urls: List[str], comments: List[str]) -> None:
        """处理输出文件"""
        output_file = OUTPUT_DIR / f"{input_file.stem}.list"
        
        # 下载并合并内容
        merged_content = await self.download_and_merge(urls)
        final_content = merged_content
        
        # 标准化比较
        final_normalized = self.normalize_content(final_content)
        
        # 检查现有文件
        existing_normalized = ""
        file_exists = output_file.exists()
        if file_exists:
            existing_content = output_file.read_text(encoding='utf-8')
            existing_normalized = self.normalize_content(existing_content)
        
        # 判断是否需要更新
        should_update = False
        update_reason = ""
        
        if self.force_refresh:
            should_update = True
            update_reason = "强制刷新模式"
            logger.info(f"🔧 强制刷新：输出文件 {output_file.name}")
        elif not file_exists:
            should_update = True
            update_reason = "文件不存在"
        elif final_normalized != existing_normalized:
            should_update = True
            update_reason = "内容变化"
        
        if should_update:
            output_file.write_text(final_content, encoding='utf-8', newline='\n')
            self.git_add(output_file)
            logger.info(f"✅ 已更新输出文件: {output_file.name}，原因: {update_reason}")
            self.has_changes = True
        else:
            logger.info(f"🔄 输出文件无需更新: {output_file.name}")
    
    @staticmethod
    def git_add(file_path: Path) -> bool:
        """Git添加文件"""
        try:
            subprocess.run(
                ["git", "add", str(file_path)],
                check=True,
                capture_output=True,
                text=True
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Git添加失败 {file_path}: {e}")
            return False
    
    async def git_commit_and_push(self) -> bool:
        """Git提交和推送"""
        if not self.has_changes:
            logger.info("✅ 无需提交：没有任何更改")
            return False
            
        try:
            # 配置Git用户
            subprocess.run(
                ["git", "config", "user.name", "github-actions[bot]"],
                check=True,
                capture_output=True,
                text=True
            )
            subprocess.run(
                ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
                check=True,
                capture_output=True,
                text=True
            )
            
            # 配置远程仓库URL（使用token认证）
            token = os.getenv("GITHUB_TOKEN")
            repo = os.getenv("GITHUB_REPOSITORY")
            if token and repo:
                remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
                subprocess.run(
                    ["git", "remote", "set-url", "origin", remote_url],
                    check=True,
                    capture_output=True,
                    text=True
                )
            
            # 检查是否有暂存的更改
            result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                # 提交更改
                commit_msg = f"🤖 自动更新合并规则文件 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                if self.force_refresh:
                    commit_msg += " [强制刷新]"
                commit_msg += " [skip ci]"
                
                subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                # 推送更改
                subprocess.run(
                    ["git", "push"],
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                logger.info("🚀 更改已提交并推送到远程仓库")
                return True
            else:
                logger.info("✅ 无需提交：没有实际更改")
                return False
                
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Git操作失败: {e}")
            if e.stderr:
                logger.error(f"Git错误输出: {e.stderr}")
            return False

async def main():
    """主函数"""
    start_time = datetime.now()
    
    # 检查强制刷新模式
    force_refresh = os.getenv("FORCE_REFRESH", "false").lower() == "true"
    logger.info(f"🚀 合并任务开始时间: {start_time.isoformat()}")
    logger.info(f"🔧 强制刷新模式: {force_refresh}")
    
    # 获取所有规则文件
    txt_files = sorted(RULES_DIR.glob("*.txt"))
    if not txt_files:
        logger.warning(f"⚠️ 在 {RULES_DIR} 目录中未找到任何 .txt 文件")
        return
    
    logger.info(f"📁 找到 {len(txt_files)} 个规则文件")
    
    async with RuleProcessor() as processor:
        # 处理每个规则文件
        for i, txt_file in enumerate(txt_files):
            if i > 0:
                logger.info("")  # 美观换行
                
            # 处理源文件
            input_file, comments, urls, duplicates = processor.process_rule_file(txt_file)
            
            # 处理输出文件（异步下载）
            await processor.process_output_file(input_file, urls, comments)
        
        # Git提交
        logger.info("")  # 美观换行
        await processor.git_commit_and_push()
    
    end_time = datetime.now()
    duration = end_time - start_time
    logger.info(f"🎉 任务完成，耗时: {duration.total_seconds():.2f}秒")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("操作被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 程序执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
