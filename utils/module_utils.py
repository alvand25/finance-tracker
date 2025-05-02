"""
Utilities for module management and auto-stubbing.
"""

import os
import textwrap
import logging

logger = logging.getLogger(__name__)

def stub_missing_module(pkg: str, module_name: str, base_class: str = None):
    """
    Creates pkg/module_name.py with a minimal stub so imports succeed.
    
    Args:
        pkg: Package directory name (e.g., 'handlers', 'storage')
        module_name: Name of the module to create (e.g., 'hmart_handler')
        base_class: Optional base class name to inherit from
    """
    folder = os.path.join(os.getcwd(), pkg)
    os.makedirs(folder, exist_ok=True)
    
    # Ensure package has __init__.py
    init_file = os.path.join(folder, "__init__.py")
    if not os.path.exists(init_file):
        open(init_file, "a").close()
        logger.info(f"Created package __init__.py: {init_file}")
    
    # Create module file
    file_path = os.path.join(folder, f"{module_name}.py")
    class_name = "".join(part.title() for part in module_name.split("_"))
    
    lines = []
    if base_class:
        lines.append(f"from services.base_handler import {base_class}")
        lines.append("")
        lines.append(f"class {class_name}({base_class}):")
    else:
        lines.append(f"class {class_name}:")
        
    lines.append("    def __init__(self, *args, **kwargs):")
    lines.append("        pass")
    lines.append("    # TODO: implement methods")
    
    with open(file_path, "w") as f:
        f.write(textwrap.dedent("\n".join(lines)))
        
    logger.info(f"Created stub module: {file_path}")
    logger.info(f"Class created: {class_name}")
    if base_class:
        logger.info(f"Inherits from: {base_class}") 