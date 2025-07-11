# Dashboard Download Tool

A Python tool to download and preserve Flipside Crypto Data Studio dashboard artifacts. This script extracts sql queries, the latest cached resultset, chart configurations and text blocks and builds a description markdown file, as well as logging the queries and results for use in Snowflake.

## Output
When you run the tool to download a dashboard, it generates an archive with the following structure:

```
outputs/<dashboard-title>/
├── assets/
│   ├── <query-name>.sql         # SQL file for each dashboard query
│   ├── <query-name>.csv         # CSV file with the latest cached results for each query
│   ├── <chart-n>.json        # JSON file for each chart configuration
│   └── ...
├── metadata.json                # Metadata about the dashboard (title, author, etc.)
├── description.md               # Markdown file describing the dashboard, queries, and charts
```

- **assets/**: Contains all extracted SQL queries, their latest resultsets as CSVs, and chart configuration files as JSON.
- **metadata.json**: Captures dashboard-level metadata such as title, author, creation date, and other relevant properties.
- **description.md**: A human-readable markdown summary of the dashboard, including descriptions, query explanations, and chart overviews.

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

### 3. Set Up Environment and Install Dependencies

UV will automatically create a virtual environment (if one does not exist) and install all required Python packages from `pyproject.toml` (and `requirements.txt` if present) with a single command:

```bash
uv sync
```

That's it! You're ready to use the tool.

### 4. Download a Dashboard

You can now use the tool to download a Flipside dashboard. Replace `<dashboard-url>` with the actual dashboard link:

```bash
uv run dashboard-dl <dashboard-url>
```

#### Additional Options:
- `-o <output-dir>`: Specify a folder to save the dashboard (default is /outputs in the current directory)
- `-v`: Enable detailed output (verbose mode)

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

---

## Global Installation (Use the CLI from Anywhere)

If you want to use `dashboard-dl` as a command-line tool from any directory, you can install it globally. The recommended way is with [`pipx`](https://pypa.github.io/pipx/), which provides isolated environments for Python CLI tools.

### 1. Install with pipx (Recommended)

**a. Install pipx (if you don't have it):**
```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```
Restart your shell or run `source ~/.profile` if needed.

**b. Install dashboard-dl globally:**
From your project directory:
```bash
pipx install .
```
Now you can run `dashboard-dl <args>` from any directory.

**c. Upgrade after making changes:**
If you update the project and want to upgrade your global CLI:
```bash
pipx upgrade dashboard-dl
```

**d. Uninstall (remove) the CLI:**
```bash
pipx uninstall dashboard-dl
```

### 2. Alternative: Symlink the Script

If you prefer, you can symlink the script to a directory in your `PATH` (e.g., `~/.local/bin`).

**a. Create a symlink:**
```bash
ln -s /full/path/to/dashboard-dl ~/.local/bin/dashboard-dl
```
Make sure `~/.local/bin` is in your `PATH`.

**b. Remove the symlink:**
```bash
rm ~/.local/bin/dashboard-dl
```

**Note:** The symlink method does not isolate dependencies. You must ensure the correct Python environment is active, or the script uses a shebang pointing to the right interpreter.
