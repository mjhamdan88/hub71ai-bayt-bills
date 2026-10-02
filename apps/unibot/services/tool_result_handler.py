"""
Module for handling tool results and file path validation.
"""
from pathlib import Path
from typing import Union, Optional, Dict, List


def validate_file_path(path_str: str) -> Optional[str]:
    """
    Validate if a string represents a valid file path.
    
    Args:
        path_str: String to validate as a file path.
        
    Returns:
        The validated file path as a string if valid, None otherwise.
    """
    try:
        path = Path(path_str)
        if path.is_file():
            return str(path)
    except Exception:
        pass
    return None


def handle_tool_result(result: Union[str, dict]) -> Optional[str]:
    """
    Check if a tool result is a file path.
    
    Args:
        result: The result from a tool call, either a string or a dictionary.
        
    Returns:
        The file path as a string if valid, None otherwise.
    """
    # If result is a string, try to interpret it as a path
    if isinstance(result, str):
        return validate_file_path(result)
        
    # If result is a dict and has a 'path' or 'file_path' key
    elif isinstance(result, dict) and ('path' in result or 'file_path' in result):
        path_str = result.get('path', result.get('file_path'))
        return validate_file_path(path_str)
        
    return None


def prepare_file_response(file_paths: List[str], platform: str) -> Dict[str, Union[str, List[str]]]:
    """
    Prepare a response dictionary with file paths based on the platform.
    
    Args:
        file_paths: List of validated file paths.
        platform: The platform type (e.g., 'Email').
        
    Returns:
        A dictionary with the appropriate file path structure for the platform.
    """
    if not file_paths:
        return {}
        
    if platform == 'Email':
        return {'attachments': file_paths}
    else:
        return {'file_path': file_paths[0] if len(file_paths) == 1 else file_paths} 