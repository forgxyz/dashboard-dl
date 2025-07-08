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
    
    def download(self, url: str, output_dir: str = './outputs') -> str:
        """Download and process a dashboard from the given URL. Artifacts are placed in the outputs directory by default."""
        self.log(f"Starting download from {url}")
        
        # Use default outputs directory if output_dir is None or empty
        if not output_dir:
            output_dir = './outputs'
        
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
        assets_dir = dashboard_dir / "assets"
        assets_dir.mkdir(exist_ok=True)
        
        # Extract and save visualizations and text blocks
        visualizations, text_blocks = self._extract_visualizations(soup, assets_dir)
        
        # Generate descriptive markdown
        self._generate_markdown(metadata, visualizations, text_blocks, dashboard_dir)
        
        # Generate metadata.json artifact
        self._generate_json_artifact(metadata, visualizations, text_blocks, dashboard_dir)
        
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
        self.log(f"Response status: {response.status_code}")
        return response.text
    
    def _extract_metadata(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract dashboard metadata from page"""
        self.log(f"Extracting metadata from page: {url}")
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
            config_key = 'publishedConfig' if ('publishedConfig' in dashboard_data and dashboard_data['publishedConfig'] is not None) else 'draftConfig'
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
        
        # Extract author/team info - skip for now to avoid JSON dump - TODO
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
    
    def _extract_visualizations(self, soup: BeautifulSoup, assets_dir: Path) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Extract visualization data and text blocks from dashboard"""
        visualizations = []
        text_blocks = []
        
        # Extract dashboard data containing visualization and query information
        dashboard_data = self._extract_dashboard_data(soup)

        # log dashboard_data to a json file
        # with open('dashboard_data.json', 'w') as f:
        #     json.dump(dashboard_data, f, indent=2)

        if dashboard_data:
            # Extract visualizations and text blocks from dashboard config
            visualizations, text_blocks = self._process_dashboard_content(dashboard_data, assets_dir)
        else:
            # No dashboard data found, text_blocks remains empty
            text_blocks = []
        
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

        return visualizations, text_blocks
    
    def _process_dashboard_content(self, dashboard_data: Dict[str, Any], assets_dir: Path) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Process all content from dashboard data including visualizations and text blocks"""
        visualizations = []
        text_blocks = []
        processed_queries = set()  # Track processed query IDs to avoid duplication
        
        try:
            # Look for visualization cells in published config
            config_key = 'publishedConfig' if ('publishedConfig' in dashboard_data and dashboard_data['publishedConfig'] is not None) else 'draftConfig'
            
            if config_key in dashboard_data:
                config = dashboard_data[config_key]
                
                # Extract contents and cells
                contents = config.get('contents', {})
                cells = config.get('cells', {})
                
                chart_count = 0
                
                # Process each cell (visualizations and text blocks)
                for cell_id, cell_data in cells.items():
                    cell_variant = cell_data.get('variant')
                    
                    if cell_variant == 'visualization':
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
                        config_file = assets_dir / f'chart-{chart_count}.json'
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
                    
                    elif cell_variant in ['text', 'markdown', 'text-markdown']:
                        # Process text/markdown cells
                        text_content = contents.get(cell_id, {})
                        
                        if text_content:
                            text_block = self._extract_text_block_content(cell_id, text_content, cell_data)
                            if text_block:
                                text_blocks.append(text_block)
                                self.log(f"Processed text block: {text_block.get('title', cell_id)}")
                
        except Exception as e:
            self.log(f"Error processing dashboard content: {e}")
        
        return visualizations, text_blocks
    
    def _extract_text_block_content(self, cell_id: str, text_content: Dict[str, Any], cell_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract content from text/markdown cells"""
        try:
            # Extract text content - it may be in different fields depending on cell type
            # Try different possible fields for content: html, text, content, description
            content = (text_content.get('html') or 
                      text_content.get('text') or 
                      text_content.get('content') or 
                      text_content.get('description') or 
                      '')
            
            title = text_content.get('title', cell_data.get('title', ''))
            
            if not content and not title:
                return None
            
            # Convert HTML to markdown for cleaner output
            markdown_content = self._html_to_markdown(content) if content else ''
            
            text_block = {
                'cell_id': cell_id,
                'variant': cell_data.get('variant', 'text'),
                'title': title,
                'content': markdown_content,
                'order': cell_data.get('order', 0)
            }
            
            return text_block
            
        except Exception as e:
            self.log(f"Error extracting text block content for {cell_id}: {e}")
            return None
    
    def _html_to_markdown(self, html_content: str) -> str:
        """Convert HTML content to clean markdown format"""
        if not html_content:
            return ''
        
        try:
            import re
            
            # Start with the original content
            markdown = html_content
            
            # Convert common HTML tags to markdown
            # Strong/Bold tags
            markdown = re.sub(r'<strong>(.*?)</strong>', r'**\1**', markdown, flags=re.DOTALL)
            markdown = re.sub(r'<b>(.*?)</b>', r'**\1**', markdown, flags=re.DOTALL)
            
            # Emphasis/Italic tags
            markdown = re.sub(r'<em>(.*?)</em>', r'*\1*', markdown, flags=re.DOTALL)
            markdown = re.sub(r'<i>(.*?)</i>', r'*\1*', markdown, flags=re.DOTALL)
            
            # Line breaks
            markdown = re.sub(r'<br\s*/?>', '\n', markdown)
            
            # Lists - convert <ul> and <li> to markdown format
            # First, handle nested list items
            markdown = re.sub(r'<li[^>]*><p>(.*?)</p></li>', r'- \1', markdown, flags=re.DOTALL)
            markdown = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1', markdown, flags=re.DOTALL)
            
            # Remove <ul> and <ol> tags with any attributes
            markdown = re.sub(r'<ul[^>]*>', '', markdown)
            markdown = re.sub(r'</ul>', '', markdown)
            markdown = re.sub(r'<ol[^>]*>', '', markdown)  
            markdown = re.sub(r'</ol>', '', markdown)
            
            # Paragraphs - convert to double newlines for proper markdown spacing
            markdown = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', markdown, flags=re.DOTALL)
            
            # Links
            markdown = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r'[\2](\1)', markdown, flags=re.DOTALL)
            
            # Code blocks
            markdown = re.sub(r'<code>(.*?)</code>', r'`\1`', markdown, flags=re.DOTALL)
            markdown = re.sub(r'<pre>(.*?)</pre>', r'```\n\1\n```', markdown, flags=re.DOTALL)
            
            # Headers (if any)
            for i in range(1, 7):
                markdown = re.sub(f'<h{i}[^>]*>(.*?)</h{i}>', f'{"#" * i} \\1\n\n', markdown, flags=re.DOTALL)
            
            # Remove any remaining HTML tags
            markdown = re.sub(r'<[^>]+>', '', markdown)
            
            # Clean up extra whitespace and newlines
            markdown = re.sub(r'\n\s*\n\s*\n', '\n\n', markdown)  # Remove triple+ newlines
            markdown = re.sub(r'^\s+|\s+$', '', markdown)  # Trim whitespace
            
            # Clean up list formatting
            lines = markdown.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.strip()
                if line.startswith('- '):
                    # Ensure proper spacing around list items
                    cleaned_lines.append(line)
                elif line and cleaned_lines and cleaned_lines[-1].startswith('- '):
                    # Add blank line after list
                    cleaned_lines.append('')
                    cleaned_lines.append(line)
                else:
                    cleaned_lines.append(line)
            
            markdown = '\n'.join(cleaned_lines)
            
            # Final cleanup
            markdown = re.sub(r'\n{3,}', '\n\n', markdown)  # Max 2 consecutive newlines
            markdown = markdown.strip()
            
            return markdown
            
        except Exception as e:
            self.log(f"Error converting HTML to markdown: {e}")
            # Fallback: just strip HTML tags
            import re
            return re.sub(r'<[^>]+>', '', html_content).strip()
    
    def _extract_chart_type(self, viz_content: Dict[str, Any], dashboard_data: Dict[str, Any]) -> str:
        """Extract the actual chart type (bar, line, pie, etc.) from visualization data"""
        try:
            # Look for chart type in the visualization definition
            vis_id = viz_content.get('visId')
            if not vis_id:
                return 'unknown'
            
            # Search through the dashboard data for visualization definitions
            # This might be in different locations depending on the dashboard structure
            config_key = 'publishedConfig' if ('publishedConfig' in dashboard_data and dashboard_data['publishedConfig'] is not None) else 'draftConfig'
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
                config_key = 'publishedConfig' if ('publishedConfig' in dashboard_data and dashboard_data['publishedConfig'] is not None) else 'draftConfig'
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
                config_key = 'publishedConfig' if ('publishedConfig' in dashboard_data and dashboard_data['publishedConfig'] is not None) else 'draftConfig'
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
                config_key = 'publishedConfig' if ('publishedConfig' in dashboard_data and dashboard_data['publishedConfig'] is not None) else 'draftConfig'
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
    
    def _generate_markdown(self, metadata: Dict[str, Any], visualizations: List[Dict[str, Any]], text_blocks: List[Dict[str, Any]], output_dir: Path):
        """Generate README.md file with visualizations and text blocks"""
        md_content = []
        
        # Overview section
        md_content.append(f"# {metadata.get('title', 'Dashboard')}\n")
        md_content.append(f"**Title:** {metadata.get('title', 'Unknown')}\n")
        
        # Extract author from URL if not in metadata
        author = metadata.get('author')
        if not author and metadata.get('url'):
            url_parts = metadata['url'].split('/')
            if len(url_parts) >= 5 and 'flipsidecrypto.xyz' in metadata['url']:
                author = url_parts[-2]  # Get username from URL
        
        if author:
            md_content.append(f"**Author:** {author}\n")
        
        md_content.append(f"**URL:** {metadata['url']}\n")
        
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
        
        # Text Blocks section
        if text_blocks:
            md_content.append("\n## Text Blocks\n")
            md_content.append("The following text blocks provide context and explanations for the dashboard:\n\n")
            
            for text_block in text_blocks:
                if text_block.get('title'):
                    md_content.append(f"### {text_block['title']}\n")
                
                if text_block.get('content'):
                    md_content.append(f"{text_block['content']}\n\n")
        
        # Visualizations section
        md_content.append("\n## Visualizations\n")
        
        if not visualizations:
            md_content.append("*No visualizations extracted from dashboard*\n")
        else:
            for viz in visualizations:
                chart_num = viz['id'].split('-')[-1]
                chart_section = []
                chart_section.append(f"\n### Chart {chart_num}: {viz.get('title', 'Untitled')}\n")
                chart_section.append(f"- **Chart Type:** {viz.get('type', 'Visualization')}")
                chart_section.append(f"- **Configuration:** `assets/{viz['id']}.json`")
                
                # Add enhanced metadata based on chart type and configuration
                chart_config = viz.get('chart_config', {})
                inputs_config = chart_config.get('inputs', {}).get('config', {})
                chart_type = viz.get('type', '')
                
                # Add type-specific metadata
                if chart_type == 'big-number':
                    if inputs_config.get('valueKey'):
                        chart_section.append(f"- **Value Key:** {inputs_config['valueKey']} (auto-formatted big number display)")
                    if chart_config.get('inputs', {}).get('config', {}).get('suffix'):
                        chart_section.append(f"- **Description:** {chart_config['inputs']['config']['suffix']}")
                elif chart_type == 'pie':
                    if inputs_config.get('slice'):
                        chart_section.append(f"- **Slice Key:** {inputs_config['slice']['key']} ({inputs_config['slice']['type']})")
                    if inputs_config.get('value'):
                        chart_section.append(f"- **Value Key:** {inputs_config['value']['key']} ({inputs_config['value']['type']})")
                    if chart_config.get('plotOptions', {}).get('pie', {}).get('showInLegend'):
                        chart_section.append(f"- **Legend:** Show in legend enabled")
                elif chart_type in ['bar-stacked', 'bar', 'bar-line']:
                    if inputs_config.get('x'):
                        chart_section.append(f"- **X-Axis:** {inputs_config['x']['key']} ({inputs_config['x']['type']})")
                    if inputs_config.get('y') and isinstance(inputs_config['y'], list) and len(inputs_config['y']) > 0:
                        y_axis = inputs_config['y'][0]
                        chart_section.append(f"- **Y-Axis:** {y_axis['key']} ({y_axis['type']})")
                    if chart_config.get('plotOptions', {}).get('column', {}).get('stacking'):
                        chart_section.append(f"- **Stacking:** Normal column stacking")
                    if chart_type == 'bar-line':
                        chart_section.append(f"- **Chart Style:** Bar-line combination")
                elif chart_type == 'viz-table':
                    # For tables, we could extract column info from the CSV if available
                    chart_section.append(f"- **Display:** Tabular data visualization")
                elif chart_type == 'heatmap':
                    chart_section.append(f"- **Chart Style:** Heatmap visualization")
                
                # Check if SQL and CSV files exist using query ID
                query_id = viz.get('query_id')
                if query_id:
                    sql_file = output_dir / "assets" / f"{query_id}.sql"
                    if sql_file.exists():
                        chart_section.append(f"- **SQL Query:** `assets/{query_id}.sql`")
                    else:
                        chart_section.append(f"- **SQL Query:** Not publicly accessible")
                    
                    csv_file = output_dir / "assets" / f"{query_id}.csv"
                    if csv_file.exists():
                        chart_section.append(f"- **Resultset:** `assets/{query_id}.csv`")
                    else:
                        chart_section.append(f"- **Resultset:** Not available for download")
                    
                    chart_section.append(f"- **Query ID:** `{query_id}`")
                    
                    # Add execution timestamps if available
                    query_metadata = viz.get('query_metadata', {})
                    if query_metadata.get('last_successful_execution'):
                        chart_section.append(f"- **Last Executed:** {query_metadata['last_successful_execution']}")
                    if query_metadata.get('result_last_accessed'):
                        chart_section.append(f"- **Result Last Accessed:** {query_metadata['result_last_accessed']}")
                else:
                    chart_section.append(f"- **SQL Query:** No query ID available")
                    chart_section.append(f"- **Resultset:** No query ID available")
                
                # Join chart section with proper line breaks
                md_content.append('\n'.join(chart_section))
        
        # Write markdown file with descriptive name
        title = metadata.get('title', 'Dashboard')
        # Clean title for filename - remove special characters
        clean_title = re.sub(r'[^\w\s-]', '', title).strip()
        clean_title = re.sub(r'[-\s]+', '-', clean_title)
        md_file = output_dir / f"{clean_title}-description.md"
        
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_content))
        
        self.log(f"Generated {md_file.name}")
    
    def _generate_json_artifact(self, metadata: Dict[str, Any], visualizations: List[Dict[str, Any]], text_blocks: List[Dict[str, Any]], output_dir: Path):
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
                "unique_queries": len(set(viz.get('query_id') for viz in visualizations if viz.get('query_id'))),
                "total_text_blocks": len(text_blocks)
            },
            "queries": {},
            "visualizations": [],
            "text_blocks": text_blocks
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
    
    def _find_compass_id_for_query(self, query_id: str, dashboard_data: Dict[str, Any]) -> Optional[str]:
        """Find compass ID for a given query ID from dashboard data"""
        try:
            config_key = 'publishedConfig' if ('publishedConfig' in dashboard_data and dashboard_data['publishedConfig'] is not None) else 'draftConfig'
            if config_key not in dashboard_data:
                return None
                
            config = dashboard_data[config_key]
            cells = config.get('layout', {}).get('body', {}).get('rows', [])
            
            for row in cells:
                for cell in row.get('cells', []):
                    if cell.get('variant') == 'visualization' and cell.get('queryId') == query_id:
                        return cell.get('compassId')
            
            return None
        except Exception as e:
            self.log(f"Error finding compass ID for query {query_id}: {e}")
            return None
    
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
