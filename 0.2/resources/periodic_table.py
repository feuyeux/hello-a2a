"""
Periodic Table module for structured element data.
Provides dataclass representation of chemical elements from the YAML data.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from .loader import load_yaml_resource


@dataclass
class Element:
    """Represents a chemical element from the periodic table."""
    name: str
    symbol: str
    atomic_number: int
    atomic_weight: float
    group: int
    period: int
    chinese_name: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Element':
        """Create an Element instance from a dictionary."""
        return cls(
            name=data['name'],
            symbol=data['symbol'],
            atomic_number=data['atomic_number'],
            atomic_weight=float(data['atomic_weight']),
            group=data['group'],
            period=data['period'],
            chinese_name=data['chinese_name']
        )


@dataclass
class PeriodicTable:
    """Collection of chemical elements representing the periodic table."""
    elements: List[Element]

    def __getitem__(self, key):
        """Allow indexing by atomic number (int) or symbol (str)."""
        if isinstance(key, int):
            # Get element by atomic number
            for element in self.elements:
                if element.atomic_number == key:
                    return element
        elif isinstance(key, str):
            # Get element by symbol - match exactly as provided
            for element in self.elements:
                if element.symbol == key:
                    return element
        raise KeyError(f"Element with key {key} not found")

    def get_by_name(self, name: str) -> Optional[Element]:
        """Get element by name."""
        for element in self.elements:
            if element.name.lower() == name.lower():
                return element
        return None

    def get_by_chinese_name(self, chinese_name: str) -> Optional[Element]:
        """Get element by Chinese name."""
        for element in self.elements:
            if element.chinese_name == chinese_name:
                return element
        return None

    def get_elements_in_group(self, group: int) -> List[Element]:
        """Get all elements in a specific group."""
        return [element for element in self.elements if element.group == group]

    def get_elements_in_period(self, period: int) -> List[Element]:
        """Get all elements in a specific period."""
        return [element for element in self.elements if element.period == period]

    def search(self, **kwargs) -> List[Element]:
        """
        Search for elements with properties matching the provided criteria.

        Args:
            **kwargs: Key-value pairs where key is an Element attribute and 
                     value is the desired value or a callable predicate

        Returns:
            List[Element]: Elements matching all the criteria

        Examples:
            # Get elements with atomic weight > 200
            table.search(atomic_weight=lambda w: w > 200)

            # Get elements with specific name pattern
            table.search(name=lambda n: n.startswith('C'))

            # Get elements in group 1 with atomic number less than 20
            table.search(group=1, atomic_number=lambda n: n < 20)
        """
        results = self.elements

        for attr, value in kwargs.items():
            if callable(value):
                # If value is a function, use it as a predicate
                results = [e for e in results if hasattr(
                    e, attr) and value(getattr(e, attr))]
            else:
                # Otherwise do exact value matching
                results = [e for e in results if hasattr(
                    e, attr) and getattr(e, attr) == value]

        return results

    def filter(self, predicate) -> List[Element]:
        """
        Filter elements using a custom predicate function.

        Args:
            predicate: A function that takes an Element and returns a boolean

        Returns:
            List[Element]: Elements for which the predicate returns True

        Example:
            # Get all elements with even atomic numbers
            table.filter(lambda e: e.atomic_number % 2 == 0)
        """
        return [element for element in self.elements if predicate(element)]

    def get_elements_by_weight_range(self, min_weight: float, max_weight: float) -> List[Element]:
        """Get elements with atomic weight within the specified range."""
        return [element for element in self.elements
                if min_weight <= element.atomic_weight <= max_weight]

    def get_transition_metals(self) -> List[Element]:
        """Return all transition metals (groups 3-12)."""
        return [element for element in self.elements
                if 3 <= element.group <= 12]


def load_periodic_table() -> PeriodicTable:
    """
    Load the periodic table data from the YAML resource file and return
    a structured PeriodicTable object.

    Returns:
        PeriodicTable: A structured representation of the periodic table
    """
    yaml_data = load_yaml_resource("periodic_table")
    elements = [Element.from_dict(element_data) for element_data in yaml_data]
    return PeriodicTable(elements=elements)
