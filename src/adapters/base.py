from abc import ABC, abstractmethod
from pathlib import Path

class BaseAdapter(ABC):
    """
    Abstract base class for platform-specific skill adapters.
    Each adapter reads the universal skill folder and outputs its platform's format.
    """
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Name of the platform (e.g., 'antigravity', 'cursor')."""
        pass
        
    @abstractmethod
    def adapt(self, skill_dir: Path, output_platform_dir: Path, metadata: dict) -> Path:
        """
        Reads files from skill_dir (README.md, skill.md, references/)
        Writes adapted files to output_platform_dir/platform_name/
        Returns the path to the output directory.
        """
        pass
        
    @abstractmethod
    def install_instructions(self, skill_name: str) -> str:
        """Returns human-readable installation instructions for this platform."""
        pass
