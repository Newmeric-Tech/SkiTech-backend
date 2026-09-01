from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseAdapter(ABC):
    
    @abstractmethod
    async def test_connection(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """
        Test API connection.
        Returns: {"success": bool, "message": str}
        """
        pass

    @abstractmethod
    async def fetch_reservations(
        self,
        credentials: Dict[str, Any],
        property_id: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch reservations from the channel manager provider.
        Returns a list of dicts conforming to the UnifiedReservation schema.
        """
        pass

    @abstractmethod
    async def fetch_availability(
        self,
        credentials: Dict[str, Any],
        property_id: str,
        from_date: str,
        to_date: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch availability restrictions from the channel manager provider.
        Returns a list of dicts conforming to the UnifiedAvailability schema.
        """
        pass
