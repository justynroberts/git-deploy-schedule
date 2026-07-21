"""Configuration management for git-deploy-schedule."""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv


class Config:
    """Configuration loader and manager."""

    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize configuration.

        Args:
            config_path: Path to YAML configuration file
        """
        load_dotenv()
        self.config_path = config_path
        self.config = self._load_config()
        self._apply_env_overrides()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file.

        Returns:
            Configuration dictionary
        """
        config_file = Path(self.config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(config_file, 'r') as f:
            return yaml.safe_load(f)

    def _apply_env_overrides(self):
        """Apply environment variable overrides to configuration."""
        # Ollama overrides
        if os.getenv('OLLAMA_URL'):
            self.config['ollama']['url'] = os.getenv('OLLAMA_URL')
        if os.getenv('OLLAMA_MODEL'):
            self.config['ollama']['model'] = os.getenv('OLLAMA_MODEL')
        if os.getenv('OLLAMA_THEME'):
            self.config['ollama']['theme'] = os.getenv('OLLAMA_THEME')

        # Repository overrides
        if os.getenv('REPO_PATH'):
            self.config['repositories'][0]['path'] = os.getenv('REPO_PATH')
        if os.getenv('REPO_BRANCH'):
            self.config['repositories'][0]['branch'] = os.getenv('REPO_BRANCH')

        # Schedule overrides
        if os.getenv('BASE_INTERVAL'):
            self.config['schedule']['base_interval'] = int(os.getenv('BASE_INTERVAL'))
        if os.getenv('JITTER_RANGE'):
            self.config['schedule']['jitter_range'] = int(os.getenv('JITTER_RANGE'))

        # Git author overrides
        if os.getenv('GIT_AUTHOR_NAME'):
            self.config['commit']['author_name'] = os.getenv('GIT_AUTHOR_NAME')
        if os.getenv('GIT_AUTHOR_EMAIL'):
            self.config['commit']['author_email'] = os.getenv('GIT_AUTHOR_EMAIL')

        # Logging overrides
        if os.getenv('LOG_LEVEL'):
            self.config.setdefault('logging', {})['level'] = os.getenv('LOG_LEVEL')
        if os.getenv('LOG_FILE'):
            self.config.setdefault('logging', {})['file'] = os.getenv('LOG_FILE')

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key.

        Args:
            key: Configuration key (supports dot notation, e.g., 'ollama.url')
            default: Default value if key not found

        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def get_repositories(self) -> List[Dict[str, Any]]:
        """Get list of repository configurations.

        Returns:
            List of repository configurations
        """
        return self.config.get('repositories', [])

    def get_schedule_config(self) -> Dict[str, int]:
        """Get schedule configuration.

        Returns:
            Schedule configuration dictionary
        """
        return self.config.get('schedule', {})

    def get_ollama_config(self) -> Dict[str, Any]:
        """Get Ollama configuration.

        Returns:
            Ollama configuration dictionary
        """
        return self.config.get('ollama', {})

    def get_commit_config(self) -> Dict[str, Any]:
        """Get commit configuration.

        Returns:
            Commit configuration dictionary
        """
        return self.config.get('commit', {})

    def get_push_config(self) -> Dict[str, Any]:
        """Get push configuration.

        Returns:
            Push configuration dictionary
        """
        return self.config.get('push', {})

    def get_logging_config(self) -> Dict[str, str]:
        """Get logging configuration.

        Returns:
            Logging configuration dictionary
        """
        return self.config.get('logging', {})
