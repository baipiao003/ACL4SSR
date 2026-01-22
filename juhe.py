import os
import re
import requests
import logging
import time
from typing import List, Set, Optional, Tuple, Dict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.parse

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
    
    def extract_and_deduplicate_links(self, content: str) -> List[str]:
        """
        从内容中提取所有链接并去重（保持顺序）
        
        Args:
            content: 文件内容
            
        Returns:
            去重后的链接列表（保持顺序）
        """
        links = []
        seen_links = set()  # 用于去重
        
        # 改进的正则表达式，支持更多字符
        url_pattern = re.compile(
            r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:[/\w\.\-?=%&+#\'\(\)~]*)?',
            re.IGNORECASE
        )
        
        try:
            # 首先尝试按行处理，每行可能包含一个URL
            lines = content.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    # 保留空行
                    links.append('')
                    continue
                
                # 保留注释行
                if line.startswith('#'):
                    links.append(line)
                    continue
                
                # 尝试查找行中的URL
                found_urls = url_pattern.findall(line)
                if found_urls:
                    for url in found_urls:
                        url = url.strip()
                        # 清理URL结尾的标点符号
                        url = self._clean_url(url)
                        if url and url not in seen_links and self._is_list_rule_link(url):
                            seen_links.add(url)
                            links.append(url)
                
                # 如果没有找到匹配的URL，但整行看起来像是一个URL，直接尝试
                elif self._looks_like_url(line):
                    cleaned_line = self._clean_url(line)
                    if cleaned_line and cleaned_line not in seen_links and self._is_list_rule_link(cleaned_line):
                        seen_links.add(cleaned_line)
                        links.append(cleaned_line)
                else:
                    # 保留非URL行（可能是注释或其他内容）
                    links.append(line)
            
            # 如果按行处理没找到足够的链接，再尝试在整个内容中查找
            if len(seen_links) == 0:
                found_urls = url_pattern.findall(content)
                for url in found_urls:
                    url = url.strip()
                    url = self._clean_url(url)
                    if url and url not in seen_links and self._is_list_rule_link(url):
                        seen_links.add(url)
                        links.append(url)
                    
            return links
        except Exception as e:
            logger.error(f"解析内容失败: {e}")
            return []
    
    def _clean_url(self, url: str) -> str:
        """
        清理URL字符串，移除末尾的标点符号
        
        Args:
            url: 原始URL字符串
            
        Returns:
            清理后的URL
        """
        if not url:
            return url
        
        # 移除URL末尾的常见标点符号
        url = url.rstrip('.,;:!?\'"')
        
        # 确保URL以http或https开头
        if not url.startswith(('http://', 'https://')):
            # 尝试在前面添加https://
            if url.startswith('//'):
                url = 'https:' + url
            elif '://' not in url and '.' in url:
                # 可能是不带协议的URL，尝试添加https://
                url = 'https://' + url
        
        return url
    
    def _looks_like_url(self, text: str) -> bool:
        """
        判断文本是否看起来像URL
        
        Args:
            text: 文本字符串
            
        Returns:
            是否像URL
        """
        if not text:
            return False
        
        # 检查是否包含常见的URL模式
        url_indicators = ['http://', 'https://', 'www.', '.com', '.net', '.org', '.io', '.list', '.yaml']
        
        for indicator in url_indicators:
            if indicator in text.lower():
                return True
        
        return False
    
    def _is_list_rule_link(self, link: str) -> bool:
        """
        判断链接是否为list规则链接
        
        Args:
            link: 链接字符串
            
        Returns:
            是否为list规则链接
        """
        if not link:
            return False
        
        # 转换为小写方便比较
        link_lower = link.lower()
        
        # 检查是否包含常见规则文件扩展名
        list_extensions = ['.list', '.yaml', '.yml', '.txt', '.conf', '.rule', '.ruleset']
        
        # 检查是否是 GitHub raw 链接
        if 'raw.githubusercontent.com' in link_lower:
            # GitHub raw 链接可能是规则文件，检查文件扩展名
            for ext in list_extensions:
                if ext in link_lower:
                    return True
            # 如果没有明确扩展名，但看起来像规则文件
            if '/master/rule/' in link_lower or '/master/' in link_lower:
                return True
            return False
        
        # 检查是否包含常见规则文件扩展名或关键词
        list_keywords = ['.list', '.yaml', '.yml', '.txt', 'clash', 'rule', 'ruleset']
        for keyword in list_keywords:
            if keyword in link_lower:
                return True
        
        return False
    
    def deduplicate_links_in_files(self):
        """
        第一部分：检查并删除rules文件夹中txt文件的重复链接
        """
        logger.info("检查并删除重复链接...")
        
        # 获取所有txt文件
        txt_files = list(self.rules_dir.glob("*.txt"))
        if not txt_files:
            logger.warning(f"在 {self.rules_dir} 目录中未找到txt文件")
            return
        
        logger.info(f"找到 {len(txt_files)} 个txt文件，开始检查重复链接...")
        
        for txt_file in txt_files:
            try:
                logger.info(f"处理文件: {txt_file.name}")
                
                # 读取文件内容
                content = self.read_file_with_retry(txt_file)
                if content is None:
                    logger.error(f"无法读取文件 {txt_file.name}，跳过处理")
                    continue
                
                # 提取并去重链接
                original_lines = content.split('\n')
                deduplicated_links = self.extract_and_deduplicate_links(content)
                
                # 统计原始链接数
                original_urls = []
                for line in original_lines:
                    line = line.strip()
                    if line and not line.startswith('#') and self._looks_like_url(line):
                        original_urls.append(line)
                
                original_count = len(original_urls)
                deduplicated_count = len([link for link in deduplicated_links if link and not link.startswith('#') and self._looks_like_url(link)])
                
                duplicates_removed = original_count - deduplicated_count
                
                # 保存文件
                try:
                    with open(txt_file, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(deduplicated_links))
                    
                    if duplicates_removed > 0:
                        logger.info(f"  ✓ 已删除 {duplicates_removed} 个重复链接")
                        logger.info(f"    原始: {original_count} 个链接，去重后: {deduplicated_count} 个链接")
                        logger.info(f"    ✓ 已保存到 {txt_file.name}")
                    else:
                        logger.info(f"  ✓ 无重复链接")
                        logger.info(f"    总共: {original_count} 个链接")
                        logger.info(f"    ✓ 已保存到 {txt_file.name}")
                    
                except Exception as save_error:
                    logger.error(f"    ✗ 保存文件失败: {save_error}")
                    continue
                
            except Exception as e:
                logger.error(f"处理文件 {txt_file.name} 时发生错误: {e}")
                continue
        
        # 输出去重统计
        logger.info("去重完成！")
        logger.info("=" * 60)
    
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
        
        # 改进的正则表达式，支持更多字符
        url_pattern = re.compile(
            r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:[/\w\.\-?=%&+#\'\(\)~]*)?',
            re.IGNORECASE
        )
        
        # 带重试读取文件
        content = self.read_file_with_retry(txt_file, max_retries)
        if content is None:
            logger.error(f"无法读取文件 {txt_file.name}，跳过处理")
            return []
        
        try:
            # 首先尝试按行处理，每行可能包含一个URL
            lines = content.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # 尝试查找行中的URL
                found_urls = url_pattern.findall(line)
                if found_urls:
                    for url in found_urls:
                        url = url.strip()
                        # 清理URL结尾的标点符号
                        url = self._clean_url(url)
                        if url and url not in seen_links and self._is_list_rule_link(url):
                            seen_links.add(url)
                            links.append(url)
                
                # 如果没有找到匹配的URL，但整行看起来像是一个URL，直接尝试
                elif self._looks_like_url(line):
                    cleaned_line = self._clean_url(line)
                    if cleaned_line and cleaned_line not in seen_links and self._is_list_rule_link(cleaned_line):
                        seen_links.add(cleaned_line)
                        links.append(cleaned_line)
            
            # 如果按行处理没找到足够的链接，再尝试在整个内容中查找
            if len(links) == 0:
                found_urls = url_pattern.findall(content)
                for url in found_urls:
                    url = url.strip()
                    url = self._clean_url(url)
                    if url and url not in seen_links and self._is_list_rule_link(url):
                        seen_links.add(url)
                        links.append(url)
                    
            return links
        except Exception as e:
            logger.error(f"解析文件 {txt_file.name} 内容失败: {e}")
            return []
    
    def download_with_retry(self, url: str, max_retries: int = 3) -> Tuple[bool, Optional[str], int]:
        """
        带重试的下载函数
        
        Args:
            url: 要下载的URL
            max_retries: 最大重试次数
            
        Returns:
            (是否成功, 下载的内容, 重试次数)
        """
        retry_count = 0
        last_exception = None
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/plain, text/*, application/x-yaml, application/yaml, application/xml'
        }
        
        while retry_count <= max_retries:
            try:
                # 确保URL是编码正确的
                try:
                    parsed_url = urllib.parse.urlparse(url)
                    if not parsed_url.scheme:
                        url = 'https://' + url
                        parsed_url = urllib.parse.urlparse(url)
                except:
                    pass
                
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                
                content = response.text
                
                # 检查内容是否为 HTML 页面
                if content.startswith('<!DOCTYPE html') or content.startswith('<html'):
                    logger.warning(f"URL {url} 返回的是HTML页面，不是规则文件")
                    return False, None, retry_count
                
                # 检查是否包含明显的 HTML 标签
                html_tags = ['<html', '<head>', '<body>', '<div class=', '<!DOCTYPE']
                for tag in html_tags:
                    if tag.lower() in content[:1000].lower():
                        logger.warning(f"URL {url} 包含HTML标签，不是规则文件")
                        return False, None, retry_count
                
                # 检查是否看起来像规则文件（包含常见规则前缀）
                rule_prefixes = ['DOMAIN-', 'DOMAIN,', 'DOMAIN-SUFFIX,', 'IP-CIDR,', 'PROCESS-NAME,', 
                                '# NAME:', '# AUTHOR:', '# REPO:', '# UPDATED:', '# TOTAL:']
                is_rule_file = False
                lines = content.split('\n')[:20]  # 检查前20行
                for line in lines:
                    line_upper = line.upper()
                    for prefix in rule_prefixes:
                        if line_upper.startswith(prefix.upper()):
                            is_rule_file = True
                            break
                    if is_rule_file:
                        break
                
                if not is_rule_file and len(content) > 1000:
                    # 如果没有找到规则前缀，且内容较长，可能是网页
                    logger.warning(f"URL {url} 没有检测到规则格式，可能是网页")
                    return False, None, retry_count
                
                return True, content, retry_count
                
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
                    return False, None, retry_count
                    
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
        
        return False, None, retry_count
    
    def process_single_file(self, txt_file: Path, max_workers: int = 5, max_retries: int = 3):
        """
        第二部分：处理单个txt文件（下载并生成list文件）
        
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
        logger.info(f"发现 {total_links} 个链接，开始下载...")
        
        # 创建一个字典来跟踪每个链接的进度和结果
        link_status = {}
        for idx, link in enumerate(links, 1):
            link_status[link] = {
                'index': idx,
                'total': total_links,
                'content': None,
                'success': False,
                'error': None,
                'retry_count': 0
            }
        
        # 记录失败的链接
        failed_links = []
        
        # 并发下载所有链接内容（带重试）
        all_contents = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.download_with_retry, link, max_retries): link for link in links}
            
            # 等待所有下载完成
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    success, content, retry_count = future.result()
                    link_status[url]['retry_count'] = retry_count
                    
                    if success and content:
                        link_status[url]['content'] = content
                        link_status[url]['success'] = True
                        all_contents.append(content)
                    else:
                        link_status[url]['success'] = False
                        link_status[url]['error'] = "下载失败或内容无效"
                        failed_links.append(url)
                except Exception as e:
                    link_status[url]['success'] = False
                    link_status[url]['error'] = str(e)
                    failed_links.append(url)
        
        # 按原始顺序显示下载结果
        success_count = 0
        for link in links:
            status = link_status[link]
            if status['success']:
                retry_info = f" (重试{status['retry_count']}次)" if status['retry_count'] > 0 else ""
                logger.info(f"✓ 成功下载 [{status['index']}/{status['total']}]{retry_info}: {link}")
                success_count += 1
            else:
                if status['error'] == "下载失败或内容无效":
                    logger.warning(f"✗ 下载失败或内容无效 [{status['index']}/{status['total']}]: {link}")
                else:
                    retry_info = f" (已重试{status['retry_count']}次)" if status['retry_count'] > 0 else ""
                    logger.error(f"✗ 下载失败 [{status['index']}/{status['total']}]{retry_info}: {link} - {status['error']}")
        
        fail_count = total_links - success_count
        if fail_count > 0:
            logger.warning(f"下载完成: {success_count}/{total_links} 成功, {fail_count}/{total_links} 失败")
        else:
            logger.info(f"下载完成: {success_count}/{total_links} 全部成功")
        
        # 如果有失败的链接，记录到文件
        if failed_links:
            failed_file = txt_file.stem + '_failed.txt'
            failed_file_path = self.clash_dir / failed_file
            try:
                with open(failed_file_path, 'w', encoding='utf-8') as f:
                    f.write('# 失败的链接列表\n')
                    f.write('# 生成时间: ' + time.strftime('%Y-%m-%d %H:%M:%S') + '\n\n')
                    for link in failed_links:
                        f.write(link + '\n')
                logger.warning(f"✓ 已保存失败的链接到 {failed_file}")
            except Exception as e:
                logger.error(f"✗ 保存失败链接文件失败: {e}")
        
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
                    # 跳过空行和特定注释
                    if line and not line.startswith('# 生成时间:') and not line.startswith('# 规则数量:'):
                        if line not in seen_lines:
                            seen_lines.add(line)
                            combined_content.append(line)
            
            # 按规则类型排序（可选）
            domain_rules = []
            domain_suffix_rules = []
            ip_cidr_rules = []
            other_rules = []
            
            for rule in combined_content:
                if rule.startswith('DOMAIN,'):
                    domain_rules.append(rule)
                elif rule.startswith('DOMAIN-SUFFIX,'):
                    domain_suffix_rules.append(rule)
                elif rule.startswith('IP-CIDR,'):
                    ip_cidr_rules.append(rule)
                else:
                    other_rules.append(rule)
            
            # 重新组合排序后的规则
            sorted_content = []
            if domain_rules:
                sorted_content.append('# DOMAIN规则')
                sorted_content.extend(sorted(domain_rules))
                sorted_content.append('')
            
            if domain_suffix_rules:
                sorted_content.append('# DOMAIN-SUFFIX规则')
                sorted_content.extend(sorted(domain_suffix_rules))
                sorted_content.append('')
            
            if ip_cidr_rules:
                sorted_content.append('# IP-CIDR规则')
                sorted_content.extend(sorted(ip_cidr_rules))
                sorted_content.append('')
            
            if other_rules:
                sorted_content.append('# 其他规则')
                sorted_content.extend(sorted(other_rules))
            
            # 生成文件头
            rule_count = len(combined_content)
            generation_time = time.strftime('%Y-%m-%d %H:%M:%S')
            header = f"""# 生成时间: {generation_time}
# 规则数量: {rule_count}
# 来源文件: {txt_file.name}
# 成功链接: {success_count}/{total_links}

"""
            
            # 写入文件
            with open(list_file_path, 'w', encoding='utf-8') as f:
                f.write(header + '\n'.join(sorted_content))
            
            logger.info(f"✓ 成功保存到 {list_file_path}, 共 {rule_count} 条规则")
            
        except Exception as e:
            logger.error(f"✗ 保存文件失败 {list_file_path}: {e}")
    
    def process_all_files(self, max_workers: int = 5, max_retries: int = 3):
        """
        第二部分：处理rules目录下所有txt文件
        """
        logger.info("下载链接并生成list文件...")
        
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
        logger.info(f"成功处理: {len(success_files)} 个文件")
        
        if failed_files:
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
    
    print("=" * 60)
    print("Clash规则聚合器 v2.0")
    print("=" * 60)
    
    # 第一部分：去重链接
    processor.deduplicate_links_in_files()
    
    # 第二部分：下载并生成list文件
    processor.process_all_files(max_workers=10, max_retries=3)
    
    # 打印最终统计
    print()
    print("最终统计:")
    print(f"规则文件目录: {processor.rules_dir.absolute()}")
    print(f"输出目录: {processor.clash_dir.absolute()}")
    
    # 统计生成的list文件
    list_files = list(processor.clash_dir.glob("*.list"))
    failed_files = list(processor.clash_dir.glob("*_failed.txt"))
    
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
                    for line in lines[:10]:  # 只检查前10行
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
    
    if failed_files:
        print(f"失败的链接记录: {len(failed_files)} 个")
        for file in failed_files:
            print(f"  - {file.name}")

if __name__ == "__main__":
    main()
