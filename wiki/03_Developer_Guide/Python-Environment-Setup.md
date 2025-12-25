# Python Environment Management Guide (Python 環境設定指南)

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 Python Environment Management Guide

### 1. Miniconda (Recommended)
Due to compilation issues with system libraries on macOS, we recommend using **Miniconda**, which provides pre-compiled binaries and is the fastest and most stable method.

#### Installation & Initialization
Assuming you have installed Miniconda via Homebrew. Please run:

```bash
# 1. Initialize Conda (This modifies ~/.zshrc)
conda init zsh

# 2. Reload Shell Config (or restart terminal)
source ~/.zshrc
```

#### Create Project Environment
```bash
# 1. Create Python 3.11 environment (Name: algo_trading)
conda create -n algo_trading python=3.11 -y

# 2. Activate Environment
conda activate algo_trading

# 3. Install Dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

#### Verification
```bash
python verify_dspy.py
```
If specific output "✅ DSPy is ready to use!" appears, success!

### 2. Pyenv (Deprecated)
**Note**: On Apple Silicon (M1/M2/M3), compiling Python 3.11 with Pyenv requires complex OpenSSL linking flags.

---

<a id="traditional-chinese"></a>

## 🇹🇼 Python 環境設定指南 (Python Environment Setup)

### 1. Miniconda (推薦方案)
由於 macOS 的系統庫編譯問題，我們改用 **Miniconda**，它提供預先編譯好的二進制檔案，安裝最快且穩定。

#### 安裝與初始化
您已透過 Homebrew 安裝 Miniconda。接下來請執行：

```bash
# 1. 初始化 Conda (這會修改 ~/.zshrc)
conda init zsh

# 2. 重新載入 Shell 設定 (或重啟終端機)
source ~/.zshrc
```

#### 建立專案環境
```bash
# 1. 建立 Python 3.11 環境 (名稱: algo_trading)
conda create -n algo_trading python=3.11 -y

# 2. 啟用環境
conda activate algo_trading

# 3. 安裝專案依賴
pip install --upgrade pip
pip install -r requirements.txt
```

#### 驗證安裝
```bash
python verify_dspy.py
```
若顯示 "✅ DSPy is ready to use!" 即代表成功。

### 2. Pyenv (舊方案 - 已封存)
**注意**: 在 Apple Silicon (M1/M2/M3) 上，Pyenv 編譯 Python 3.11 需要複雜的 OpenSSL 連結參數。若您堅持使用 Pyenv，請參考以下指令：

```bash
LDFLAGS="-L$(brew --prefix openssl@3)/lib -L$(brew --prefix readline)/lib -L$(brew --prefix zlib)/lib" \
CPPFLAGS="-I$(brew --prefix openssl@3)/include -I$(brew --prefix readline)/include -I$(brew --prefix zlib)/include" \
PKG_CONFIG_PATH="$(brew --prefix openssl@3)/lib/pkgconfig" \
CONFIGURE_OPTS="--with-openssl=$(brew --prefix openssl@3)" \
pyenv install -v 3.11.9
```
