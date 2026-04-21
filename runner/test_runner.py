import json
import subprocess
import os
import sys
import tempfile
import re
import argparse
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional


class TestCaseNormalizer:
    """测试用例规范化处理器"""
    
    @staticmethod
    def normalize_input(input_text: str) -> str:
        """
        规范化输入文本
        处理：统一换行符、中文逗号转英文、统一大小写
        """
        # 统一换行符
        normalized = input_text.replace('\r\n', '\n').replace('\r', '\n')
        
        # 中文逗号转英文逗号（包括全角逗号）
        normalized = normalized.replace('，', ',').replace('、', ',')
        
        # 中文句号转英文换行（可选）
        normalized = normalized.replace('。', '\n')
        
        # 统一空格：多个连续空格转单个空格
        normalized = re.sub(r'[ \t]+', ' ', normalized)
        
        # 处理特殊字符：去除BOM头
        if normalized.startswith('\ufeff'):
            normalized = normalized[1:]
        
        # 统一地区名称大小写（首字母大写）
        lines = normalized.split('\n')
        normalized_lines = []
        region_found = False
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not region_found and line_stripped and not line_stripped[0].isdigit():
                # 第一行通常是地区
                region_map = {
                    'beijing': 'Beijing',
                    '北京': 'Beijing',
                    'xinjiang': 'Xinjiang',
                    '新疆': 'Xinjiang',
                    'tibet': 'Tibet',
                    '西藏': 'Tibet'
                }
                lower_line = line_stripped.lower()
                if lower_line in region_map:
                    normalized_lines.append(region_map[lower_line])
                    region_found = True
                    continue
                elif line_stripped and not any(c.isdigit() for c in line_stripped):
                    # 可能是地区名但未在映射中，保持原样但首字母大写
                    normalized_lines.append(line_stripped.capitalize())
                    region_found = True
                    continue
            normalized_lines.append(line)
        
        return '\n'.join(normalized_lines)
    
    @staticmethod
    def normalize_output(output_text: str) -> str:
        """
        规范化输出文本
        处理：去除多余空格、统一大小写、统一格式
        """
        if not output_text:
            return ""
        
        # 去除首尾空白
        normalized = output_text.strip()
        
        # 去除多余空格
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # 统一 key 为小写
        normalized = re.sub(r'(?i)(status)=', 'status=', normalized)
        normalized = re.sub(r'(?i)(final_payable)=', 'final_payable=', normalized)
        
        # 统一 value 格式
        normalized = normalized.lower()
        
        return normalized
    
    @staticmethod
    def validate_json_structure(data: dict) -> List[str]:
        """
        验证JSON文件结构是否正确
        检查：中英文逗号、括号匹配、字段完整性
        """
        errors = []
        
        # 检查是否包含 test_case 字段
        if 'test_case' not in data:
            errors.append("缺少 'test_case' 字段")
            return errors
        
        test_cases = data['test_case']
        if not isinstance(test_cases, list):
            errors.append("'test_case' 应该是数组类型")
            return errors
        
        for i, case in enumerate(test_cases):
            case_id = case.get('id', f'索引 {i}')
            
            # 检查必要字段
            if 'id' not in case:
                errors.append(f"用例 {case_id}: 缺少 'id' 字段")
            if 'input' not in case:
                errors.append(f"用例 {case_id}: 缺少 'input' 字段")
            if 'output' not in case:
                errors.append(f"用例 {case_id}: 缺少 'output' 字段")
            
            # 检查输入中的中英文符号混合问题
            input_text = case.get('input', '')
            if '，' in input_text:
                errors.append(f"用例 {case_id}: 输入中包含中文逗号 '，' (建议使用英文逗号)")
            if '。' in input_text:
                errors.append(f"用例 {case_id}: 输入中包含中文句号 '。' (建议使用换行)")
        
        return errors


class TestExecutor:
    """测试执行器"""
    
    def __init__(self, program_path: str):
        """
        初始化执行器
        :param program_path: 被测程序路径
        """
        self.program_path = Path(program_path)
        self.normalizer = TestCaseNormalizer()
        
        # 验证程序是否存在
        if not self.program_path.exists():
            raise FileNotFoundError(f"被测程序不存在: {program_path}")
        
        # 检查是否可执行
        if os.name == 'nt':  # Windows
            if self.program_path.suffix not in ['.exe', '.bat', '.cmd']:
                # 尝试添加.exe后缀
                alt_path = self.program_path.with_suffix('.exe')
                if alt_path.exists():
                    self.program_path = alt_path
        else:  # Unix/Linux/Mac
            if not os.access(self.program_path, os.X_OK):
                try:
                    os.chmod(self.program_path, 0o755)
                except:
                    pass
    
    def execute_program(self, input_text: str, timeout_seconds: int = 5) -> Tuple[str, str, int]:
        """
        执行被测程序
        :return: (stdout, stderr, return_code)
        """
        # 创建临时文件存储输入
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(input_text)
            temp_input_file = f.name
        
        try:
            # 执行程序，从临时文件读取输入
            with open(temp_input_file, 'r', encoding='utf-8') as stdin_file:
                result = subprocess.run(
                    [str(self.program_path)],
                    stdin=stdin_file,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds
                )
            
            return result.stdout.strip(), result.stderr.strip(), result.returncode
        
        except subprocess.TimeoutExpired:
            return "", f"执行超时 (>{timeout_seconds}秒)", -1
        except Exception as e:
            return "", f"执行错误: {str(e)}", -1
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_input_file)
            except:
                pass
    
    def compare_results(self, actual: str, expected: str) -> Tuple[bool, str, dict]:
        """
        比较实际输出和期望输出
        :return: (是否成功, 比较详情, 解析后的数值)
        """
        actual_norm = self.normalizer.normalize_output(actual)
        expected_norm = self.normalizer.normalize_output(expected)
        
        # 解析数值
        def parse_output(text: str) -> dict:
            result = {'status': None, 'final_payable': None}
            if not text:
                return result
            
            # 匹配 status=xxx
            status_match = re.search(r'status=(\w+)', text)
            if status_match:
                result['status'] = status_match.group(1)
            
            # 匹配 final_payable=xxx
            payable_match = re.search(r'final_payable=([\d.-]+)', text)
            if payable_match:
                try:
                    result['final_payable'] = float(payable_match.group(1))
                except:
                    result['final_payable'] = None
            
            return result
        
        actual_parsed = parse_output(actual_norm)
        expected_parsed = parse_output(expected_norm)
        
        # 比较
        details = {
            'actual_raw': actual,
            'expected_raw': expected,
            'actual_normalized': actual_norm,
            'expected_normalized': expected_norm,
            'actual_parsed': actual_parsed,
            'expected_parsed': expected_parsed
        }
        
        # 状态比较
        if actual_parsed['status'] != expected_parsed['status']:
            return False, f"状态不匹配: 期望 {expected_parsed['status']}, 实际 {actual_parsed['status']}", details
        
        # 数值比较（允许0.01的浮点误差）
        if actual_parsed['final_payable'] is not None and expected_parsed['final_payable'] is not None:
            diff = abs(actual_parsed['final_payable'] - expected_parsed['final_payable'])
            if diff < 0.01:
                return True, "PASS", details
            else:
                return False, f"金额不匹配: 期望 {expected_parsed['final_payable']}, 实际 {actual_parsed['final_payable']}, 差值 {diff:.2f}", details
        
        # 字符串完全匹配
        if actual_norm == expected_norm:
            return True, "PASS (完全匹配)", details
        else:
            return False, f"输出不匹配", details


class TestRunner:
    """测试运行器主类"""
    
    def __init__(self, program_path: str, testcases_path: str):
        """
        初始化测试运行器
        :param program_path: 被测程序路径
        :param testcases_path: 测试用例JSON文件路径
        """
        self.program_path = Path(program_path)
        self.testcases_path = Path(testcases_path)
        self.executor = None
        self.test_cases = []
        self.results = []
        self.compiled_program_path: Optional[Path] = None
        
        # 验证测试用例文件
        if not self.testcases_path.exists():
            raise FileNotFoundError(f"测试用例文件不存在: {testcases_path}")
        
        # 加载测试用例
        self._load_testcases()
    
    def _load_testcases(self):
        """加载并验证测试用例"""
        with open(self.testcases_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # 检查文件内容是否有中文字符问题
            if '，' in content or '。' in content:
                print(f"警告: 测试用例文件中包含中文标点符号")
            
            data = json.loads(content)
        
        # 验证JSON结构
        errors = self.executor.normalizer.validate_json_structure(data) if self.executor else []
        if errors:
            print("JSON结构警告:")
            for err in errors:
                print(f"  - {err}")
        
        self.test_cases = data.get('test_case', [])
        if not self.test_cases:
            raise ValueError("测试用例文件不包含 'test_case' 数组或数组为空")
        
        print(f"成功加载 {len(self.test_cases)} 个测试用例")

    def _prepare_program(self) -> Path:
        """准备被测程序：如果传入 C/C++ 源文件则先自动编译。"""
        source_path = self.program_path
        source_suffix = source_path.suffix.lower()
        cpp_suffixes = {'.cpp', '.cc', '.cxx', '.c'}

        if source_suffix not in cpp_suffixes:
            return source_path

        compiler_candidates = []
        cxx_env = os.environ.get('CXX')
        if cxx_env:
            compiler_candidates.append(cxx_env)
        compiler_candidates.extend(['g++', 'clang++'])

        compiler = None
        for candidate in compiler_candidates:
            if shutil.which(candidate):
                compiler = candidate
                break

        if compiler is None:
            raise RuntimeError('未找到可用 C/C++ 编译器，请安装 g++ 或 clang++，或设置环境变量 CXX。')

        exe_name = source_path.stem + ('_autobuild.exe' if os.name == 'nt' else '_autobuild')
        output_path = source_path.parent / exe_name

        compile_cmd = [
            compiler,
            '-std=c++17',
            '-O2',
            '-o',
            str(output_path),
            str(source_path),
        ]

        print(f'检测到源码输入，开始自动编译: {source_path}')
        result = subprocess.run(compile_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            err_text = (result.stderr or result.stdout or '未知编译错误').strip()
            raise RuntimeError(f'自动编译失败: {err_text}')

        self.compiled_program_path = output_path
        print(f'自动编译成功: {output_path}')
        return output_path
    
    def run(self) -> Dict:
        """运行所有测试"""
        # 初始化执行器（如传入源码则先自动编译）
        executable_path = self._prepare_program()
        self.executor = TestExecutor(str(executable_path))
        
        print(f"\n{'='*70}")
        print(f"自动化测试执行器")
        print(f"被测程序输入: {self.program_path}")
        print(f"实际执行文件: {self.executor.program_path}")
        print(f"测试用例: {self.testcases_path}")
        print(f"用例数量: {len(self.test_cases)}")
        print(f"{'='*70}\n")
        
        # 执行每个测试用例
        for i, case in enumerate(self.test_cases):
            result = self._run_single_test(case, i)
            self.results.append(result)
            self._print_result(result)
        
        # 生成汇总
        return self._generate_summary()
    
    def _run_single_test(self, case: Dict, index: int) -> Dict:
        """运行单个测试用例"""
        case_id = case.get('id', f'CASE_{index+1:03d}')
        raw_input = case.get('input', '')
        expected_output = case.get('output', '')
        
        start_time = datetime.now()
        
        # 规范化输入
        normalized_input = self.executor.normalizer.normalize_input(raw_input)
        
        # 执行程序
        stdout, stderr, return_code = self.executor.execute_program(normalized_input)
        
        end_time = datetime.now()
        execution_time_ms = (end_time - start_time).total_seconds() * 1000
        
        # 比较结果
        if stderr or return_code != 0:
            success = False
            message = f"程序执行异常 (返回码: {return_code})"
            if stderr:
                message += f", 错误: {stderr[:200]}"
            comparison_details = {}
        else:
            success, message, comparison_details = self.executor.compare_results(stdout, expected_output)
        
        return {
            'id': case_id,
            'index': index,
            'input': {
                'raw': raw_input,
                'normalized': normalized_input
            },
            'expected_output': expected_output,
            'actual_output': stdout,
            'stderr': stderr,
            'return_code': return_code,
            'success': success,
            'message': message,
            'execution_time_ms': round(execution_time_ms, 2),
            'comparison_details': comparison_details,
            'timestamp': end_time.isoformat()
        }
    
    def _print_result(self, result: Dict):
        """打印单个测试结果"""
        icon = "✓" if result['success'] else "✗"
        status = "PASS" if result['success'] else "FAIL"
        print(f"{icon} [{result['id']}] {status} - {result['message']} ({result['execution_time_ms']}ms)")
        
        if not result['success'] and result.get('comparison_details'):
            details = result['comparison_details']
            if 'actual_parsed' in details and 'expected_parsed' in details:
                actual = details['actual_parsed']
                expected = details['expected_parsed']
                if actual.get('final_payable') != expected.get('final_payable'):
                    print(f"    期望金额: {expected.get('final_payable')}, 实际金额: {actual.get('final_payable')}")
    
    def _generate_summary(self) -> Dict:
        """生成测试汇总"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r['success'])
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        summary = {
            'test_info': {
                'program_path': str(self.program_path),
                'executable_path': str(self.executor.program_path) if self.executor else str(self.program_path),
                'testcases_path': str(self.testcases_path),
                'execution_time': datetime.now().isoformat()
            },
            'summary': {
                'total_tests': total,
                'passed': passed,
                'failed': failed,
                'pass_rate': f"{pass_rate:.2f}%"
            },
            'results': self.results,
            'failed_cases': [
                {
                    'id': r['id'],
                    'message': r['message'],
                    'expected': r['expected_output'],
                    'actual': r['actual_output']
                }
                for r in self.results if not r['success']
            ]
        }
        
        # 打印汇总
        print(f"\n{'='*70}")
        print(f"测试完成!")
        print(f"{'='*70}")
        print(f"总计: {total} | 通过: {passed} | 失败: {failed} | 通过率: {pass_rate:.2f}%")
        print(f"{'='*70}")
        
        if failed > 0:
            print(f"\n失败用例列表:")
            for r in summary['failed_cases']:
                print(f"  [{r['id']}] {r['message']}")
        
        return summary
    
    def save_report(self, output_path: str = None) -> str:
        """保存测试报告为JSON文件"""
        if not self.results:
            raise ValueError("没有测试结果，请先运行测试")
        
        summary = self._generate_summary()
        
        if output_path is None:
            # 生成默认文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f"test_report_{timestamp}.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        print(f"\n测试报告已保存: {output_path}")
        return output_path


def main():
    """主函数 - 命令行入口"""
    parser = argparse.ArgumentParser(
        description='自动化测试执行器 - 电商购物车结算系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python test_runner.py --program ./checkout --testcases white_box_test_cases.json
  python test_runner.py -p ./checkout.exe -t test_cases.json -o report.json
        '''
    )
    
    parser.add_argument(
        '-p', '--program',
        required=True,
        help='被测程序路径 (可执行文件)'
    )
    
    parser.add_argument(
        '-t', '--testcases',
        required=True,
        help='测试用例JSON文件路径'
    )
    
    parser.add_argument(
        '-o', '--output',
        default=None,
        help='测试报告输出路径 (默认: test_report_<时间戳>.json)'
    )
    
    args = parser.parse_args()
    
    try:
        # 创建测试运行器
        runner = TestRunner(args.program, args.testcases)
        
        # 运行测试
        runner.run()
        
        # 保存报告
        output_path = runner.save_report(args.output)
        
        print(f"\n✅ 测试执行完成! 报告已保存至: {output_path}")
        return 0
        
    except FileNotFoundError as e:
        print(f"❌ 文件错误: {e}")
        return 1
    except ValueError as e:
        print(f"❌ 数据错误: {e}")
        return 1
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析错误: {e}")
        print("请检查测试用例文件格式是否正确 (注意中英文逗号、括号匹配)")
        return 1
    except Exception as e:
        print(f"❌ 未知错误: {e}")
        return 1


if __name__ == "__main__":
    exit(main())