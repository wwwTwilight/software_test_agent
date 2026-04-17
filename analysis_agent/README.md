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
  --output-dir analysis_agent/generated
```

## 输出

脚本会在输出目录下按每次运行创建一个批次文件夹，例如：

- `analysis_agent/generated/batch_20260417_153000/`

每个批次文件夹内包含：

- `model_output.md`：模型完整输出
- `test_cases.json`：提取出的 JSON 结果
- `manifest.json`：本次运行的元数据
- `last_llm_raw_response.txt`：本次运行的 API 原始响应