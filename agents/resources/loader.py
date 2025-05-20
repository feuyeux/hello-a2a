"""
Resource loader for the agents module.
Loads YAML resources for use by the agents.
"""

import os
import yaml
from typing import List, Dict, Any
from common.utils.logger import setup_logger

logger = setup_logger("ResourceLoader")


def load_yaml_resource(resource_name: str) -> Any:
    """
    Load a YAML resource file from the resources directory.

    Args:
        resource_name: Name of the resource file (without .yml extension)

    Returns:
        The loaded YAML data
    """
    try:
        # Get the path to the resource file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        resource_path = os.path.join(current_dir, f"{resource_name}.yml")

        logger.info(f"Loading YAML resource from: {resource_path}")

        # Load and return the YAML data
        with open(resource_path, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)

        logger.info(f"Successfully loaded {resource_name} resource")
        return data
    except Exception as e:
        logger.error(
            f"Error loading YAML resource '{resource_name}': {str(e)}")
        raise


def get_periodic_table() -> List[Dict[str, Any]]:
    """
    Load the periodic table data from the YAML resource file.

    Returns:
        List of dictionaries containing element data

    Note:
        For a structured representation, use the load_periodic_table() function
        from the periodic_table module instead.
    """
    return load_yaml_resource("periodic_table")
