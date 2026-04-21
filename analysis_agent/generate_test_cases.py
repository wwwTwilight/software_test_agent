from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib import error, request


DEFAULT_MODEL = "deepseek-reasoner"
DEFAULT_BASE_URL = "https://api.deepseek.com"
JSON_START_MARKER = "<<<json_start>>>"
JSON_END_MARKER = "<<<json_end>>>"


@dataclass(frozen=True)
class InputBundle:
    spec_text: str
    code_texts: dict[str, str]
    existing_tests_text: str


def get_workspace_root(script_path: Path) -> Path:
    return script_path.resolve().parent.parent


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalize_to_workspace_path(path: Path, workspace_root: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (workspace_root / path).resolve()


def load_api_key(script_dir: Path) -> str:
    env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key

    local_key_file = script_dir / "deepseekAPI"
    if local_key_file.exists():
        file_key = local_key_file.read_text(encoding="utf-8").strip()
        if file_key:
            return file_key

    raise RuntimeError(
        "未找到 DeepSeek API key，请先设置环境变量 DEEPSEEK_API_KEY 或填写 analysis_agent/deepseekAPI 文件。"
    )


def collect_inputs(workspace_root: Path, spec_path: Path, code_paths: Iterable[Path], tests_path: Path) -> InputBundle:
    spec_text = read_text_file(spec_path)
    code_texts: dict[str, str] = {}
    for code_path in code_paths:
        try:
            display_path = str(code_path.relative_to(workspace_root))
        except ValueError:
            display_path = str(code_path)
        code_texts[display_path] = read_text_file(code_path)
    existing_tests_text = read_text_file(tests_path)
    return InputBundle(spec_text=spec_text, code_texts=code_texts, existing_tests_text=existing_tests_text)


def build_prompt(inputs: InputBundle, test_type: str = "all") -> str:
    """Build prompt for test case generation.
    
    Args:
        inputs: InputBundle containing spec, code, and tests
        test_type: 'blackbox', 'whitebox', or 'all'
    """
    if test_type == "blackbox":
        include_spec = True
        include_code = False
        source_desc = "规格说明书、已有测试用例"
        code_note = "\n\n注：黑盒测试仅基于规格说明书，不参考代码实现。"
    elif test_type == "whitebox":
        include_spec = False
        include_code = True
        source_desc = "待测代码、已有测试用例"
        code_note = "\n\n注：白盒测试仅基于代码实现，不参考规格说明书。"
    else:  # test_type == "all"
        include_spec = True
        include_code = True
        source_desc = "规格说明书、待测代码、已有测试用例"
        code_note = ""
    
    code_sections = ""
    if include_code:
        code_sections = "\n\n".join(
            f"[FILE] {path}\n```text\n{content}\n```" for path, content in inputs.code_texts.items()
        )
    
    test_type_desc = {
        "blackbox": "黑盒测试用例",
        "whitebox": "白盒测试用例",
        "all": "测试用例"
    }.get(test_type, "测试用例")
    
    json_template = """{
  "test_case": [
    {
      "id": "001",
      "input": "Xinjiang\n2\nSKU_001 MechanicalKeyboard 299 1 1.2 0 10\nSKU_002 SpecialMousePad 9.9 2 0.1 1 5\n1\nCPN_100 discount 0.9 200 0 1\n",
      "output": "status=SUCCESS final_payable=343.8"
    },
    {
      "id": "002",
      "input": "Beijing\n1\nSKU_001 MechanicalKeyboard 299 1 1.2 0 0\n0\n",
      "output": "status=FAIL message=\"商品 SKU_001 库存不足，当前库存: 0, 需求: 1\""
    },
    {
      "id": "003",
      "input": "Beijing\n1\nSKU_010 Cable 20 1 0.2 0 100\n0\n",
      "output": "status=SUCCESS final_payable=26.0"
    },
    {
      "id": "004",
      "input": "Beijing\n1\nSKU_011 Speaker 50 2 1.1 0 8\n0\n",
      "output": "status=SUCCESS final_payable=100.0"
    },
    {
      "id": "005",
      "input": "Xinjiang\n1\nSKU_012 Chair 90 1 2.4 0 6\n0\n",
      "output": "status=SUCCESS final_payable=125.0"
    },
    {
      "id": "006",
      "input": "Beijing\n1\nSKU_013 Lamp 80 1 0.5 0 9\n1\nCPN_201 full_reduction 10 100 0 1\n",
      "output": "status=SUCCESS final_payable=86.0"
    },
    {
      "id": "007",
      "input": "Beijing\n1\nSKU_014 Book 80 1 0.5 0 9\n1\nCPN_202 full_reduction 10 100 0 0\n",
      "output": "status=SUCCESS final_payable=86.0"
    },
    {
      "id": "008",
      "input": "Beijing\n1\nSKU_015 Pen 30 -2 0.3 0 50\n0\n",
      "output": "status=FAIL message=\"商品数量必须大于0\""
    },
    {
      "id": "009",
      "input": "Beijing\n1\nSKU_016 Notebook 50 1 0.4 0 30\n2\nCPN_301 full_reduction 20 100 0 1\nCPN_302 full_reduction 10 100 0 1\n",
      "output": "status=SUCCESS final_payable=56.0"
    },
    {
      "id": "010",
      "input": "Xinjiang\n1\nSKU_017 Sticker 5 1 3.2 1 999\n0\n",
      "output": "status=SUCCESS final_payable=50.0"
    }
  ]
}"""

    prompt_parts = [
        f"你是软件测试{test_type_desc}生成器。请严格按照下面要求输出。",
        f"",
        f"任务：根据{source_desc}，生成新的{test_type_desc}JSON。",
        f"",
        "输出格式：",
        "1. 先输出简短分析，1 到 3 段即可。",
        "2. 然后输出 JSON，且必须被以下两行标记包裹：",
        JSON_START_MARKER,
        JSON_END_MARKER,
        "3. 标记之间只能放 JSON，不能放代码块、注释、解释文字。",
        "",
        "JSON 必须完全符合这个结构，字段名、层级、类型都不能改：",
        json_template,
        "",
        "生成规则：",
        "- 顶层只能有 test_case。",
        "- test_case 是数组，至少 20 条。",
        "- 每条用例只允许 id、input、output 三个字段。",
        "- id 必须是三位数字字符串，从 001 开始递增。这是新生成用例集合的独立编号，不要基于已有测试用例的ID继续编号。",
        "- input 必须是可直接喂给程序的原始输入，保留换行。",
        "- output 必须是期望输出字符串，格式与样例一致，如 status=SUCCESS final_payable=318.8。",
        "- 尽量覆盖黑盒、白盒、边界、异常、优惠券、地区运费等场景。",
        "- 尽量不要与已有测试用例重复。",
        "- 如果发现规格、代码、样例冲突，在简短分析里指出。",
        "",
        "输入材料：",
    ]
    
    if include_spec:
        prompt_parts.extend([
            "",
            "规格说明书：",
            "```markdown",
            inputs.spec_text,
            "```",
        ])
    
    if include_code and code_sections:
        prompt_parts.extend([
            "",
            "待测代码：",
            code_sections,
        ])
    
    prompt_parts.extend([
        "",
        "已有测试用例：",
        "```json",
        inputs.existing_tests_text,
        "```",
        "",
        f"只输出\"简短分析 + 标记包裹的 JSON\"，不要输出其他内容。{code_note}",
    ])
    
    return "\n".join(prompt_parts)


def call_deepseek(api_key: str, model: str, prompt: str, base_url: str, temperature: float, max_tokens: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是严谨的软件测试分析助手。"},
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
        with request.urlopen(req, timeout=120) as resp:
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
    return text


def find_json_candidate(text: str) -> str:
    marker_pattern = re.compile(re.escape(JSON_START_MARKER) + r"\s*(.*?)\s*" + re.escape(JSON_END_MARKER), re.DOTALL)
    marker_match = marker_pattern.search(text)
    if marker_match:
        return marker_match.group(1).strip()

    fenced_json_pattern = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
    fenced_match = fenced_json_pattern.search(text)
    if fenced_match:
        return fenced_match.group(1).strip()

    start_candidates = [index for index in (text.find("{"), text.find("[")) if index != -1]
    if not start_candidates:
        raise ValueError("未能在模型输出中找到 JSON 起始位置")

    start_index = min(start_candidates)
    candidate = text[start_index:].strip()

    brace_start = candidate.find("{")
    bracket_start = candidate.find("[")
    if brace_start == -1 and bracket_start == -1:
        raise ValueError("未能提取 JSON 候选内容")

    if brace_start != -1 and (bracket_start == -1 or brace_start < bracket_start):
        opener, closer = "{", "}"
        candidate = candidate[brace_start:]
    else:
        opener, closer = "[", "]"
        candidate = candidate[bracket_start:]

    depth = 0
    in_string = False
    escape = False
    end_index = None
    for index, char in enumerate(candidate):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                end_index = index + 1
                break

    if end_index is None:
        raise ValueError("未能从模型输出中恢复完整 JSON")

    return candidate[:end_index].strip()


def parse_json_with_recovery(text: str) -> tuple[Any, str]:
    candidate = find_json_candidate(text)
    try:
        return json.loads(candidate), candidate
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        parsed, end = decoder.raw_decode(candidate)
        if candidate[end:].strip():
            return parsed, candidate[:end]
        return parsed, candidate


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_batch_structure(output_dir: Path) -> tuple[Path, Path, Path]:
    """Create batch directory with blackbox and whitebox subdirectories."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = output_dir / f"batch_{timestamp}"
    counter = 1
    while batch_dir.exists():
        batch_dir = output_dir / f"batch_{timestamp}_{counter:02d}"
        counter += 1
    
    blackbox_dir = batch_dir / "blackbox"
    whitebox_dir = batch_dir / "whitebox"
    blackbox_dir.mkdir(parents=True, exist_ok=False)
    whitebox_dir.mkdir(parents=True, exist_ok=True)
    
    return batch_dir, blackbox_dir, whitebox_dir


def save_outputs(output_subdir: Path, model_text: str, parsed_json: Any, raw_response: dict[str, Any], source_files: list[Path], test_type: str = "all") -> tuple[Path, Path, Path, Path]:
    md_path = output_subdir / "model_output.md"
    json_path = output_subdir / "test_cases.json"
    raw_path = output_subdir / "last_llm_raw_response.txt"

    md_content = model_text.strip() + "\n"
    md_path.write_text(md_content, encoding="utf-8")
    json_path.write_text(json.dumps(parsed_json, ensure_ascii=False, indent=2), encoding="utf-8")
    raw_path.write_text(json.dumps(raw_response, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest_path = output_subdir / "manifest.json"
    manifest = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": raw_response.get("model"),
        "test_type": test_type,
        "output_dir": str(output_subdir),
        "source_files": [str(path) for path in source_files],
        "markdown_output": str(md_path),
        "json_output": str(json_path),
        "raw_response_output": str(raw_path),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return output_subdir, md_path, json_path, manifest_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="使用 DeepSeek 生成软件测试用例并保存 markdown/JSON 输出。")
    parser.add_argument("--workspace-root", type=Path, default=None, help="工作区根目录，默认自动推断。")
    parser.add_argument("--spec", type=Path, default=None, help="规格说明书路径。")
    parser.add_argument("--tests", type=Path, default=None, help="已有测试用例 JSON 路径。")
    parser.add_argument(
        "--code",
        type=Path,
        nargs="+",
        default=None,
        help="待测代码路径，可传多个文件。默认读取 cpp_project 下的 C++ 文件。",
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="输出目录，默认 generated（项目根目录下）。")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="DeepSeek 模型名。")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="DeepSeek API 基础地址。")
    parser.add_argument("--temperature", type=float, default=0.2, help="生成温度。")
    parser.add_argument("--max-tokens", type=int, default=4096, help="最大输出 token 数。")
    parser.add_argument("--print-json", action="store_true", help="将提取出的 JSON 额外打印到标准输出。")
    parser.add_argument(
        "--mode",
        choices=["blackbox", "whitebox", "all"],
        default="all",
        help="测试类型：blackbox（仅规格）、whitebox（规格+代码）、all（同时生成两种）。默认 all。",
    )
    return parser


def resolve_default_paths(workspace_root: Path, spec_path: Path | None, tests_path: Path | None, code_paths: list[Path] | None) -> tuple[Path, Path, list[Path]]:
    cpp_project = workspace_root / "cpp_project"
    resolved_spec = normalize_to_workspace_path(spec_path, workspace_root) if spec_path else (cpp_project / "电商购物车结算系统.md").resolve()
    resolved_tests = normalize_to_workspace_path(tests_path, workspace_root) if tests_path else (cpp_project / "test_cases.json").resolve()

    if code_paths:
        resolved_code_paths = [normalize_to_workspace_path(code_path, workspace_root) for code_path in code_paths]
    else:
        resolved_code_paths = sorted(path.resolve() for path in cpp_project.glob("*.cpp"))

    return resolved_spec, resolved_tests, resolved_code_paths


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    script_dir = script_path.parent
    workspace_root = args.workspace_root or get_workspace_root(script_path)
    output_dir = ensure_output_dir(args.output_dir or (workspace_root / "generated"))

    spec_path, tests_path, code_paths = resolve_default_paths(workspace_root, args.spec, args.tests, args.code)

    missing_paths = [path for path in [spec_path, tests_path, *code_paths] if not path.exists()]
    if missing_paths:
        raise FileNotFoundError("以下输入文件不存在：\n" + "\n".join(str(path) for path in missing_paths))

    inputs = collect_inputs(workspace_root, spec_path, code_paths, tests_path)
    api_key = load_api_key(script_dir)

    batch_dir, blackbox_dir, whitebox_dir = create_batch_structure(output_dir)
    results = []

    # 黑盒测试
    if args.mode in ("blackbox", "all"):
        print("[INFO] 生成黑盒测试用例...")
        blackbox_inputs = InputBundle(spec_text=inputs.spec_text, code_texts={}, existing_tests_text=inputs.existing_tests_text)
        blackbox_prompt = build_prompt(blackbox_inputs, test_type="blackbox")
        
        blackbox_response = call_deepseek(
            api_key=api_key,
            model=args.model,
            prompt=blackbox_prompt,
            base_url=args.base_url,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        blackbox_model_text = extract_model_text(blackbox_response)
        
        try:
            blackbox_json, blackbox_json_text = parse_json_with_recovery(blackbox_model_text)
        except Exception as exc:
            raw_path = blackbox_dir / "last_llm_raw_response.txt"
            raw_path.write_text(json.dumps(blackbox_response, ensure_ascii=False, indent=2), encoding="utf-8")
            error_message = f"黑盒测试 JSON 解析失败。原始响应已保存到 {raw_path}. 错误: {exc}"
            raise RuntimeError(error_message) from exc
        
        _, bb_md_path, bb_json_path, bb_manifest_path = save_outputs(
            output_subdir=blackbox_dir,
            model_text=blackbox_model_text,
            parsed_json=blackbox_json,
            raw_response=blackbox_response,
            source_files=[spec_path, tests_path],
            test_type="blackbox",
        )
        results.append(("blackbox", blackbox_dir, bb_md_path, bb_json_path, bb_manifest_path, len(blackbox_json_text)))
        if args.print_json:
            print("[BLACKBOX JSON]")
            print(json.dumps(blackbox_json, ensure_ascii=False, indent=2))

    # 白盒测试
    if args.mode in ("whitebox", "all"):
        print("[INFO] 生成白盒测试用例...")
        whitebox_prompt = build_prompt(inputs, test_type="whitebox")
        
        whitebox_response = call_deepseek(
            api_key=api_key,
            model=args.model,
            prompt=whitebox_prompt,
            base_url=args.base_url,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        whitebox_model_text = extract_model_text(whitebox_response)
        
        try:
            whitebox_json, whitebox_json_text = parse_json_with_recovery(whitebox_model_text)
        except Exception as exc:
            raw_path = whitebox_dir / "last_llm_raw_response.txt"
            raw_path.write_text(json.dumps(whitebox_response, ensure_ascii=False, indent=2), encoding="utf-8")
            error_message = f"白盒测试 JSON 解析失败。原始响应已保存到 {raw_path}. 错误: {exc}"
            raise RuntimeError(error_message) from exc
        
        _, wb_md_path, wb_json_path, wb_manifest_path = save_outputs(
            output_subdir=whitebox_dir,
            model_text=whitebox_model_text,
            parsed_json=whitebox_json,
            raw_response=whitebox_response,
            source_files=[spec_path, tests_path, *code_paths],
            test_type="whitebox",
        )
        results.append(("whitebox", whitebox_dir, wb_md_path, wb_json_path, wb_manifest_path, len(whitebox_json_text)))
        if args.print_json:
            print("[WHITEBOX JSON]")
            print(json.dumps(whitebox_json, ensure_ascii=False, indent=2))

    print(f"\nbatch_dir={batch_dir}")
    for test_type, test_dir, md_path, json_path, manifest_path, json_len in results:
        print(f"[{test_type.upper()}]")
        print(f"  dir={test_dir}")
        print(f"  markdown_saved={md_path}")
        print(f"  json_saved={json_path}")
        print(f"  manifest_saved={manifest_path}")
        print(f"  json_block_length={json_len}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
