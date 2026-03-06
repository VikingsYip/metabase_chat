"""
MCP Client Service for communicating with the Metabase MCP server.
"""
import httpx
import os
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class MCPClient:
    """HTTP client for communicating with the MCP server."""

    def __init__(self):
        self.base_url = os.getenv('MCP_SERVER_URL', 'http://localhost:8000')
        self.timeout = 30.0
        logger.info(f"MCP Client initialized with base_url: {self.base_url}")

    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool by name.

        Args:
            tool_name: Name of the MCP tool to call
            params: Parameters to pass to the tool

        Returns:
            Dict containing the tool response

        Raises:
            httpx.HTTPError: If the HTTP request fails
        """
        url = f"{self.base_url}/tools/{tool_name}"

        logger.debug(f"Calling MCP tool: {tool_name} with params: {params}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json=params,
                    headers={'Content-Type': 'application/json'}
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"MCP tool {tool_name} executed successfully")
                return result

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling MCP tool {tool_name}: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error calling MCP tool {tool_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling MCP tool {tool_name}: {e}")
            raise

    # Database Operations

    async def list_databases(self) -> List[Dict]:
        """
        List all databases in Metabase.

        Returns:
            List of database dictionaries
        """
        result = await self.call_tool("list_databases", {})
        # REST API returns {"data": {"data": [...]}} - need to extract properly
        data = result.get('data', result)
        # If data is a dict with 'data' key, extract it
        if isinstance(data, dict) and 'data' in data:
            return data['data']
        return data if isinstance(data, list) else [data]

    async def list_tables(self, database_id: int) -> str:
        """
        List all tables in a specific database.

        Args:
            database_id: ID of the database

        Returns:
            Formatted markdown table of tables
        """
        result = await self.call_tool("list_tables", {"database_id": database_id})
        data = result.get('data', result)
        # REST API returns {"data": {...}} - extract properly
        if isinstance(data, dict) and 'data' in data:
            return str(data.get('data', data))
        return str(data)

    async def get_table_fields(self, table_id: int, limit: int = 20) -> Dict:
        """
        Get field/column information for a table.

        Args:
            table_id: ID of the table
            limit: Maximum number of fields to return

        Returns:
            Dictionary with field metadata
        """
        result = await self.call_tool("get_table_fields", {
            "table_id": table_id,
            "limit": limit
        })
        data = result.get('data', result)
        # REST API returns {"data": {...}} - extract properly
        if isinstance(data, dict) and 'data' in data:
            return data['data']
        return data

    # Query Operations

    async def execute_query(
        self,
        database_id: int,
        query: str,
        native_parameters: Optional[Dict] = None
    ) -> Dict:
        """
        Execute a native SQL query.

        Args:
            database_id: ID of the database
            query: SQL query string
            native_parameters: Optional parameters for parameterized queries

        Returns:
            Dictionary with query results
        """
        params = {
            "database_id": database_id,
            "query": query
        }
        if native_parameters:
            params["native_parameters"] = native_parameters

        result = await self.call_tool("execute_query", params)
        data = result.get('data', result)
        # REST API returns {"data": {...}} - extract properly
        if isinstance(data, dict) and 'data' in data:
            return data['data']
        return data

    async def execute_card(self, card_id: int, parameters: Optional[Dict] = None) -> Dict:
        """
        Execute a saved Metabase question/card.

        Args:
            card_id: ID of the card
            parameters: Optional parameters for the card

        Returns:
            Dictionary with card execution results
        """
        params = {"card_id": card_id}
        if parameters:
            params["parameters"] = parameters

        result = await self.call_tool("execute_card", params)
        return result.get('data', result)

    # Card Management

    async def list_cards(self) -> List[Dict]:
        """
        List all saved questions/cards in Metabase.

        Returns:
            List of card dictionaries
        """
        result = await self.call_tool("list_cards", {})
        return result.get('data', result)

    async def create_card(
        self,
        name: str,
        database_id: int,
        query: str,
        description: Optional[str] = None,
        collection_id: Optional[int] = None,
        visualization_settings: Optional[Dict] = None
    ) -> Dict:
        """
        Create a new Metabase card/question.

        Args:
            name: Name of the card
            database_id: ID of the database
            query: SQL query for the card
            description: Optional description
            collection_id: Optional collection ID
            visualization_settings: Optional visualization settings

        Returns:
            Dictionary with created card information
        """
        params = {
            "name": name,
            "database_id": database_id,
            "query": query
        }
        if description:
            params["description"] = description
        if collection_id:
            params["collection_id"] = collection_id
        if visualization_settings:
            params["visualization_settings"] = visualization_settings

        result = await self.call_tool("create_card", params)
        return result.get('data', result)

    # Collection Management

    async def list_collections(self) -> List[Dict]:
        """
        List all collections in Metabase.

        Returns:
            List of collection dictionaries
        """
        result = await self.call_tool("list_collections", {})
        return result.get('data', result)

    async def create_collection(
        self,
        name: str,
        description: Optional[str] = None,
        color: Optional[str] = None,
        parent_id: Optional[int] = None
    ) -> Dict:
        """
        Create a new collection in Metabase.

        Args:
            name: Name of the collection
            description: Optional description
            color: Optional color hex code
            parent_id: Optional parent collection ID for nested collections

        Returns:
            Dictionary with created collection information
        """
        params = {"name": name}
        if description:
            params["description"] = description
        if color:
            params["color"] = color
        if parent_id:
            params["parent_id"] = parent_id

        result = await self.call_tool("create_collection", params)
        return result.get('data', result)
