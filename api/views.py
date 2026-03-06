"""
REST API views for the Metabase chat application.
"""
import asyncio
import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from chat.services.mcp_client import MCPClient

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_databases(request):
    """
    API: List all Metabase databases.

    Returns a list of all databases configured in Metabase.
    """
    try:
        client = MCPClient()
        databases = asyncio.run(client.list_databases())
        return Response({
            'success': True,
            'data': databases
        })
    except Exception as e:
        logger.error(f"Error listing databases: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_tables(request, database_id):
    """
    API: List tables in a database.

    Args:
        database_id: ID of the database

    Returns a formatted list of tables in the specified database.
    """
    try:
        client = MCPClient()
        tables = asyncio.run(client.list_tables(database_id))
        return Response({
            'success': True,
            'data': tables,
            'database_id': database_id
        })
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_table_fields(request, table_id):
    """
    API: Get field/column information for a table.

    Args:
        table_id: ID of the table
        limit: Query parameter for max fields to return (default: 20)

    Returns field metadata for the specified table.
    """
    try:
        limit = int(request.query_params.get('limit', 20))
        client = MCPClient()
        fields = asyncio.run(client.get_table_fields(table_id, limit))
        return Response({
            'success': True,
            'data': fields,
            'table_id': table_id
        })
    except Exception as e:
        logger.error(f"Error getting table fields: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def execute_query(request):
    """
    API: Execute SQL query.

    Body:
        database_id: ID of the database
        query: SQL query string
        native_parameters: Optional parameters for parameterized queries

    Executes the SQL query and returns the results.
    """
    try:
        database_id = request.data.get('database_id')
        query = request.data.get('query')

        if not database_id or not query:
            return Response({
                'success': False,
                'error': 'database_id and query are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        client = MCPClient()
        native_parameters = request.data.get('native_parameters')

        result = asyncio.run(client.execute_query(
            database_id,
            query,
            native_parameters
        ))

        return Response({
            'success': True,
            'data': result
        })
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_cards(request):
    """
    API: List all saved Metabase questions/cards.

    Returns a list of all saved questions in Metabase.
    """
    try:
        client = MCPClient()
        cards = asyncio.run(client.list_cards())
        return Response({
            'success': True,
            'data': cards
        })
    except Exception as e:
        logger.error(f"Error listing cards: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_card(request):
    """
    API: Create a new Metabase card/question.

    Body:
        name: Name of the card
        database_id: ID of the database
        query: SQL query for the card
        description: Optional description
        collection_id: Optional collection ID
        visualization_settings: Optional visualization settings

    Creates a new saved question in Metabase.
    """
    try:
        name = request.data.get('name')
        database_id = request.data.get('database_id')
        query = request.data.get('query')

        if not all([name, database_id, query]):
            return Response({
                'success': False,
                'error': 'name, database_id, and query are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        client = MCPClient()
        card = asyncio.run(client.create_card(
            name=name,
            database_id=database_id,
            query=query,
            description=request.data.get('description'),
            collection_id=request.data.get('collection_id'),
            visualization_settings=request.data.get('visualization_settings')
        ))

        return Response({
            'success': True,
            'data': card
        })
    except Exception as e:
        logger.error(f"Error creating card: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def execute_card(request):
    """
    API: Execute a saved Metabase card/question.

    Body:
        card_id: ID of the card
        parameters: Optional parameters for the card

    Executes the saved question and returns the results.
    """
    try:
        card_id = request.data.get('card_id')

        if not card_id:
            return Response({
                'success': False,
                'error': 'card_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        client = MCPClient()
        parameters = request.data.get('parameters')

        result = asyncio.run(client.execute_card(card_id, parameters))

        return Response({
            'success': True,
            'data': result
        })
    except Exception as e:
        logger.error(f"Error executing card: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_collections(request):
    """
    API: List all Metabase collections.

    Returns a list of all collections in Metabase.
    """
    try:
        client = MCPClient()
        collections = asyncio.run(client.list_collections())
        return Response({
            'success': True,
            'data': collections
        })
    except Exception as e:
        logger.error(f"Error listing collections: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_collection(request):
    """
    API: Create a new Metabase collection.

    Body:
        name: Name of the collection
        description: Optional description
        color: Optional color hex code
        parent_id: Optional parent collection ID

    Creates a new collection in Metabase.
    """
    try:
        name = request.data.get('name')

        if not name:
            return Response({
                'success': False,
                'error': 'name is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        client = MCPClient()
        collection = asyncio.run(client.create_collection(
            name=name,
            description=request.data.get('description'),
            color=request.data.get('color'),
            parent_id=request.data.get('parent_id')
        ))

        return Response({
            'success': True,
            'data': collection
        })
    except Exception as e:
        logger.error(f"Error creating collection: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def login(request):
    """
    API: Login endpoint (handled by JWT, but keeping for consistency).

    Note: Authentication is handled by djangorestframework-simplejwt.
    Use POST /auth/jwt/ to obtain tokens.
    """
    return Response({
        'message': 'Please use POST /auth/jwt/ for authentication',
        'login_url': '/auth/jwt/'
    })
