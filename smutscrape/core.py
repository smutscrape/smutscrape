#!/usr/bin/env python3
"""
Core Processing Module for Smutscrape

This module contains the core processing functions for URL handling, 
video processing, and scraping operations.
"""

import os
import re
import time
import random
import tempfile
import urllib.parse
import feedparser
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from loguru import logger
from termcolor import colored

# Selenium imports with availability check
SELENIUM_AVAILABLE = True
try:
    from selenium.webdriver.common.by import By
except ImportError:
    SELENIUM_AVAILABLE = False

# Import functions from other modules
from smutscrape.utilities import (
    get_terminal_width, is_url, handle_vpn, pattern_to_regex,
    should_ignore_video, construct_filename
)
from smutscrape.metadata import finalize_metadata, generate_nfo
from smutscrape.session import is_url_processed
from smutscrape.sites import SiteConfiguration


def get_config_manager():
    """Get or create the configuration manager instance via CLI module."""
    from smutscrape.cli import get_config_manager as _get_config_manager
    return _get_config_manager()


def get_session_manager():
    """Get or create the session manager instance via CLI module."""
    from smutscrape.cli import get_session_manager as _get_session_manager
    return _get_session_manager()


def get_storage_manager():
    """Get storage manager instance."""
    from smutscrape.storage import get_storage_manager as _get_storage_manager
    return _get_storage_manager()


def get_selenium_driver(general_config, force_new=False):
    """Get selenium driver via config manager."""
    return get_config_manager().get_selenium_driver(force_new=force_new)


# Helper functions for the core processing functions

def pierce_iframe(driver, url, site_config):
    """
    Attempts to pierce into an iframe if specified in site_config.
    Returns the final URL loaded (iframe src or original URL).
    """
    iframe_config = site_config.get('iframe', {})
    if not iframe_config.get('enabled', False):
        driver.get(url)
        return url
    
    logger.debug(f"Attempting iframe piercing for: {url}")
    driver.get(url)
    time.sleep(random.uniform(1, 2))  # Initial page load
    
    try:
        iframe_selector = iframe_config.get('selector', 'iframe')
        iframe = driver.find_element(By.CSS_SELECTOR, iframe_selector)
        iframe_url = iframe.get_attribute("src")
        if iframe_url:
            logger.info(f"Found iframe with src: {iframe_url}")
            driver.get(iframe_url)
            time.sleep(random.uniform(1, 2)) 
            return iframe_url
        else:
            logger.warning("Iframe found but no src attribute.")
            return url
    except Exception as e:
        logger.warning(f"No iframe found or error piercing: {e}")
        return url


def fetch_page(url, user_agents, headers, use_selenium=False, driver=None, retry_count=0):
    if not use_selenium:
        import cloudscraper
        import requests
        scraper = cloudscraper.create_scraper()
        if 'User-Agent' not in headers:
            headers['User-Agent'] = random.choice(user_agents)
        logger.debug(f"Fetching URL (requests): {url}")
        time.sleep(random.uniform(1, 3))
        try:
            response = scraper.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    else:
        if driver is None:
            logger.warning("Selenium requested, but no driver provided.")
            return None
        logger.debug(f"Fetching URL (selenium): {url}")
        try:
            site_config = globals().get('site_config', {})
            if site_config.get('iframe', {}).get('enabled'):
                final_url = pierce_iframe(driver, url, site_config)
            else:
                driver.get(url)
                final_url = url
            logger.debug(f"Final URL after iframe handling: {final_url}")
            time.sleep(random.uniform(2, 4))
            return BeautifulSoup(driver.page_source, 'html.parser')
        except Exception as e:
            if retry_count < 2:
                logger.warning(f"Selenium error: {e}. Retrying with new session...")
                new_driver = get_selenium_driver({'general_config': True}, force_new=True)
                if new_driver:
                    return fetch_page(url, user_agents, headers, use_selenium, new_driver, retry_count + 1)
            logger.error(f"Failed to fetch {url} with Selenium: {e}")
            return None


def extract_data(soup, selectors, driver=None, site_config=None):
    data = {}
    if soup is None:
        logger.error("Soup is None; cannot extract data")
        return data
    
    for field, config in selectors.items():
        if field == 'download_url' and site_config.get('m3u8_mode', False):
            continue
        if isinstance(config, str):
            elements = soup.select(config)
        elif isinstance(config, dict):
            if 'iframe' in config and driver and site_config:
                iframe_selector = config['iframe']
                logger.debug(f"Piercing iframe '{iframe_selector}' for field '{field}'")
                try:
                    iframe = driver.find_element(By.CSS_SELECTOR, iframe_selector)
                    driver.switch_to.frame(iframe)
                    iframe_soup = BeautifulSoup(driver.page_source, 'html.parser')
                    elements = iframe_soup.select(config.get('selector', ''))
                    driver.switch_to.default_content()
                except Exception as e:
                    logger.error(f"Failed to pierce iframe '{iframe_selector}' for '{field}': {e}")
                    elements = []
            elif 'selector' in config:
                selector = config['selector']
                if isinstance(selector, list):
                    elements = []
                    for sel in selector:
                        elements.extend(soup.select(sel))
                        if elements:
                            break
                else:
                    # Handle namespace in selector (e.g., "content|encoded")
                    if '|' in selector:
                        namespace, tag = selector.split('|', 1)
                        elements = soup.find_all(f"{namespace}:{tag}")
                    else:
                        elements = soup.select(selector)
            elif 'attribute' in config:
                elements = [soup]
            else:
                elements = []
        else:
            elements = []
        
        if not elements:
            data[field] = ''
            logger.debug(f"No elements found for '{field}'")
            continue
        
        if isinstance(config, dict) and 'attribute' in config:
            # Handle attribute-based extraction (e.g., href, src)
            values = [element.get(config['attribute']) for element in elements if element.get(config['attribute'])]
            value = values[0] if len(values) == 1 else values if values else ''
            if value is None:
                logger.debug(f"Attribute '{config['attribute']}' for '{field}' is None; defaulting to empty string")
                value = ''
        else:
            # Handle text-based extraction
            value = elements[0].text.strip() if hasattr(elements[0], 'text') and elements[0].text else ''
            if value is None:
                value = ''
        
        # Handle multi-value fields with deduplication only for text-based fields
        if field in ['tags', 'actors', 'producers', 'studios'] and not (isinstance(config, dict) and 'attribute' in config):
            values = [element.text.strip() for element in elements if hasattr(element, 'text') and element.text and element.text.strip()]
            normalized_values = {v.lower() for v in values if v}
            value = [v for v in values if v.lower() in normalized_values]
            seen = set()
            value = [v for v in value if not (v.lower() in seen or seen.add(v.lower()))]
        
        # Apply post-processing if present
        if isinstance(config, dict) and 'postProcess' in config:
            for step in config['postProcess']:
                if 'replace' in step:
                    for pair in step['replace']:
                        regex, replacement = pair['regex'], pair['with']
                        try:
                            if isinstance(value, list):
                                value = [re.sub(regex, replacement, v, flags=re.DOTALL) if v else '' for v in value]
                            else:
                                old_value = value
                                value = re.sub(regex, replacement, value, flags=re.DOTALL) if value else ''
                                if value != old_value:
                                    logger.debug(f"Applied regex '{regex}' -> '{replacement}' for '{field}': {value}")
                        except re.error as e:
                            logger.error(f"Regex error for '{field}': regex={regex}, error={e}")
                            value = ''
                elif 'max_attribute' in step:
                    if not isinstance(value, list):
                        logger.debug(f"Skipping max_attribute for '{field}' as value is not a list: {value}")
                        continue
                    attr_name = step.get('attribute')
                    attr_type = step.get('type', 'str')
                    if not attr_name:
                        logger.error(f"max_attribute for '{field}' missing 'attribute' key")
                        continue
                    try:
                        attr_values = [(val, elements[i].get(attr_name)) for i, val in enumerate(value) if elements[i].get(attr_name) is not None]
                        if not attr_values:
                            logger.debug(f"No valid '{attr_name}' attributes found for '{field}'; using first value")
                            value = value[0] if value else ''
                        else:
                            if attr_type == 'int':
                                converted_attrs = [(val, int(attr)) for val, attr in attr_values]
                            elif attr_type == 'float':
                                converted_attrs = [(val, float(attr)) for val, attr in attr_values]
                            else:
                                converted_attrs = [(val, str(attr)) for val, attr in attr_values]
                            value = max(converted_attrs, key=lambda x: x[1])[0]
                            logger.debug(f"Applied max_attribute '{attr_name}' (type: {attr_type}) for '{field}': selected {value}")
                    except (ValueError, TypeError) as e:
                        logger.error(f"Failed to convert '{attr_name}' to {attr_type} for '{field}': {e}")
                        value = value[0] if value else ''
                elif 'first' in step and step['first'] and isinstance(value, list):
                    value = value[0] if value else ''
        
        # Default to first value for lists without postProcess, except multi-value fields
        if isinstance(config, dict) and 'postProcess' not in config and isinstance(value, list) and field not in ['tags', 'actors', 'studios']:
            value = value[0] if value else ''
            logger.debug(f"No postProcess for '{field}' with multiple values; defaulted to first: {value}")
        
        data[field] = value if value or isinstance(value, list) else ''
        # logger.debug(f"Final value for '{field}': {data[field]}")
    
    return data


# Core processing functions

def construct_url(base_url, pattern, site_config, mode=None, **kwargs):
    mode_specific_rules = {}
    if mode and mode in site_config.get('modes', {}) and 'url_encoding_rules' in site_config['modes'][mode]:
        mode_specific_rules = site_config['modes'][mode]['url_encoding_rules']
        logger.debug(f"Loaded mode-specific URL encoding rules for mode '{mode}': {mode_specific_rules}")

    site_specific_rules = site_config.get('url_encoding_rules', {})
    if site_specific_rules:
        logger.debug(f"Loaded site-specific URL encoding rules: {site_specific_rules}")

    encoded_kwargs = {}
    logger.debug(f"Constructing URL with pattern '{pattern}' and mode '{mode}'. Applying encoding rules if any.")
    
    # Handle arithmetic expressions like {page - 1}, {page + 2}, etc.
    page_pattern = r'\{page\s*([+-])\s*(\d+)\}'  # Matches {page - 1}, {page + 2}, etc.
    match = re.search(page_pattern, pattern)
    if match and 'page' in kwargs:
        operator, value = match.group(1), int(match.group(2))
        page_value = kwargs.get('page')
        if page_value is not None:
            try:
                page_num = int(page_value)
                if operator == '+':
                    adjusted_page = page_num + value
                elif operator == '-':
                    adjusted_page = page_num - value
                # Replace the full expression (e.g., "{page - 1}") with the computed value
                pattern = pattern.replace(match.group(0), str(adjusted_page))
                logger.debug(f"Adjusted page {page_value} {operator} {value} = {adjusted_page}")
            except (ValueError, TypeError):
                logger.error(f"Invalid page value '{page_value}' for arithmetic adjustment")
                pattern = pattern.replace(match.group(0), str(page_value))  # Fallback to original
        else:
            pattern = pattern.replace(match.group(0), '')  # Remove if page is None
    elif 'page' in kwargs:
        # Ensure 'page' kwarg is preserved if not used in arithmetic, will be handled by the loop below
        pass # No special action needed here, will be processed by the main loop
    
    # Encode remaining kwargs with rules
    for k, v in kwargs.items():
        if k == 'page' and match:  # Skip page if already handled by arithmetic adjustment of the pattern
            continue
        
        if isinstance(v, str):
            encoded_v = v
            # Apply mode-specific rules first
            if mode_specific_rules:
                for original, replacement in mode_specific_rules.items():
                    if original in encoded_v:
                        logger.debug(f"Applying mode rule for key '{k}': '{original}' -> '{replacement}' to value '{encoded_v}'")
                        encoded_v = encoded_v.replace(original, replacement)
                        logger.debug(f"Value after mode rule for key '{k}': '{encoded_v}'")
            
            # Then apply site-specific rules to the (potentially already modified) string
            if site_specific_rules:
                for original, replacement in site_specific_rules.items():
                    if original in encoded_v:
                        logger.debug(f"Applying site rule for key '{k}': '{original}' -> '{replacement}' to value '{encoded_v}'")
                        encoded_v = encoded_v.replace(original, replacement)
                        logger.debug(f"Value after site rule for key '{k}': '{encoded_v}'")
            
            encoded_kwargs[k] = encoded_v
        elif k == 'page' and v is None and not match : # handle case where page is None and not part of an arithmetic expression
            encoded_kwargs[k] = None # Preserve None page if not handled by arithmetic
        else:
            encoded_kwargs[k] = v # Preserve non-string or already handled page values
    
    # Format the pattern with encoded kwargs, handling missing keys gracefully
    try:
        # Filter out None page values before formatting if they are not explicitly in the pattern
        # or if the pattern expects a page but it's None (e.g. for first page where page is not in URL)
        final_format_kwargs = {key: val for key, val in encoded_kwargs.items() if val is not None or f"{{{key}}}" in pattern}
        path = pattern.format(**final_format_kwargs)
    except KeyError as e:
        logger.error(f"Missing key in URL pattern '{pattern}': {e}. Available kwargs: {final_format_kwargs.keys()}")
        return None
    
    full_url = urllib.parse.urljoin(base_url, path)
    return full_url


def match_url_to_mode(url, site_config):
    parsed_url = urlparse(url)
    netloc = parsed_url.netloc.lower().replace("www.", "", 1)
    full_path = parsed_url.path.rstrip("/").lower() + ("?" + parsed_url.query.lower() if parsed_url.query else "")
    
    base_netloc = urlparse(site_config["base_url"]).netloc.lower().replace("www.", "", 1)
    if netloc != base_netloc:
        # logger.debug(f"No match: netloc '{netloc}' != base_netloc '{base_netloc}'")
        return None, None
    
    modes = site_config.get("modes", {})
    non_video_modes = {k: v for k, v in modes.items() if k != "video"}
    video_mode = modes.get("video")
    
    best_match = None
    best_static_count = -1
    best_static_length = -1
    
    for mode, config in non_video_modes.items():
        # logger.debug(f"Checking mode: '{mode}'")
        for pattern_key in ["url_pattern", "url_pattern_pages"]:
            if pattern_key not in config:
                continue
            pattern = config[pattern_key]
            regex, static_count, static_length = pattern_to_regex(pattern)
            # logger.debug(f"Testing pattern '{pattern}' -> regex '{regex.pattern}'")
            match = regex.match(full_path)
            if match:
                extracted = match.groupdict()
                # logger.debug(f"Match found: extracted={extracted}")
                if (static_count > best_static_count) or (static_count == best_static_count and static_length > best_static_length):
                    best_match = (mode, config["scraper"])
                    best_static_count = static_count
                    best_static_length = static_length
                # logger.debug(f"Matched URL '{url}' to mode '{mode}' with {pattern_key} (static_count={static_count}, static_length={static_length})")
            #else:
                # logger.debug(f"No match for '{pattern}'")
    
    if best_match:
        logger.debug(f"Best match selected: {best_match} (static_count={best_static_count}, static_length={best_static_length})")
        return best_match
    
    if video_mode and "url_pattern" in video_mode:
        pattern = video_mode["url_pattern"]
        regex, static_count, static_length = pattern_to_regex(pattern)
        logger.debug(f"Testing video pattern '{pattern}' -> regex '{regex.pattern}'")
        match = regex.match(full_path)
        if match:
            extracted = match.groupdict()
            logger.debug(f"Matched URL '{url}' to mode 'video' with pattern '{pattern}' (static_count={static_count}, static_length={static_length})")
            return "video", video_mode["scraper"]
        else:
            logger.debug(f"No match for video mode with pattern '{pattern}'")
    
    logger.debug(f"No mode matched for URL: '{url}'")
    return None, None


def process_url(url, site_config, general_config, overwrite, re_nfo, start_page, apply_state=False, state_set=None):
    headers = general_config.get("headers", {}).copy()
    headers["User-Agent"] = random.choice(general_config["user_agents"])
    mode, scraper = match_url_to_mode(url, site_config)
    
    # Split start_page into page_num and video_offset
    page_parts = start_page.split('.')
    page_num = int(page_parts[0])
    video_offset = int(page_parts[1]) if len(page_parts) > 1 else 0
    
    # Check if the input is a full URL using is_url
    is_full_url = is_url(url)
    
    if mode:
        logger.info(f"Matched URL to mode '{mode}' with scraper '{scraper}'")
        if mode == "video":
            success = process_video_page(
                url, site_config, general_config, overwrite, headers, re_nfo,
                apply_state=apply_state, state_set=state_set
            )
        elif mode == "rss":
            success = process_rss_feed(
                url, site_config, general_config, overwrite, headers, re_nfo,
                apply_state=apply_state, state_set=state_set
            )
        else:
            # Extract identifier only if not a full URL
            identifier = url.split("/")[-1].split(".")[0] if not is_full_url else None
            current_page_num = page_num
            current_video_offset = video_offset
            mode_config = site_config["modes"][mode]
            
            # Use the original URL if provided, otherwise construct it
            if is_full_url:
                effective_url = url
                logger.info(f"Using provided URL: {effective_url}")
            else:
                if page_num > 1 and mode_config.get("url_pattern_pages"):
                    effective_url = construct_url(
                        site_config["base_url"],
                        mode_config["url_pattern_pages"],
                        site_config,
                        mode=mode,
                        **{mode: identifier, "page": page_num}
                    )
                    logger.info(f"Starting at custom page {page_num}.{video_offset}: {effective_url}")
                else:
                    effective_url = construct_url(
                        site_config["base_url"],
                        mode_config["url_pattern"],
                        site_config,
                        mode=mode,
                        **{mode: identifier}
                    )
                    logger.info(f"Constructed URL: {effective_url}")
            
            success = False
            while effective_url:
                next_page, new_page_number, page_success = process_list_page(
                    effective_url, site_config, general_config, current_page_num, current_video_offset,
                    mode, identifier, overwrite, headers, re_nfo, apply_state=apply_state, state_set=state_set
                )
                success = success or page_success
                effective_url = next_page
                current_page_num = new_page_number
                current_video_offset = 0  # Reset after first page
                time.sleep(general_config["sleep"]["between_pages"])
    else:
        logger.warning("URL didn't match any specific mode; attempting all configured modes.")
        available_modes = site_config.get("modes", {})
        success = False
        for mode_name in available_modes:
            if mode_name == "video":
                logger.info("Trying 'video' mode...")
                success = process_video_page(
                    url, site_config, general_config, overwrite, headers, re_nfo,
                    apply_state=apply_state, state_set=state_set
                )
                if success:
                    logger.info("Video mode succeeded.")
                    break
            elif mode_name == "rss":
                logger.info("Trying 'rss' mode...")
                success = process_rss_feed(
                    url, site_config, general_config, overwrite, headers, re_nfo,
                    apply_state=apply_state, state_set=state_set
                )
                if success:
                    logger.info("RSS mode succeeded.")
                    break
            else:
                logger.info(f"Attempting mode '{mode_name}'...")
                identifier = url.split("/")[-1].split(".")[0] if not is_full_url else None
                current_page_num = page_num
                current_video_offset = video_offset
                mode_config = site_config["modes"][mode_name]
                
                # Use the original URL if provided, otherwise construct it
                if is_full_url:
                    constructed_url = url
                    logger.info(f"Using provided URL for mode '{mode_name}': {constructed_url}")
                else:
                    try:
                        constructed_url = construct_url(
                            site_config["base_url"],
                            mode_config["url_pattern"] if current_page_num == 1 else mode_config.get("url_pattern_pages", mode_config["url_pattern"]),
                            site_config,
                            mode=mode_name,
                            **{mode_name: identifier, "page": current_page_num if current_page_num > 1 else None}
                        )
                        logger.info(f"Starting at custom page {current_page_num}.{current_video_offset}: {constructed_url}")
                    except Exception as e:
                        logger.warning(f"Mode '{mode_name}' failed to construct URL: {e}")
                        continue
                
                success = False
                while constructed_url:
                    next_page, new_page_number, page_success = process_list_page(
                        constructed_url, site_config, general_config, current_page_num, current_video_offset,
                        mode_name, identifier, overwrite, headers, re_nfo, apply_state=apply_state, state_set=state_set
                    )
                    success = success or page_success
                    constructed_url = next_page
                    current_page_num = new_page_number
                    current_video_offset = 0  # Reset after first page
                    time.sleep(general_config["sleep"]["between_pages"])
                if success:
                    logger.info(f"Mode '{mode_name}' succeeded.")
                    break
        
        if not success:
            logger.error(f"Failed to process URL '{url}' with any mode.")
            get_config_manager().download_manager.process_fallback_download(url, overwrite)
    
    return success


def process_list_page(url, site_config, general_config, page_num=1, video_offset=0, mode=None, identifier=None, overwrite=False, headers=None, new_nfo=False, do_not_ignore=False, apply_state=False, state_set=None):
    use_selenium = site_config.get('use_selenium', False)
    driver = get_selenium_driver(general_config) if use_selenium else None
    soup = fetch_page(url, general_config['user_agents'], headers if headers else {}, use_selenium, driver)
    if soup is None:
        logger.error(f"Failed to fetch page: {url}")
        return None, None, False
    
    list_scraper = site_config['scrapers']['list_scraper']
    base_url = site_config['base_url']
    container_selector = list_scraper['video_container']['selector']
    
    container = None
    if isinstance(container_selector, list):
        for selector in container_selector:
            container = soup.select_one(selector)
            if container:
                logger.debug(f"Found container with selector '{selector}': {container.name}[class={container.get('class', [])}]")
                break
        if not container:
            logger.error(f"Could not find video container at {url} with any selector in {container_selector}")
            return None, None, False
    else:
        logger.debug(f"Searching for container with selector: '{container_selector}'")
        container = soup.select_one(container_selector)
        if not container:
            logger.error(f"Could not find video container at {url} with selector '{container_selector}'")
            return None, None, False
        logger.debug(f"Found container: {container.name}[class={container.get('class', [])}]")
    
    item_selector = list_scraper['video_item']['selector']
    logger.debug(f"Searching for video items with selector: '{item_selector}'")
    video_elements = container.select(item_selector)
    logger.debug(f"Found {len(video_elements)} video items")
    if not video_elements:
        logger.debug(f"No videos found on page {page_num} with selector '{item_selector}'")
        return None, None, False
    
    term_width = get_terminal_width()
    print()
    print()
    page_info = f" page {page_num}, {site_config['name'].lower()} {mode}: \"{identifier}\" "
    page_line = page_info.center(term_width, "═")
    print(colored(page_line, "yellow"))
    
    success = False
    for i, video_element in enumerate(video_elements, 1):
        if video_offset > 0 and i < video_offset:  # Start at video_offset, 1-based
            continue
        
        video_data = extract_data(video_element, list_scraper['video_item']['fields'], driver, site_config)
        if 'url' in video_data:
            video_url = video_data['url']
            if not video_url.startswith(('http://', 'https://')):
                video_url = f"http:{video_url}" if video_url.startswith('//') else urllib.parse.urljoin(base_url, video_url)
        elif 'video_key' in video_data:
            video_url = construct_url(base_url, site_config['modes']['video']['url_pattern'], site_config, mode='video', video=video_data['video_key'])
        else:
            logger.warning("Unable to construct video URL")
            continue
        video_title = video_data.get('title', '').strip() or video_element.text.strip()
        
        print()
        counter = f"{i} of {len(video_elements)}"
        counter_line = f"┈┈┈ {counter} ┈ {video_url} ".ljust(term_width, "┈")
        print(colored(counter_line, "magenta"))
        
        if is_url_processed(video_url, state_set) and not (overwrite or new_nfo):
            logger.info(f"Skipping already processed video: {video_url}")
            success = True
            continue
        
        video_success = process_video_page(video_url, site_config, general_config, overwrite, headers, new_nfo, do_not_ignore, apply_state=apply_state, state_set=state_set)
        if video_success:
            success = True
    
    if driver:
        driver.quit()
    
    if mode not in site_config['modes']:
        logger.warning(f"No pagination for mode '{mode}' as it's not defined in site_config['modes']")
        return None, None, success
    
    mode_config = site_config['modes'][mode]
    scraper_pagination = list_scraper.get('pagination', {})
    url_pattern_pages = mode_config.get('url_pattern_pages')
    max_pages = mode_config.get('max_pages', scraper_pagination.get('max_pages', float('inf')))
    
    if page_num >= max_pages:
        logger.warning(f"Stopping pagination: page_num={page_num} >= max_pages={max_pages}")
        return None, None, success
    
    next_url = None
    if url_pattern_pages:
        next_url = construct_url(
            base_url,
            url_pattern_pages,
            site_config,
            mode=mode,
            **{mode: identifier, 'page': page_num + 1}
        )
        logger.info(f"Generated next page URL (pattern-based): {next_url}")
        
    elif scraper_pagination:
        if 'next_page' in scraper_pagination:
            next_page_config = scraper_pagination['next_page']
            next_page = soup.select_one(next_page_config.get('selector', ''))
            if next_page:
                next_url = next_page.get(next_page_config.get('attribute', 'href'))
                if next_url and not next_url.startswith(('http://', 'https://')):
                    next_url = urllib.parse.urljoin(base_url, next_url)
                logger.info(f"Found next page URL (selector-based): {next_url}")
            else:
                logger.warning(f"No 'next' element found with selector '{next_page_config.get('selector')}'")
    
    if next_url:
        return next_url, page_num + 1, success
    logger.warning("No next page URL generated; stopping pagination")
    return None, None, success


def process_rss_feed(url, site_config, general_config, overwrite=False, headers=None, re_nfo=False, apply_state=False, state_set=None):
    """Process an RSS feed, downloading videos from oldest to newest."""
    logger.info(f"Fetching RSS feed: {url}")
    
    # Fetch the RSS feed
    feed = feedparser.parse(url)
    if feed.bozo:
        logger.error(f"Failed to parse RSS feed at {url}: {feed.bozo_exception}")
        return False
    
    entries = feed.entries
    if not entries:
        logger.warning(f"No entries found in RSS feed at {url}")
        return False
    
    # Reverse entries to process from oldest to newest
    entries = list(reversed(entries))
    logger.info(f"Found {len(entries)} entries in RSS feed; processing from oldest to newest")
    
    term_width = get_terminal_width()
    print()
    print()
    feed_info = f" RSS feed for {site_config['name']} "
    feed_line = feed_info.center(term_width, "═")
    print(colored(feed_line, "yellow"))
    
    success = False
    rss_scraper = site_config['scrapers']['rss_scraper']
    
    for i, entry in enumerate(entries, 1):
        # Extract video URL from the <link> element
        video_url = entry.get('link', '')
        if not video_url or not is_url(video_url):
            logger.warning(f"Entry {i} has no valid URL; skipping")
            continue
        
        # Convert feedparser entry to XML string for BeautifulSoup
        entry_xml = '<item>'
        entry_xml += f'<title><![CDATA[{entry.get("title", "")}]]></title>'
        entry_xml += f'<link><![CDATA[{entry.get("link", "")}]]></link>'
        entry_xml += f'<description><![CDATA[{entry.get("description", "")}]]></description>'
        if 'content' in entry and entry.content:
            entry_xml += f'<content:encoded><![CDATA[{entry.content[0].value}]]></content:encoded>'
        for category in entry.get('categories', []):
            entry_xml += f'<category><![CDATA[{category[0]}]]></category>'
        entry_xml += '</item>'
        
        # Parse the entry with BeautifulSoup using lxml parser
        entry_soup = BeautifulSoup(entry_xml, 'lxml-xml')  # Use lxml-xml for proper XML parsing
        
        # Extract data using the scraper configuration
        video_data = extract_data(entry_soup, rss_scraper['video_item']['fields'], None, site_config)
        
        # Fallback to RSS fields if not found in content
        video_title = video_data.get('title', '').strip() or entry.get('title', 'Untitled').strip()
        video_data['title'] = video_title
        video_data['url'] = video_url
        
        print()
        counter = f"{i} of {len(entries)}"
        counter_line = f"┈┈┈ {counter} ┈ {video_url} ".ljust(term_width, "┈")
        print(colored(counter_line, "magenta"))
        
        if is_url_processed(video_url, state_set) and not (overwrite or re_nfo):
            logger.info(f"Skipping already processed video: {video_url}")
            success = True
            continue
        
        # Process the video page
        video_success = process_video_page(
            video_url, site_config, general_config, overwrite, headers, re_nfo,
            apply_state=apply_state, state_set=state_set
        )
        if video_success:
            success = True
    
    return success


def has_metadata_selectors(site_config, return_fields=False):
    """
    Check if the site config has selectors for metadata fields beyond title, download_url, and image.
    If return_fields=True, return the list of fields instead of a boolean.
    """
    # If it's a SiteConfiguration object, use its methods
    if isinstance(site_config, SiteConfiguration):
        if return_fields:
            return site_config.get_metadata_fields()
        return site_config.has_metadata_selectors()
    
    # Backward compatibility for dict configs
    video_scraper = site_config.get('scrapers', {}).get('video_scraper', {})
    excluded = {'title', 'download_url', 'image'}
    metadata_fields = [field for field in video_scraper.keys() if field not in excluded]
    
    if return_fields:
        return sorted(metadata_fields) if metadata_fields else []
    return bool(metadata_fields)


def download_video(video_url, destination_path, site_config, general_config, headers=None, metadata=None, overwrite=False):
    """Download a video file to a temporary or final path."""
    download_method = site_config.get('download', {}).get('method', 'curl')
    origin = urllib.parse.urlparse(video_url).scheme + "://" + urllib.parse.urlparse(video_url).netloc
    
    if os.path.exists(destination_path) and not overwrite:
        video_info = get_config_manager().download_manager.get_video_metadata(destination_path)
        if video_info:
            logger.info(f"Valid video exists at {destination_path}. Skipping download.")
            return True
        else:
            logger.warning(f"Invalid video file at {destination_path}. Redownloading.")
            os.remove(destination_path)
    
    logger.info(f"Downloading to {destination_path}")
    success = get_config_manager().download_manager.download_file(
        video_url, destination_path, download_method, site_config,
        headers=headers, metadata=metadata, origin=origin, overwrite=overwrite
    )
    if success:
        logger.success(f"Downloaded video to {destination_path}")
    else:
        logger.error(f"Failed to download video to {destination_path}")
    return success


def process_video_page(url, site_config, general_config, overwrite=False, headers=None, new_nfo=False, do_not_ignore=False, apply_state=False, state_set=None):
    # VPN handling via session manager
    session_mgr = get_session_manager()
    vpn_config = general_config.get('vpn', {})
    if vpn_config.get('enabled', False):
        if session_mgr.should_refresh_vpn(vpn_config.get('new_node_time', 300)):
            new_time = handle_vpn(general_config, 'new_node')
            session_mgr.update_vpn_time(new_time)
    
    logger.info(f"Processing video page: {url}")
    use_selenium = site_config.get('use_selenium', False)
    driver = get_selenium_driver(general_config) if use_selenium else None
    original_url = url
    
    iframe_url = None
    video_url = None
    raw_data = {'title': original_url.split('/')[-2]}
    
    if site_config.get('m3u8_mode', False) and driver:
        video_scraper = site_config['scrapers']['video_scraper']
        iframe_config = next(({'enabled': True, 'selector': config['iframe']} for field, config in video_scraper.items() 
                              if isinstance(config, dict) and 'iframe' in config), None)
        if iframe_config:
            logger.debug(f"Piercing iframe '{iframe_config['selector']}' for M3U8")
            driver.get(original_url)
            time.sleep(random.uniform(1, 2))
            try:
                iframe = driver.find_element(By.CSS_SELECTOR, iframe_config['selector'])
                iframe_url = iframe.get_attribute("src")
                if iframe_url:
                    logger.info(f"Found iframe: {iframe_url}")
                    driver.get(iframe_url)
                    time.sleep(random.uniform(1, 2))
                    m3u8_url, cookies = get_config_manager().download_manager.extract_m3u8_urls(driver, iframe_url, site_config)
                    if m3u8_url:
                        video_url = m3u8_url
                        headers = headers or general_config.get('headers', {}).copy()
                        headers.update({"Cookie": cookies, "Referer": iframe_url, 
                                        "User-Agent": get_config_manager().selenium_user_agent or random.choice(general_config['user_agents'])})
            except Exception as e:
                logger.warning(f"Iframe error: {e}")
        soup = fetch_page(original_url, general_config['user_agents'], headers or {}, use_selenium, driver)
        if soup:
            raw_data = extract_data(soup, site_config['scrapers']['video_scraper'], driver, site_config)
        video_url = video_url or raw_data.get('download_url')
    elif site_config.get('mp4_mode', False) and driver: # New MP4 mode
        logger.info("Attempting MP4 mode detection.")
        video_scraper = site_config['scrapers']['video_scraper']
        iframe_config = next(({'enabled': True, 'selector': config['iframe']} for field, config in video_scraper.items()
                              if isinstance(config, dict) and 'iframe' in config), None)
        page_to_scan = original_url
        if iframe_config:
            logger.debug(f"Piercing iframe '{iframe_config['selector']}' for MP4")
            driver.get(original_url)
            time.sleep(random.uniform(1, 2))
            try:
                iframe = driver.find_element(By.CSS_SELECTOR, iframe_config['selector'])
                iframe_src = iframe.get_attribute("src")
                if iframe_src:
                    logger.info(f"Found iframe for MP4 scan: {iframe_src}")
                    page_to_scan = iframe_src # Scan inside iframe
                    # driver.get(iframe_src) # Already done by extract_mp4_urls
                    # time.sleep(random.uniform(1, 2))
            except Exception as e:
                logger.warning(f"Iframe error during MP4 mode: {e}")

        mp4_found_url, cookies = get_config_manager().download_manager.extract_mp4_urls(driver, page_to_scan, site_config)
        if mp4_found_url:
            video_url = mp4_found_url
            site_config['download'] = {'method': 'requests'} # Override to requests for MP4
            logger.info(f"MP4 detected: {video_url}, download method set to 'requests'")
            headers = headers or general_config.get('headers', {}).copy()
            headers.update({"Cookie": cookies, "Referer": page_to_scan,
                            "User-Agent": get_config_manager().selenium_user_agent or random.choice(general_config['user_agents'])})
        soup = fetch_page(original_url, general_config['user_agents'], headers or {}, use_selenium, driver)
        if soup:
            raw_data = extract_data(soup, site_config['scrapers']['video_scraper'], driver, site_config)
        video_url = video_url or raw_data.get('download_url') # Fallback to scraped URL if direct detection fails
    elif site_config.get('detect_mode', False) and driver: # New Detect mode
        logger.info("Attempting Detect mode (MP4 then M3U8).")
        video_scraper = site_config['scrapers']['video_scraper']
        iframe_config = next(({'enabled': True, 'selector': config['iframe']} for field, config in video_scraper.items()
                              if isinstance(config, dict) and 'iframe' in config), None)
        page_to_scan = original_url
        scan_headers = headers or general_config.get('headers', {}).copy()

        if iframe_config:
            logger.debug(f"Piercing iframe '{iframe_config['selector']}' for Detect mode")
            driver.get(original_url)
            time.sleep(random.uniform(1, 2))
            try:
                iframe = driver.find_element(By.CSS_SELECTOR, iframe_config['selector'])
                iframe_src = iframe.get_attribute("src")
                if iframe_src:
                    logger.info(f"Found iframe for Detect scan: {iframe_src}")
                    page_to_scan = iframe_src
                    # driver.get(iframe_src) # Done by extract functions
                    # time.sleep(random.uniform(1, 2))
            except Exception as e:
                logger.warning(f"Iframe error during Detect mode: {e}")
        
        # Try MP4 first
        mp4_found_url, mp4_cookies = get_config_manager().download_manager.extract_mp4_urls(driver, page_to_scan, site_config)
        if mp4_found_url:
            video_url = mp4_found_url
            site_config['download'] = {'method': 'requests'}
            logger.info(f"Detect mode: MP4 found: {video_url}, download method 'requests'")
            scan_headers.update({"Cookie": mp4_cookies, "Referer": page_to_scan,
                                 "User-Agent": get_config_manager().selenium_user_agent or random.choice(general_config['user_agents'])})
        else:
            logger.info("Detect mode: MP4 not found, trying M3U8.")
            # Try M3U8 second
            m3u8_found_url, m3u8_cookies = get_config_manager().download_manager.extract_m3u8_urls(driver, page_to_scan, site_config)
            if m3u8_found_url:
                video_url = m3u8_found_url
                site_config['download'] = {'method': 'ffmpeg'} # Ensure ffmpeg for m3u8
                logger.info(f"Detect mode: M3U8 found: {video_url}, download method 'ffmpeg'")
                scan_headers.update({"Cookie": m3u8_cookies, "Referer": page_to_scan,
                                     "User-Agent": get_config_manager().selenium_user_agent or random.choice(general_config['user_agents'])})
            else:
                logger.warning("Detect mode: Neither MP4 nor M3U8 found via network sniffing.")
        
        headers = scan_headers # Update main headers with cookies if found
        soup = fetch_page(original_url, general_config['user_agents'], headers, use_selenium, driver)
        if soup:
            raw_data = extract_data(soup, site_config['scrapers']['video_scraper'], driver, site_config)
        video_url = video_url or raw_data.get('download_url') # Fallback
    else:
        soup = fetch_page(original_url, general_config['user_agents'], headers or {}, use_selenium, driver)
        if soup is None and use_selenium:
            logger.warning("Selenium failed; retrying with requests")
            soup = fetch_page(original_url, general_config['user_agents'], headers or {}, False, None)
        if soup is None:
            logger.error(f"Failed to fetch: {original_url}")
            if driver:
                driver.quit()
            return False
        raw_data = extract_data(soup, site_config['scrapers']['video_scraper'], driver, site_config)
        video_url = raw_data.get('download_url')
    
    video_url = video_url or original_url
    video_title = raw_data.get('title', '').strip() or 'Untitled'

    remove_title_string = site_config.get('remove_title_string', '')

    if remove_title_string:
        if video_title.endswith(remove_title_string):
            video_title = video_title[:-len(remove_title_string)].rstrip()
            logger.debug(f"Removed string '{remove_title_string}' from title: {video_title}")
        else:
            logger.debug(f"\"{remove_title_string}\" not found in title: {video_title}")
    else:
        logger.debug("Site config has no remove_title_string set")
    
    raw_data['title'] = video_title
    logger.debug(f"Final title: {raw_data['title']}")
    raw_data['url'] = original_url
    
    if not do_not_ignore and should_ignore_video(raw_data, general_config['ignored']):
        if driver:
            driver.quit()
        return True
    
    final_metadata = finalize_metadata(raw_data, general_config)
    file_name = construct_filename(final_metadata['title'], site_config, general_config)
    destination_config = general_config['download_destinations'][0]
    state_updated = False
    
    if destination_config['type'] == 'smb':
        smb_path = os.path.join(destination_config['path'], file_name)
        if not overwrite and get_storage_manager().file_exists_on_smb(destination_config, smb_path):
            logger.info(f"File '{smb_path}' exists on SMB share. Skipping download.")
            if apply_state and not is_url_processed(original_url, state_set):
                state_set.add(original_url)
                get_session_manager().save_state(original_url)
                logger.info(f"Retroactively added {original_url} to state due to existing file and --applystate")
                state_updated = True
            if general_config.get('make_nfo', False) and has_metadata_selectors(site_config):
                smb_nfo_path = os.path.join(destination_config['path'], f"{file_name.rsplit('.', 1)[0]}.nfo")
                if not (new_nfo or get_storage_manager().file_exists_on_smb(destination_config, smb_nfo_path)):
                    temp_nfo_path = os.path.join(tempfile.gettempdir(), 'smutscrape', f"{file_name.rsplit('.', 1)[0]}.nfo")
                    os.makedirs(os.path.dirname(temp_nfo_path), exist_ok=True)
                    generate_nfo(temp_nfo_path, final_metadata, True)
                    get_storage_manager().upload_to_smb(temp_nfo_path, smb_nfo_path, destination_config, overwrite)
                    os.remove(temp_nfo_path)
            if driver:
                driver.quit()
            return True
            
    if destination_config['type'] == 'smb':
        temp_dir = destination_config.get('temporary_storage', os.path.join(tempfile.gettempdir(), 'smutscrape'))
        os.makedirs(temp_dir, exist_ok=True)
        final_destination_path = os.path.join(temp_dir, file_name)
        # logger.debug(f"Final SMB destination path: {final_destination_path}")
        temp_destination_path = os.path.join(temp_dir, f".{file_name}")  # Changed from .part suffix to . prefix
        logger.debug(f"Temporary intermediate path: {temp_destination_path}")
    else:
        final_destination_path = os.path.join(destination_config['path'], file_name)
        temp_destination_path = final_destination_path  # No prefix for local
    
    # Check for existing complete file in temp dir
    if destination_config['type'] == 'smb' and not overwrite and os.path.exists(final_destination_path):
        video_info = get_config_manager().download_manager.get_video_metadata(final_destination_path)
        if video_info:
            logger.info(f"Valid complete file '{final_destination_path}' exists in temp dir. Skipping download.")
            success = True
        else:
            logger.warning(f"Invalid file '{final_destination_path}' in temp dir. Redownloading.")
            os.remove(final_destination_path)
            success = download_video(video_url, final_destination_path, site_config, general_config, headers, final_metadata, overwrite)
    else:
        success = download_video(video_url, final_destination_path, site_config, general_config, headers, final_metadata, overwrite)
        
    if success and general_config.get('make_nfo', False) and has_metadata_selectors(site_config):
        logger.debug(f"Successful video download, now generating nfo.")
        generate_nfo(final_destination_path, final_metadata, overwrite or new_nfo)
        
    if success and destination_config['type'] == 'smb':
        logger.debug(f"Successful video download, now managing file.")
        get_storage_manager().manage_file(final_destination_path, destination_config, overwrite, video_url=original_url, state_set=state_set)

    # After successful download + NFO + file move:
    stash = get_config_manager().stash_client
    if stash and final_metadata:
        _ingest_to_stash(stash, final_destination_path, final_metadata, general_config)
  
    if success and not is_url_processed(original_url, state_set):
        logger.debug(f"Adding {original_url} to state")
        state_set.add(original_url)
        get_session_manager().save_state(original_url)
    
    if driver:
        driver.quit()
    time.sleep(general_config['sleep']['between_videos'])
    return success or state_updated

def _map_to_stash_path(host_path: str, stash_config: dict) -> str:
    """Map a host filesystem path to the path Stash sees (for Docker bind mounts)."""
    path_map = stash_config.get("path_map", {})
    for host_prefix, stash_prefix in path_map.items():
        if host_path.startswith(host_prefix):
            return host_path.replace(host_prefix, stash_prefix, 1)
    return host_path  # no mapping configured, assume same path

def _ingest_to_stash(client, file_path, metadata, config):
    stash_config = config.get("stash", {})
    scan_paths = stash_config.get("scan_paths", [])

    # 1. Trigger scan of the relevant directory
    for sp in scan_paths:
        client.metadata_scan([sp])

    # 2. Map host path → Stash-visible path
    stash_path = _map_to_stash_path(file_path, stash_config)

    # 3. Poll until scene appears (with timeout)
    scene_id = None
    for _ in range(30):  # ~30 seconds
        scene_id = client.find_scene_by_path(stash_path)
        if scene_id:
            break
        time.sleep(1)

    if not scene_id:
        logger.warning(f"Stash: scene not found for {stash_path} after scan")
        return

    # 4. Push metadata
    client.update_scene(scene_id,
        title=metadata.get("title"),
        details=metadata.get("description"),
        date=metadata.get("date"),
        url=metadata.get("url"),
        cover_image=metadata.get("image"),
    )

    # 5. Apply tags/performers/studios (creates missing ones in Stash)
    if metadata.get("tags"):
        client.apply_tags(scene_id, metadata["tags"])
    if metadata.get("actors"):
        client.apply_performers(scene_id, metadata["actors"])
    if metadata.get("studios"):
        client.apply_studios(scene_id, metadata["studios"])

    # 6. Generate covers/previews
    if stash_config.get("generate_after_ingest", True):
        client.generate([scene_id])

    logger.success(f"Stash: ingested scene {scene_id} — {metadata.get('title')}")
  