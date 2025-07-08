# Dashboard Download Tool

A Python tool to download and preserve Flipside Crypto Data Studio dashboard artifacts. This script extracts sql queries, the latest cached resultset, chart configurations and text blocks and builds a description markdown file, as well as logging the queries and results for use in Snowflake.

---

## Quickstart Guide

This guide will help you get started, even if you are new to Python. Follow these steps to download and use the Dashboard Download Tool.

### 1. Clone the Repository

First, download the project files to your computer:

```bash
git clone https://github.com/YOUR-ORG/dashboard-dl.git
cd dashboard-dl
```

### 2. Install the UV Python Tool (Recommended)

UV is a fast, modern Python tool that makes setup easy. If you don't have it yet, install it with:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation, restart your terminal or run:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

You can check that UV is installed with:

```bash
uv --version
```

### 3. Set Up a Virtual Environment (Optional but Recommended)

A virtual environment keeps your Python packages isolated. UV handles this automatically when you run commands below.

### 4. Install Project Dependencies

Install all required Python packages using UV:

```bash
uv pip install -r pyproject.toml
```

Or, if you want to use the project as a script, you can run it directly with UV (see below).

### 5. Download a Dashboard

You can now use the tool to download a Flipside dashboard. Replace `<dashboard-url>` with the actual dashboard link:

```bash
uv run dashboard-dl <dashboard-url>
```

#### Example:

```bash
uv run dashboard-dl https://flipsidecrypto.xyz/flipsideteam/near-intents-insights-XO29Lh
```

#### Additional Options:
- `-o <output-dir>`: Specify a folder to save the dashboard (default is current directory)
- `-v`: Enable detailed output (verbose mode)

---

## Installation (Advanced/Alternative)

If you prefer, you can install dependencies and run the tool using standard Python tools. Make sure you have Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r pyproject.toml
python -m dashboard_dl.main <dashboard-url>
```

---

## Usage

```bash
# Download a dashboard
uv run dashboard-dl https://flipsidecrypto.xyz/flipsideteam/near-intents-insights-XO29Lh

# Specify output directory
uv run dashboard-dl https://flipsidecrypto.xyz/flipsideteam/near-intents-insights-XO29Lh -o ./downloads

# Enable verbose output
uv run dashboard-dl https://flipsidecrypto.xyz/flipsideteam/near-intents-insights-XO29Lh -v
```