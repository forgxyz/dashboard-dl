"""Main CLI entry point for dashboard-dl tool"""

import click
import os
import sys
from pathlib import Path
from .downloader import DashboardDownloader


@click.command()
@click.argument('url', required=True)
@click.option('--output-dir', '-o', default='.', help='Output directory for downloaded dashboard')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
def cli(url: str, output_dir: str, verbose: bool):
    """Download and preserve a Flipside Crypto Data Studio dashboard.
    
    URL: Public Flipside dashboard URL (e.g., https://flipsidecrypto.xyz/flipsideteam/dashboard-slug)
    """
    if verbose:
        click.echo(f"Downloading dashboard from: {url}")
    
    try:
        downloader = DashboardDownloader(verbose=verbose)
        dashboard_dir = downloader.download(url, output_dir)
        
        click.echo(f"Dashboard successfully downloaded to: {dashboard_dir}")
        
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()