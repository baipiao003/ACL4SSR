import os
import re
import requests
import logging
import time
from typing import List, Set, Optional, Tuple, Dict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志，不显示时间戳
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ListRuleProcessor:
    def __init__(self, rules_dir: str = "rules", clash_dir: str = "Clash"):
        """
        初始化处理器
        
        Args:
            rules_dir: 存放规则txt文件的目录
            clash_dir: 存放生成的list文件的目录
        """
        self.rules_dir = Path(rules_dir)
        self.clash_dir = Path(clash_dir)
        
        # 确保目录存在
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        self.clash_dir.mkdir(parents=True, exist_ok=True)
    
    def read_file_with_retry(self, txt_file: Path, max_retries: int = 3) -> Optional[str]:
        """
        带重试的文件读取函数
        
        Args:
            txt_file: 要读取的文件路径
            max_retries: 最大重试次数
            
        Returns:
            文件内容或None（如果读取失败）
        """
        retry_count = 0
        last_exception = None
        
        # 尝试不同的编码格式
        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16', 'latin-1']
        
        while retry_count <= max_retries:
            try:
                for encoding in encodings:
                    try:
                        with open(txt_file, 'r', encoding=encoding) as f:
                            content = f.read()
                        logger.info(f"使用 {encoding} 编码成功读取文件: {txt_file.name}")
                        return content
                    except UnicodeDecodeError:
                        continue
                
                # 如果所有编码都失败，尝试二进制读取
                with open(txt_file, 'rb') as f:
                    content = f.read()
                    # 尝试解码为utf-8并忽略错误
                    return content.decode('utf-8', errors='ignore')
                    
            except Exception as e:
                last_exception = e
                retry_count += 1
                if retry_count <= max_retries:
                    wait_time = 2 ** retry_count  # 指数退避
                    logger.warning(f"第 {retry_count} 次读取文件失败 {txt_file.name}, {wait_time}秒后重试: {e}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"读取文件失败 {txt_file.name}, 已达最大重试次数: {e}")
        
        return None
    
    def extract_links_from_file(self, txt_file: Path, max_retries: int = 3) -> List[str]:
        """
        从txt文件中提取所有链接（带重试）
        
        Args:
            txt_file: txt文件路径
            max_retries: 最大重试次数
            
        Returns:
            提取到的链接列表（保持顺序）
        """
        links = []
        seen_links = set()  # 用于去重
        url_pattern = re.compile(
            r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.\-?=%&+#]*',
            re.IGNORECASE
        )
        
        # 带重试读取文件
        content = self.read_file_with_retry(txt_file, max_retries)
        if content is None:
            logger.error(f"无法读取文件 {txt_file.name}，跳过处理")
            return []
        
        try:
            found_links = url_pattern.findall(content)
            
            # 过滤出list规则链接（保持原始顺序）
            for link in found_links:
                link = link.strip()
                if link and link not in seen_links and self._is_list_rule_link(link):
                    seen_links.add(link)
                    links.append(link)
                    
            logger.info(f"从文件 {txt_file.name} 中提取到 {len(links)} 个链接")
            return links
        except Exception as e:
            logger.error(f"解析文件 {txt_file.name} 内容失败: {e}")
            return []
    
    def _is_list_rule_link(self, link: str) -> bool:
        """
        判断链接是否为list规则链接
        
        Args:
            link: 链接字符串
            
        Returns:
            是否为list规则链接
        """
        # 这里可以根据需要添加更多判断条件
        list_keywords = ['.list', '.yaml', '.yml', '.txt', 'clash', 'rule']
        link_lower = link.lower()
        
        # 检查是否包含常见规则文件扩展名或关键词
        for keyword in list_keywords:
            if keyword in link_lower:
                return True
        return False
    
    def download_with_retry(self, url: str, max_retries: int = 3) -> Optional[str]:
        """
        带重试的下载函数
        
        Args:
            url: 要下载的URL
            max_retries: 最大重试次数
            
        Returns:
            下载的内容或None（如果下载失败）
        """
        retry_count = 0
        last_exception = None
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        while retry_count <= max_retries:
            try:
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                
                # 检查内容类型
                content_type = response.headers.get('content-type', '').lower()
                if 'text' not in content_type and 'application/json' not in content_type:
                    logger.warning(f"URL {url} 返回的内容类型不是文本: {content_type}")
                
                return response.text
                
            except requests.exceptions.Timeout:
                last_exception = f"请求超时"
                retry_count += 1
                if retry_count <= max_retries:
                    wait_time = 2 ** retry_count  # 指数退避策略
                    logger.warning(f"第 {retry_count} 次下载超时 {url}, {wait_time}秒后重试")
                    time.sleep(wait_time)
                    
            except requests.exceptions.ConnectionError:
                last_exception = f"连接错误"
                retry_count += 1
                if retry_count <= max_retries:
                    wait_time = 2 ** retry_count
                    logger.warning(f"第 {retry_count} 次连接错误 {url}, {wait_time}秒后重试")
                    time.sleep(wait_time)
                    
            except requests.exceptions.HTTPError as e:
                if e.response.status_code >= 500:
                    # 服务器错误，可以重试
                    last_exception = f"HTTP错误: {e.response.status_code}"
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = 2 ** retry_count
                        logger.warning(f"第 {retry_count} 次服务器错误 {url} ({e.response.status_code}), {wait_time}秒后重试")
                        time.sleep(wait_time)
                    else:
                        break
                else:
                    # 客户端错误（4xx），不重试
                    logger.error(f"客户端错误 {url}: {e.response.status_code}")
                    return None
                    
            except Exception as e:
                last_exception = str(e)
                retry_count += 1
                if retry_count <= max_retries:
                    wait_time = 2 ** retry_count
                    logger.warning(f"第 {retry_count} 次下载失败 {url}, {wait_time}秒后重试: {e}")
                    time.sleep(wait_time)
        
        if last_exception:
            logger.error(f"下载失败 {url} (已重试{retry_count}次): {last_exception}")
        else:
            logger.error(f"下载失败 {url} (已重试{retry_count}次)")
        
        return None
    
    def process_single_file(self, txt_file: Path, max_workers: int = 5, max_retries: int = 3):
        """
        处理单个txt文件
        
        Args:
            txt_file: txt文件路径
            max_workers: 最大并发下载数
            max_retries: 最大重试次数
        """
        logger.info(f"开始处理文件: {txt_file.name}")
        
        # 提取链接（带重试，保持顺序）
        links = self.extract_links_from_file(txt_file, max_retries)
        if not links:
            logger.warning(f"文件 {txt_file.name} 中没有找到有效链接")
            return
        
        total_links = len(links)
        logger.info(f"文件 {txt_file.name} 发现 {total_links} 个链接，开始下载...")
        
        # 创建一个字典来跟踪每个链接的进度和结果
        link_status = {}
        for idx, link in enumerate(links, 1):
            link_status[link] = {
                'index': idx,
                'total': total_links,
                'content': None,
                'success': False,
                'error': None
            }
        
        # 用于跟踪已完成的数量（用于进度条）
        completed_count = 0
        
        # 并发下载所有链接内容（带重试）
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.download_with_retry, link, max_retries): link for link in links}
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                completed_count += 1
                
                try:
                    content = future.result()
                    if content:
                        link_status[url]['content'] = content
                        link_status[url]['success'] = True
                        # 按顺序显示成功信息
                        status = link_status[url]
                        logger.info(f"✓ 成功下载 [{status['index']}/{status['total']}]: {url}")
                    else:
                        link_status[url]['success'] = False
                        link_status[url]['error'] = "下载内容为空"
                        status = link_status[url]
                        logger.warning(f"✗ 下载内容为空 [{status['index']}/{status['total']}]: {url}")
                except Exception as e:
                    link_status[url]['success'] = False
                    link_status[url]['error'] = str(e)
                    status = link_status[url]
                    logger.error(f"✗ 下载失败 [{status['index']}/{status['total']}]: {url}")
        
        # 统计下载结果
        success_count = sum(1 for status in link_status.values() if status['success'])
        fail_count = total_links - success_count
        
        if fail_count > 0:
            logger.warning(f"下载完成: {success_count}/{total_links} 成功, {fail_count}/{total_links} 失败")
        
        # 按原始顺序收集成功下载的内容
        all_contents = []
        for link in links:
            if link_status[link]['success'] and link_status[link]['content']:
                all_contents.append(link_status[link]['content'])
        
        if not all_contents:
            logger.error(f"文件 {txt_file.name} 的所有链接下载失败")
            return
        
        # 保存到list文件
        list_filename = txt_file.stem + '.list'
        list_file_path = self.clash_dir / list_filename
        
        try:
            # 合并所有内容，去除重复行
            combined_content = []
            seen_lines = set()
            
            for content in all_contents:
                lines = content.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and line not in seen_lines:
                        seen_lines.add(line)
                        combined_content.append(line)
            
            # 生成文件头（只保留生成时间和规则数量）
            rule_count = len(combined_content)
            generation_time = time.strftime('%Y-%m-%d %H:%M:%S')
            header = f"""# 生成时间: {generation_time}
# 规则数量: {rule_count}

"""
            
            # 写入文件
            with open(list_file_path, 'w', encoding='utf-8') as f:
                f.write(header + '\n'.join(combined_content))
            
            logger.info(f"✓ 成功保存到 {list_file_path}, 共 {rule_count} 条规则")
            
        except Exception as e:
            logger.error(f"✗ 保存文件失败 {list_file_path}: {e}")
    
    def process_all_files(self, max_workers: int = 5, max_retries: int = 3):
        """
        处理rules目录下所有txt文件
        
        Args:
            max_workers: 最大并发下载数
            max_retries: 最大重试次数
        """
        # 获取所有txt文件
        txt_files = list(self.rules_dir.glob("*.txt"))
        if not txt_files:
            logger.warning(f"在 {self.rules_dir} 目录中未找到txt文件")
            return
        
        logger.info(f"找到 {len(txt_files)} 个txt文件，开始处理...")
        
        # 逐个处理文件
        success_files = []
        failed_files = []
        
        for txt_file in txt_files:
            try:
                self.process_single_file(txt_file, max_workers, max_retries)
                success_files.append(txt_file.name)
            except Exception as e:
                failed_files.append(f"{txt_file.name}: {e}")
                logger.error(f"处理文件 {txt_file.name} 时发生错误: {e}")
                continue
        
        # 输出处理摘要
        logger.info("所有文件处理完成！")
        logger.info(f"成功处理: {len(success_files)}/{len(txt_files)} 个文件")
        
        if failed_files:
            logger.warning(f"失败处理: {len(failed_files)}/{len(txt_files)} 个文件")
            logger.warning("失败的文件列表:")
            for failed in failed_files:
                logger.warning(f"  - {failed}")

def main():
    """
    主函数
    """
    # 初始化处理器
    processor = ListRuleProcessor(
        rules_dir="rules",
        clash_dir="Clash"
    )
    
    # 处理所有文件（带重试）
    processor.process_all_files(max_workers=10, max_retries=3)
    
    # 打印最终统计
    print()
    print("最终统计:")
    print(f"规则文件目录: {processor.rules_dir.absolute()}")
    print(f"输出目录: {processor.clash_dir.absolute()}")
    
    # 统计生成的list文件
    list_files = list(processor.clash_dir.glob("*.list"))
    if list_files:
        print(f"生成的list文件: {len(list_files)} 个")
        
        # 显示每个文件的信息
        total_rules = 0
        for file in list_files:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    # 从文件头读取规则数量
                    rule_count = 0
                    generation_time = "未知"
                    for line in lines[:5]:  # 只检查前5行
                        if line.startswith('# 规则数量:'):
                            rule_count = int(line.split(':')[1].strip())
                        elif line.startswith('# 生成时间:'):
                            generation_time = line.split(':')[1].strip()
                    
                    if rule_count == 0:  # 如果没有从头部读取到，则计算实际规则数
                        rule_count = len([l for l in lines if l.strip() and not l.startswith('#')])
                    
                    total_rules += rule_count
                    
                    print(f"  - {file.name}")
                    print(f"    生成时间: {generation_time}")
                    print(f"    规则数量: {rule_count}")
                    print()
            except Exception as e:
                print(f"  - {file.name} (读取失败: {e})")
        
        print(f"总计规则数: {total_rules}")
    else:
        print("未生成任何list文件")

if __name__ == "__main__":
    main()
