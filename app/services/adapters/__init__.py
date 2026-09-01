from app.services.adapters.base import BaseAdapter
from app.services.adapters.channex import ChannexAdapter
from app.services.adapters.mews import MewsAdapter
from app.services.adapters.cloudbeds import CloudbedsAdapter
from app.services.adapters.siteminder import SiteMinderAdapter
from app.services.adapters.little_hotelier import LittleHotelierAdapter

def get_adapter(provider_name: str) -> BaseAdapter:
    provider = provider_name.lower()
    if provider == "channex":
        return ChannexAdapter()
    elif provider == "mews":
        return MewsAdapter()
    elif provider == "cloudbeds":
        return CloudbedsAdapter()
    elif provider == "siteminder":
        return SiteMinderAdapter()
    elif provider == "little_hotelier":
        return LittleHotelierAdapter()
    else:
        raise ValueError(f"Unknown provider: {provider_name}")
