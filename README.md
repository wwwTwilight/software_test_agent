# software_test_agent
# 自动化测试工具

## 1. 快速开始

```bash
# 运行测试
python test_runner.py -p <被测程序.exe> -t <测试用例.json> [-o <报告.json>]
```
##  2. 示例
```bash
# 编译C++程序
g++ -std=c++11 checkout.cpp -o checkout.exe

# 执行测试
python test_runner.py -p checkout.exe -t white_test_cases.json -o report.json
```
## 3. 参数说明
| 参数 | 说明 |
|------|------|
| `-p` | 被测程序路径（必需） |
| `-t` | 测试用例JSON文件路径（必需） |
| `-o` | 测试报告输出路径（可选，默认自动生成） |

## 4. 测试用例格式
```json
{
  "test_case": [
    {
      "id": "001",
      "input": "Beijing\n1\nSKU_101 Book 30 1 0.5 0 20\n0\n",
      "output": "status=SUCCESS final_payable=30"
    }
  ]
}
```
## 5. 输出报告格式
```json
{
  "summary": {
    "total_tests": 8,
    "passed": 6,
    "failed": 2,
    "pass_rate": "75.00%"
  },
  "failed_cases": [...]
}
```
## 6. 常见问题
Q: 提示找不到文件

A: 检查程序路径是否正确，C++程序需要先编译成exe

<br>

Q: conda install报错

A: 本工具只用Python标准库，无需安装任何包，直接运行即可

## 7. 环境要求
Python 3.7+（无需安装第三方包）

g++（如需编译C++程序）
