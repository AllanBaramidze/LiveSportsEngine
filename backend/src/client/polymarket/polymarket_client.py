import asyncio
from httpx import AsyncClient

gammaURL = "https://gamma-api.polymarket.com"
'''Discover events and markets, and retrieve the metadata needed to work with them.'''

clobURL = "https://clob.polymarket.com"
'''Read live market state, then place and manage orders.'''

class PolymarketClient:

    def __init__(self, timeout: float = 5.0) -> None:
        self._http = AsyncClient()

