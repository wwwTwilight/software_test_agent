from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_command(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n")
    if result.returncode != 0:
        raise RuntimeError(f"命令执行失败: {' '.join(cmd)}")
    return result


def find_latest_batch(generated_root: Path) -> Path:
    if not generated_root.exists():
        raise FileNotFoundError(f"目录不存在: {generated_root}")

    batch_dirs = [p for p in generated_root.iterdir() if p.is_dir() and re.match(r"^batch_\d{8}_\d{6}(?:_\d+)?$", p.name)]
    if not batch_dirs:
        raise FileNotFoundError(f"未找到 batch_* 目录: {generated_root}")

    return max(batch_dirs, key=lambda p: p.stat().st_mtime)


def ensure_testcase_files(batch_dir: Path) -> tuple[Path, Path]:
    blackbox_json = batch_dir / "blackbox" / "test_cases.json"
    whitebox_json = batch_dir / "whitebox" / "test_cases.json"

    missing = [str(p) for p in [blackbox_json, whitebox_json] if not p.exists()]
    if missing:
        raise FileNotFoundError("以下测试用例文件不存在:\n" + "\n".join(missing))
    return blackbox_json, whitebox_json


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="端到端自动流程：生成测试用例 -> 执行测试 -> DeepSeek 缺陷分析。")
    parser.add_argument("--workspace-root", type=Path, default=None, help="工作区根目录，默认自动推断。")
    parser.add_argument("--python", type=str, default=sys.executable, help="用于运行子脚本的 Python 可执行文件路径。")
    parser.add_argument("--program", type=Path, default=Path("cpp_project/checkout_engine_test.cpp"), help="被测程序路径（可执行文件或 .cpp 源码）。")
    parser.add_argument("--generate-mode", choices=["blackbox", "whitebox", "all"], default="all", help="测试用例生成模式。")
    parser.add_argument("--generate-model", type=str, default="deepseek-reasoner", help="generate_test_cases.py 使用的模型。")
    parser.add_argument("--summary-model", type=str, default="deepseek-reasoner", help="summery.py 使用的模型。")
    parser.add_argument("--base-url", type=str, default="https://api.deepseek.com", help="DeepSeek API 地址。")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    script_path = Path(__file__).resolve()
    workspace_root = args.workspace_root.resolve() if args.workspace_root else script_path.parent.resolve()

    generate_script = workspace_root / "analysis_agent" / "generate_test_cases.py"
    summary_script = workspace_root / "analysis_agent" / "summery.py"
    runner_script = workspace_root / "runner" / "test_runner.py"

    for path in [generate_script, summary_script, runner_script]:
        if not path.exists():
            raise FileNotFoundError(f"脚本不存在: {path}")

    generated_root = workspace_root / "generated"

    print("\n=== STEP 1/4: 生成黑白盒测试用例 ===")
    run_command(
        [
            args.python,
            str(generate_script),
            "--workspace-root",
            str(workspace_root),
            "--output-dir",
            str(generated_root),
            "--mode",
            args.generate_mode,
            "--model",
            args.generate_model,
            "--base-url",
            args.base_url,
        ],
        cwd=workspace_root,
    )

    latest_batch = find_latest_batch(generated_root)
    print(f"latest_batch={latest_batch}")

    blackbox_json, whitebox_json = ensure_testcase_files(latest_batch)

    runner_report_dir = latest_batch / "runner_reports"
    runner_report_dir.mkdir(parents=True, exist_ok=True)
    blackbox_report = runner_report_dir / "blackbox_report.json"
    whitebox_report = runner_report_dir / "whitebox_report.json"

    program_path = args.program.resolve() if args.program.is_absolute() else (workspace_root / args.program).resolve()
    if not program_path.exists():
        raise FileNotFoundError(f"被测程序不存在: {program_path}")

    print("\n=== STEP 2/4: 运行黑盒测试 ===")
    run_command(
        [
            args.python,
            str(runner_script),
            "--program",
            str(program_path),
            "--testcases",
            str(blackbox_json),
            "--output",
            str(blackbox_report),
        ],
        cwd=workspace_root,
    )

    print("\n=== STEP 3/4: 运行白盒测试 ===")
    run_command(
        [
            args.python,
            str(runner_script),
            "--program",
            str(program_path),
            "--testcases",
            str(whitebox_json),
            "--output",
            str(whitebox_report),
        ],
        cwd=workspace_root,
    )

    final_report = latest_batch / f"final_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    code_paths = sorted((workspace_root / "cpp_project").glob("*.cpp"))
    summary_cmd = [
        args.python,
        str(summary_script),
        "--workspace-root",
        str(workspace_root),
        "--reports",
        str(blackbox_report),
        str(whitebox_report),
        "--output",
        str(final_report),
        "--model",
        args.summary_model,
        "--base-url",
        args.base_url,
    ]
    if code_paths:
        summary_cmd.append("--code")
        summary_cmd.extend(str(p.resolve()) for p in code_paths)

    print("\n=== STEP 4/4: 生成缺陷分析报告 ===")
    run_command(summary_cmd, cwd=workspace_root)

    print("\n=== 全流程完成 ===")
    print(f"batch_dir={latest_batch}")
    print(f"blackbox_report={blackbox_report}")
    print(f"whitebox_report={whitebox_report}")
    print(f"final_analysis_report={final_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
