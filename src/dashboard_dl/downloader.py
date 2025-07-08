"""Core dashboard downloader functionality"""

import requests
import json
import re
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any


class DashboardDownloader:
    """Downloads and processes Flipside Crypto dashboards"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def log(self, message: str):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[INFO] {message}")
    
    def download(self, url: str, output_dir: str) -> str:
        """Download and process a dashboard from the given URL"""
        self.log(f"Starting download from {url}")
        
        # Extract dashboard slug from URL
        slug = self._extract_slug(url)
        if not slug:
            raise ValueError("Could not extract dashboard slug from URL")
        
        # Create output directory
        dashboard_dir = Path(output_dir) / slug
        dashboard_dir.mkdir(parents=True, exist_ok=True)
        self.log(f"Created output directory: {dashboard_dir}")
        
        # Download and parse main dashboard page
        html_content = self._fetch_page(url)
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract dashboard metadata
        metadata = self._extract_metadata(soup, url)
        
        # Create subdirectories
        viz_dir = dashboard_dir / "visualizations"
        assets_dir = dashboard_dir / "assets"
        viz_dir.mkdir(exist_ok=True)
        assets_dir.mkdir(exist_ok=True)
        
        # Extract and save visualizations
        visualizations = self._extract_visualizations(soup, viz_dir, assets_dir)
        
        # Generate dashboard.md
        self._generate_markdown(metadata, visualizations, dashboard_dir)
        
        # Generate metadata.json artifact
        self._generate_json_artifact(metadata, visualizations, dashboard_dir)
        
        # Generate index.html
        self._generate_html(metadata, visualizations, dashboard_dir)
        
        self.log("Download completed successfully")
        return str(dashboard_dir)
    
    def _extract_slug(self, url: str) -> Optional[str]:
        """Extract dashboard slug from URL"""
        parts = url.rstrip('/').split('/')
        if len(parts) >= 2:
            return parts[-1]
        return None
    
    def _fetch_page(self, url: str) -> str:
        """Fetch page content from URL"""
        self.log(f"Fetching page: {url}")
        response = self.session.get(url)
        response.raise_for_status()
        return response.text
    
    def _extract_metadata(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract dashboard metadata from page"""
        metadata = {
            'url': url,
            'title': None,
            'author': None,
            'abstract': None,
            'tags': []
        }
        
        # Look for dashboard data in script tags
        dashboard_data = self._extract_dashboard_data(soup)
        
        if dashboard_data:
            # Extract title from dashboard data
            if 'title' in dashboard_data:
                metadata['title'] = dashboard_data['title']
            
            # Extract description from published config
            config_key = 'publishedConfig' if 'publishedConfig' in dashboard_data else 'draftConfig'
            if config_key in dashboard_data:
                config = dashboard_data[config_key]
                contents = config.get('contents', {})
                
                # Look for root-header content
                root_header = contents.get('root-header', {})
                if 'dashboardTitle' in root_header:
                    metadata['title'] = root_header['dashboardTitle']
                if 'dashboardDescription' in root_header:
                    metadata['abstract'] = root_header['dashboardDescription']
        
        # Fallback to traditional extraction if no dashboard data found
        if not metadata['title']:
            title_elem = soup.find('title')
            if title_elem:
                metadata['title'] = title_elem.get_text().strip()
            
            # Try to find dashboard title in common locations
            for selector in ['h1', '.dashboard-title', '[data-testid="dashboard-title"]']:
                elem = soup.select_one(selector)
                if elem:
                    metadata['title'] = elem.get_text().strip()
                    break
        
        # Extract author/team info - skip for now to avoid JSON dump
        # Will be extracted from proper metadata in future versions
        
        # Extract abstract/description if not found in dashboard data
        if not metadata['abstract']:
            desc_selectors = [
                '.dashboard-description',
                '[data-testid="dashboard-description"]',
                'meta[name="description"]',
                'meta[property="og:description"]'
            ]
            
            for selector in desc_selectors:
                elem = soup.select_one(selector)
                if elem:
                    if elem.name == 'meta':
                        metadata['abstract'] = elem.get('content', '').strip()
                    else:
                        metadata['abstract'] = elem.get_text().strip()
                    break
        
        # Extract tags
        tag_elems = soup.find_all(class_=re.compile(r'tag', re.I))
        for elem in tag_elems:
            tag_text = elem.get_text().strip()
            if tag_text.startswith('#'):
                metadata['tags'].append(tag_text)
        
        return metadata
    
    def _extract_dashboard_data(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Extract dashboard data from script tags"""
        script_tags = soup.find_all('script')
        
        for script in script_tags:
            if not script.string:
                continue
                
            # Look for __remixContext or similar dashboard data
            if '__remixContext' in script.string:
                try:
                    # Extract JSON data from the script
                    json_start = script.string.find('{')
                    json_end = script.string.rfind('}') + 1
                    
                    if json_start != -1 and json_end > json_start:
                        json_str = script.string[json_start:json_end]
                        data = json.loads(json_str)
                        
                        # Navigate to dashboard data
                        if 'state' in data and 'loaderData' in data['state']:
                            loader_data = data['state']['loaderData']
                            for value in loader_data.values():
                                if isinstance(value, dict) and 'dashboard' in value:
                                    return value['dashboard']
                        
                except (json.JSONDecodeError, KeyError) as e:
                    self.log(f"Error parsing dashboard data: {e}")
                    continue
        
        return None
    
    def _extract_visualizations(self, soup: BeautifulSoup, viz_dir: Path, assets_dir: Path) -> List[Dict[str, Any]]:
        """Extract visualization data from dashboard"""
        visualizations = []
        
        # Extract dashboard data containing visualization and query information
        dashboard_data = self._extract_dashboard_data(soup)
        
        if dashboard_data:
            # Extract visualizations from dashboard config
            visualizations = self._process_dashboard_visualizations(dashboard_data, viz_dir, assets_dir)
        
        # Fallback: Look for query links in the HTML
        query_links = soup.find_all('a', href=re.compile(r'/queries/'))
        for i, link in enumerate(query_links):
            query_url = urljoin('https://flipsidecrypto.xyz', link['href'])
            self.log(f"Found query link: {query_url}")
            
            # Try to fetch SQL query
            try:
                sql_content = self._fetch_sql_query(query_url)
                if sql_content:
                    sql_file = assets_dir / f'query-{i+1}.sql'
                    with open(sql_file, 'w') as f:
                        f.write(sql_content)
                    self.log(f"Saved SQL query to {sql_file}")
            except Exception as e:
                self.log(f"Could not fetch SQL query: {e}")
        
        return visualizations
    
    def _process_dashboard_visualizations(self, dashboard_data: Dict[str, Any], viz_dir: Path, assets_dir: Path) -> List[Dict[str, Any]]:
        """Process visualizations from dashboard data"""
        visualizations = []
        processed_queries = set()  # Track processed query IDs to avoid duplication
        
        try:
            # Look for visualization cells in published config
            config_key = 'publishedConfig' if 'publishedConfig' in dashboard_data else 'draftConfig'
            
            if config_key in dashboard_data:
                config = dashboard_data[config_key]
                
                # Extract contents and cells
                contents = config.get('contents', {})
                cells = config.get('cells', {})
                
                chart_count = 0
                
                # Process each visualization cell
                for cell_id, cell_data in cells.items():
                    if cell_data.get('variant') == 'visualization':
                        chart_count += 1
                        
                        # Get visualization content
                        viz_content = contents.get(cell_id, {})
                        
                        # Extract chart type (will be enhanced with API data)
                        chart_type = self._extract_chart_type(viz_content, dashboard_data)
                        
                        # Find compass ID and query metadata for this query
                        query_id = viz_content.get('queryId')
                        compass_id = self._find_compass_id_for_query(query_id, dashboard_data)
                        query_metadata = self._get_query_metadata(query_id, dashboard_data)
                        
                        # Extract Highcharts configuration from API first (contains title)
                        chart_config = self._fetch_chart_config_from_api(viz_content.get('visId'))
                        
                        # Extract chart title with API data preferred
                        chart_title = self._extract_chart_title_with_api(viz_content, cell_data, dashboard_data, chart_config)
                        
                        # Extract axes information (enhanced with API data)
                        axes_info = self._extract_axes_info_with_api(viz_content, dashboard_data, chart_config)
                        
                        # Use API chart type if available
                        final_chart_type = chart_config.get('type', chart_type)
                        
                        viz_info = {
                            'id': f'chart-{chart_count}',
                            'cell_id': cell_id,
                            'title': chart_title,
                            'type': final_chart_type,
                            'vis_id': viz_content.get('visId'),
                            'query_id': query_id,
                            'compass_id': compass_id,
                            'query_metadata': query_metadata,
                            'axes': axes_info,
                            'chart_config': chart_config
                        }
                        
                        # Save enhanced visualization config
                        config_file = viz_dir / f'chart-{chart_count}.json'
                        enhanced_config = {
                            'id': f'chart-{chart_count}',
                            'cell_id': cell_id,
                            'title': chart_title,
                            'type': final_chart_type,
                            'vis_id': viz_content.get('visId'),
                            'query_id': query_id,
                            'axes': axes_info,
                            'chart_config': chart_config,
                            'original_viz_content': viz_content
                        }
                        with open(config_file, 'w') as f:
                            json.dump(enhanced_config, f, indent=2)
                        
                        # Only process SQL and CSV if we haven't seen this query before
                        if query_id and query_id not in processed_queries:
                            processed_queries.add(query_id)
                            
                            # Try to extract SQL query from dashboard data first
                            sql_extracted = self._extract_sql_from_dashboard_data(
                                query_id, query_id, assets_dir, dashboard_data
                            )
                            
                            # Fallback to studio URL if not found in dashboard data
                            if not sql_extracted:
                                self._extract_sql_for_query(query_id, query_id, assets_dir)
                            
                            # Try to fetch CSV data using compass ID
                            if compass_id:
                                self._fetch_csv_data_from_compass(compass_id, query_id, assets_dir)
                        
                        visualizations.append(viz_info)
                        self.log(f"Processed visualization: {viz_info['title']} ({chart_type})")
                
        except Exception as e:
            self.log(f"Error processing dashboard visualizations: {e}")
        
        return visualizations
    
    def _extract_chart_type(self, viz_content: Dict[str, Any], dashboard_data: Dict[str, Any]) -> str:
        """Extract the actual chart type (bar, line, pie, etc.) from visualization data"""
        try:
            # Look for chart type in the visualization definition
            vis_id = viz_content.get('visId')
            if not vis_id:
                return 'unknown'
            
            # Search through the dashboard data for visualization definitions
            # This might be in different locations depending on the dashboard structure
            config_key = 'publishedConfig' if 'publishedConfig' in dashboard_data else 'draftConfig'
            config = dashboard_data.get(config_key, {})
            
            # Check if there are visualization definitions with chart type info
            visualizations = config.get('visualizations', {})
            if vis_id in visualizations:
                viz_def = visualizations[vis_id]
                chart_type = viz_def.get('chartType') or viz_def.get('type') or viz_def.get('chart_type')
                if chart_type:
                    return chart_type
            
            # Fallback: try to infer from title or other metadata
            title = viz_content.get('title', '').lower()
            if 'bar' in title:
                return 'bar'
            elif 'line' in title:
                return 'line'
            elif 'pie' in title:
                return 'pie'
            elif 'histogram' in title:
                return 'histogram'
            elif 'scatter' in title:
                return 'scatter'
            elif 'table' in title:
                return 'table'
            else:
                return 'chart'
                
        except Exception as e:
            self.log(f"Error extracting chart type: {e}")
            return 'unknown'
    
    def _extract_chart_title(self, viz_content: Dict[str, Any], cell_data: Dict[str, Any], dashboard_data: Dict[str, Any]) -> str:
        """Extract chart title from multiple sources"""
        try:
            # Check viz_content for title
            if viz_content.get('title'):
                return viz_content['title']
            
            # Check cell_data for title
            if cell_data.get('title'):
                return cell_data['title']
            
            # Look for display name or label
            if viz_content.get('displayName'):
                return viz_content['displayName']
            
            if viz_content.get('label'):
                return viz_content['label']
            
            # Try to find visualization definition in dashboard data
            vis_id = viz_content.get('visId')
            if vis_id:
                config_key = 'publishedConfig' if 'publishedConfig' in dashboard_data else 'draftConfig'
                config = dashboard_data.get(config_key, {})
                
                # Look for visualization definition
                visualizations = config.get('visualizations', {})
                if vis_id in visualizations:
                    viz_def = visualizations[vis_id]
                    if viz_def.get('title'):
                        return viz_def['title']
                    if viz_def.get('displayName'):
                        return viz_def['displayName']
            
            # Fallback to generic title
            return f"Chart {viz_content.get('id', 'Unknown')}"
            
        except Exception as e:
            self.log(f"Error extracting chart title: {e}")
            return "Untitled Chart"
    
    def _extract_chart_title_with_api(self, viz_content: Dict[str, Any], cell_data: Dict[str, Any], dashboard_data: Dict[str, Any], chart_config: Dict[str, Any]) -> str:
        """Extract chart title preferring API data"""
        try:
            # First check API config for title
            api_title = chart_config.get('title', '')
            if api_title:
                return api_title
            
            # Fall back to original method
            return self._extract_chart_title(viz_content, cell_data, dashboard_data)
            
        except Exception as e:
            self.log(f"Error extracting chart title with API: {e}")
            return self._extract_chart_title(viz_content, cell_data, dashboard_data)
    
    def _extract_axes_info_with_api(self, viz_content: Dict[str, Any], dashboard_data: Dict[str, Any], chart_config: Dict[str, Any]) -> Dict[str, Any]:
        """Extract axes information preferring API data"""
        axes_info = {}
        
        try:
            # Get axes from API config
            api_x_axis = chart_config.get('xAxis', {})
            api_y_axis = chart_config.get('yAxis', {})
            
            if api_x_axis:
                axes_info['xAxis'] = api_x_axis
            if api_y_axis:
                axes_info['yAxis'] = api_y_axis
            
            # Add subtitle if available
            subtitle = chart_config.get('subtitle', '')
            if subtitle:
                axes_info['subtitle'] = subtitle
            
            # Fall back to original method and merge
            original_axes = self._extract_axes_info(viz_content, dashboard_data)
            for key, value in original_axes.items():
                if key not in axes_info:
                    axes_info[key] = value
            
        except Exception as e:
            self.log(f"Error extracting axes info with API: {e}")
            axes_info = self._extract_axes_info(viz_content, dashboard_data)
        
        return axes_info
    
    def _extract_axes_info(self, viz_content: Dict[str, Any], dashboard_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract axes information from visualization data"""
        axes_info = {}
        
        try:
            # Look for axes configuration in viz_content
            if 'axes' in viz_content:
                axes_info = viz_content['axes']
            
            # Try to find in visualization definition
            vis_id = viz_content.get('visId')
            if vis_id:
                config_key = 'publishedConfig' if 'publishedConfig' in dashboard_data else 'draftConfig'
                config = dashboard_data.get(config_key, {})
                
                visualizations = config.get('visualizations', {})
                if vis_id in visualizations:
                    viz_def = visualizations[vis_id]
                    if 'axes' in viz_def:
                        axes_info.update(viz_def['axes'])
                    
                    # Look for xAxis and yAxis specifically
                    if 'xAxis' in viz_def:
                        axes_info['xAxis'] = viz_def['xAxis']
                    if 'yAxis' in viz_def:
                        axes_info['yAxis'] = viz_def['yAxis']
            
        except Exception as e:
            self.log(f"Error extracting axes info: {e}")
        
        return axes_info
    
    def _extract_chart_config(self, viz_content: Dict[str, Any], dashboard_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Highcharts configuration from visualization data"""
        chart_config = {}
        
        try:
            # Look for chart configuration in viz_content
            if 'chartConfig' in viz_content:
                chart_config = viz_content['chartConfig']
            
            # Try to find full visualization definition
            vis_id = viz_content.get('visId')
            if vis_id:
                config_key = 'publishedConfig' if 'publishedConfig' in dashboard_data else 'draftConfig'
                config = dashboard_data.get(config_key, {})
                
                visualizations = config.get('visualizations', {})
                if vis_id in visualizations:
                    viz_def = visualizations[vis_id]
                    
                    # Extract various configuration keys
                    config_keys = ['chartConfig', 'highchartsConfig', 'config', 'options', 'chartOptions']
                    for key in config_keys:
                        if key in viz_def:
                            chart_config.update(viz_def[key])
                    
                    # Also capture the full visualization definition for reference
                    chart_config['_full_viz_def'] = viz_def
            
        except Exception as e:
            self.log(f"Error extracting chart config: {e}")
        
        return chart_config
    
    def _fetch_chart_config_from_api(self, vis_id: str) -> Dict[str, Any]:
        """Fetch chart configuration from Flipside visualization API"""
        if not vis_id:
            return {}
        
        try:
            api_url = f"https://flipsidecrypto.xyz/api/visualizations/{vis_id}"
            self.log(f"Fetching chart config from {api_url}")
            
            response = self.session.get(api_url)
            response.raise_for_status()
            
            viz_data = response.json()
            
            # Extract relevant configuration
            config = viz_data.get('config', {})
            chart_config = {
                'type': config.get('inputs', {}).get('type', 'unknown'),
                'title': config.get('options', {}).get('title', {}).get('text', ''),
                'subtitle': config.get('options', {}).get('subtitle', {}).get('text', ''),
                'xAxis': config.get('options', {}).get('xAxis', {}),
                'yAxis': config.get('options', {}).get('yAxis', {}),
                'colors': config.get('options', {}).get('colors', []),
                'plotOptions': config.get('options', {}).get('plotOptions', {}),
                'inputs': config.get('inputs', {}),
                'options': config.get('options', {}),
                'api_version': viz_data.get('version'),
                'created_at': viz_data.get('createdAt'),
                'updated_at': viz_data.get('updatedAt'),
                '_full_api_response': viz_data
            }
            
            self.log(f"Successfully fetched config for {vis_id}: {chart_config.get('type')} chart")
            return chart_config
            
        except Exception as e:
            self.log(f"Error fetching chart config for {vis_id}: {e}")
            return {}
    
    def _extract_sql_from_dashboard_data(self, query_id: str, file_identifier: str, assets_dir: Path, dashboard_data: Dict[str, Any]) -> bool:
        """Extract SQL statement from dashboard data if available"""
        try:
            if not query_id:
                return False
            
            # Search through the dashboard data for SQL statements
            # Look for "statement" key as mentioned by the user
            def find_statement_recursive(data, target_query_id):
                if isinstance(data, dict):
                    # Check if this object has the query ID and statement
                    if data.get('id') == target_query_id and 'statement' in data:
                        return data['statement']
                    
                    # Recursively search through all values
                    for value in data.values():
                        result = find_statement_recursive(value, target_query_id)
                        if result:
                            return result
                elif isinstance(data, list):
                    for item in data:
                        result = find_statement_recursive(item, target_query_id)
                        if result:
                            return result
                return None
            
            # Search for the SQL statement
            sql_statement = find_statement_recursive(dashboard_data, query_id)
            
            if sql_statement:
                sql_file = assets_dir / f'{file_identifier}.sql'
                with open(sql_file, 'w') as f:
                    f.write(sql_statement)
                self.log(f"Extracted SQL statement from dashboard data for {file_identifier}")
                return True
            
        except Exception as e:
            self.log(f"Error extracting SQL from dashboard data: {e}")
        
        return False
    
    def _extract_sql_for_query(self, query_id: str, file_identifier: str, assets_dir: Path):
        """Extract SQL query for a given query ID using studio URL"""
        try:
            # Use the studio URL as fallback
            studio_url = f"https://flipsidecrypto.xyz/studio/queries/{query_id}"
            self.log(f"Attempting to fetch SQL from studio URL for query {query_id}")
            
            sql_content = self._fetch_sql_query(studio_url)
            if sql_content:
                sql_file = assets_dir / f'{file_identifier}.sql'
                with open(sql_file, 'w') as f:
                    f.write(sql_content)
                self.log(f"Saved SQL query to {sql_file}")
                return True
            
            # Also try to fetch CSV data if available
            self._try_fetch_csv_data(query_id, file_identifier, assets_dir)
            
        except Exception as e:
            self.log(f"Could not extract SQL for query {query_id}: {e}")
        
        return False
    
    def _try_fetch_csv_data(self, query_id: str, file_identifier: str, assets_dir: Path):
        """Try to fetch CSV data for a query"""
        try:
            # Try common CSV endpoint patterns
            csv_urls = [
                f"https://flipsidecrypto.xyz/api/queries/{query_id}/data/csv",
                f"https://flipsidecrypto.xyz/studio/queries/{query_id}/data.csv"
            ]
            
            for csv_url in csv_urls:
                try:
                    response = self.session.get(csv_url)
                    if response.status_code == 200 and 'text/csv' in response.headers.get('content-type', ''):
                        csv_file = assets_dir / f'{file_identifier}.csv'
                        with open(csv_file, 'w') as f:
                            f.write(response.text)
                        self.log(f"Saved CSV data to {csv_file}")
                        return True
                except Exception:
                    continue
        except Exception as e:
            self.log(f"Could not fetch CSV data for query {query_id}: {e}")
        
        return False
    
    def _fetch_sql_query(self, query_url: str) -> Optional[str]:
        """Fetch SQL query from query URL"""
        try:
            response = self.session.get(query_url)
            response.raise_for_status()
            
            # Parse the query page to extract SQL
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for SQL content in common locations
            sql_selectors = [
                'pre code',
                '.sql-query',
                '[data-testid="sql-query"]',
                'textarea'
            ]
            
            for selector in sql_selectors:
                elem = soup.select_one(selector)
                if elem:
                    sql_text = elem.get_text().strip()
                    if sql_text and ('select' in sql_text.lower() or 'with' in sql_text.lower()):
                        return sql_text
            
        except Exception as e:
            self.log(f"Error fetching SQL query: {e}")
        
        return None
    
    def _generate_markdown(self, metadata: Dict[str, Any], visualizations: List[Dict[str, Any]], output_dir: Path):
        """Generate dashboard.md file"""
        md_content = []
        
        # Overview section
        md_content.append("# Dashboard Overview\n")
        md_content.append(f"**Title:** {metadata.get('title', 'Unknown')}\n")
        md_content.append(f"**URL:** {metadata['url']}\n")
        
        if metadata.get('author'):
            md_content.append(f"**Author:** {metadata['author']}\n")
        
        if metadata.get('abstract'):
            md_content.append(f"**Abstract:** {metadata['abstract']}\n")
        
        if metadata.get('tags'):
            md_content.append(f"**Tags:** {', '.join(metadata['tags'])}\n")
        
        # Data Sources section
        md_content.append("\n## Data Sources\n")
        
        # Collect unique data sources from SQL files
        data_sources = set()
        assets_dir = output_dir / "assets"
        
        for sql_file in assets_dir.glob("*.sql"):
            try:
                with open(sql_file, 'r') as f:
                    sql_content = f.read()
                    # Extract table references (basic pattern matching)
                    table_matches = re.findall(r'\b\w+\.\w+\.\w+\b', sql_content, re.IGNORECASE)
                    for match in table_matches:
                        data_sources.add(match)
            except Exception as e:
                self.log(f"Error reading SQL file {sql_file}: {e}")
        
        if data_sources:
            md_content.append("The following data sources are referenced in the dashboard queries:\n")
            for source in sorted(data_sources):
                md_content.append(f"- `{source}`\n")
        else:
            md_content.append("*Data sources will be identified from SQL queries when available*\n")
        
        # Visualizations section
        md_content.append("\n## Visualizations\n")
        
        if not visualizations:
            md_content.append("*No visualizations extracted from dashboard*\n")
        else:
            for viz in visualizations:
                chart_num = viz['id'].split('-')[-1]
                md_content.append(f"\n### Chart {chart_num}: {viz.get('title', 'Untitled')}\n")
                md_content.append(f"- **Chart Type:** {viz.get('type', 'Visualization')}\n")
                md_content.append(f"- **Configuration:** `visualizations/{viz['id']}.json`\n")
                
                # Check if SQL and CSV files exist using query ID
                query_id = viz.get('query_id')
                if query_id:
                    sql_file = output_dir / "assets" / f"{query_id}.sql"
                    if sql_file.exists():
                        md_content.append(f"- **SQL Query:** `assets/{query_id}.sql`\n")
                    else:
                        md_content.append(f"- **SQL Query:** Not publicly accessible\n")
                    
                    csv_file = output_dir / "assets" / f"{query_id}.csv"
                    if csv_file.exists():
                        md_content.append(f"- **Resultset:** `assets/{query_id}.csv`\n")
                    else:
                        md_content.append(f"- **Resultset:** Not available for download\n")
                    
                    md_content.append(f"- **Query ID:** `{query_id}`\n")
                    
                    # Add execution timestamps if available
                    query_metadata = viz.get('query_metadata', {})
                    if query_metadata.get('last_successful_execution'):
                        md_content.append(f"- **Last Executed:** {query_metadata['last_successful_execution']}\n")
                    if query_metadata.get('result_last_accessed'):
                        md_content.append(f"- **Result Last Accessed:** {query_metadata['result_last_accessed']}\n")
                else:
                    md_content.append(f"- **SQL Query:** No query ID available\n")
                    md_content.append(f"- **Resultset:** No query ID available\n")
        
        # Write markdown file
        md_file = output_dir / "dashboard.md"
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_content))
        
        self.log(f"Generated dashboard.md")
    
    def _generate_json_artifact(self, metadata: Dict[str, Any], visualizations: List[Dict[str, Any]], output_dir: Path):
        """Generate comprehensive JSON metadata artifact for programmatic access"""
        import datetime
        
        # Create comprehensive metadata structure
        json_artifact = {
            "metadata": {
                "dashboard_url": metadata.get('url'),
                "title": metadata.get('title'),
                "abstract": metadata.get('abstract'),
                "author": metadata.get('author'),
                "tags": metadata.get('tags', []),
                "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
                "total_charts": len(visualizations),
                "unique_queries": len(set(viz.get('query_id') for viz in visualizations if viz.get('query_id')))
            },
            "queries": {},
            "visualizations": []
        }
        
        # Process each visualization
        for viz in visualizations:
            query_id = viz.get('query_id')
            
            # Add query metadata if not already processed
            if query_id and query_id not in json_artifact["queries"]:
                query_metadata = viz.get('query_metadata', {})
                
                # Check if files exist
                sql_file = output_dir / "assets" / f"{query_id}.sql"
                csv_file = output_dir / "assets" / f"{query_id}.csv"
                
                json_artifact["queries"][query_id] = {
                    "query_id": query_id,
                    "sql_file": f"assets/{query_id}.sql" if sql_file.exists() else None,
                    "csv_file": f"assets/{query_id}.csv" if csv_file.exists() else None,
                    "last_executed": query_metadata.get('last_successful_execution'),
                    "result_last_accessed": query_metadata.get('result_last_accessed'),
                    "compass_id": viz.get('compass_id')
                }
            
            # Add visualization info
            viz_info = {
                "chart_id": viz.get('id'),
                "cell_id": viz.get('cell_id'),
                "title": viz.get('title'),
                "type": viz.get('type'),
                "vis_id": viz.get('vis_id'),
                "query_id": query_id,
                "config_file": f"visualizations/{viz.get('id')}.json",
                "axes": viz.get('axes', {}),
                "chart_config": viz.get('chart_config', {})
            }
            
            json_artifact["visualizations"].append(viz_info)
        
        # Write JSON artifact
        json_file = output_dir / "metadata.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_artifact, f, indent=2, ensure_ascii=False)
        
        self.log(f"Generated metadata.json artifact")
    
    def _generate_html(self, metadata: Dict[str, Any], visualizations: List[Dict[str, Any]], output_dir: Path):
        """Generate interactive HTML dashboard with Chart.js"""
        
        # Generate CSS styles
        css_styles = """
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; 
            margin: 0; 
            padding: 20px; 
            background-color: #f5f7fa; 
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { 
            background: white; 
            padding: 20px; 
            border-radius: 8px; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
            margin-bottom: 20px; 
        }
        .metadata { 
            background: white; 
            padding: 20px; 
            border-radius: 8px; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
            margin-bottom: 20px; 
        }
        .chart-grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); 
            gap: 20px; 
        }
        .chart-container { 
            background: white; 
            padding: 20px; 
            border-radius: 8px; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
        }
        .chart-canvas { 
            max-height: 400px; 
            margin: 15px 0; 
        }
        .chart-title { 
            margin: 0 0 10px 0; 
            color: #2c3e50; 
            font-size: 1.1em; 
        }
        .chart-meta { 
            font-size: 0.9em; 
            color: #7f8c8d; 
            margin-bottom: 15px; 
        }
        .metric-value { 
            font-size: 2em; 
            font-weight: bold; 
            color: #3498db; 
            text-align: center; 
            padding: 20px; 
        }
        """
        
        # Generate JavaScript for chart rendering
        js_content = self._generate_chart_js(visualizations, output_dir)
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{metadata.get('title', 'Dashboard Snapshot')}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>{css_styles}</style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{metadata.get('title', 'Dashboard Snapshot')}</h1>
            <p><strong>Source:</strong> <a href="{metadata['url']}">{metadata['url']}</a></p>
        </div>
        
        <div class="metadata">
            <h2>Dashboard Information</h2>
            <p><strong>Description:</strong> {metadata.get('abstract', 'No description available')}</p>
            <p><strong>Total Charts:</strong> {len(visualizations)}</p>
            <p><strong>Generated:</strong> <span id="generated-time"></span></p>
        </div>
        
        <div class="visualizations">
            <h2>Interactive Visualizations</h2>
            <div class="chart-grid">"""
        
        if not visualizations:
            html_content += """
                <p>No visualizations were extracted from this dashboard.</p>"""
        else:
            for viz in visualizations:
                query_id = viz.get('query_id', '')
                chart_id = f"chart-{viz['id'].split('-')[-1]}"
                
                html_content += f"""
                <div class="chart-container">
                    <h3 class="chart-title">{viz.get('title', 'Untitled Chart')}</h3>
                    <div class="chart-meta">
                        Query ID: {query_id[:8]}... | Type: {viz.get('type', 'Unknown')}
                    </div>
                    <div class="chart-canvas">
                        <canvas id="{chart_id}" width="400" height="300"></canvas>
                    </div>
                </div>"""
        
        html_content += f"""
            </div>
        </div>
    </div>
    
    <script>
        // Set generated time
        document.getElementById('generated-time').textContent = new Date().toLocaleString();
        
        {js_content}
    </script>
</body>
</html>"""
        
        # Write HTML file
        html_file = output_dir / "index.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        self.log(f"Generated interactive HTML dashboard")
    
    def _generate_chart_js(self, visualizations: List[Dict[str, Any]], output_dir: Path) -> str:
        """Generate JavaScript code for rendering charts with CSV data"""
        js_content = []
        
        for viz in visualizations:
            query_id = viz.get('query_id')
            if not query_id:
                continue
                
            chart_id = f"chart-{viz['id'].split('-')[-1]}"
            csv_file = output_dir / "assets" / f"{query_id}.csv"
            
            if csv_file.exists():
                try:
                    # Read and parse CSV data
                    with open(csv_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    if len(lines) < 2:
                        continue
                        
                    headers = [h.strip() for h in lines[0].split(',')]
                    rows = []
                    for line in lines[1:]:
                        if line.strip():
                            row = [cell.strip().strip('"') for cell in line.split(',')]
                            rows.append(row)
                    
                    # Generate chart based on data structure
                    chart_js = self._generate_chart_for_data(chart_id, viz.get('title', 'Chart'), headers, rows)
                    if chart_js:
                        js_content.append(chart_js)
                        
                except Exception as e:
                    self.log(f"Error generating chart for {chart_id}: {e}")
                    # Fallback to placeholder
                    js_content.append(f"""
                    // Error rendering chart {chart_id}: {e}
                    const ctx_{chart_id} = document.getElementById('{chart_id}').getContext('2d');
                    ctx_{chart_id}.fillText('Error loading chart data', 10, 50);
                    """)
        
        return '\n'.join(js_content)
    
    def _generate_chart_for_data(self, chart_id: str, title: str, headers: List[str], rows: List[List[str]]) -> str:
        """Generate Chart.js code based on data structure"""
        
        # Single value metric (1 column, 1 row)
        if len(headers) == 1 and len(rows) == 1:
            try:
                value = float(rows[0][0])
                formatted_value = f"{value:,.0f}" if value > 1000 else f"{value:.2f}"
                return f"""
                // Single metric for {chart_id}
                document.getElementById('{chart_id}').parentElement.innerHTML = 
                    '<div class="metric-value">{formatted_value}</div>' +
                    '<div style="text-align: center; color: #7f8c8d;">{headers[0].replace('_', ' ').title()}</div>';
                """
            except (ValueError, IndexError):
                pass
        
        # Time series data (has DATE column)
        date_col = None
        for i, header in enumerate(headers):
            if 'date' in header.lower() or 'time' in header.lower():
                date_col = i
                break
                
        if date_col is not None and len(headers) >= 2:
            # Use first non-date column as primary metric
            value_col = 0 if date_col != 0 else 1
            if value_col < len(headers):
                return self._generate_time_series_chart(chart_id, title, headers, rows, date_col, value_col)
        
        # Two-column data (category/value pairs)
        if len(headers) == 2 and len(rows) > 1:
            return self._generate_bar_chart(chart_id, title, headers, rows)
        
        # Multi-column data - use as bar chart with first column as labels
        if len(headers) > 2 and len(rows) > 1:
            return self._generate_multi_series_chart(chart_id, title, headers, rows)
        
        # Fallback: display as table
        return self._generate_table_display(chart_id, title, headers, rows)
    
    def _generate_time_series_chart(self, chart_id: str, title: str, headers: List[str], rows: List[List[str]], date_col: int, value_col: int) -> str:
        """Generate time series line chart"""
        try:
            data_points = []
            for row in rows[:50]:  # Limit to 50 points for performance
                if len(row) > max(date_col, value_col):
                    try:
                        date_str = row[date_col].split(' ')[0]  # Extract date part
                        value = float(row[value_col])
                        data_points.append(f"{{x: '{date_str}', y: {value}}}")
                    except (ValueError, IndexError):
                        continue
            
            if not data_points:
                return ""
                
            return f"""
            // Time series chart for {chart_id}
            new Chart(document.getElementById('{chart_id}'), {{
                type: 'line',
                data: {{
                    datasets: [{{
                        label: '{headers[value_col].replace('_', ' ').title()}',
                        data: [{', '.join(data_points)}],
                        borderColor: '#3498db',
                        backgroundColor: 'rgba(52, 152, 219, 0.1)',
                        tension: 0.1
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        title: {{
                            display: false
                        }}
                    }},
                    scales: {{
                        x: {{
                            type: 'time',
                            time: {{
                                parser: 'YYYY-MM-DD'
                            }}
                        }},
                        y: {{
                            beginAtZero: true
                        }}
                    }}
                }}
            }});
            """
        except Exception as e:
            return f"// Error generating time series for {chart_id}: {e}"
    
    def _generate_bar_chart(self, chart_id: str, title: str, headers: List[str], rows: List[List[str]]) -> str:
        """Generate horizontal bar chart for category/value data"""
        try:
            labels = []
            values = []
            
            # Take top 15 items for readability
            for row in rows[:15]:
                if len(row) >= 2:
                    try:
                        label = row[0][:30]  # Truncate long labels
                        value = float(row[1])
                        labels.append(f"'{label}'")
                        values.append(str(value))
                    except (ValueError, IndexError):
                        continue
            
            if not labels:
                return ""
                
            return f"""
            // Bar chart for {chart_id}
            new Chart(document.getElementById('{chart_id}'), {{
                type: 'bar',
                data: {{
                    labels: [{', '.join(labels)}],
                    datasets: [{{
                        label: '{headers[1].replace('_', ' ').title()}',
                        data: [{', '.join(values)}],
                        backgroundColor: 'rgba(52, 152, 219, 0.6)',
                        borderColor: '#3498db',
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    indexAxis: 'y',
                    plugins: {{
                        legend: {{
                            display: false
                        }}
                    }},
                    scales: {{
                        x: {{
                            beginAtZero: true
                        }}
                    }}
                }}
            }});
            """
        except Exception as e:
            return f"// Error generating bar chart for {chart_id}: {e}"
    
    def _generate_multi_series_chart(self, chart_id: str, title: str, headers: List[str], rows: List[List[str]]) -> str:
        """Generate multi-series bar chart"""
        try:
            labels = []
            datasets = []
            
            # Use first column as labels, rest as data series
            for row in rows[:10]:  # Limit for performance
                if len(row) >= len(headers):
                    labels.append(f"'{row[0][:20]}'")  # Truncate label
            
            colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c']
            
            for i, header in enumerate(headers[1:]):  # Skip first column (labels)
                if i >= len(colors):
                    break
                    
                values = []
                for row in rows[:10]:
                    if len(row) > i + 1:
                        try:
                            values.append(str(float(row[i + 1])))
                        except (ValueError, IndexError):
                            values.append('0')
                    else:
                        values.append('0')
                
                datasets.append(f"""{{
                    label: '{header.replace('_', ' ').title()}',
                    data: [{', '.join(values)}],
                    backgroundColor: '{colors[i]}',
                    borderColor: '{colors[i]}',
                    borderWidth: 1
                }}""")
            
            return f"""
            // Multi-series chart for {chart_id}
            new Chart(document.getElementById('{chart_id}'), {{
                type: 'bar',
                data: {{
                    labels: [{', '.join(labels)}],
                    datasets: [{', '.join(datasets)}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            position: 'top'
                        }}
                    }},
                    scales: {{
                        y: {{
                            beginAtZero: true
                        }}
                    }}
                }}
            }});
            """
        except Exception as e:
            return f"// Error generating multi-series chart for {chart_id}: {e}"
    
    def _generate_table_display(self, chart_id: str, title: str, headers: List[str], rows: List[List[str]]) -> str:
        """Generate table display for complex data"""
        try:
            table_html = "<table style='width:100%; border-collapse: collapse;'>"
            table_html += "<tr>" + "".join([f"<th style='border:1px solid #ddd; padding:8px; background:#f2f2f2;'>{h}</th>" for h in headers[:5]]) + "</tr>"
            
            for row in rows[:10]:  # Show first 10 rows
                table_html += "<tr>" + "".join([f"<td style='border:1px solid #ddd; padding:8px;'>{cell[:50]}</td>" for cell in row[:5]]) + "</tr>"
            
            table_html += "</table>"
            
            return f"""
            // Table display for {chart_id}
            document.getElementById('{chart_id}').parentElement.innerHTML = '{table_html}';
            """
        except Exception as e:
            return f"// Error generating table for {chart_id}: {e}"
    
    def _find_compass_id_for_query(self, query_id: str, dashboard_data: Dict[str, Any]) -> Optional[str]:
        """Find compass ID for a given query ID"""
        if not query_id:
            return None
        
        try:
            # Look for queries array in dashboard data
            queries = dashboard_data.get('queries', [])
            for query in queries:
                if query.get('id') == query_id:
                    # Try to get the lastSuccessfulCompassId or lastExecutedCompassId
                    compass_id = query.get('lastSuccessfulCompassId') or query.get('lastExecutedCompassId')
                    if compass_id:
                        self.log(f"Found compass ID {compass_id} for query {query_id}")
                        return compass_id
            
            self.log(f"No compass ID found for query {query_id}")
            return None
        except Exception as e:
            self.log(f"Error finding compass ID for query {query_id}: {e}")
            return None
    
    def _fetch_csv_data_from_compass(self, compass_id: str, file_identifier: str, assets_dir: Path) -> bool:
        """Fetch CSV data using compass ID from query-runs API"""
        try:
            api_url = f"https://flipsidecrypto.xyz/api/query-runs/{compass_id}/results"
            self.log(f"Fetching CSV data from {api_url}")
            
            response = self.session.get(api_url)
            if response.status_code == 200:
                data = response.json()
                
                # Extract columns and csvData
                columns = data.get('columns', [])
                csv_data = data.get('csvData', [])
                
                if columns and csv_data:
                    # Convert to CSV format
                    csv_content = []
                    csv_content.append(','.join(columns))  # Header row
                    
                    for row in csv_data:
                        # Convert each row to CSV, handling quotes and escaping
                        csv_row = []
                        for cell in row:
                            if isinstance(cell, str) and (',' in cell or '"' in cell or '\n' in cell):
                                # Escape quotes and wrap in quotes
                                escaped_cell = cell.replace('"', '""')
                                csv_row.append(f'"{escaped_cell}"')
                            else:
                                csv_row.append(str(cell))
                        csv_content.append(','.join(csv_row))
                    
                    # Save CSV file
                    csv_file = assets_dir / f'{file_identifier}.csv'
                    with open(csv_file, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(csv_content))
                    
                    self.log(f"Saved CSV data to {csv_file} ({len(csv_data)} rows)")
                    return True
                else:
                    self.log(f"No CSV data found in response for compass ID {compass_id}")
            else:
                self.log(f"Failed to fetch CSV data for compass ID {compass_id}: HTTP {response.status_code}")
                
        except Exception as e:
            self.log(f"Error fetching CSV data for compass ID {compass_id}: {e}")
        
        return False
    
    def _get_query_metadata(self, query_id: str, dashboard_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get metadata for a query including execution timestamps"""
        metadata = {
            'last_executed': None,
            'last_successful_execution': None,
            'result_last_accessed': None
        }
        
        if not query_id:
            return metadata
        
        try:
            queries = dashboard_data.get('queries', [])
            for query in queries:
                if query.get('id') == query_id:
                    metadata['last_executed'] = query.get('lastExecutedAt')
                    metadata['last_successful_execution'] = query.get('lastSuccessfulExecutionAt')
                    metadata['result_last_accessed'] = query.get('resultLastAccessedAt')
                    break
            
            return metadata
        except Exception as e:
            self.log(f"Error getting query metadata for {query_id}: {e}")
            return metadata