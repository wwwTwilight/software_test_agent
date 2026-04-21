# analysis_agent

这里放大模型调用与提示词工程相关代码。

## 用法

默认会读取：

- `cpp_project/电商购物车结算系统.md`
- `cpp_project/test_cases.json`
- `cpp_project/*.cpp`

先确保 DeepSeek API key 可从以下任一位置读取：

- 环境变量 `DEEPSEEK_API_KEY`
- `analysis_agent/deepseekAPI` 文件

运行示例：

```bash
python analysis_agent/generate_test_cases.py
```

如果你想临时用环境变量传 key，可直接执行：

```bash
DEEPSEEK_API_KEY="你的key" python analysis_agent/generate_test_cases.py
```

也可以覆盖输入和输出路径：

```bash
python analysis_agent/generate_test_cases.py \
  --spec cpp_project/电商购物车结算系统.md \
  --tests cpp_project/test_cases.json \
  --code cpp_project/checkout_engine_test.cpp \
  --output-dir generated
```

## 输出

脚本会在输出目录下按每次运行创建一个批次文件夹，并根据 `--mode` 参数分别生成黑盒和白盒测试用例。

批次文件夹结构示例：

```
generated/batch_20260417_153000/
├── blackbox/
│   ├── model_output.md
│   ├── test_cases.json
│   ├── manifest.json
│   └── last_llm_raw_response.txt
└── whitebox/
    ├── model_output.md
    ├── test_cases.json
    ├── manifest.json
    └── last_llm_raw_response.txt
```

默认情况下（`--mode all`），会同时生成两种测试用例。

## 参数说明

- `--mode all`（默认）：同时调用两次 API，分别生成黑盒和白盒测试用例
- `--mode blackbox`：仅生成黑盒测试用例（仅输入规格说明书）
- `--mode whitebox`：仅生成白盒测试用例（输入规格说明书和代码）
- `--output-dir`：指定输出根目录（默认 `generated`（项目根目录下））
- `--model`：指定 DeepSeek 模型（默认 `deepseek-chat`）
- `--temperature`：生成温度（默认 `0.2`）
- `--max-tokens`：最大输出 token 数（默认 `4096`）
- `--print-json`：打印提取出的 JSON 到标准输出

## 文件说明

- `model_output.md`：模型完整输出
- `test_cases.json`：提取出的 JSON 结果，格式与 `cpp_project/test_cases.json` 一致
- `manifest.json`：本次运行的元数据（包含 `test_type` 字段标识黑盒或白盒）
- `last_llm_raw_response.txt`：本次运行的 API 原始响应