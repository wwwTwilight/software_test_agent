from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, render_template, request


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
GENERATED_ROOT = WORKSPACE_ROOT / "generated"
UPLOAD_ROOT = WORKSPACE_ROOT / "web_uploads"

app = Flask(__name__)


ABS_PATH_PATTERN = re.compile(r'(?<!\w)/(?:[^\s"\'<>]+)')


def redact_host_paths(text: str) -> str:
    if not text:
        return text
    redacted = text.replace(str(WORKSPACE_ROOT), "[workspace]")
    redacted = ABS_PATH_PATTERN.sub("[path]", redacted)
    return redacted


def run_command(cmd: list[str], cwd: Path, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def parse_batch_dir(stdout_text: str) -> Path | None:
    for line in stdout_text.splitlines():
        if line.startswith("batch_dir="):
            return Path(line.split("=", 1)[1].strip())
    return None


def parse_summary(report_path: Path) -> dict[str, Any]:
    if not report_path.exists():
        return {"summary": {}, "failed_cases": []}
    data = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "summary": data.get("summary", {}),
        "failed_cases": data.get("failed_cases", []),
    }


def save_uploaded_file(file_storage, target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(str(target_path))
    return target_path


def make_manual_testcases(raw_json: str) -> dict[str, Any]:
    rows = json.loads(raw_json)
    if not isinstance(rows, list):
        raise ValueError("手工测试用例必须是数组")

    cases: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        case_id = str(row.get("id", "")).strip() or f"{index:03d}"
        input_text = str(row.get("input", "")).strip()
        output_text = str(row.get("output", "")).strip()
        if not input_text or not output_text:
            continue
        cases.append({"id": case_id, "input": input_text, "output": output_text})

    if not cases:
        raise ValueError("手工输入的测试样例为空，请至少填写一条完整 input/output")

    return {"test_case": cases}


@app.get("/")
def index():
    return render_template("index.html", result=None, error=None)


@app.post("/run")
def run_pipeline():
    try:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = UPLOAD_ROOT / f"run_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        python_exec = sys.executable
        generate_mode = request.form.get("generate_mode", "all").strip() or "all"
        generate_model = request.form.get("generate_model", "deepseek-reasoner").strip() or "deepseek-reasoner"
        summary_model = request.form.get("summary_model", "deepseek-reasoner").strip() or "deepseek-reasoner"
        base_url = request.form.get("base_url", "https://api.deepseek.com").strip() or "https://api.deepseek.com"
        case_mode = request.form.get("case_mode", "upload")

        if generate_mode not in {"all", "blackbox", "whitebox"}:
            raise ValueError("generate_mode 非法")

        code_path = (WORKSPACE_ROOT / "cpp_project" / "checkout_engine_test.cpp").resolve()
        spec_path = (WORKSPACE_ROOT / "cpp_project" / "电商购物车结算系统.md").resolve()
        tests_path = (WORKSPACE_ROOT / "cpp_project" / "test_cases.json").resolve()

        code_file = request.files.get("code_file")
        if code_file and code_file.filename:
            ext = Path(code_file.filename).suffix or ".cpp"
            code_path = save_uploaded_file(code_file, run_dir / f"uploaded_code{ext}").resolve()

        spec_file = request.files.get("spec_file")
        if spec_file and spec_file.filename:
            ext = Path(spec_file.filename).suffix or ".md"
            spec_path = save_uploaded_file(spec_file, run_dir / f"uploaded_spec{ext}").resolve()

        if case_mode == "upload":
            case_file = request.files.get("cases_file")
            if case_file and case_file.filename:
                tests_path = save_uploaded_file(case_file, run_dir / "uploaded_test_cases.json").resolve()
        else:
            manual_json = request.form.get("manual_cases_json", "[]")
            manual_data = make_manual_testcases(manual_json)
            tests_path = (run_dir / "manual_test_cases.json").resolve()
            tests_path.write_text(json.dumps(manual_data, ensure_ascii=False, indent=2), encoding="utf-8")

        generate_script = (WORKSPACE_ROOT / "analysis_agent" / "generate_test_cases.py").resolve()
        runner_script = (WORKSPACE_ROOT / "runner" / "test_runner.py").resolve()
        summary_script = (WORKSPACE_ROOT / "analysis_agent" / "summery.py").resolve()

        gen_cmd = [
            python_exec,
            str(generate_script),
            "--workspace-root",
            str(WORKSPACE_ROOT),
            "--spec",
            str(spec_path),
            "--tests",
            str(tests_path),
            "--code",
            str(code_path),
            "--output-dir",
            str(GENERATED_ROOT),
            "--mode",
            generate_mode,
            "--model",
            generate_model,
            "--base-url",
            base_url,
        ]
        gen_ret = run_command(gen_cmd, WORKSPACE_ROOT)
        if gen_ret.returncode != 0:
            raise RuntimeError("生成测试用例失败\n" + (gen_ret.stdout or "") + "\n" + (gen_ret.stderr or ""))

        batch_dir = parse_batch_dir(gen_ret.stdout)
        if batch_dir is None:
            raise RuntimeError("无法从生成脚本输出中解析 batch_dir")
        batch_dir = batch_dir.resolve()

        runner_reports_dir = batch_dir / "runner_reports"
        runner_reports_dir.mkdir(parents=True, exist_ok=True)
        blackbox_report = runner_reports_dir / "blackbox_report.json"
        whitebox_report = runner_reports_dir / "whitebox_report.json"

        logs: list[str] = []
        logs.append("[STEP1] generate_test_cases.py\n" + (gen_ret.stdout or "") + "\n" + (gen_ret.stderr or ""))

        if generate_mode in {"all", "blackbox"}:
            blackbox_case = batch_dir / "blackbox" / "test_cases.json"
            bb_cmd = [
                python_exec,
                str(runner_script),
                "--program",
                str(code_path),
                "--testcases",
                str(blackbox_case),
                "--output",
                str(blackbox_report),
            ]
            bb_ret = run_command(bb_cmd, WORKSPACE_ROOT)
            if bb_ret.returncode != 0:
                raise RuntimeError("黑盒测试运行失败\n" + (bb_ret.stdout or "") + "\n" + (bb_ret.stderr or ""))
            logs.append("[STEP2] blackbox test_runner.py\n" + (bb_ret.stdout or "") + "\n" + (bb_ret.stderr or ""))

        if generate_mode in {"all", "whitebox"}:
            whitebox_case = batch_dir / "whitebox" / "test_cases.json"
            wb_cmd = [
                python_exec,
                str(runner_script),
                "--program",
                str(code_path),
                "--testcases",
                str(whitebox_case),
                "--output",
                str(whitebox_report),
            ]
            wb_ret = run_command(wb_cmd, WORKSPACE_ROOT)
            if wb_ret.returncode != 0:
                raise RuntimeError("白盒测试运行失败\n" + (wb_ret.stdout or "") + "\n" + (wb_ret.stderr or ""))
            logs.append("[STEP3] whitebox test_runner.py\n" + (wb_ret.stdout or "") + "\n" + (wb_ret.stderr or ""))

        final_report = batch_dir / f"final_analysis_report_{run_id}.md"
        reports_for_summary = []
        if blackbox_report.exists():
            reports_for_summary.append(str(blackbox_report))
        if whitebox_report.exists():
            reports_for_summary.append(str(whitebox_report))
        if not reports_for_summary:
            raise RuntimeError("没有可用于分析的测试报告")

        summary_cmd = [
            python_exec,
            str(summary_script),
            "--workspace-root",
            str(WORKSPACE_ROOT),
            "--reports",
            *reports_for_summary,
            "--code",
            str(code_path),
            "--output",
            str(final_report),
            "--model",
            summary_model,
            "--base-url",
            base_url,
        ]
        summary_ret = run_command(summary_cmd, WORKSPACE_ROOT)
        if summary_ret.returncode != 0:
            raise RuntimeError("分析报告生成失败\n" + (summary_ret.stdout or "") + "\n" + (summary_ret.stderr or ""))
        logs.append("[STEP4] summery.py\n" + (summary_ret.stdout or "") + "\n" + (summary_ret.stderr or ""))

        final_md = ""
        if final_report.exists():
            final_md = redact_host_paths(final_report.read_text(encoding="utf-8"))

        result = {
            "blackbox": parse_summary(blackbox_report),
            "whitebox": parse_summary(whitebox_report),
            "final_report_md": final_md,
            "logs": redact_host_paths("\n\n".join(logs)),
        }
        return render_template("index.html", result=result, error=None)

    except Exception as exc:
        return render_template("index.html", result=None, error=redact_host_paths(str(exc)))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
