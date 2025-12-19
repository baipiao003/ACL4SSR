#!/usr/bin/env python3
"""
Clash规则去重脚本
功能：去除Clash规则文件中的重复规则，支持批量处理
注意：直接修改原文件，不创建备份
作者：优化版
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class RuleFileStats:
    """规则文件统计信息"""
    file_name: str
    input_rules: int
    output_rules: int
    removed_count: int
    rule_type_counts: Dict[str, int]
    processing_time: float
    file_size_before: int
    file_size_after: int
    
@dataclass
class ProcessingResult:
    """处理结果"""
    files_processed: int
    total_removed: int
    details: List[RuleFileStats]
    success: bool
    error_message: Optional[str] = None

class ClashRuleProcessor:
    """Clash规则处理器"""
    
    # 支持的规则类型（针对.list文件优化）
    SUPPORTED_RULE_TYPES = {
        'DOMAIN': ',',
        'DOMAIN-SUFFIX': ',',
        'DOMAIN-KEYWORD': ',',
        'IP-CIDR': ',',
        'IP-ASN': ',',
        'SRC-IP-CIDR': ',',
        'GEOIP': ',',
        'DST-PORT': ',',
        'SRC-PORT': ',',
        'PROCESS-NAME': ',',
        'RULE-SET': ',',
        'MATCH': '',  # MATCH规则没有参数
    }
    
    def __init__(self, verbose: bool = False):
        """
        初始化处理器
        
        Args:
            verbose: 是否显示详细输出
        """
        self.verbose = verbose
        self._processed_files = 0
        self._total_removed = 0
        
    def _extract_rule_value(self, line: str) -> Tuple[Optional[str], str, str]:
        """
        从规则行中提取规则类型、值和完整规则
        
        Returns:
            (rule_type, rule_value, full_rule)
        """
        line = line.strip()
        
        # 检查支持的规则类型
        for rule_type, separator in self.SUPPORTED_RULE_TYPES.items():
            if line.startswith(rule_type):
                if separator:  # 有分隔符的规则
                    parts = line.split(separator, 1)
                    if len(parts) >= 2:
                        rule_value = parts[1].strip()
                        return rule_type, rule_value, line
                else:  # 没有分隔符的规则（如MATCH）
                    rule_value = line
                    return rule_type, rule_value, line
        
        # 未知规则类型或非规则行
        return None, line, line
    
    def _is_rule_line(self, line: str) -> bool:
        """判断是否为规则行（非空行、非注释行）"""
        stripped = line.strip()
        return bool(stripped) and not stripped.startswith('#')
    
    def process_file(self, file_path: Path) -> Optional[RuleFileStats]:
        """
        处理单个.list规则文件
        
        Returns:
            RuleFileStats or None if failed
        """
        if not file_path.exists():
            print(f"  ❌ 文件不存在: {file_path}")
            return None
        
        if file_path.suffix != '.list':
            print(f"  ⚠️  跳过非.list文件: {file_path}")
            return None
        
        start_time = datetime.now()
        
        try:
            # 记录原始文件大小
            file_size_before = file_path.stat().st_size
            
            # 读取文件
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
                original_lines = original_content.splitlines()
            
            # 初始化数据结构
            seen_rules: Dict[str, Set[str]] = {rt: set() for rt in self.SUPPORTED_RULE_TYPES}
            output_lines: List[str] = []
            rule_type_counts: Dict[str, int] = {rt: 0 for rt in self.SUPPORTED_RULE_TYPES}
            rule_type_counts['OTHER'] = 0
            rule_type_counts['COMMENT'] = 0
            
            input_rule_count = 0
            skipped_rules = []
            
            # 处理每一行
            for i, line in enumerate(original_lines, 1):
                # 保持原始行的格式（包括缩进）
                stripped_line = line.rstrip()
                
                # 空行
                if not stripped_line:
                    output_lines.append(line)
                    continue
                
                # 注释行
                if stripped_line.startswith('#'):
                    output_lines.append(line)
                    rule_type_counts['COMMENT'] += 1
                    continue
                
                # 解析规则
                rule_type, rule_value, full_rule = self._extract_rule_value(stripped_line)
                
                if rule_type:  # 是支持的规则类型
                    input_rule_count += 1
                    
                    # 检查是否重复
                    if rule_value in seen_rules[rule_type]:
                        if self.verbose:
                            skipped_rules.append((i, stripped_line[:80]))
                        continue
                    
                    # 记录规则
                    seen_rules[rule_type].add(rule_value)
                    rule_type_counts[rule_type] += 1
                    output_lines.append(line)
                else:  # 其他行（如URL规则、未知规则等）
                    output_lines.append(line)
                    rule_type_counts['OTHER'] += 1
            
            # 计算输出规则数
            output_rule_count = sum(rule_type_counts[rt] for rt in self.SUPPORTED_RULE_TYPES)
            removed_count = input_rule_count - output_rule_count
            
            # 如果有更改，写入文件
            new_content = '\n'.join(output_lines)
            if new_content != original_content:
                # 检查文件是否只改变了行尾
                if new_content.replace('\r\n', '\n') != original_content.replace('\r\n', '\n'):
                    with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                        f.write(new_content)
                    
                    # 显示跳过的规则
                    if self.verbose and skipped_rules:
                        print(f"  ⚠️  跳过了 {len(skipped_rules)} 条重复规则:")
                        for line_num, rule in skipped_rules[:3]:  # 只显示前3条
                            print(f"    第{line_num}行: {rule}{'...' if len(rule) >= 80 else ''}")
                        if len(skipped_rules) > 3:
                            print(f"    ... 还有 {len(skipped_rules) - 3} 条")
                else:
                    removed_count = 0  # 只有行尾变化，不算作实际去重
            
            # 记录处理后文件大小
            file_size_after = file_path.stat().st_size
            
            # 计算处理时间
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # 更新统计
            self._processed_files += 1
            self._total_removed += removed_count
            
            return RuleFileStats(
                file_name=file_path.name,
                input_rules=input_rule_count,
                output_rules=output_rule_count,
                removed_count=removed_count,
                rule_type_counts=rule_type_counts,
                processing_time=processing_time,
                file_size_before=file_size_before,
                file_size_after=file_size_after
            )
            
        except UnicodeDecodeError:
            print(f"  ❌ 文件编码错误，请使用UTF-8编码: {file_path}")
            return None
        except PermissionError:
            print(f"  ❌ 没有写入权限: {file_path}")
            return None
        except Exception as e:
            print(f"  ❌ 处理文件时出错: {file_path} - {e}")
            return None
    
    def process_folder(self, folder_path: Path) -> ProcessingResult:
        """
        处理文件夹中的所有.list规则文件
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            ProcessingResult
        """
        if not folder_path.exists():
            return ProcessingResult(
                files_processed=0,
                total_removed=0,
                details=[],
                success=False,
                error_message=f"文件夹不存在: {folder_path}"
            )
        
        if not folder_path.is_dir():
            return ProcessingResult(
                files_processed=0,
                total_removed=0,
                details=[],
                success=False,
                error_message=f"路径不是文件夹: {folder_path}"
            )
        
        # 查找.list文件
        rule_files = sorted(folder_path.glob("*.list"))
        if not rule_files:
            return ProcessingResult(
                files_processed=0,
                total_removed=0,
                details=[],
                success=False,
                error_message=f"未找到 .list 文件"
            )
        
        # 显示文件信息
        print(f"📁 找到 {len(rule_files)} 个.list规则文件:")
        total_size = 0
        for file in rule_files:
            file_size = file.stat().st_size
            total_size += file_size
            rule_count = self._count_rules_in_file(file)
            print(f"  • {file.name} ({file_size:,} bytes, 约 {rule_count} 条规则)")
        
        print(f"📊 总计: {total_size:,} bytes")
        
        # 处理每个文件
        results = []
        for file in rule_files:
            print(f"\n🔧 处理文件: {file.name}")
            
            result = self.process_file(file)
            if result:
                results.append(result)
                if result.removed_count > 0:
                    size_change = result.file_size_after - result.file_size_before
                    size_change_str = f"(大小: {size_change:+,} bytes)" if size_change != 0 else ""
                    print(f"  ✅ 移除了 {result.removed_count} 条重复规则 {size_change_str}")
                    print(f"    原始: {result.input_rules} 条 → 现在: {result.output_rules} 条")
                else:
                    print(f"  ℹ️  没有发现重复规则")
            else:
                print(f"  ❌ 处理失败")
        
        return ProcessingResult(
            files_processed=len(results),
            total_removed=self._total_removed,
            details=results,
            success=len(results) > 0
        )
    
    def _count_rules_in_file(self, file_path: Path) -> int:
        """快速统计文件中的规则数量"""
        try:
            count = 0
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith('#'):
                        count += 1
            return count
        except:
            return 0

class ReportGenerator:
    """报告生成器"""
    
    @staticmethod
    def generate_detailed_report(result: ProcessingResult, show_all: bool = False) -> str:
        """生成详细报告"""
        if not result.success:
            return f"❌ 处理失败: {result.error_message}"
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("📊 CLASH规则去重处理报告")
        report_lines.append("=" * 80)
        
        # 汇总信息
        report_lines.append("📈 汇总统计:")
        report_lines.append(f"  • 处理文件数: {result.files_processed}")
        report_lines.append(f"  • 移除重复规则: {result.total_removed:,} 条")
        
        # 文件大小变化
        total_size_before = sum(r.file_size_before for r in result.details)
        total_size_after = sum(r.file_size_after for r in result.details)
        total_size_change = total_size_after - total_size_before
        
        report_lines.append(f"  • 文件大小变化: {total_size_change:+,} bytes")
        report_lines.append(f"  • 原始总大小: {total_size_before:,} bytes")
        report_lines.append(f"  • 处理后大小: {total_size_after:,} bytes")
        report_lines.append(f"  • 处理时间: {sum(r.processing_time for r in result.details):.2f}秒")
        
        report_lines.append("\n📋 文件详情:")
        report_lines.append("-" * 80)
        
        for stats in result.details:
            status = "✅ 已清理" if stats.removed_count > 0 else "ℹ️  无重复"
            size_change = stats.file_size_after - stats.file_size_before
            size_change_str = f"[{size_change:+,} bytes]" if size_change != 0 else ""
            
            report_lines.append(
                f"{stats.file_name:30} {status:15} "
                f"规则: {stats.output_rules:4} 条 "
                f"(移除 {stats.removed_count:3} 条) "
                f"{size_change_str:15}"
                f"[{stats.processing_time:.2f}s]"
            )
            
            if show_all and stats.removed_count > 0:
                for rule_type, count in sorted(stats.rule_type_counts.items()):
                    if count > 0 and rule_type not in ['COMMENT', 'OTHER']:
                        report_lines.append(f"      {rule_type:15}: {count:4} 条")
        
        # 按规则类型统计总数
        report_lines.append("\n📊 规则类型统计:")
        report_lines.append("-" * 80)
        
        type_totals = {}
        for stats in result.details:
            for rule_type, count in stats.rule_type_counts.items():
                if rule_type not in ['COMMENT', 'OTHER']:
                    type_totals[rule_type] = type_totals.get(rule_type, 0) + count
        
        for rule_type, count in sorted(type_totals.items()):
            if count > 0:
                report_lines.append(f"  {rule_type:15} {count:6,} 条")
        
        # 性能分析
        if len(result.details) > 1:
            report_lines.append("\n⚡ 性能分析:")
            report_lines.append("-" * 80)
            avg_time = sum(r.processing_time for r in result.details) / len(result.details)
            avg_rules = sum(r.output_rules for r in result.details) / len(result.details)
            report_lines.append(f"  • 平均处理时间: {avg_time:.3f}秒/文件")
            report_lines.append(f"  • 平均规则数: {avg_rules:.0f}条/文件")
            report_lines.append(f"  • 最快文件: {min(r.processing_time for r in result.details):.3f}秒")
            report_lines.append(f"  • 最慢文件: {max(r.processing_time for r in result.details):.3f}秒")
        
        report_lines.append("=" * 80)
        
        return '\n'.join(report_lines)
    
    @staticmethod
    def generate_summary_report(result: ProcessingResult) -> str:
        """生成简要报告"""
        if not result.success:
            return f"❌ 处理失败: {result.error_message}"
        
        total_size_before = sum(r.file_size_before for r in result.details)
        total_size_after = sum(r.file_size_after for r in result.details)
        total_size_change = total_size_after - total_size_before
        
        size_change_str = f"(大小变化: {total_size_change:+,} bytes)" if total_size_change != 0 else ""
        
        return (
            f"✅ 处理完成! "
            f"共处理 {result.files_processed} 个文件, "
            f"移除 {result.total_removed:,} 条重复规则 "
            f"{size_change_str}."
        )

def find_clash_folders(current_dir: Path) -> List[Path]:
    """查找Clash文件夹"""
    possible_names = ['Clash', 'clash', 'CLASH', 'rules']
    found_folders = []
    
    for folder_name in possible_names:
        test_path = current_dir / folder_name
        if test_path.exists() and test_path.is_dir():
            # 检查是否有.list文件
            list_files = list(test_path.glob("*.list"))
            if list_files:
                found_folders.append(test_path)
    
    return found_folders

def setup_argument_parser() -> argparse.ArgumentParser:
    """设置命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description='Clash规则去重工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                         # 自动查找Clash文件夹
  %(prog)s ./Clash                 # 指定Clash文件夹路径
  %(prog)s -f rule.list            # 处理单个文件
  %(prog)s -v                      # 显示详细信息
        
注意: 直接修改原文件，不创建备份
        """
    )
    
    parser.add_argument(
        'path',
        nargs='?',
        help='Clash规则文件夹路径'
    )
    
    parser.add_argument(
        '-f', '--file',
        help='处理单个.list文件'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细信息'
    )
    
    parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='跳过确认提示'
    )
    
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='静默模式，只显示错误'
    )
    
    return parser

def main():
    """主函数"""
    print("=" * 60)
    print("🛠️  Clash规则去重工具 - 专注.list文件")
    print("=" * 60)
    
    # 解析命令行参数
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # 设置静默模式
    if args.quiet:
        args.verbose = False
    
    # 确定目标路径
    target_path = None
    if args.file:
        target_path = Path(args.file).resolve()
        if not target_path.exists():
            print(f"❌ 文件不存在: {target_path}")
            sys.exit(1)
        if target_path.suffix != '.list':
            print(f"❌ 只支持.list文件: {target_path}")
            sys.exit(1)
    elif args.path:
        target_path = Path(args.path).resolve()
        if not target_path.exists():
            print(f"❌ 路径不存在: {target_path}")
            sys.exit(1)
    else:
        # 自动查找
        current_dir = Path.cwd()
        if not args.quiet:
            print(f"📂 当前工作目录: {current_dir}")
        
        clash_folders = find_clash_folders(current_dir)
        
        if not clash_folders:
            print("❌ 未找到包含.list文件的Clash文件夹")
            if not args.quiet:
                print("\n请执行以下操作:")
                print("1. 将脚本放在Clash文件夹同级目录")
                print("2. 指定文件夹路径: python quchong.py ./Clash")
                print("3. 指定文件路径: python quchong.py -f rule.list")
            sys.exit(1)
        
        if len(clash_folders) == 1:
            target_path = clash_folders[0]
            if not args.quiet:
                print(f"✅ 找到Clash文件夹: {target_path}")
        else:
            print("🔍 找到多个Clash文件夹:")
            for i, folder in enumerate(clash_folders, 1):
                list_files = list(folder.glob("*.list"))
                print(f"  {i}. {folder} ({len(list_files)} 个.list文件)")
            
            try:
                choice = input(f"\n请选择 (1-{len(clash_folders)}): ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(clash_folders):
                    target_path = clash_folders[int(choice) - 1]
                else:
                    print("❌ 无效选择")
                    sys.exit(1)
            except (ValueError, KeyboardInterrupt):
                print("\n操作已取消")
                sys.exit(0)
    
    # 显示目标信息
    if target_path.is_file():
        file_size = target_path.stat().st_size
        print(f"🎯 目标文件: {target_path.name} ({file_size:,} bytes)")
    else:
        list_files = list(target_path.glob("*.list"))
        print(f"🎯 目标文件夹: {target_path} ({len(list_files)} 个.list文件)")
    
    # 警告信息
    print("⚠️  注意: 将直接在原文件上修改，不创建备份")
    print("-" * 60)
    
    # 确认提示
    if not args.yes and not args.file:
        response = input("❓ 确定要继续吗？(y/N): ").strip().lower()
        if response not in ['y', 'yes', 'Y']:
            print("操作已取消")
            return
    
    # 创建处理器
    processor = ClashRuleProcessor(verbose=args.verbose)
    
    # 处理文件或文件夹
    start_time = datetime.now()
    
    if target_path.is_file():
        result = processor.process_file(target_path)
        if result:
            process_result = ProcessingResult(
                files_processed=1,
                total_removed=result.removed_count,
                details=[result],
                success=True
            )
        else:
            process_result = ProcessingResult(
                files_processed=0,
                total_removed=0,
                details=[],
                success=False,
                error_message="处理文件失败"
            )
    else:
        process_result = processor.process_folder(target_path)
    
    # 生成并显示报告
    total_time = (datetime.now() - start_time).total_seconds()
    
    if process_result.success:
        if args.quiet:
            summary = ReportGenerator.generate_summary_report(process_result)
            print(summary)
        else:
            report = ReportGenerator.generate_detailed_report(process_result, args.verbose)
            print(report)
            print(f"\n⏱️  总处理时间: {total_time:.2f}秒")
    else:
        print(f"\n❌ {process_result.error_message}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n操作被用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 发生未预期错误: {e}")
        if '--verbose' in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(1)
