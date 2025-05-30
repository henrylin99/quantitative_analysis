# 多因子选股系统安装指南

## 🚨 依赖包兼容性问题解决方案

如果您在安装过程中遇到了依赖包兼容性问题（如 `empyrical` 或 `TA-Lib` 安装失败），请按照以下步骤操作：

## 🔧 方案一：使用修复版快速启动（推荐）

```bash
# 运行修复版启动脚本
python quick_start_fixed.py
```

这个脚本会：
- 自动安装核心依赖包
- 跳过有问题的包
- 启动最小化版本的系统
- 提供基础功能

## 🔧 方案二：手动安装核心依赖

### 1. 安装核心依赖包

```bash
# 安装Web框架
pip install Flask>=2.3.0 Flask-RESTful>=0.3.10 Flask-CORS>=4.0.0

# 安装数据库相关
pip install SQLAlchemy>=2.0.0 Flask-SQLAlchemy>=3.0.0

# 安装数据处理核心
pip install pandas>=2.0.0 numpy>=1.24.0

# 安装机器学习核心
pip install scikit-learn>=1.3.0 scipy>=1.11.0

# 安装工具库
pip install loguru>=0.7.0 requests>=2.31.0 python-dateutil>=2.8.0
pip install python-dotenv>=1.0.0 matplotlib>=3.7.0 joblib>=1.3.0
```

### 2. 可选：安装高级功能依赖

```bash
# 组合优化功能
pip install cvxpy>=1.4.0

# 机器学习增强
pip install xgboost>=1.7.0 lightgbm>=4.0.0
```

### 3. 启动系统

```bash
# 使用系统启动器
python run_system.py

# 或直接运行
python app.py
```

## 🔧 方案三：使用最小化依赖文件

```bash
# 使用最小化依赖文件
pip install -r requirements_minimal.txt
```

## 📋 常见问题解决

### 1. TA-Lib 安装失败

**问题**: `TA-Lib==0.4.28` 在新版本Python中有兼容性问题

**解决方案**: 
- 系统已移除对 TA-Lib 的依赖
- 使用纯 pandas 实现技术指标
- 无需手动安装 TA-Lib

### 2. empyrical 安装失败

**问题**: `empyrical>=0.5.5` 在Python 3.12中有兼容性问题

**解决方案**:
- 系统已移除对 empyrical 的依赖
- 使用内置的性能指标计算
- 或使用 `quantlib-python` 作为替代

### 3. numexpr 相关问题

**问题**: `numexpr` 可能导致兼容性问题

**解决方案**:
- 系统已移除对 numexpr 的直接依赖
- 使用标准的 pandas 和 numpy 操作

### 4. cvxpy 安装失败

**问题**: `cvxpy` 安装可能需要编译器

**解决方案**:
```bash
# macOS
brew install gcc

# Ubuntu/Debian
sudo apt-get install build-essential

# 然后重新安装
pip install cvxpy
```

## 🎯 功能对比

| 功能模块 | 最小化版本 | 完整版本 |
|---------|-----------|----------|
| Web界面 | ✅ | ✅ |
| 数据处理 | ✅ | ✅ |
| 基础因子计算 | ✅ | ✅ |
| 机器学习(基础) | ✅ | ✅ |
| 机器学习(高级) | ❌ | ✅ |
| 组合优化 | ❌ | ✅ |
| 高级技术指标 | ❌ | ✅ |
| 回测验证 | ✅ | ✅ |

## 🚀 推荐安装流程

### 新用户（快速体验）
1. 运行 `python quick_start_fixed.py`
2. 体验基础功能
3. 根据需要安装高级依赖

### 开发者（完整功能）
1. 安装核心依赖：`pip install -r requirements_minimal.txt`
2. 安装可选依赖：`pip install cvxpy xgboost lightgbm`
3. 运行系统：`python run_system.py`

### 生产环境
1. 使用虚拟环境
2. 安装完整依赖
3. 配置数据库连接
4. 使用生产模式启动

## 💡 提示

1. **虚拟环境**: 强烈建议使用虚拟环境避免包冲突
2. **Python版本**: 推荐使用 Python 3.8-3.11，避免最新版本的兼容性问题
3. **依赖管理**: 优先安装核心功能，再逐步添加高级功能
4. **错误处理**: 如果某个包安装失败，可以跳过继续使用其他功能

## 📞 获取帮助

如果仍然遇到问题：
1. 查看错误日志
2. 检查Python版本兼容性
3. 尝试使用最小化版本
4. 提交Issue描述具体问题

---

**记住**: 即使某些高级功能暂时不可用，系统的核心功能仍然可以正常使用！ 