#!/usr/bin/env python3
"""
Configuration Management Module for Smutscrape

This module provides centralized configuration loading, caching, and management
for both general application settings and site-specific configurations.
"""

import os
import yaml
from typing import Dict, Any, Optional
from loguru import logger

from smutscrape.stash import StashClient
from smutscrape.sites import SiteManager, SiteConfiguration
from smutscrape.downloaders import DownloadManager


class ConfigManager:
    """Centralized configuration management with caching and validation."""
    
    def __init__(self, script_dir: str):
        """Initialize the configuration manager.
        
        Args:
            script_dir: Root directory of the script for finding config files
        """
        self.script_dir = script_dir
        self.site_dir = os.path.join(script_dir, 'sites')
        self.config_file = os.path.join(script_dir, 'config.yaml')
        
        # Cache
        self._general_config = None
        self._site_manager = None
        self._download_manager = None
        
        # Selenium driver management (moved out of general_config dict)
        self._selenium_driver = None
        self._selenium_user_agent = None

        self._stash_client = None
        
    @property
    def general_config(self) -> Dict[str, Any]:
        """Get the general configuration, loading it if necessary."""
        if self._general_config is None:
            self._load_general_config()
        return self._general_config
    
    @property
    def site_manager(self) -> SiteManager:
        """Get the site manager, creating it if necessary."""
        if self._site_manager is None:
            self._site_manager = SiteManager(self.site_dir)
        return self._site_manager
    
    @property
    def download_manager(self) -> DownloadManager:
        """Get the download manager, creating it if necessary."""
        if self._download_manager is None:
            self._download_manager = DownloadManager(self.general_config)
        return self._download_manager
    
    def _load_general_config(self):
        """Load the general configuration from config.yaml."""
        try:
            with open(self.config_file, 'r') as file:
                self._general_config = yaml.safe_load(file)
                logger.debug(f"Loaded general config from '{self.config_file}'")
        except Exception as e:
            logger.error(f"Failed to load general config from '{self.config_file}': {e}")
            raise
    
    def get_site_config(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Get site configuration by identifier (URL, shortcode, name, or domain).
        
        Args:
            identifier: Site identifier to look up
            
        Returns:
            Site configuration dict or None if not found
        """
        site_obj = self.site_manager.get_site_by_identifier(identifier)
        if site_obj:
            logger.debug(f"Found site config for '{identifier}': {site_obj.name}")
            return site_obj.to_dict()
        else:
            logger.debug(f"No site config found for identifier '{identifier}'")
            return None
    
    def get_site_object(self, identifier: str) -> Optional[SiteConfiguration]:
        """Get site configuration object by identifier.
        
        Args:
            identifier: Site identifier to look up
            
        Returns:
            SiteConfiguration object or None if not found
        """
        return self.site_manager.get_site_by_identifier(identifier)
    
    def reload_configs(self):
        """Reload all configurations from disk."""
        logger.info("Reloading all configurations")
        self._general_config = None
        if self._site_manager:
            self._site_manager.reload()
        # Download manager will be recreated with new config when accessed
        self._download_manager = None
        
    def get_selenium_driver(self, force_new: bool = False):
        """Get or create a selenium driver instance.
        
        Args:
            force_new: Force creation of a new driver instance
            
        Returns:
            WebDriver instance or None if creation fails
        """
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
        
        selenium_config = self.general_config.get('selenium', {})
        chromedriver_path = selenium_config.get('chromedriver_path')
        
        create_new = force_new or self._selenium_driver is None
        if not create_new:
            try:
                # Test if existing driver is still valid
                self._selenium_driver.current_url
            except Exception as e:
                logger.warning(f"Existing Selenium driver invalid: {e}")
                create_new = True
        
        if create_new:
            # Clean up old driver
            if self._selenium_driver:
                try:
                    self._selenium_driver.quit()
                except:
                    pass
                self._selenium_driver = None
            
            # Create new driver
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
            
            chrome_binary = selenium_config.get('chrome_binary')
            if chrome_binary:
                chrome_options.binary_location = chrome_binary
                logger.debug(f"Set Chrome binary location to: {chrome_binary}")
            
            try:
                if chromedriver_path:
                    logger.debug(f"Using user-specified ChromeDriver at: {chromedriver_path}")
                    service = Service(executable_path=chromedriver_path)
                else:
                    logger.debug("Using webdriver_manager to fetch ChromeDriver")
                    service = Service(ChromeDriverManager().install())
                
                self._selenium_driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.debug(f"Initialized Selenium driver with Chrome version: {self._selenium_driver.capabilities['browserVersion']}")
                
                # Inject M3U8 detection script
                self._selenium_driver.execute_script("""
                    (function() {
                        let open = XMLHttpRequest.prototype.open;
                        XMLHttpRequest.prototype.open = function(method, url) {
                            if (url.includes(".m3u8")) {
                                console.log("🔥 Found M3U8 via XHR:", url);
                            }
                            return open.apply(this, arguments);
                        };
                    })();
                """)
                
                # Store User-Agent for later use
                self._selenium_user_agent = self._selenium_driver.execute_script("return navigator.userAgent;")
                logger.debug(f"Selenium User-Agent: {self._selenium_user_agent}")
                
            except Exception as e:
                logger.error(f"Failed to initialize Selenium driver: {e}")
                return None
        
        return self._selenium_driver
    
    @property
    def selenium_user_agent(self) -> Optional[str]:
        """Get the current selenium user agent string."""
        return self._selenium_user_agent
    
    def cleanup_selenium(self):
        """Clean up selenium driver resources."""
        if self._selenium_driver:
            try:
                self._selenium_driver.quit()
                logger.info("Selenium driver closed.")
            except Exception as e:
                logger.warning(f"Failed to close Selenium driver: {e}")
            finally:
                self._selenium_driver = None
                self._selenium_user_agent = None

    @property
    def stash_client(self) -> StashClient | None:
        """Get the Stash client (for optional Stash integration)."""
        stash_config = self.general_config.get("stash", {})
        if not stash_config.get("enabled"):
            return None
        if self._stash_client is None:
            self._stash_client = StashClient(
                url=stash_config["url"],
                api_key=stash_config.get("api_key", "")
            )
        return self._stash_client
    
    def cleanup(self):
        """Clean up all resources."""
        self.cleanup_selenium()
