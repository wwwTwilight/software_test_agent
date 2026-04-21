# software_test_agent

电商购物车结算系统的自动化测试与缺陷分析流水线。

当前项目支持完整流程：
1. 调用 DeepSeek 生成黑盒/白盒测试用例
2. 自动运行测试（传入 .cpp 时可自动编译）
3. 调用 DeepSeek 读取测试报告与代码并生成缺陷分析报告（Markdown）

## 环境准备

建议使用你已创建的 conda 环境：

```bash
conda activate testAgent
```

确保 DeepSeek API Key 可被读取（任选一种）：

1. 环境变量 `DEEPSEEK_API_KEY`
2. 文件 `analysis_agent/deepseekAPI`

## 一键运行（推荐）

在项目根目录执行：

```bash
python main.py
```

说明：
- 会先运行 `analysis_agent/generate_test_cases.py` 生成黑白盒测试
- 自动选择项目内 `generated/` 下最新的 `batch_*`
- 运行 `runner/test_runner.py` 生成黑盒和白盒测试报告
- 最后运行 `analysis_agent/summery.py` 生成最终缺陷分析报告（.md）

## 常用命令

### 1) 指定被测程序（推荐传 .cpp，runner 会自动编译）

```bash
python main.py \
  --program cpp_project/checkout_engine_test.cpp
```

### 2) 只生成某一类测试用例

```bash
python main.py --generate-mode blackbox
python main.py --generate-mode whitebox
python main.py --generate-mode all
```

### 3) 指定模型

```bash
python main.py \
  --generate-model deepseek-reasoner \
  --summary-model deepseek-reasoner
```

## 分步运行（调试时用）

### Step 1: 生成测试用例

```bash
python analysis_agent/generate_test_cases.py \
  --workspace-root . \
  --output-dir generated \
  --mode all
```

### Step 2: 运行黑盒测试

```bash
python runner/test_runner.py \
  --program cpp_project/checkout_engine_test.cpp \
  --testcases generated/<latest_batch>/blackbox/test_cases.json \
  --output generated/<latest_batch>/runner_reports/blackbox_report.json
```

### Step 3: 运行白盒测试

```bash
python runner/test_runner.py \
  --program cpp_project/checkout_engine_test.cpp \
  --testcases generated/<latest_batch>/whitebox/test_cases.json \
  --output generated/<latest_batch>/runner_reports/whitebox_report.json
```

### Step 4: 生成缺陷分析报告

```bash
python analysis_agent/summery.py \
  --workspace-root . \
  --reports \
    generated/<latest_batch>/runner_reports/blackbox_report.json \
    generated/<latest_batch>/runner_reports/whitebox_report.json \
  --output generated/<latest_batch>/final_analysis_report.md
```

## 结果文件位置

每次主流程运行后，结果在最新 batch 目录中：

- 黑盒用例：`generated/batch_*/blackbox/test_cases.json`
- 白盒用例：`generated/batch_*/whitebox/test_cases.json`
- 黑盒报告：`generated/batch_*/runner_reports/blackbox_report.json`
- 白盒报告：`generated/batch_*/runner_reports/whitebox_report.json`
- 最终分析：`generated/batch_*/final_analysis_report_*.md`

## 常见问题

1. 提示找不到 API Key
- 检查 `analysis_agent/deepseekAPI` 是否有正确 key
- 或导出环境变量：`export DEEPSEEK_API_KEY=你的key`

2. .cpp 编译失败
- 安装 g++ 或 clang++
- 或设置编译器：`export CXX=g++`

3. 结果通过率低
- 当前被测代码中包含故意保留的 buggy 逻辑，用于测试与缺陷分析验证
