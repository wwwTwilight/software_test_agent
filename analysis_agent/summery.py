from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request

DEFAULT_MODEL = "deepseek-reasoner"
DEFAULT_BASE_URL = "https://api.deepseek.com"


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_api_key(script_dir: Path) -> str:
    env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key

    local_key_file = script_dir / "deepseekAPI"
    if local_key_file.exists():
        file_key = local_key_file.read_text(encoding="utf-8").strip()
        if file_key:
            return file_key

    raise RuntimeError("未找到 DeepSeek API key，请先设置环境变量 DEEPSEEK_API_KEY 或填写 analysis_agent/deepseekAPI 文件。")


def call_deepseek(api_key: str, model: str, prompt: str, base_url: str, temperature: float, max_tokens: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是资深测试分析与缺陷定位助手。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    url = base_url.rstrip("/") + "/chat/completions"
    req = request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API 调用失败: HTTP {exc.code} {exc.reason}\n{detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"DeepSeek API 连接失败: {exc.reason}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"DeepSeek 返回了非 JSON 响应: {body[:1000]}") from exc


def extract_model_text(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices") or []
    if not choices:
        raise ValueError("API 响应中缺少 choices 字段")
    first_choice = choices[0] or {}
    message = first_choice.get("message") or {}
    text = message.get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("API 响应中缺少 message.content")
    return text.strip()


def collect_reports(report_paths: list[Path]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in report_paths:
        content = read_text_file(path)
        data = json.loads(content)
        reports.append({
            "path": str(path),
            "content": data,
        })
    return reports


def collect_code_texts(code_paths: list[Path]) -> dict[str, str]:
    code_map: dict[str, str] = {}
    for path in code_paths:
        code_map[str(path)] = read_text_file(path)
    return code_map


def build_prompt(reports: list[dict[str, Any]], code_map: dict[str, str]) -> str:
    report_summaries: list[dict[str, Any]] = []
    for item in reports:
        content = item["content"]
        summary = content.get("summary", {})
        failed_cases = content.get("failed_cases", [])
        report_summaries.append(
            {
                "report_path": item["path"],
                "total_tests": summary.get("total_tests"),
                "passed": summary.get("passed"),
                "failed": summary.get("failed"),
                "pass_rate": summary.get("pass_rate"),
                "failed_cases": failed_cases,
            }
        )

    code_sections = "\n\n".join(
        f"[FILE] {path}\n```cpp\n{code}\n```" for path, code in code_map.items()
    )

    return f"""你是软件测试缺陷分析专家。

我会给你：
1. 自动化测试报告（黑盒和白盒）
2. C++ 源代码

请输出一份 Markdown 分析报告，必须包含这些部分：
- # 测试结果概览
- # 关键失败用例分析
- # 代码缺陷定位（指出具体逻辑 bug）
- # 缺陷优先级与影响评估
- # 修复建议（按优先级）
- # 回归测试建议

要求：
- 重点指出代码中的真实逻辑问题，不要泛泛而谈。
- 将失败用例与代码逻辑关联起来，解释“为什么失败”。
- 对每个主要 bug 给出“现象-根因-修复建议”三段式说明。
- 使用简洁、专业、可执行的中文表述。

测试报告摘要（JSON）：
```json
{json.dumps(report_summaries, ensure_ascii=False, indent=2)}
```

源代码：
{code_sections}

请直接输出 Markdown 正文，不要附加多余前后缀。"""


def resolve_default_code_paths(workspace_root: Path, code_paths: list[Path] | None) -> list[Path]:
    if code_paths:
        return [p.resolve() if p.is_absolute() else (workspace_root / p).resolve() for p in code_paths]
    cpp_project = workspace_root / "cpp_project"
    return sorted(path.resolve() for path in cpp_project.glob("*.cpp"))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="读取测试报告与代码，调用 DeepSeek 生成 Markdown 分析报告。")
    parser.add_argument("--reports", type=Path, nargs="+", required=True, help="runner 生成的测试报告 JSON 路径（可传多个）。")
    parser.add_argument("--code", type=Path, nargs="+", default=None, help="待分析代码文件路径（可传多个）。默认读取 cpp_project/*.cpp")
    parser.add_argument("--output", type=Path, required=True, help="输出 Markdown 报告路径。")
    parser.add_argument("--workspace-root", type=Path, default=None, help="工作区根目录，默认自动推断。")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="DeepSeek 模型名。")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="DeepSeek API 基础地址。")
    parser.add_argument("--temperature", type=float, default=0.1, help="生成温度。")
    parser.add_argument("--max-tokens", type=int, default=4096, help="最大输出 token 数。")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    script_dir = script_path.parent
    workspace_root = args.workspace_root.resolve() if args.workspace_root else script_dir.parent.resolve()

    report_paths = [p.resolve() if p.is_absolute() else (workspace_root / p).resolve() for p in args.reports]
    missing_reports = [str(p) for p in report_paths if not p.exists()]
    if missing_reports:
        raise FileNotFoundError("以下报告文件不存在:\n" + "\n".join(missing_reports))

    code_paths = resolve_default_code_paths(workspace_root, args.code)
    if not code_paths:
        raise FileNotFoundError("未找到可分析的代码文件，请通过 --code 指定。")
    missing_codes = [str(p) for p in code_paths if not p.exists()]
    if missing_codes:
        raise FileNotFoundError("以下代码文件不存在:\n" + "\n".join(missing_codes))

    reports = collect_reports(report_paths)
    code_map = collect_code_texts(code_paths)

    api_key = load_api_key(script_dir)
    prompt = build_prompt(reports, code_map)

    response = call_deepseek(
        api_key=api_key,
        model=args.model,
        prompt=prompt,
        base_url=args.base_url,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    model_text = extract_model_text(response)

    output_path = args.output.resolve() if args.output.is_absolute() else (workspace_root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report_md = (
        f"# 缺陷分析报告\n\n"
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- 模型: {args.model}\n"
        f"- 报告输入: {', '.join(str(p) for p in report_paths)}\n"
        f"- 代码文件: {', '.join(str(p) for p in code_paths)}\n\n"
        f"---\n\n"
        f"{model_text}\n"
    )
    output_path.write_text(report_md, encoding="utf-8")

    print(f"analysis_report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
