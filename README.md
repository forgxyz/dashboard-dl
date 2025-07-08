# Dashboard Download Tool

A Python tool to download and preserve Flipside Crypto Data Studio dashboards.

## Installation

```bash
uv run dashboard-dl <dashboard-url>
```

## Usage

```bash
# Download a dashboard
uv run dashboard-dl https://flipsidecrypto.xyz/flipsideteam/near-intents-insights-XO29Lh

# Specify output directory
uv run dashboard-dl https://flipsidecrypto.xyz/flipsideteam/near-intents-insights-XO29Lh -o ./downloads

# Enable verbose output
uv run dashboard-dl https://flipsidecrypto.xyz/flipsideteam/near-intents-insights-XO29Lh -v
```